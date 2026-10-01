"""Extract ingredient definitions and their raw Bezier paths from the installed game."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))

import UnityPy  # noqa: E402


def main():
    bundle = Path(sys.argv[1])
    env = UnityPy.load(str(bundle))
    by_id = {obj.path_id: obj for obj in env.objects}
    ingredients = []
    full_ingredients = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            data = obj.read_typetree()
        except Exception:
            continue
        if not {"price", "path", "growthData", "chapter"}.issubset(data):
            continue
        path_id = data["path"]["m_PathID"]
        if path_id not in by_id:
            raise ValueError(f"Missing path {path_id} for {data['m_Name']}")
        path = by_id[path_id].read_typetree()
        full_ingredients.append({"asset_id": obj.path_id, "ingredient": data,
                                 "path": path})
        ingredients.append({
            "name": data["m_Name"],
            "asset_id": obj.path_id,
            "price": data["price"],
            "chapter": data["chapter"],
            "is_teleportation": bool(data["isTeleportationIngredient"]),
            "can_be_damaged": bool(data["canBeDamaged"]),
            "is_solid": bool(data["isSolid"]),
            "viscosity_down": data["viscosityDown"],
            "viscosity_up": data["viscosityUp"],
            "grind_status_curve": data["grindStatusByLeafGrindingCurve"],
            "substance_grinding_settings": data["substanceGrindingSettings"],
            "grinded_path_starts_from": path["grindedPathStartsFrom"],
            "bezier_path": path["path"],
            "path_builder_id": path["pathBuilderSettings"]["m_PathID"],
            "growth_data_id": data["growthData"]["m_PathID"],
        })
    ingredients.sort(key=lambda x: x["name"])
    output = ROOT / "data" / "ingredients.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(ingredients, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "data" / "ingredients_full.json").write_text(
        json.dumps(full_ingredients, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(ingredients)} ingredients to {output}")
    for item in ingredients:
        print(f"{item['name']:24} {item['price']:8.2f} {len(item['bezier_path']):3} curves")


if __name__ == "__main__":
    main()
