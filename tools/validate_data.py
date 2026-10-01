"""Cross-check independently extracted Potion Craft map and asset data."""

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def read(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def main():
    ingredients = read("ingredients.json")
    assert len(ingredients) == 59
    assert len({item["name"] for item in ingredients}) == len(ingredients)
    assert sum(item["is_teleportation"] for item in ingredients) == 9
    for item in ingredients:
        curves = item["bezier_path"]
        assert curves and 0 <= item["grinded_path_starts_from"] <= 1
        for first, second in zip(curves, curves[1:]):
            assert math.dist(tuple(first["PLast"].values()),
                             tuple(second["PFirst"].values())) < 1e-4

    bases = read("bases.json")
    for base, level, expected in (("Water", 6, 41), ("Oil", 7, 21), ("Wine", 8, 21)):
        effects = bases[base]["effects"]
        markers = {m["name"].split(" ", 1)[1]: m for m in read(f"level{level}_markers.json")
                   if m["name"].startswith("PotionEffect ")}
        colliders = read(f"level{level}_effect_colliders.json")
        assert len(effects) == len(markers) == len(colliders) == expected
        for effect in effects:
            name = effect["name"]
            assert name in markers and name in colliders
            a, b = effect["Position"], markers[name]["position"]
            assert math.dist((a["x"], a["y"]), (b["x"], b["y"])) < 1e-6
            assert len(colliders[name]) == 1
            assert abs(colliders[name][0]["radius"] - 0.7900000214576721) < 1e-6
            assert colliders[name][0]["offset"] == {"x": 0.0, "y": 0.0}
        for vortex in read(f"level{level}_vortices.json"):
            endpoint = vortex["path"][-1]["PLast"]
            exit_point = vortex["exit_local"]
            assert math.dist((endpoint["x"], endpoint["y"]),
                             (exit_point["x"], exit_point["y"])) < 1e-6
        print(f"{base}: {len(effects)} effects and collider radii verified")
    print(f"{len(ingredients)} ingredient assets verified")


if __name__ == "__main__":
    main()
