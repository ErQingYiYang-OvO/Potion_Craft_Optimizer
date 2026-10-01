"""Extract potion-effect coordinates and rotations for every base."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


def main():
    env = UnityPy.load(sys.argv[1])
    by_id = {obj.path_id: obj for obj in env.objects}
    bases = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        if obj.peek_name() not in ("Water", "Oil", "Wine"):
            continue
        data = obj.read_typetree()
        if "potionEffectsDictionary" not in data:
            continue
        dictionary = data["potionEffectsDictionary"]
        keys = dictionary["m_keys"]
        values = dictionary["m_values"]
        if len(keys) != len(values):
            raise ValueError(f"Mismatched effect table: {data['m_Name']}")
        effects = []
        for key, value in zip(keys, values):
            effect_id = key["m_PathID"]
            effect = by_id[effect_id].read_typetree()
            effects.append({"name": effect["m_Name"], "effect_id": effect_id,
                            "price": effect.get("price"), **value})
        bases[data["m_Name"]] = {
            "asset_id": obj.path_id,
            "map_index": data["recipeMapIndexEnum"],
            "map_size": data["mapBgSize"],
            "instant_regeneration": bool(data["instantIndicatorRegeneration"]),
            "regeneration_coefficient": data["indicatorRegenerationCoefficient"],
            "effects": effects,
        }
    output = ROOT / "data" / "bases.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(bases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(bases)} bases to {output}")
    for name, base in bases.items():
        print(f"{name}: {len(base['effects'])} effects, map size {base['map_size']}")
        print("First effect:", base["effects"][0])


if __name__ == "__main__":
    main()
