"""Extract serialized brewing settings, preserving every numeric field."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


PREFIXES = (
    "RecipeMapManager", "PotionManagerSettings", "CoalsSettings",
    "GrindingSettings", "PathBuilderSettings", "RecipeMapChunkSystemSettings",
)


def main():
    env = UnityPy.load(sys.argv[1])
    result = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        name = obj.peek_name() or ""
        if not name.startswith(PREFIXES):
            continue
        data = obj.read_typetree()
        result[name] = {"asset_id": obj.path_id, **data}
    output = ROOT / "data" / "brewing_settings.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(result)} settings objects to {output}")
    print("\n".join(sorted(result)))


if __name__ == "__main__":
    main()
