"""Verify map collider hierarchy transforms without starting the game."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy


def main(scene_path):
    scene = Path(scene_path)
    env = UnityPy.load(str(scene))
    objects = {obj.path_id: obj for obj in env.objects}

    def ancestors(transform_id):
        chain = []
        while transform_id:
            tf = objects[transform_id].read_typetree()
            chain.append({"name": objects[tf["m_GameObject"]["m_PathID"]].peek_name(),
                          "position": tf["m_LocalPosition"], "rotation": tf["m_LocalRotation"],
                          "scale": tf["m_LocalScale"]})
            transform_id = tf["m_Father"]["m_PathID"]
        return chain

    records = []
    for obj in env.objects:
        if obj.type.name == "PolygonCollider2D":
            data = obj.read_typetree()
            go = objects[data["m_GameObject"]["m_PathID"]].read_typetree()
            records.append({"kind": "forcefield", "name": go["m_Name"], "enabled": data["m_Enabled"],
                            "active": go["m_IsActive"], "layer": go["m_Layer"],
                            "chain": ancestors(go["m_Component"][0]["component"]["m_PathID"])})
        elif obj.type.name == "GameObject" and (obj.peek_name() or "").startswith("Vortex"):
            go = obj.read_typetree()
            records.append({"kind": "vortex", "name": go["m_Name"], "active": go["m_IsActive"],
                            "chain": ancestors(go["m_Component"][0]["component"]["m_PathID"])})
    output = ROOT / "data" / f"{scene.name}_transform_audit.json"
    output.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(scene.name, "records", len(records))
    for record in records:
        for depth, entry in enumerate(record["chain"]):
            pos, rot, scale = entry["position"], entry["rotation"], entry["scale"]
            if (0 < depth < len(record["chain"])-1 and any(pos[k] != 0 for k in ("x", "y"))) or rot != {"x": 0., "y": 0., "z": 0., "w": 1.} or any(scale[k] != 1 for k in ("x", "y")):
                print("NONIDENTITY", record["kind"], record["name"], depth, entry)
    print("Forcefield chains", [[item["name"] for item in record["chain"]] for record in records if record["kind"] == "forcefield"])
    print("Map roots", sorted({tuple(record["chain"][-1]["position"][key] for key in ("x", "y")) for record in records}))


if __name__ == "__main__":
    for path in sys.argv[1:]:
        main(path)
