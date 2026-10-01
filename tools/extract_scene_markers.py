"""Extract map scene marker positions for visual comparison."""

import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


def main():
    scene = Path(sys.argv[1])
    env = UnityPy.load(str(scene))
    by_id = {obj.path_id: obj for obj in env.objects}
    markers = []
    parent_counts = Counter()
    names = Counter()
    for obj in env.objects:
        if obj.type.name != "GameObject":
            continue
        name = obj.peek_name() or ""
        if not re.match(r"(?:PotionEffect |Vortex|Teleport|StrongDangerZoneContainer|DangerZoneContainer|HealZoneContainer|SwampZoneContainer)", name):
            continue
        go = obj.read_typetree()
        tfid = go["m_Component"][0]["component"]["m_PathID"]
        tf = by_id[tfid].read_typetree()
        parent_id = tf["m_Father"]["m_PathID"]
        markers.append({"name": name, "game_object_id": obj.path_id,
                        "transform_id": tfid, "parent_transform_id": parent_id,
                        "position": tf["m_LocalPosition"], "rotation": tf["m_LocalRotation"],
                        "scale": tf["m_LocalScale"]})
        parent_counts[parent_id] += 1
        names[name.split(" ")[0].split("(")[0]] += 1
    output = ROOT / "data" / f"{scene.name}_markers.json"
    output.write_text(json.dumps(markers, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(markers)} markers to {output}")
    print("Types:", names)
    print("Parent counts:", parent_counts.most_common(8))
    print("First markers:", markers[:3])


if __name__ == "__main__":
    main()
