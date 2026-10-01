"""Read installed Unity physics, layers and timestep settings without launching it."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


def main():
    source = Path(sys.argv[1])
    wanted = {"Physics2DSettings", "PhysicsManager", "TimeManager", "TagManager"}
    env = UnityPy.load(str(source))
    result = {}
    for obj in env.objects:
        if obj.type.name in wanted:
            result[obj.type.name] = {"object_id": obj.path_id, "data": obj.read_typetree()}
    output = ROOT / "data" / "unity_simulation_settings.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Extracted:", sorted(result))
    if "TagManager" in result:
        print("Layers:", list(enumerate(result["TagManager"]["data"].get("layers", []))))
    if "TimeManager" in result:
        print("Time:", result["TimeManager"]["data"])


if __name__ == "__main__":
    main()
