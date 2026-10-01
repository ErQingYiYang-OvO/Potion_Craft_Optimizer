"""Extract heat-control instance curves from game prefabs (read-only)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools" / ".vendor_tt"), str(ROOT / "tools" / ".vendor")]
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


def main():
    game = Path(sys.argv[1])
    bundles = list((game / "StreamingAssets/aa/StandaloneWindows64").glob("*assets_all*.bundle"))
    env = UnityPy.load(*map(str, bundles), str(game / "globalgamemanagers.assets"))
    objects = list(env.objects)
    generator = TypeTreeGenerator(objects[0].assets_file.unity_version)
    generator.load_local_dll_folder(str(game / "Managed"))
    env.typetree_generator = generator
    found, pouring = [], []
    for obj in objects:
        if obj.type.name != "GameObject" or not any(word in (obj.peek_name() or "").lower() for word in ("coal", "bellows", "stream")):
            continue
        go = obj.read_typetree()
        for component in go["m_Component"]:
            reader = obj.assets_file.objects.get(component["component"]["m_PathID"])
            if reader is None or reader.type.name != "MonoBehaviour":
                continue
            data = reader.read_typetree()
            if "heatIncreasingSpeed" in data:
                found.append({"name": go["m_Name"], "asset_id": reader.path_id,
                              "source": reader.assets_file.name, "data": data})
            if "heatCoolingDependence" in data:
                pouring.append({"name": go["m_Name"], "asset_id": reader.path_id,
                                "source": reader.assets_file.name, "data": data})
    if not found:
        raise RuntimeError("No BellowsCoals instances found")
    (ROOT / "data/bellows_controls.json").write_text(json.dumps(found, indent=2), encoding="utf-8")
    if pouring:
        (ROOT / "data/pouring_controls.json").write_text(json.dumps(pouring, indent=2), encoding="utf-8")
    print("Pouring instances:", [(item["name"], item["data"]["heatCoolingDependence"]) for item in pouring])
    print("Bellows instances:", [(item["name"], item["asset_id"]) for item in found])
    for item in found:
        print({key: value for key, value in item["data"].items() if key.startswith("heat") or key == "disableCoolingDown"})


if __name__ == "__main__":
    main()
