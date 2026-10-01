"""Warm-start continuous controls from verified cold macro recipes."""
import argparse
import hashlib
import json
from pathlib import Path

from engine.brew import BrewWorld
from optimizer.search import Planner, ROOT, tier_variants


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--effects',nargs='+',required=True)
    parser.add_argument('--iterations',type=int,default=240)
    parser.add_argument('--append',choices=['Windbloom','Waterbloom','Lifeleaf','Firebell'])
    args=parser.parse_args()
    from optimizer.provenance import capture_run_snapshot
    snapshot=capture_run_snapshot()
    world=BrewWorld()
    manifest=json.loads((ROOT/'result/manifest.json').read_text(encoding='utf-8'))
    output=ROOT/'result/search/warm_candidates.json'
    saved=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {'records':{},'runs':[]}
    seen=set()
    solver_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for record in manifest['records']:
        if record['effect'] not in args.effects or record['mode']!='no_salt' or 'operations' not in record:continue
        key=json.dumps([record['base'],record['operations']],sort_keys=True)
        if key in seen:continue
        seen.add(key)
        actions=[];controls=[];legal=True
        ops=[a for a in record['operations'] if a['kind']!='pump']
        for index in range(0,len(ops),2):
            action=ops[index]
            if action['kind']=='pour':break
            if action['kind']!='add' or index+1>=len(ops) or ops[index+1]['kind']!='stir':legal=False;break
            name=action['name'];stroke=ops[index+1]
            actions.append((name,action['grind'],world.ingredient_path(name,action['grind'])))
            controls.append(action['grind'])
            if index+2<len(ops) and ops[index+2]['kind']=='add' and stroke['fraction']!=1:legal=False;break
            if index+2>=len(ops) or ops[index+2]['kind']=='pour':
                if not world.ingredients[name]['is_teleportation']:
                    minimum=world.ingredients[name]['grinded_path_starts_from']
                    controls[-1]=(minimum+action['grind']*(1-minimum))*stroke['fraction']
                elif stroke['fraction']!=1:legal=False;break
        if not legal or not actions:continue
        if args.append:
            # Only completed strokes without a final pour can be translated
            # directly into an additional ordinary ingredient macro here.
            if any(a['kind']=='pour' for a in ops) or ops[-1]['kind']!='stir' or ops[-1]['fraction']!=1:continue
            if not world.ingredients[actions[-1][0]]['is_teleportation'] and actions[-1][1]!=1:continue
            actions.append((args.append,.05,world.ingredient_path(args.append,1)))
            controls.append(.05)
        planner=Planner.__new__(Planner);planner.world=world;planner.base=record['base'];planner.actions=actions
        target=next(e for e in world.bases[record['base']]['effects'] if e['name']==record['effect'])
        refined=planner.refine(tuple(range(len(actions))),target,iterations=args.iterations,
                               tail_count=len(actions),initial_controls=controls)
        variants=tier_variants(planner,refined[0],target) if refined else {}
        for tier,candidate in variants.items():
            for objective in ('P1','P2'):
                identity=f'{objective}:{record["effect"]}:{tier}'
                previous=saved['records'].get(identity)
                rank=lambda c:(c['costs'][objective],c['costs']['P2' if objective=='P1' else 'P1'])
                if previous is None or rank(candidate)<rank(previous):
                    saved['records'][identity]={**candidate,'objective':objective,'effect':record['effect'],'tier':tier}
        saved['runs'].append({'base':record['base'],'effect':record['effect'],'source_tier':record['tier'],
                              'snapshot':snapshot,'parameters':vars(args),
                              'iterations':args.iterations,'found_tiers':list(variants),'solver_sha256':solver_hash,
                              'append':args.append,
                              'scope':'all controls of existing cold macro; no salt; final pour'})
        temporary=output.with_suffix('.tmp')
        temporary.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(output)
        print('warm',record['effect'],record['tier'],'->',list(variants),flush=True)


if __name__=='__main__':main()
