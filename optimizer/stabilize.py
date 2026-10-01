"""Improve empirical tolerance without changing the paid resource inventory."""
import argparse
import copy
import json
from collections import Counter

from optimizer.robustness import ROOT, check, recipe_key, current_result
from optimizer.costs import resource_cost
from playground.serve import replay, WORLD
from engine.brew import curve_value


def control_candidates(operations):
    """Propose actual sequences; speed rescaling is not a validity proof."""
    indices=[i for i,a in enumerate(operations) if a['kind']=='pour' or (a['kind']=='stir' and 0<a['fraction']<1)]
    for index in reversed(indices[-2:]):
        action=operations[index];field='seconds' if action['kind']=='pour' else 'fraction'
        if field=='seconds':
            speed_curve=WORLD.settings['RecipeMapManagerPouringSettings']['standardSpeedByPouring']
            original_speed=curve_value(speed_curve,action['strength'])
            for strength in (.5,.2,.1,.05):
                if strength>=action['strength']:continue
                seconds=action['seconds']*original_speed/curve_value(speed_curve,strength)
                if not 0 < seconds <= 120:continue
                candidate=copy.deepcopy(operations)
                candidate[index].update(seconds=seconds,strength=strength)
                yield candidate
        offsets=(.01,-.01,.03,-.03,.1,-.1) if field=='seconds' else (.002,-.002,.005,-.005,.01,-.01,.02,-.02)
        for delta in offsets:
            candidate=copy.deepcopy(operations)
            candidate[index][field]=max(0,action[field]+delta)
            if field=='fraction':candidate[index][field]=min(1,candidate[index][field])
            yield candidate


def write_atomic(path,document):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--effects',nargs='*')
    args=parser.parse_args()
    folder=ROOT/'result/search'
    manifest=json.loads((ROOT/'result/manifest.json').read_text(encoding='utf-8'))
    robustness_path=folder/'robustness.json'
    statistics=json.loads(robustness_path.read_text(encoding='utf-8'))
    output=folder/'stable_candidates.json'
    document=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {'records':{},'runs':[]}
    visited=set()
    for row in manifest['records']:
        if 'operations' not in row or (args.effects and row['effect'] not in args.effects):continue
        key=recipe_key(row)
        original=statistics.get(key)
        if original and not current_result(original):
            original=check(row,original['samples']);statistics[key]=original
        if key in visited or not original or original['passed']==original['samples']:continue
        visited.add(key)
        best_passed=original['passed'];best=None
        operations=row['operations']
        # Weaker pouring reduces movement caused by the same timing error.
        # Heat/collisions and rotation can break the simple speed equivalence,
        # so every proposed sequence must pass actual replay and perturbations.
        for candidate in control_candidates(operations):
            result=replay(row['base'],candidate)
            state=result['state']
            if result['failure'] or [list(e) for e in state['effects']]!=[[row['effect'],row['tier']]]:continue
            ingredients=dict(Counter(state['used']))
            costs=resource_cost(ingredients,state['salts'],{n:i['price'] for n,i in WORLD.ingredients.items()})
            if costs['P1_exact']!=row['costs']['P1_exact'] or costs['P2_exact']!=row['costs']['P2_exact']:continue
            record={**row,'operations':candidate,'ingredients':ingredients,'salts':state['salts'],'costs':costs,
                    'ingredient_count':costs['ingredient_count'],'ingredient_value':costs['ingredient_value'],
                    'minimum_health':state['minimum_health'],'minimum_action_endpoint_health':state['minimum_health'],
                    'health':state['health'],'replay_verified':True,'game_verified':False}
            tested=check(record,original['samples'])
            statistics[recipe_key(record)]=tested
            if tested['passed']>best_passed:best_passed=tested['passed'];best=record
            if best_passed==original['samples']:break
        if best:
            document['records'][f'{row["objective"]}:{row["mode"]}:{row["effect"]}:{row["tier"]}']=best
        document['runs'].append({'effect':row['effect'],'tier':row['tier'],'original_passed':original['passed'],
                                 'improved_passed':best_passed,'samples':original['samples'],
                                 'scope':'last two partial controls and weaker pouring; unchanged resource inventory; empirical tolerance'})
        write_atomic(robustness_path,statistics);write_atomic(output,document)
        print(row['effect'],row['tier'],original['passed'],'->',best_passed,flush=True)


if __name__=='__main__':main()
