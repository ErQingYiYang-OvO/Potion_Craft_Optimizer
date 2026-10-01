"""Extract the map forcefield polygons from each scene."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


def main():
    scene = Path(sys.argv[1])
    env = UnityPy.load(str(scene))
    by_id = {o.path_id: o for o in env.objects}
    polygons = []
    for obj in env.objects:
        if obj.type.name != "PolygonCollider2D":
            continue
        data = obj.read_typetree()
        go = by_id[data["m_GameObject"]["m_PathID"]].read_typetree()
        tfid = go["m_Component"][0]["component"]["m_PathID"]
        tf = by_id[tfid].read_typetree()
        polygons.append({"name": go["m_Name"], "position": tf["m_LocalPosition"],
                         "offset": data["m_Offset"], "paths": data["m_Points"]["m_Paths"]})
    output = ROOT / "data" / f"{scene.name}_boundaries.json"
    output.write_text(json.dumps(polygons, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(polygons)} polygons to {output}")
    print([(p["name"], list(map(len, p["paths"]))) for p in polygons])


if __name__ == "__main__":
    main()
