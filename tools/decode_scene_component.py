"""Probe a scene MonoBehaviour using generated type trees from game assemblies."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools" / ".vendor_tt"), str(ROOT / "tools" / ".vendor")]
import UnityPy  # noqa: E402
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator  # noqa: E402


def main():
    scene = sys.argv[1]
    bundle = sys.argv[2]
    path_id = int(sys.argv[3])
    env = UnityPy.load(scene, bundle, str(Path(scene).parent / "globalgamemanagers.assets"))
    obj = next(x for x in env.objects if x.path_id == path_id and x.assets_file.name.endswith(Path(scene).name))
    generator = TypeTreeGenerator(obj.assets_file.unity_version)
    generator.load_local_dll_folder(str(Path(scene).parent / "Managed"))
    env.typetree_generator = generator
    print("Unity", obj.assets_file.unity_version, "size", obj.byte_size)
    print(json.dumps(obj.read_typetree(), indent=2, default=str))


if __name__ == "__main__":
    main()
