"""Real-origin portal prefixes followed by cold ingredient-route search.

No observation scenes or assigned coordinates are accepted as recipe origins.
This bounded pilot does not exhaust portal chains or overlapping inputs.
"""
import argparse
import json
import hashlib
from pathlib import Path

from engine.brew import BrewWorld, PotionFailed, distance, xy
from optimizer.search import Planner, ROOT, tier_variants
from optimizer.costs import resource_cost
from optimizer.state import future_state_key


def save(path,document):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)


def activate(planner,operations,vortex):
    operations=[dict(a) for a in operations]
    # Replace final partial ordinary stirring by equivalent partial grinding
    # when legal, avoiding leftover paid path after the portal.
    last=next((i for i in range(len(operations)-1,-1,-1) if operations[i]['kind']=='stir'),None)
    if last is not None and last and operations[last-1]['kind']=='add':
        material=operations[last-1]
        if not planner.world.ingredients[material['name']]['is_teleportation']:
            minimum=planner.world.ingredients[material['name']]['grinded_path_starts_from']
            effective=(minimum+material['grind']*(1-minimum))*operations[last]['fraction']
            if effective>=minimum and minimum<1:
                material['grind']=(effective-minimum)/(1-minimum);operations[last]['fraction']=1.
    session,_=planner.replay(operations)
    if not session.touching_vortex() or session.touching_vortex()['name']!=vortex['name']:return None
    for _ in range(80):
        action=dict(kind='pump',angle=12.,seconds=.2)
        session.pump_bellows(action['angle'],action['seconds']);operations.append(action)
        if session.effects:return None
        if any(t['kind']=='vortex' and t['name']==vortex['name'] for t in session.teleports):break
    else:return None
    # Cool, then explicitly consume any remaining path before continuing.
    for action in (dict(kind='wait',seconds=3.),dict(kind='stir',fraction=1.),dict(kind='wait',seconds=3.)):
        if action['kind']=='wait':session.wait(action['seconds'])
        else:session.stir(action['fraction'])
        operations.append(action)
    if session.effects or session.pending or session.heat>1e-8:return None
    return operations,session


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',choices=['Water','Oil'],default='Water')
    parser.add_argument('--effects',nargs='+',default=['MagicalVision','Lightning','Levitation'])
    parser.add_argument('--portals',type=int,default=2)
    parser.add_argument('--nodes',type=int,default=250)
    args=parser.parse_args()
    from optimizer.provenance import capture_run_snapshot
    snapshot=capture_run_snapshot()
    world=BrewWorld();planner=Planner(world,args.base)
    manifest=json.loads((ROOT/'result/manifest.json').read_text(encoding='utf-8'))
    output=ROOT/'result/search/vortex_candidates.json'
    document=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {'records':{},'runs':[]}
    prefixes=[];seen_prefixes=set();solver_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    portals=sorted(world.vortices[args.base],key=lambda v:distance((0,0),xy(v['entry'])))[:args.portals]
    for vortex in portals:
        target={'Position':vortex['entry']}
        routes,nodes=planner.search(target,'P1',args.nodes,4)
        for route in routes:
            refined=planner.refine(route,target,iterations=90)
            if not refined:continue
            try:prefix=activate(planner,refined[0],vortex)
            except PotionFailed:continue
            if prefix:
                key=future_state_key(prefix[1])
                if key not in seen_prefixes:prefixes.append(prefix);seen_prefixes.add(key)
        print('portal',vortex['name'],'valid prefixes',len(prefixes),flush=True)
    prices={n:i['price'] for n,i in world.ingredients.items()}
    save(ROOT/'result/search/vortex_prefixes.json',{'base':args.base,'prefixes':[
         {'operations':ops,'position':session.position,'costs':resource_cost(dict(session.ingredients_used),dict(session.salts_used),prices)}
         for ops,session in prefixes]})
    for operations,session in prefixes:
        paid=resource_cost(dict(session.ingredients_used),dict(session.salts_used),prices)
        for target in world.bases[args.base]['effects']:
            if target['name'] not in args.effects:continue
            for tier,candidate in tier_variants(planner,operations,target).items():
                for chosen in ('P1','P2'):
                    key=f'{chosen}:{target["name"]}:{tier}'
                    old=document['records'].get(key)
                    rank=lambda c:(c['costs'][chosen],c['costs']['P2' if chosen=='P1' else 'P1'])
                    if old is None or rank(candidate)<rank(old):document['records'][key]={**candidate,'objective':chosen,'effect':target['name'],'tier':tier}
            save(output,document)
            for objective in ('P1','P2'):
                upper=max(r['costs'][objective] for r in manifest['records'] if r['objective']==objective and
                          r['mode']=='no_salt' and r['effect']==target['name'] and 'operations' in r)-paid[objective]
                if upper<(1 if objective=='P1' else min(prices.values())):continue
                routes,nodes=planner.search(target,objective,args.nodes,4,upper_bound=upper,prefix_operations=operations)
                for route in routes:
                    refined=planner.refine(route,target,iterations=90,prefix_operations=operations)
                    if not refined:continue
                    for tier,candidate in tier_variants(planner,refined[0],target).items():
                        for chosen in ('P1','P2'):
                            key=f'{chosen}:{target["name"]}:{tier}'
                            old=document['records'].get(key)
                            rank=lambda c:(c['costs'][chosen],c['costs']['P2' if chosen=='P1' else 'P1'])
                            if old is None or rank(candidate)<rank(old):document['records'][key]={**candidate,'objective':chosen,'effect':target['name'],'tier':tier}
                document['runs'].append({'base':args.base,'effect':target['name'],'objective':objective,'nodes':nodes,
                                        'snapshot':snapshot,'parameters':vars(args),
                                        'prefix_cost':paid[objective],'solver_sha256':solver_hash,
                                        'scope':'one deliberate portal; cold continuation; bounded macro controls'})
                save(output,document)
                print('portal continuation',target['name'],objective,'nodes',nodes,flush=True)


if __name__=='__main__':main()
