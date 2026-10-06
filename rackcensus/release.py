import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import frameworks

ARCHES = ("amd64", "arm64")


def read_all(directory, pattern):
    found = {}
    for path in sorted(glob.glob(os.path.join(directory, "**", pattern), recursive=True)):
        with open(path) as f:
            data = json.load(f)
        found[(data["image"], data.get("arch"))] = data
    return found


def main():
    parser = argparse.ArgumentParser(description="assemble frameworks.json from the image workflow artifacts")
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    indexes = read_all(args.artifacts, "index-*.json")
    checks = read_all(args.artifacts, "check-*.json")
    problems = []
    images = {}
    entries = []
    measurements = {}

    for entry in frameworks.load():
        image = entry["image"]
        index = indexes.get((image, None))
        if index is None:
            problems.append("%s has no pushed index" % image)
            continue
        platforms = {}
        rss_proc = {}
        rss_base = {}
        verified = {}
        for arch in ARCHES:
            platform = "linux/%s" % arch
            pushed = index["platforms"].get(platform)
            check = checks.get((image, arch))
            if pushed is None:
                problems.append("%s has no %s digest" % (image, platform))
                continue
            if check is None:
                problems.append("%s was never checked on %s" % (image, arch))
                continue
            if check["digest"] != pushed["digest"]:
                problems.append("%s on %s was checked at %s but the index has %s"
                                % (image, arch, check["digest"], pushed["digest"]))
            platforms[platform] = {
                "digest": pushed["digest"],
                "compressed_bytes": pushed["compressed_bytes"],
                "unpacked_bytes": check["unpacked_bytes"],
            }
            verified[arch] = all(check["verified"].values())
            if not verified[arch]:
                problems.append("%s failed verification on %s: %s" % (image, arch, check["verified"]))
            rss = check.get("rss")
            if not rss:
                problems.append("%s has no memory measurement on %s" % (image, arch))
                continue
            rss_proc[arch] = rss["rss_proc_mb"]
            rss_base[arch] = rss["rss_base_mb"]
            measurements.setdefault(entry["name"], {})[arch] = {
                "rss_proc_mb": rss["rss_proc_mb"],
                "rss_base_mb": rss["rss_base_mb"],
                "resident_mb_1_worker": round(rss["runs"]["1"]["steady_bytes"] / 1048576.0, 1),
                "resident_mb_2_workers": round(rss["runs"]["2"]["steady_bytes"] / 1048576.0, 1),
                "memory_current_mb_1_worker": round(rss["runs"]["1"]["steady_current_bytes"] / 1048576.0, 1),
                "memory_current_mb_2_workers": round(rss["runs"]["2"]["steady_current_bytes"] / 1048576.0, 1),
                "method": rss["method"],
            }
        images[image] = {"repo": index["repo"], "index": index["index"], "platforms": platforms}
        entries.append({
            "name": entry["name"],
            "image": image,
            "port": entry["port"],
            "class": entry["class"],
            "rss_proc_mb": rss_proc,
            "rss_base_mb": max(rss_base.values()) if rss_base else None,
            "urls": entry["urls"],
            "verified": verified,
        })

    if problems:
        for problem in problems:
            print(problem)
        raise SystemExit("not writing %s, %d problem(s) above" % (args.out, len(problems)))

    document = {
        "schema": 1,
        "release": args.release,
        "fork": {"repo": args.repo, "sha": args.sha},
        "images": images,
        "frameworks": entries,
        "measurements": measurements,
    }
    with open(args.out, "w") as f:
        json.dump(document, f, indent=2)
        f.write("\n")
    print("wrote %s with %d frameworks" % (args.out, len(entries)))


if __name__ == "__main__":
    main()
