"""One-item candidates with partial stirring and pouring, on every base.

Full ingredient curves propose useful control starts. This is a numerical
upper-bound search, not a certificate excluding other one-item recipes.
"""
import argparse
import json
import hashlib
from pathlib import Path

from engine.brew import BrewWorld, distance, xy
from optimizer.search import Planner, ROOT, tier_variants

SOLVER_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def ingredient_seed_path(world, name, grind=1.):
    """Use the same sampling mode as PotionSession.add, including crystals."""
    return world.ingredient_path(name, grind,
                                 graphics=bool(world.ingredients[name]['is_teleportation']))


def seeds(path,goal,crystal=False):
    total=sum(distance(a,b) for a,b in zip(path,path[1:]))
    walked=0.;candidates=[]
    for index,point in enumerate(path):
        if index:walked+=distance(path[index-1],point)
        if crystal and index!=len(path)-1:continue
        norm=point[0]**2+point[1]**2
        factor=min(1,max(0,(point[0]*goal[0]+point[1]*goal[1])/norm)) if norm else 0
        error=distance((point[0]*factor,point[1]*factor),goal)
        if error<1.55:candidates.append((error,min(1.,max(0.,walked/total)) if total else 0.))
    selected=[]
    for error,fraction in sorted(candidates):
        if all(abs(fraction-value)>.07 for value in selected):selected.append(fraction)
        if len(selected)==3:break
    return selected


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--effects',nargs='*')
    parser.add_argument('--iterations',type=int,default=100)
    parser.add_argument('--ingredients',nargs='*')
    parser.add_argument('--all-crystal-starts',action='store_true',
                        help='Refine all five crystal grind starts without geometric rejection; still a numerical search')
    parser.add_argument('--output',default='result/search/single_candidates.json')
    args=parser.parse_args()
    from optimizer.provenance import capture_run_snapshot
    snapshot=capture_run_snapshot()
    world=BrewWorld()
    if args.ingredients and any(name not in world.ingredients for name in args.ingredients):parser.error('Unknown ingredient')
    output=(ROOT/args.output).resolve()
    if not output.is_relative_to(ROOT/'result/search'):raise ValueError('Search output must stay in result/search')
    output.parent.mkdir(parents=True,exist_ok=True)
    saved=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {'records':{},'runs':[]}
    for base,data in world.bases.items():
        # The continuous evaluator does not need the coarse collision raster.
        planner=Planner.__new__(Planner);planner.world=world;planner.base=base
        for target in data['effects']:
            name=target['name']
            if args.effects and name not in args.effects:continue
            evaluations=0;successful=0
            for ingredient,item in sorted(world.ingredients.items(),key=lambda pair:pair[1]['price']):
                if args.ingredients and ingredient not in args.ingredients:continue
                path=ingredient_seed_path(world,ingredient)
                starts=seeds(path,xy(target['Position']))
                if item['is_teleportation']:
                    starts=[g for g in (0,.25,.5,.75,1) if args.all_crystal_starts or seeds(ingredient_seed_path(world,ingredient,g),xy(target['Position']),True)]
                for start in starts:
                    planner.actions=[(ingredient,start,path)]
                    refined=planner.refine((0,),target,iterations=args.iterations,tail_count=1,initial_controls=[start])
                    evaluations+=1
                    if not refined:continue
                    variants=tier_variants(planner,refined[0],target)
                    for tier,record in variants.items():
                        successful+=1
                        for objective in ('P1','P2'):
                            key=f'{objective}:{name}:{tier}'
                            previous=saved['records'].get(key)
                            if previous is None or (record['costs'][objective],record['costs']['P2' if objective=='P1' else 'P1'])<(previous['costs'][objective],previous['costs']['P2' if objective=='P1' else 'P1']):
                                saved['records'][key]={**record,'effect':name,'tier':tier,'objective':objective}
            saved['runs'].append({'base':base,'effect':name,'refinements':evaluations,'successful_variants':successful,
                                  'snapshot':snapshot,'parameters':vars(args),
                                  'iterations':args.iterations,'solver_sha256':SOLVER_SHA256,
                                  'scope':'one item; partial final stirring; final pouring; no salt or intentional vortex'})
            temporary=output.with_suffix('.tmp')
            temporary.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(output)
            print('single',base,name,'refinements',evaluations,'variants',successful,flush=True)


if __name__=='__main__':main()
