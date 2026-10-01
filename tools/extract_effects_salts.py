"""Extract full potion effect, base, and salt ScriptableObjects."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / ".vendor"))
import UnityPy  # noqa: E402


def save(name, values):
    (ROOT / "data" / name).write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    env = UnityPy.load(sys.argv[1])
    by_id = {o.path_id: o for o in env.objects}
    bases = []
    effects = {}
    salts = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        name = obj.peek_name() or ""
        if name not in ("Water", "Oil", "Wine") and "Salt" not in name:
            continue
        data = obj.read_typetree()
        if "potionEffectsDictionary" in data:
            bases.append({"asset_id": obj.path_id, "data": data})
            for ref in data["potionEffectsDictionary"]["m_keys"]:
                eid = ref["m_PathID"]
                if eid not in effects:
                    effects[eid] = {"asset_id": eid, "data": by_id[eid].read_typetree()}
        if "saltPile" in data:
            salts.append({"asset_id": obj.path_id, "data": data})
    save("bases_full.json", bases)
    save("potion_effects_full.json", list(effects.values()))
    save("salts_full.json", salts)
    print(f"Extracted {len(bases)} bases, {len(effects)} effects, {len(salts)} salts")
    print("Salts:", [s["data"]["m_Name"] for s in salts])


if __name__ == "__main__":
    main()
