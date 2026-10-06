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


def memory(container):
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


def process_count(container):
    result = docker("top", container, "-o", "pid", check=False)
    if result.returncode != 0:
        return None
    return max(0, len(result.stdout.strip().splitlines()) - 1)


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


def run_load(network, wrk_image, app, database, url, duration, connections, threads, settle):
    command = ["docker", "run", "--rm", "--network", network, wrk_image,
               "wrk", "-t%d" % threads, "-c%d" % connections, "-d%ds" % duration,
               "--timeout", "8", url]
    samples = []
    connections_seen = []
    started = time.time()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = []
    reader = threading.Thread(target=lambda: output.append(process.stdout.read()))
    reader.start()
    while process.poll() is None:
        time.sleep(1)
        if time.time() - started < settle:
            continue
        sample = memory(app)
        if sample is not None:
            samples.append(sample)
        value = db_connections(database)
        if value is not None:
            connections_seen.append(value)
    reader.join()
    result = parse_wrk("".join(output))
    result["memory_samples"] = len(samples)
    result["resident_max_bytes"] = max(s["resident"] for s in samples) if samples else None
    result["current_max_bytes"] = max(s["current"] for s in samples) if samples else None
    result["db_connections_max"] = max(connections_seen) if connections_seen else None
    return result


def measure(entry, args, network, database, workers):
    app = "%s-app-%d" % (network, workers)
    env = {"RC_CPUS": "1", "RC_WORKERS": str(workers), "RC_THREADS": str(args.threads_per_worker),
           "RC_DB_POOL": str(args.db_pool)}
    run = ["run", "-d", "--name", app, "--network", network, "--network-alias", "tfb-server",
           "--init", "--ulimit", "nofile=200000:200000", "--sysctl", "net.core.somaxconn=65535",
           "--label", "rackcensus=1"]
    if args.memory:
        run += ["--memory", args.memory, "--memory-swap", args.memory]
    for key, value in env.items():
        run += ["-e", "%s=%s" % (key, value)]
    docker(*run, args.image)
    try:
        base = "http://tfb-server:%d" % entry["port"]
        log("waiting for %s with %d worker(s) to answer" % (entry["name"], workers))
        wait_for("%s to answer" % entry["name"], lambda: docker(
            "run", "--rm", "--network", network, args.wrk_image,
            "curl", "-sf", "-o", "/dev/null", "--max-time", "5", base + entry["urls"]["json"],
            check=False).returncode == 0, args.start_timeout)
        for test_type in ("db", "fortune"):
            docker("run", "--rm", "--network", network, args.wrk_image,
                   "curl", "-sf", "-o", "/dev/null", "--max-time", "5", base + entry["urls"][test_type])
        idle = memory(app)
        processes = process_count(app)
        tests = {}
        for test_type in ("json", "db", "fortune"):
            log("loading %s %s at %d connections for %ds" % (entry["name"], test_type, args.connections, args.duration))
            tests[test_type] = run_load(network, args.wrk_image, app, database, base + entry["urls"][test_type],
                                        args.duration, args.connections, args.wrk_threads, args.settle)
            log("%s %s did %s requests/sec, %s resident bytes at peak, %s db connections" % (
                entry["name"], test_type, tests[test_type]["requests_per_second"],
                tests[test_type]["resident_max_bytes"], tests[test_type]["db_connections_max"]))
        resident = [t["resident_max_bytes"] for t in tests.values() if t["resident_max_bytes"] is not None]
        current = [t["current_max_bytes"] for t in tests.values() if t["current_max_bytes"] is not None]
        return {"env": env, "memory_limit": args.memory, "oom_kills": oom_kills(app), "processes": processes,
                "idle_resident_bytes": idle["resident"] if idle else None,
                "idle_current_bytes": idle["current"] if idle else None,
                "steady_bytes": max(resident) if resident else None,
                "steady_current_bytes": max(current) if current else None,
                "tests": tests}
    finally:
        docker("rm", "-f", app, check=False)


def to_mb(value):
    return int(math.ceil(value / 1048576.0))


def main():
    parser = argparse.ArgumentParser(description="measure steady-state memory of a tfb image under load")
    parser.add_argument("--name", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--db-image", default="techempower/postgres")
    parser.add_argument("--wrk-image", default="techempower/tfb.wrk")
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
    docker("network", "create", "--label", "rackcensus=1", network)
    try:
        docker("run", "-d", "--name", database, "--network", network, "--network-alias", "tfb-database",
               "--label", "rackcensus=1", args.db_image)
        log("waiting for postgres")
        wait_for("postgres", lambda: docker(
            "exec", database, "pg_isready", "-h", "127.0.0.1", "-U", "benchmarkdbuser", "-d", "hello_world",
            check=False).returncode == 0, 120)
        runs = {}
        for workers in (1, 2):
            runs[str(workers)] = measure(entry, args, network, database, workers)
    finally:
        docker("rm", "-f", database, check=False)
        docker("network", "rm", network, check=False)

    one = runs["1"]["steady_bytes"]
    two = runs["2"]["steady_bytes"]
    per_process = max(two - one, 0)
    base = max(one - per_process, 0)
    result = {
        "name": entry["name"],
        "image": args.image,
        "arch": args.arch,
        "class": entry["class"],
        "rss_proc_mb": to_mb(per_process),
        "rss_base_mb": to_mb(base),
        "method": "resident = memory.current - file + shmem of the app container, max over the last %ds of "
                  "%ds wrk runs at %d connections against json, db and fortune; per process = 2 workers minus "
                  "1 worker, base = 1 worker minus per process"
                  % (args.duration - args.settle, args.duration, args.connections),
        "runs": runs,
    }
    log("%s on %s: %d MB per process, %d MB base" % (entry["name"], args.arch, result["rss_proc_mb"], result["rss_base_mb"]))
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
