"""Read-only inventory of Unity objects in a Potion Craft asset file."""

import argparse
import collections
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))

import UnityPy  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asset", type=Path)
    parser.add_argument("--match", default="")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    env = UnityPy.load(str(args.asset))
    counts = collections.Counter()
    matches = []
    errors = collections.Counter()
    needle = args.match.casefold()
    for obj in env.objects:
        kind = obj.type.name
        counts[kind] += 1
        if kind not in ("MonoBehaviour", "GameObject", "TextAsset", "MonoScript"):
            continue
        try:
            name = obj.peek_name() or ""
        except Exception as exc:
            errors[type(exc).__name__] += 1
            continue
        if needle in name.casefold() and len(matches) < args.limit:
            matches.append({"name": name, "type": kind, "path_id": obj.path_id})
    print(json.dumps({"asset": str(args.asset), "counts": counts,
                      "matches": matches, "errors": errors}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
