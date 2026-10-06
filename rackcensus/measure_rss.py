import argparse
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import frameworks

PROCESS_SNAPSHOT = (
    'for d in /proc/[0-9]*; do '
    '[ -r "$d/smaps_rollup" ] || continue; '
    'echo "@@ ${d#/proc/}"; '
    'cat "$d/stat" 2>/dev/null; echo; '
    'tr "\\0" " " < "$d/cmdline" 2>/dev/null; echo; '
    'cat "$d/smaps_rollup" 2>/dev/null; '
    'done'
)

METRICS = ("rss", "pss", "uss")


def log(message):
    print(message, flush=True)


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError("docker %s failed: %s" % (" ".join(args[:2]), result.stderr.strip()))
    return result


def wait_for(description, check, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return
        time.sleep(1)
    raise RuntimeError("gave up waiting for %s after %ss" % (description, timeout))


def processes(container):
    result = docker("exec", "--privileged", container, "sh", "-c", PROCESS_SNAPSHOT, check=False)
    if result.returncode != 0:
        return None
    found = []
    for block in result.stdout.split("@@ ")[1:]:
        lines = block.split("\n")
        stat = lines[1]
        if ")" not in stat:
            continue
        comm = stat[stat.index("(") + 1:stat.rindex(")")]
        fields = stat[stat.rindex(")") + 2:].split()
        kb = {}
        for line in lines[3:]:
            match = re.match(r"(\w+):\s+(\d+) kB", line)
            if match:
                kb[match.group(1)] = int(match.group(2))
        if "Pss" not in kb:
            continue
        found.append({
            "pid": int(lines[0].strip()),
            "ppid": int(fields[1]),
            "comm": comm,
            "cmdline": lines[2].strip()[:120],
            "rss": kb.get("Rss", 0) * 1024,
            "pss": kb.get("Pss", 0) * 1024,
            "uss": (kb.get("Private_Clean", 0) + kb.get("Private_Dirty", 0)) * 1024,
        })
    return found


def worker_group(snapshot, workers):
    pids = {p["pid"] for p in snapshot}
    groups = {}
    for p in snapshot:
        if p["ppid"] in pids:
            groups.setdefault((p["ppid"], p["comm"]), []).append(p)
    if not groups:
        return []
    ranked = sorted(groups.values(), key=lambda g: (abs(len(g) - workers), -sum(p["pss"] for p in g)))
    return ranked[0]


def cgroup_memory(container):
    result = docker("exec", container, "cat", "/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.stat",
                    check=False)
    if result.returncode != 0:
        return None
    lines = result.stdout.splitlines()
    stat = {}
    for line in lines[1:]:
        key, _, value = line.partition(" ")
        if value:
            stat[key] = int(value)
    current = int(lines[0])
    return {"current": current, "resident": current - stat.get("file", 0) + stat.get("shmem", 0)}


def oom_kills(container):
    result = docker("exec", container, "cat", "/sys/fs/cgroup/memory.events", check=False)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        key, _, value = line.partition(" ")
        if key == "oom_kill":
            return int(value)
    return 0


def db_connections(database):
    result = docker("exec", database, "psql", "-U", "benchmarkdbuser", "-d", "hello_world", "-Atc",
                    "select count(*) from pg_stat_activity where datname = 'hello_world' and pid <> pg_backend_pid()",
                    check=False)
    if result.returncode != 0:
        return None
    return int(result.stdout.strip())


def parse_wrk(output):
    parsed = {"requests": None, "requests_per_second": None, "non_2xx": 0,
              "socket_errors": {"connect": 0, "read": 0, "write": 0, "timeout": 0}}
    match = re.search(r"(\d+) requests in", output)
    if match:
        parsed["requests"] = int(match.group(1))
    match = re.search(r"Requests/sec:\s+([\d.]+)", output)
    if match:
        parsed["requests_per_second"] = float(match.group(1))
    match = re.search(r"Non-2xx or 3xx responses: (\d+)", output)
    if match:
        parsed["non_2xx"] = int(match.group(1))
    match = re.search(r"Socket errors: connect (\d+), read (\d+), write (\d+), timeout (\d+)", output)
    if match:
        parsed["socket_errors"] = dict(zip(("connect", "read", "write", "timeout"), map(int, match.groups())))
    return parsed


def peak(current, values):
    return {m: max(current.get(m, 0), values[m]) for m in METRICS}


def run_load(network, wrk_image, app, database, url, args, totals):
    command = ["docker", "run", "--rm", "--network", network, wrk_image,
               "wrk", "-t%d" % args.wrk_threads, "-c%d" % args.connections, "-d%ds" % args.duration,
               "--timeout", "8", url]
    connections_seen = []
    cgroup = []
    started = time.time()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = []
    reader = threading.Thread(target=lambda: output.append(process.stdout.read()))
    reader.start()
    worker_peak = {}
    base_peak = {}
    while process.poll() is None:
        time.sleep(1)
        if time.time() - started < args.settle:
            continue
        snapshot = processes(app)
        if snapshot:
            group = worker_group(snapshot, args.workers)
            group_pids = {p["pid"] for p in group}
            for p in group:
                worker_peak = peak(worker_peak, p)
            base = {m: sum(p[m] for p in snapshot if p["pid"] not in group_pids) for m in METRICS}
            base_peak = peak(base_peak, base)
            totals["snapshot"] = snapshot
            totals["group"] = sorted(group_pids)
        sample = cgroup_memory(app)
        if sample is not None:
            cgroup.append(sample)
        value = db_connections(database)
        if value is not None:
            connections_seen.append(value)
    reader.join()
    result = parse_wrk("".join(output))
    result["worker_peak_bytes"] = worker_peak
    result["base_peak_bytes"] = base_peak
    result["cgroup_resident_max_bytes"] = max(s["resident"] for s in cgroup) if cgroup else None
    result["cgroup_current_max_bytes"] = max(s["current"] for s in cgroup) if cgroup else None
    result["db_connections_max"] = max(connections_seen) if connections_seen else None
    return result


def to_mb(value):
    return int(math.ceil(value / 1048576.0))


def main():
    parser = argparse.ArgumentParser(description="measure per-process memory of a tfb image under load")
    parser.add_argument("--name", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--db-image", default="techempower/postgres")
    parser.add_argument("--wrk-image", default="techempower/tfb.wrk")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--settle", type=int, default=10)
    parser.add_argument("--connections", type=int, default=256)
    parser.add_argument("--wrk-threads", type=int, default=4)
    parser.add_argument("--threads-per-worker", type=int, default=4)
    parser.add_argument("--db-pool", type=int, default=4)
    parser.add_argument("--start-timeout", type=int, default=180)
    parser.add_argument("--memory", help="optional docker --memory limit for the app container, for example 1g")
    parser.add_argument("--out")
    args = parser.parse_args()

    entry = frameworks.find(args.name)
    network = "rcm-%s" % uuid.uuid4().hex[:8]
    database = "%s-db" % network
    app = "%s-app" % network
    env = {"RC_CPUS": "1", "RC_WORKERS": str(args.workers), "RC_THREADS": str(args.threads_per_worker),
           "RC_DB_POOL": str(args.db_pool)}
    docker("network", "create", "--label", "rackcensus=1", network)
    try:
        docker("run", "-d", "--name", database, "--network", network, "--network-alias", "tfb-database",
               "--label", "rackcensus=1", args.db_image)
        log("waiting for postgres")
        wait_for("postgres", lambda: docker(
            "exec", database, "pg_isready", "-h", "127.0.0.1", "-U", "benchmarkdbuser", "-d", "hello_world",
            check=False).returncode == 0, 120)
        run = ["run", "-d", "--name", app, "--network", network, "--network-alias", "tfb-server",
               "--init", "--ulimit", "nofile=200000:200000", "--sysctl", "net.core.somaxconn=65535",
               "--label", "rackcensus=1"]
        if args.memory:
            run += ["--memory", args.memory, "--memory-swap", args.memory]
        for key, value in env.items():
            run += ["-e", "%s=%s" % (key, value)]
        docker(*run, args.image)
        base_url = "http://tfb-server:%d" % entry["port"]
        log("waiting for %s with %d workers to answer" % (entry["name"], args.workers))
        wait_for("%s to answer" % entry["name"], lambda: docker(
            "run", "--rm", "--network", network, args.wrk_image,
            "curl", "-sf", "-o", "/dev/null", "--max-time", "5", base_url + entry["urls"]["json"],
            check=False).returncode == 0, args.start_timeout)
        for test_type in ("db", "fortune"):
            docker("run", "--rm", "--network", network, args.wrk_image,
                   "curl", "-sf", "-o", "/dev/null", "--max-time", "5", base_url + entry["urls"][test_type])
        idle = processes(app)
        totals = {}
        tests = {}
        for test_type in ("json", "db", "fortune"):
            log("loading %s %s at %d connections for %ds" % (entry["name"], test_type, args.connections, args.duration))
            tests[test_type] = run_load(network, args.wrk_image, app, database, base_url + entry["urls"][test_type],
                                        args, totals)
            log("%s %s did %s requests/sec, worker pss peak %s bytes, %s db connections" % (
                entry["name"], test_type, tests[test_type]["requests_per_second"],
                tests[test_type]["worker_peak_bytes"].get("pss"), tests[test_type]["db_connections_max"]))
        kills = oom_kills(app)
    finally:
        docker("rm", "-f", "-v", app, check=False)
        docker("rm", "-f", "-v", database, check=False)
        docker("network", "rm", network, check=False)

    worker = {}
    base = {}
    for test in tests.values():
        if test["worker_peak_bytes"]:
            worker = peak(worker, test["worker_peak_bytes"])
        if test["base_peak_bytes"]:
            base = peak(base, test["base_peak_bytes"])
    if not worker or not base:
        raise SystemExit("no process samples for %s, nothing to report" % entry["name"])
    group = set(totals.get("group", []))
    if len(group) != args.workers:
        raise SystemExit("expected %d workers in %s but found %d (%s)" % (
            args.workers, entry["name"], len(group), sorted(group)))

    result = {
        "name": entry["name"],
        "image": args.image,
        "arch": args.arch,
        "class": entry["class"],
        "rss_proc_mb": to_mb(worker["pss"]),
        "rss_base_mb": to_mb(base["pss"]),
        "memory": {
            "workers": args.workers,
            "worker": {"%s_mb" % m: to_mb(worker[m]) for m in METRICS},
            "base": {"%s_mb" % m: to_mb(base[m]) for m in METRICS},
            "cgroup_resident_mb": to_mb(max(t["cgroup_resident_max_bytes"] or 0 for t in tests.values())),
            "cgroup_current_mb": to_mb(max(t["cgroup_current_max_bytes"] or 0 for t in tests.values())),
            "oom_kills": kills,
        },
        "method": "per-process Rss, Pss and Private_Clean + Private_Dirty (uss) from /proc/<pid>/smaps_rollup "
                  "in the app container with RC_WORKERS=%d, sampled over the last %ds of %ds wrk runs at %d "
                  "connections against json, db and fortune. rss_proc_mb is the peak pss of one worker, "
                  "rss_base_mb the peak pss sum of every other process in the container (master, init, "
                  "nginx, and so on)." % (args.workers, args.duration - args.settle, args.duration, args.connections),
        "env": env,
        "processes": {
            "idle": idle,
            "last_under_load": totals.get("snapshot"),
            "worker_pids": sorted(group),
        },
        "tests": tests,
    }
    log("%s on %s: worker pss %d MB (rss %d, uss %d), base pss %d MB" % (
        entry["name"], args.arch, result["rss_proc_mb"], result["memory"]["worker"]["rss_mb"],
        result["memory"]["worker"]["uss_mb"], result["rss_base_mb"]))
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
