"""Validate saved candidate operations through the GUI's actual dispatcher."""
import argparse
import json
from pathlib import Path

from playground.serve import replay, WORLD
from optimizer.costs import resource_cost

ROOT=Path(__file__).resolve().parent.parent


def verify_record(record,details=False):
    for action in record['operations']:
        if action['kind'] in ('vortex_demo','inspect'):
            raise ValueError('Recipe must start at legal base center, not observation scene')
        if action['kind']=='salt' and action['salt']=='philosopher':
            raise ValueError('Philosopher salt is forbidden')
    result=replay(record['base'],record['operations'])
    state=result['state']
    expected=[[record['effect'],record['tier']]]
    if result['failure'] or state['failed_reason'] or state['start_mode']!='base' or [list(e) for e in state['effects']]!=expected:
        raise ValueError(f"Replay failed target: {record['effect']} {record['tier']}, actual {state['effects']}")
    from collections import Counter
    used=dict(Counter(state['used']))
    if used!=record['ingredients'] or state['salts']!=record.get('salts',{}):
        raise ValueError('Recorded ingredients/salts do not match replay')
    costs=resource_cost(used,state['salts'],{name:item['price'] for name,item in WORLD.ingredients.items()})
    return {'costs':costs,'minimum_health':state['minimum_health'],'health':state['health']} if details else costs


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',nargs='?',default='result/search/no_salt_candidates.json')
    args=parser.parse_args()
    document=json.loads((ROOT/args.source).read_text(encoding='utf-8'))
    failures=[]
    for key,record in document['records'].items():
        try:verify_record(record)
        except (ValueError,KeyError,TypeError) as error:failures.append({'record':key,'error':str(error)})
    report={'source':args.source,'records':len(document['records']),'failures':failures,
            'dispatcher':'playground.serve.replay','actualGameVerified':False}
    (ROOT/'result/search/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
