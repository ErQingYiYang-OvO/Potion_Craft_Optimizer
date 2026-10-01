"""Summarize names beneath a Unity Transform without exporting artwork."""

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


def main():
    env = UnityPy.load(sys.argv[1])
    root = int(sys.argv[2])
    by_id = {obj.path_id: obj for obj in env.objects}
    names = collections.Counter()
    depths = collections.Counter()
    examples = []
    stack = [(root, 0)]
    while stack:
        tfid, depth = stack.pop()
        tf = by_id[tfid].read_typetree()
        goid = tf["m_GameObject"]["m_PathID"]
        name = by_id[goid].peek_name()
        names[name] += 1
        depths[depth] += 1
        if depth <= 2 and len(examples) < 30:
            examples.append((depth, name, goid, len(tf["m_Children"])))
        for child in tf["m_Children"]:
            stack.append((child["m_PathID"], depth + 1))
    print("Total", sum(names.values()), "depths", depths)
    print("Common", names.most_common(30))
    print("Examples", examples)


if __name__ == "__main__":
    main()
