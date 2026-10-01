"""Locate selected serialized gameplay objects in a Unity bundle."""

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asset")
    parser.add_argument("--name", default="")
    parser.add_argument("--field", default="")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    env = UnityPy.load(args.asset)
    found = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        name = obj.peek_name() or ""
        if args.name and not re.search(args.name, name, re.I):
            continue
        data = obj.read_typetree()
        if args.field and args.field not in data:
            continue
        found.append({"name": name, "path_id": obj.path_id,
                      "fields": list(data)[:30]})
        if len(found) >= args.limit:
            break
    print(json.dumps(found, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
