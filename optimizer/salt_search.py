"""Salt-enabled candidates from cold routes on every base.

Enumerates integer salt units; final rotation is verified by actual collection.
This is an upper-bound generator, not an exhaustive salt/control search.
"""
import argparse
import copy
import json
import math
import time
import hashlib
from pathlib import Path

from engine.brew import BrewWorld, PotionSession, PotionFailed
from optimizer.search import Planner, capture, tier_variants, ROOT

VERSION='salt.v2'
SOLVER_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def rotation_operation(world,current,target):
    delta=(target-current+180)%360-180
    if abs(delta)<1e-7:return []
    salt='moon' if delta>0 else 'sun'
    unit=-world.settings['RecipeMapManagerIndicatorSettings']['moonSaltIndicatorRotationAngle' if salt=='moon' else 'sunSaltIndicatorRotationAngle']
    amount=round(delta/unit)
    return [dict(kind='salt',salt=salt,amount=amount)] if amount>0 else []


def life_supported(planner,operations):
    """Pay for small life top-ups before ordinary-path chunks can fail."""
    session=PotionSession(planner.world,base=planner.base)
    expanded=[]
    for action in operations:
        if action['kind']=='add':
            session.add(action['name'],action['grind']);expanded.append(action)
        elif action['kind']=='stir':
            if session.path_sections and session.path_sections[0]['teleport']:
                session.stir(action['fraction']);expanded.append(action);continue
            left=session.remaining_length*action['fraction']
            while left>1e-8 and session.pending:
                if session.health<.09:
                    amount=math.ceil((.15-session.health)/planner.world.salts['Life Salt']['healthToAdd'])
                    salt=dict(kind='salt',salt='life',amount=amount)
                    session.life_salt(amount);expanded.append(salt)
                amount=min(.15,left)
                stroke=dict(kind='stir',fraction=min(1,amount/session.remaining_length))
                session.stir(stroke['fraction']);expanded.append(stroke);left-=amount
        elif action['kind']=='pour':
            session.pour(action['seconds'],action['strength']);expanded.append(action)
        else:raise ValueError(action['kind'])
    return expanded,session


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--effects',nargs='*')
    parser.add_argument('--nodes',type=int,default=700)
    parser.add_argument('--alternatives',type=int,default=5)
    parser.add_argument('--missing-only',action='store_true')
    parser.add_argument('--output',default='result/search/with_salt_candidates.json')
    args=parser.parse_args()
    from optimizer.provenance import capture_run_snapshot
    snapshot=capture_run_snapshot()
    world=BrewWorld()
    path=(ROOT/args.output).resolve()
    if not path.is_relative_to(ROOT/'result/search'):raise ValueError('Search output must stay in result/search')
    path.parent.mkdir(parents=True,exist_ok=True)
    document=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'records':{},'runs':[]}
    names=json.loads((ROOT/'data/ui_manifest.json').read_text(encoding='utf-8'))['effects']
    planners={}
    for name in names:
        if args.effects and name not in args.effects:continue
        if args.missing_only:
            manifest=json.loads((ROOT/'result/manifest.json').read_text(encoding='utf-8'))
            if all(any(r['objective']=='P1' and r['mode']=='with_salt' and r['effect']==name and r['tier']==tier
                       and 'operations' in r for r in manifest['records']) for tier in (1,2,3)):continue
        started=time.time()
        for base,data in world.bases.items():
            targets=[e for e in data['effects'] if e['name']==name]
            if not targets:continue
            if base not in planners:
                print('Build salt roadmap:',base,flush=True)
                planners[base]=Planner(world,base)
            planner=planners[base]
            for objective in ('P1','P2'):
                if any(run.get('version')==VERSION and run['effect']==name and run['base']==base and run['objective']==objective
                       and run.get('node_limit',0)>=args.nodes and run.get('alternatives',0)>=args.alternatives
                       for run in document['runs']):continue
                routes,nodes=planner.search(targets[0],objective,args.nodes,args.alternatives)
                for route in routes:
                    refined=planner.refine(route,targets[0],iterations=90)
                    if refined is None:
                        refined=planner.refine(route,targets[0],iterations=120,allow_void=True)
                    if refined:
                        operations,session,minimum,evaluations=refined
                    else:
                        controls=[planner.actions[i][1] for i in route]
                        if not world.ingredients[planner.actions[route[-1]][0]]['is_teleportation']:controls[-1]=1.
                        try:operations,session=life_supported(planner,planner.operations(route,controls))
                        except PotionFailed:continue
                    before_rotate=operations
                    operations=operations+rotation_operation(world,session.rotation,targets[0]['Rotation'])
                    variants=tier_variants(planner,operations,targets[0])
                    unrotated=tier_variants(planner,before_rotate,targets[0]) if operations!=before_rotate else {}
                    all_variants=[*variants.items(),*unrotated.items()]
                    for tier,result in all_variants:
                        for selected_objective in ('P1','P2'):
                            key=f'{selected_objective}:{name}:{tier}'
                            previous=document['records'].get(key)
                            score=lambda r:(r['costs'][selected_objective],r['costs']['P2' if selected_objective=='P1' else 'P1'],len(r['operations']))
                            if previous is None or score(result)<score(previous):
                                document['records'][key]={**result,'effect':name,'tier':tier,'objective':selected_objective}
                document['runs'].append(dict(effect=name,base=base,objective=objective,nodes=nodes,
                                             snapshot=snapshot,parameters=vars(args),
                                             elapsed_seconds=time.time()-started,scope='cold routes; integer final rotation; ordinary life support; void tail trim; unrotated variants',
                                             version=VERSION,solver_sha256=SOLVER_SHA256,node_limit=args.nodes,alternatives=args.alternatives))
                temporary=path.with_suffix('.tmp')
                temporary.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
                temporary.replace(path)
                print('salt',objective,base,name,[(key.split(':')[-1],round(r['costs'][objective],3)) for key,r in document['records'].items() if r['effect']==name and key.startswith(objective+':')],flush=True)


if __name__=='__main__':main()
