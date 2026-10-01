"""Extract individual vortex entry, exit, trajectory and collider data."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools" / ".vendor_tt"), str(ROOT / "tools" / ".vendor")]
import UnityPy  # noqa: E402
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator  # noqa: E402


def main():
    scene = Path(sys.argv[1])
    bundle = Path(sys.argv[2])
    env = UnityPy.load(str(scene), str(bundle), str(scene.parent / "globalgamemanagers.assets"))
    scene_objects = [o for o in env.objects if o.assets_file.name.endswith(scene.name)]
    by_id = {o.path_id: o for o in scene_objects}
    generator = TypeTreeGenerator(scene_objects[0].assets_file.unity_version)
    generator.load_local_dll_folder(str(scene.parent / "Managed"))
    env.typetree_generator = generator
    vortexes = []
    errors = []
    for obj in scene_objects:
        if obj.type.name != "GameObject" or not (obj.peek_name() or "").startswith("Vortex"):
            continue
        go = obj.read_typetree()
        components = [c["component"]["m_PathID"] for c in go["m_Component"]]
        tf = by_id[components[0]].read_typetree()
        path = None
        vortex = None
        for cid in components[1:]:
            component = by_id[cid]
            if component.type.name != "MonoBehaviour":
                continue
            try:
                data = component.read_typetree()
            except Exception as exc:
                errors.append((go["m_Name"], cid, str(exc)))
                continue
            if "exitPoint" in data and "path" in data:
                path = data
            if "vortexCollider" in data:
                vortex = data
        if path is None or vortex is None:
            errors.append((go["m_Name"], obj.path_id, "missing vortex path or settings"))
            continue
        collider_id = vortex["vortexCollider"]["m_PathID"]
        collider = by_id[collider_id].read_typetree()
        exit_tf = by_id[path["exitPoint"]["m_PathID"]].read_typetree()
        vortexes.append({"name": go["m_Name"], "game_object_id": obj.path_id,
                         "entry": tf["m_LocalPosition"],
                         "path": path["path"],
                         "exit_local": exit_tf["m_LocalPosition"],
                         "entry_radius": collider["m_Radius"],
                         "entry_offset": collider["m_Offset"]})
    output = ROOT / "data" / f"{scene.name}_vortices.json"
    output.write_text(json.dumps(vortexes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(vortexes)} vortices to {output}")
    print("First:", vortexes[:1])
    print("Errors:", errors[:8], "total", len(errors))


if __name__ == "__main__":
    main()
