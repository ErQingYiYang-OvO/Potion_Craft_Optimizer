"""Bounded one-herb search with paid rotation of the remaining path.

Integer salt samples and macro timing produce upper bounds, not exclusions.
Only ordinary herbs are proposed here; crystals and other schedules remain.
"""
import argparse
import hashlib
import json
from pathlib import Path

from engine.brew import BrewWorld, rotate_about, xy, cut_path
from engine.rotation import RotationTween
from optimizer.search import Planner, ROOT, tier_variants
from optimizer.single_ingredient import seeds
from optimizer.costs import resource_cost, competitive_tiers
from optimizer.provenance import capture_run_snapshot


class RotatedPlanner(Planner):
    def operations(self, route, controls):
        if len(route) != 1: raise ValueError('RotatedPlanner requires one ingredient')
        name = self.actions[route[0]][0]
        operations=[dict(kind='add',name=name,grind=1.)]
        if getattr(self,'pre_stir',0):operations.append(dict(kind='stir',fraction=self.pre_stir))
        return operations+[
                dict(kind='salt',salt=self.salt,amount=self.units,deferred=True),
                dict(kind='wait',seconds=self.wait_seconds),
                dict(kind='stir',fraction=float(controls[0]))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--effects',nargs='*')
    parser.add_argument('--bases',nargs='+',choices=['Water','Oil','Wine'])
    parser.add_argument('--ingredients',nargs='*')
    parser.add_argument('--max-units',type=int,default=100)
    parser.add_argument('--step',type=int,default=10)
    parser.add_argument('--iterations',type=int,default=60)
    parser.add_argument('--waits',nargs='+',type=float,default=[.06])
    parser.add_argument('--output',default='result/search/rotated_single_candidates.json')
    parser.add_argument('--pre-stirs',nargs='+',type=float,default=[0.])
    args = parser.parse_args()
    if not 1 <= args.max_units <= 10000 or args.step < 1 or any(not 0 <= t <= 1 for t in args.waits):
        parser.error('Invalid salt grid or wait duration')
    if any(not 0 <= t < 1 for t in args.pre_stirs):parser.error('Pre-stir fraction must be in [0,1)')
    world = BrewWorld()
    if args.ingredients and any(n not in world.ingredients for n in args.ingredients):parser.error('Unknown ingredient')
    prices = {n:i['price'] for n,i in world.ingredients.items()}
    manifest_bytes=(ROOT/'result/manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    path = (ROOT/args.output).resolve()
    if not path.is_relative_to(ROOT/'result/search') or not path.name.endswith('candidates.json'):
        parser.error('Output must be result/search/*candidates.json')
    checkpoint_bytes=path.read_bytes() if path.exists() else None
    saved = json.loads(checkpoint_bytes) if checkpoint_bytes else {'records':{},'runs':[]}
    solver = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    overrides={'result/manifest.json':manifest_bytes}
    if checkpoint_bytes is not None:overrides[path.relative_to(ROOT).as_posix()]=checkpoint_bytes
    snapshot=capture_run_snapshot(overrides=overrides)
    units_grid = sorted({1,args.max_units,*range(args.step,args.max_units+1,args.step)})
    for base,data in world.bases.items():
        if args.bases and base not in args.bases:continue
        planner = RotatedPlanner.__new__(RotatedPlanner); planner.world=world; planner.base=base
        for target in data['effects']:
            effect = target['name']
            if args.effects and effect not in args.effects: continue
            incumbents={(r['objective'],r['tier']):r['costs'] for r in manifest['records']
                        if r['effect']==effect and r['mode']=='with_salt' and 'operations' in r}
            refinements=0; successful=0; resource_pruned=0
            for ingredient,item in sorted(world.ingredients.items(),key=lambda p:p[1]['price']):
                if args.ingredients and ingredient not in args.ingredients:continue
                if item['is_teleportation']: continue
                original = world.ingredient_path(ingredient,1)
                for salt in ('moon','sun'):
                    for units in units_grid:
                        paid=resource_cost({ingredient:1},{salt:units},prices)
                        if not competitive_tiers(paid,incumbents):resource_pruned+=1;continue
                        controller=RotationTween()
                        controller.salt_batch(world.settings['RecipeMapManagerIndicatorSettings'],salt,units)
                        for pre_stir,wait in ((p,w) for p in args.pre_stirs for w in args.waits):
                            prefix=cut_path(original,pre_stir) if pre_stir else [original[0]]
                            pivot=prefix[-1]
                            remaining=[pivot]+original[len(prefix)-1:] if pre_stir else original
                            rotated=[rotate_about(p,pivot,controller.target) for p in remaining]
                            starts=seeds(rotated,xy(target['Position']))
                            planner.pre_stir=pre_stir
                            planner.salt=salt;planner.units=units;planner.wait_seconds=wait
                            # The rotated geometry proposes seeds even for an
                            # unfinished tween. Real timed replay decides validity.
                            for start in starts:
                                planner.actions=[(ingredient,start,original)]
                                refined=planner.refine((0,),target,iterations=args.iterations,tail_count=1,initial_controls=[start])
                                refinements+=1
                                if not refined: continue
                                operations=refined[0]
                                alternatives=[operations]
                                # Opposite salt may restore neutral orientation.
                                # Pouring can already have changed the angle, so
                                # this is a proposal, checked by actual replay.
                                alternatives.append(operations+[dict(kind='salt',salt='sun' if salt=='moon' else 'moon',amount=units,deferred=True),dict(kind='wait',seconds=.06)])
                                for sequence in alternatives:
                                    inventory,_=planner.replay(sequence)
                                    sequence_cost=resource_cost(dict(inventory.ingredients_used),dict(inventory.salts_used),prices)
                                    wanted=competitive_tiers(sequence_cost,incumbents)
                                    for tier,record in tier_variants(planner,sequence,target,allowed_tiers=wanted,scan_prefixes=False).items():
                                        successful+=1
                                        for objective in ('P1','P2'):
                                            key=f'{objective}:{effect}:{tier}'
                                            previous=saved['records'].get(key)
                                            rank=lambda r:(r['costs'][objective],r['costs']['P2' if objective=='P1' else 'P1'])
                                            if previous is None or rank(record)<rank(previous):
                                                saved['records'][key]={**record,'effect':effect,'tier':tier,'objective':objective}
            saved['runs'].append({'base':base,'effect':effect,'solver_sha256':solver,'refinements':refinements,
                                 'snapshot':snapshot,
                                 'parameters':vars(args),
                                 'successful_variants':successful,'resource_pruned':resource_pruned,'units_grid':units_grid,'pre_stirs':args.pre_stirs,'waits':args.waits,'iterations':args.iterations,
                                 'scope':'one ordinary herb; optional partial stirring before paid path rotation; optional opposite salt; numerical macro search, no proof'})
            temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
            print('rotated single',base,effect,'refinements',refinements,'variants',successful,flush=True)


if __name__=='__main__': main()
