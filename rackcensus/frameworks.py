import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROFILE = {
    "RC_CPUS": "2",
    "RC_THREADS": "4",
    "RC_DB_POOL": "4",
    "RC_MEMORY_MB": "1150",
}

PROFILE_WORKERS = {"async": "2", "threaded": "2", "prefork": "8"}


def load():
    with open(os.path.join(ROOT, "rackcensus", "frameworks.json")) as f:
        entries = json.load(f)
    return [describe(entry) for entry in entries]


def describe(entry):
    with open(os.path.join(ROOT, entry["directory"], "benchmark_config.json")) as f:
        config = json.load(f)
    framework = config["framework"]
    for tests in config["tests"]:
        for key, test in tests.items():
            name = framework if key == "default" else "%s-%s" % (framework, key)
            if name != entry["test"]:
                continue
            return dict(
                entry,
                dockerfile=test.get("dockerfile", "%s.dockerfile" % name),
                port=int(test["port"]),
                urls={
                    "json": test["json_url"],
                    "db": test["db_url"],
                    "fortune": test["fortune_url"],
                },
            )
    raise SystemExit("%s has no test named %s" % (entry["directory"], entry["test"]))


def find(name):
    for entry in load():
        if name in (entry["name"], entry["test"], entry["image"]):
            return entry
    raise SystemExit("no framework called %s" % name)


def profile_env(entry):
    env = dict(PROFILE)
    env["RC_WORKERS"] = PROFILE_WORKERS[entry["class"]]
    return env


def main():
    parser = argparse.ArgumentParser(description="framework list for the rackcensus workflows")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("matrix", help="print the frameworks as a json array")
    info = sub.add_parser("info", help="print one framework as KEY=value lines")
    info.add_argument("name")
    profile = sub.add_parser("profile", help="print the 2 cpu / 2 gb RC_* profile as KEY=value lines")
    profile.add_argument("name")
    args = parser.parse_args()

    if args.command == "matrix":
        json.dump(load(), sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
    elif args.command == "info":
        entry = find(args.name)
        for key in ("name", "test", "directory", "dockerfile", "image", "class", "port"):
            print("%s=%s" % (key.upper(), entry[key]))
    else:
        for key, value in sorted(profile_env(find(args.name)).items()):
            print("%s=%s" % (key, value))


if __name__ == "__main__":
    main()
