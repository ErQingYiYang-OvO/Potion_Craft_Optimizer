"""Content-addressed, restorable solver/data snapshots for future runs.

An archive freezes project files at launch. It does not retroactively identify
the loaded code of older live jobs, or certify the game's simulation model.
"""
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent.parent


def capture_run_snapshot(root=ROOT, overrides=None):
    root=Path(root).resolve()
    paths=[]
    for directory,pattern in [('data','*.json'),('engine','*.py'),('optimizer','*.py'),('tests','*.py')]:
        paths+=sorted((root/directory).glob(pattern))
    paths += [root/p for p in ('playground/serve.py','optimizer/requirements.txt','docs/PLAN.md') if (root/p).is_file()]
    if (root/'result/manifest.json').is_file():paths.append(root/'result/manifest.json')
    # Warm starts, incumbent bounds and resume checkpoints are solver inputs.
    paths+=sorted((root/'result/search').glob('*candidates.json'))
    paths+=sorted((root/'result/search').glob('robustness*.json'))
    contents={p.relative_to(root).as_posix():p.read_bytes() for p in paths}
    for name,data in (overrides or {}).items():
        if not (root/name).resolve().is_relative_to(root):raise ValueError('Snapshot override outside project')
        contents[name]=data
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in contents.items()}
    manifest={'schema':1,'gameVersion':'2.0.2','files':hashes,
              'scope':'project source, extracted data and solver input checkpoints; no installed game binaries or environment packages'}
    encoded=json.dumps(manifest,sort_keys=True,ensure_ascii=False,indent=2).encode('utf-8')
    identity=hashlib.sha256(encoded).hexdigest()
    folder=root/'result/search/snapshots';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(identity+'.zip')
    if not path.exists():
        temporary=path.with_suffix('.tmp')
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for name,data in sorted({**contents,'RUN_SNAPSHOT.json':encoded}.items()):
                entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(entry,data)
        temporary.replace(path)
    # Existing content-addressed artifacts must still be intact.
    with zipfile.ZipFile(path) as archive:
        if archive.read('RUN_SNAPSHOT.json')!=encoded:raise ValueError('Snapshot manifest mismatch')
        for name,digest in hashes.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest:raise ValueError('Corrupt snapshot member: '+name)
    try:numpy_version=importlib.metadata.version('numpy')
    except importlib.metadata.PackageNotFoundError:numpy_version=None
    return {'id':identity,'archive':path.relative_to(root).as_posix(),'file_count':len(contents),
            'archive_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'python':platform.python_version(),'numpy':numpy_version,'platform':platform.system()}


if __name__=='__main__':print(json.dumps(capture_run_snapshot(),ensure_ascii=False))
