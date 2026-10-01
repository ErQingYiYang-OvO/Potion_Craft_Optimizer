"""Extract actual CircleCollider2D radii for every effect in one map scene."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


def main():
    scene = Path(sys.argv[1])
    env = UnityPy.load(str(scene))
    by_id = {obj.path_id: obj for obj in env.objects}
    transform_to_go = {}
    for obj in env.objects:
        if obj.type.name == "GameObject":
            go = obj.read_typetree()
            transform_to_go[go["m_Component"][0]["component"]["m_PathID"]] = go

    def descendants(transform_id):
        yield transform_to_go[transform_id]
        transform = by_id[transform_id].read_typetree()
        for child in transform["m_Children"]:
            yield from descendants(child["m_PathID"])

    effects = {}
    for obj in env.objects:
        if obj.type.name != "GameObject" or not (obj.peek_name() or "").startswith("PotionEffect "):
            continue
        go = obj.read_typetree()
        colliders = []
        transform_id = go["m_Component"][0]["component"]["m_PathID"]
        for child_go in descendants(transform_id):
            for ref in child_go["m_Component"]:
                component = by_id[ref["component"]["m_PathID"]]
                if component.type.name == "CircleCollider2D":
                    data = component.read_typetree()
                    colliders.append({"radius": data["m_Radius"], "offset": data["m_Offset"],
                                      "enabled": data["m_Enabled"], "object": child_go["m_Name"]})
        effects[go["m_Name"].split(" ", 1)[1]] = colliders
    output = ROOT / "data" / f"{scene.name}_effect_colliders.json"
    output.write_text(json.dumps(effects, indent=2), encoding="utf-8")
    print(f"{scene.name}: {len(effects)} effects, collider-count distribution:",
          {n: sum(len(c) == n for c in effects.values()) for n in set(map(len, effects.values()))})
    print("radii:", sorted({c["radius"] for colliders in effects.values() for c in colliders}))


if __name__ == "__main__":
    main()
