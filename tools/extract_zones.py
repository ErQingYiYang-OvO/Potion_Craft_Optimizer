"""Extract map-zone collider geometry from the installed Unity scenes."""

import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


ZONE_NAMES = {
    "StrongDangerZoneContainer": "strong_danger",
    "WeakDangerZoneContainer": "weak_danger",
    "HealZoneContainer": "heal",
    "SwampZoneContainer": "swamp",
}


def compose(parent, local):
    px, py, pa, psx, psy = parent
    v = local["m_LocalPosition"]
    q = local["m_LocalRotation"]
    angle = 2 * math.atan2(q["z"], q["w"])
    x, y = v["x"] * psx, v["y"] * psy
    return (px + x * math.cos(pa) - y * math.sin(pa),
            py + x * math.sin(pa) + y * math.cos(pa),
            pa + angle, psx * local["m_LocalScale"]["x"],
            psy * local["m_LocalScale"]["y"])


def main():
    scene = Path(sys.argv[1])
    env = UnityPy.load(str(scene))
    by_id = {obj.path_id: obj for obj in env.objects}
    roots = {}
    for obj in env.objects:
        if obj.type.name == "GameObject" and obj.peek_name() in ZONE_NAMES:
            go = obj.read_typetree()
            tfid = go["m_Component"][0]["component"]["m_PathID"]
            roots[ZONE_NAMES[go["m_Name"]]] = tfid

    zones = {}
    skipped = Counter()
    layers = Counter()
    for zone, root_id in roots.items():
        shapes = []
        stack = [(root_id, (0, 0, 0, 1, 1))]
        while stack:
            tfid, parent = stack.pop()
            tf = by_id[tfid].read_typetree()
            world = compose(parent, tf)
            goid = tf["m_GameObject"]["m_PathID"]
            go = by_id[goid].read_typetree()
            if not go["m_IsActive"]:
                # Unity disables all descendant colliders of an inactive object.
                continue
            if go["m_IsActive"]:
                for component in go["m_Component"][1:]:
                    cid = component["component"]["m_PathID"]
                    collider = by_id[cid]
                    if collider.type.name not in ("BoxCollider2D", "CircleCollider2D"):
                        continue
                    try:
                        data = collider.read_typetree()
                    except Exception:
                        skipped[collider.type.name] += 1
                        continue
                    if not data["m_Enabled"]:
                        continue
                    layers[go["m_Layer"]] += 1
                    cx, cy, angle, sx, sy = world
                    offset = data["m_Offset"]
                    ox, oy = offset["x"] * sx, offset["y"] * sy
                    cx += ox * math.cos(angle) - oy * math.sin(angle)
                    cy += ox * math.sin(angle) + oy * math.cos(angle)
                    if collider.type.name == "BoxCollider2D":
                        size = data["m_Size"]
                        shapes.append(["box", cx, cy, size["x"] * sx,
                                       size["y"] * sy, angle])
                    else:
                        shapes.append(["circle", cx, cy,
                                       data["m_Radius"] * max(abs(sx), abs(sy))])
            for child in tf["m_Children"]:
                stack.append((child["m_PathID"], world))
        zones[zone] = shapes

    output = ROOT / "data" / f"{scene.name}_zones.json"
    output.write_text(json.dumps(zones, separators=(",", ":")), encoding="utf-8")
    metadata = {"source": str(scene), "layers": dict(layers), "skipped": dict(skipped),
                "active_hierarchy_only": True, "counts": {k: len(v) for k, v in zones.items()}}
    (ROOT / "data" / f"{scene.name}_zone_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Extracted {sum(map(len, zones.values()))} collider shapes to {output}")
    print({key: len(value) for key, value in zones.items()}, "skipped", skipped)


if __name__ == "__main__":
    main()
