"""Inspect one named serialized Unity object without modifying game files."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))

import UnityPy  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asset", type=Path)
    parser.add_argument("name", nargs="?")
    parser.add_argument("--kind", default="MonoBehaviour")
    parser.add_argument("--id", type=int)
    parser.add_argument("--keys", action="store_true")
    parser.add_argument("--select")
    args = parser.parse_args()
    env = UnityPy.load(str(args.asset))
    for obj in env.objects:
        if args.id is not None:
            if obj.path_id != args.id:
                continue
        elif obj.type.name != args.kind or obj.peek_name() != args.name:
            continue
        try:
            data = obj.read_typetree()
        except Exception as exc:
            print(json.dumps({"path_id": obj.path_id, "type": obj.type.name,
                              "is_stripped": obj.is_stripped,
                              "error": str(exc)}, ensure_ascii=False))
            continue
        if args.select:
            if args.select not in data:
                continue
            data = data[args.select]
        if args.keys:
            data = {k: (f"list[{len(v)}]" if isinstance(v, list) else type(v).__name__)
                    for k, v in data.items()}
        print(json.dumps({"path_id": obj.path_id, "type": obj.type.name, "data": data},
                         ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
