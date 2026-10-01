"""Empirical control perturbations; never a certified error bound."""
import argparse
import copy
import hashlib
import json
import random
from pathlib import Path

from playground.serve import replay

ROOT=Path(__file__).resolve().parent.parent
SAMPLER_VERSION=2
_model_files=sorted((ROOT/'data').glob('*.json'))+sorted((ROOT/'engine').glob('*.py'))+[ROOT/'playground/serve.py']
MODEL_FINGERPRINT=hashlib.sha256(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in _model_files},sort_keys=True).encode()).hexdigest()


def current_result(result):
    return isinstance(result,dict) and result.get('model_fingerprint')==MODEL_FINGERPRINT and result.get('sampler_version')==SAMPLER_VERSION


def recipe_key(record):
    content={key:record[key] for key in ('base','effect','tier','operations')}
    return hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()


def check(record,samples=8):
    rng=random.Random(20261001)
    outcomes=[]
    for index in range(samples):
        operations=copy.deepcopy(record['operations'])
        for action in operations:
            if action['kind']=='add' and 0<action['grind']<1:
                action['grind']=min(1,max(0,action['grind']+rng.choice((-1,1))*.001))
            elif action['kind']=='stir' and 0<action['fraction']<1:
                action['fraction']=min(1,max(0,action['fraction']+rng.choice((-1,1))*.001))
            elif action['kind']=='pour':
                action['seconds']=max(0,action['seconds']+rng.choice((-1,1))*.005)
            elif action['kind']=='wait':
                action['seconds']=max(.000001,action['seconds']+rng.choice((-1,1))*.005)
            elif action['kind']=='salt':
                action['amount']=max(0,action['amount']+rng.choice((-1,1)))
        result=replay(record['base'],operations)
        effects=[list(e) for e in result['state']['effects']]
        outcomes.append({'passed':not result['failure'] and effects==[[record['effect'],record['tier']]],
                         'effects':effects,'failure':result['failure'],'health':result['state']['health']})
    return {'passed':sum(o['passed'] for o in outcomes),'samples':samples,
            'model_fingerprint':MODEL_FINGERPRINT,'sampler_version':SAMPLER_VERSION,
            'method':f'{samples} deterministic joint perturbations; empirical only',
            'parameters':{'grind_absolute':.001,'partial_stir_absolute':.001,'pour_seconds':.005,'wait_seconds':.005,'salt_units':1},
            'outcomes':outcomes,'certified':False,'game_verified':False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--effects',nargs='*')
    parser.add_argument('--samples',type=int,default=8)
    parser.add_argument('--source',default='result/manifest.json')
    parser.add_argument('--output',default='result/search/robustness.json')
    args=parser.parse_args()
    if args.samples<1:parser.error('--samples must be positive')
    manifest=json.loads((ROOT/args.source).read_text(encoding='utf-8'))
    path=(ROOT/args.output).resolve()
    if not path.is_relative_to(ROOT/'result/search') or not path.name.startswith('robustness'):
        parser.error('Statistics output must be result/search/robustness*.json')
    saved=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    records=manifest['records'].values() if isinstance(manifest['records'],dict) else manifest['records']
    for record in records:
        if 'operations' not in record or (args.effects and record['effect'] not in args.effects):continue
        key=recipe_key(record)
        if key in saved and current_result(saved[key]) and saved[key]['samples']>=args.samples:continue
        saved[key]=check(record,args.samples)
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(path)
        print(record.get('objective','candidate'),record.get('mode','candidate'),record['effect'],record['tier'],saved[key]['passed'], '/',args.samples,flush=True)


if __name__=='__main__':main()
