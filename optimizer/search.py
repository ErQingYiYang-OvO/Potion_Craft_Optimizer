"""Multi-resource route search; coarse geometry proposes, BrewWorld verifies.

The roadmap is a heuristic, not an exhaustive discretization or a proof.
No grid position or synthetic starting state is exported as a real recipe.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import heapq
import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np

from engine.brew import BrewWorld, PotionSession, PotionFailed, cut_path, distance, xy
from optimizer.costs import resource_cost, no_salt_search_bound

ROOT = Path(__file__).resolve().parent.parent
SOLVER_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def apply_action(session, action):
    """Same explicit action semantics for refinement and final replay."""
    kind = action['kind']
    if kind == 'add': session.add(action['name'], action['grind'])
    elif kind == 'stir': session.stir(action['fraction'])
    elif kind == 'pour': session.pour(action['seconds'], action['strength'])
    elif kind == 'pump': session.pump_bellows(action['angle'], action['seconds'])
    elif kind == 'wait': session.wait(action['seconds'])
    elif kind == 'salt':
        salt = action['salt']
        if salt in ('sun','moon'): session.rotate_salt(salt, action['amount'], deferred=action.get('deferred',False))
        elif salt == 'life': session.life_salt(action['amount'])
        elif salt == 'void': session.void_salt(action['amount'])
        else: raise ValueError('Forbidden salt')
    else: raise ValueError(kind)


class Raster:
    """Nearest-grid collision hints, used only to propose routes."""
    def __init__(self, world, base, spacing=.2):
        self.spacing, self.origin = spacing, -85.0
        self.size = round(170/spacing)+1
        self.flags = np.zeros((self.size, self.size), dtype=np.uint8)
        radius = world.geometry['indicator_radius']
        for zone, shape in world.zones[base].shapes:
            from engine.brew import shape_bbox
            bit = {'strong_danger':1, 'weak_danger':2, 'heal':4, 'swamp':8}[zone]
            xmin, ymin, xmax, ymax = shape_bbox(shape, radius)
            ix0=max(0,math.floor((xmin-self.origin)/spacing))
            iy0=max(0,math.floor((ymin-self.origin)/spacing))
            ix1=min(self.size,math.ceil((xmax-self.origin)/spacing)+1)
            iy1=min(self.size,math.ceil((ymax-self.origin)/spacing)+1)
            if ix0>=ix1 or iy0>=iy1:continue
            dx=(np.arange(ix0,ix1)*spacing+self.origin-shape[1])[None,:]
            dy=(np.arange(iy0,iy1)*spacing+self.origin-shape[2])[:,None]
            if shape[0]=='circle':
                hit=dx*dx+dy*dy<=(shape[3]+radius)**2
            else:
                co,si=math.cos(shape[5]),math.sin(shape[5])
                qx=np.maximum(np.abs(dx*co+dy*si)-abs(shape[3])/2,0)
                qy=np.maximum(np.abs(-dx*si+dy*co)-abs(shape[4])/2,0)
                hit=qx*qx+qy*qy<=radius*radius
            patch=self.flags[iy0:iy1,ix0:ix1]
            patch[hit]|=bit

    def at(self, points):
        indices=np.rint((np.asarray(points)-self.origin)/self.spacing).astype(int)
        valid=np.all((indices>=0)&(indices<self.size),axis=-1)
        indices=np.clip(indices,0,self.size-1)
        return np.where(valid,self.flags[indices[...,1],indices[...,0]],1)


class Planner:
    def __init__(self, world, base):
        self.world,self.base=world,base
        self.raster=Raster(world,base)
        self.paths={name:world.ingredient_path(name,1) for name in world.ingredients}
        self.lengths={name:sum(distance(a,b) for a,b in zip(path,path[1:])) for name,path in self.paths.items()}
        self.actions=[]
        # Fully traverse every intermediate ingredient; partial grind may vary.
        # Cold stirring, no salt, no intentionally activated vortex.
        for name,item in world.ingredients.items():
            for grind in (0,.25,.5,.75,1):
                path=world.ingredient_path(name,grind)
                self.actions.append((name,grind,path))
        self.cost=np.array([world.ingredients[n]['price'] for n,g,p in self.actions])
        self.crystal=np.array([world.ingredients[n]['is_teleportation'] for n,g,p in self.actions])
        # Coarse arc-length sampling. Final validation uses original 0.05 data.
        self.steps=64
        self.deltas=np.zeros((len(self.actions),self.steps,2))
        for index,(name,grind,path) in enumerate(self.actions):
            samples=[self.point(path,j/self.steps) for j in range(self.steps+1)]
            self.deltas[index]=np.diff(samples,axis=0)
        self.max_jump=max(float(np.linalg.norm(np.asarray(p),axis=1).max()) for p in self.paths.values())
        peaks=np.linalg.norm(np.cumsum(self.deltas,axis=1),axis=2).max(axis=1)
        self.cost_per_distance=float(np.min(self.cost/np.maximum(peaks,.001)))

    @staticmethod
    def point(path,fraction):
        if fraction>=1:return path[-1]
        if fraction<=0:return path[0]
        lengths=np.array([distance(a,b) for a,b in zip(path,path[1:])])
        cumulative=np.cumsum(lengths)
        target=float(cumulative[-1])*fraction
        index=min(int(np.searchsorted(cumulative,target)),len(lengths)-1)
        before=float(cumulative[index-1]) if index else 0
        t=(target-before)/lengths[index] if lengths[index] else 0
        a,b=path[index],path[index+1]
        return (a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t)

    def successors(self,position,health,goal=None):
        positions=np.tile(position,(len(self.actions),1)).astype(float)
        hp=np.full(len(self.actions),health,dtype=float)
        minimum=hp.copy()
        near=np.full(len(self.actions),np.inf)
        base=self.world.bases[self.base]
        for step in range(self.steps):
            before=self.raster.at(positions)
            factor=np.where((before&8)!=0,1-self.world.settings['RecipeMapManagerIndicatorSettings']['indicatorInSwampPathDeletion'],1)
            factor=np.where(self.crystal,1,factor)
            delta=self.deltas[:,step]*factor[:,None]
            positions+=delta
            length=np.linalg.norm(delta,axis=1)
            flags=self.raster.at(positions)
            damage=np.where((flags&1)!=0,-.4000000059604645,np.where((flags&2)!=0,-.10000000149011612,0))*length
            heal=np.where((flags&4)!=0,length,0)
            safe=(flags&7)==0
            regeneration=np.where(safe,base['regeneration_coefficient']*length,0)
            hp=np.minimum(1,hp+damage+heal+regeneration)
            if base['instant_regeneration']:hp=np.where(safe,1,hp)
            # Crystal passage differs from ordinary damage; require exact replay.
            hp=np.where(self.crystal,health,hp)
            minimum=np.minimum(minimum,hp)
            if goal is not None:
                # Final ordinary ingredients can be stopped before their end.
                # Crystal endpoints remain the only coarse teleport proposals.
                reachable=(minimum>.06)&(~self.crystal if step<self.steps-1 else True)
                near=np.minimum(near,np.where(reachable,np.linalg.norm(positions-goal,axis=1),np.inf))
        size=base['map_size']
        valid=(minimum>.06)&(abs(positions[:,0])<size['x']/2-1)&(abs(positions[:,1])<size['y']/2-1)
        return (positions,hp,valid,near) if goal is not None else (positions,hp,valid)

    def search(self,target,objective,limit=1200,alternatives=8,upper_bound=None,prefix_operations=None):
        goal=np.array(xy(target['Position']))
        serial=0
        # Quantization and weighted priorities prune aggressively: upper bounds only.
        prefix_operations=list(prefix_operations or [])
        start,_=self.replay(prefix_operations)
        if start.pending or start.effects or start.heat>1e-8:
            raise ValueError('Cold macro continuation requires no pending path, effects, or heat')
        heap=[(0,serial,start.position,start.health,(),0.)]
        seen={}
        found=[]
        partial_found=[]
        prefix_survival={}
        def live_prefix(candidate):
            prefix=candidate[:-1]
            if prefix not in prefix_survival:
                try:
                    # operations(candidate) keeps every prefix stroke intermediate.
                    self.replay(prefix_operations+self.operations(candidate)[:2*len(prefix)])
                    prefix_survival[prefix]=True
                except PotionFailed:prefix_survival[prefix]=False
            return prefix_survival[prefix]
        expanded=0
        minimum_price=min(self.cost)
        while heap and expanded<limit and len(found)<alternatives:
            priority,_,position,health,route,cost=heapq.heappop(heap)
            key=(round(position[0]*3),round(position[1]*3),round(health*5))
            label=(len(route),cost) if objective=='P1' else (cost,len(route))
            if key in seen and seen[key]<=label:continue
            seen[key]=label;expanded+=1
            if route and np.linalg.norm(np.array(position)-goal)<1.7 and live_prefix(route):
                found.append(route)
            if len(route)>=24:continue
            positions,hp,valid,near=self.successors(position,health,goal)
            remaining=np.linalg.norm(positions-goal,axis=1)/self.max_jump
            ranks=(len(route)+1+1.6*remaining if objective=='P1' else cost+self.cost+3.*remaining*self.max_jump*self.cost_per_distance)
            if upper_bound is not None:
                valid&=(len(route)+1<=upper_bound if objective=='P1' else cost+self.cost<=upper_bound+1e-8)
            within_budget=(np.full(len(self.actions),True) if upper_bound is None else
                           (len(route)+1<=upper_bound if objective=='P1' else cost+self.cost<=upper_bound+1e-8))
            if len(partial_found)<alternatives:
                for i in sorted(np.flatnonzero((near<1.7)&within_budget),key=lambda i:(near[i],self.cost[i])):
                    candidate=route+(int(i),)
                    if candidate not in partial_found and live_prefix(candidate):partial_found.append(candidate)
                    if len(partial_found)>=alternatives:break
            for i in np.flatnonzero(valid):
                serial+=1
                next_cost=cost+float(self.cost[i])
                heapq.heappush(heap,(float(ranks[i]),serial,tuple(positions[i]),float(hp[i]),route+(int(i),),next_cost))
        return list(dict.fromkeys(found+partial_found)),expanded

    def operations(self,route,parameters=None):
        operations=[]
        for index,action in enumerate(route):
            name,grind,path=self.actions[action]
            value=grind if parameters is None else parameters[index]
            if index==len(route)-1 and not self.world.ingredients[name]['is_teleportation']:
                operations.extend([dict(kind='add',name=name,grind=1.),dict(kind='stir',fraction=value)])
            else:
                operations.extend([dict(kind='add',name=name,grind=value),dict(kind='stir',fraction=1.)])
        return operations

    def replay(self,operations):
        session=PotionSession(self.world,base=self.base)
        minimum=1.
        for action in operations:
            apply_action(session, action)
            minimum=min(minimum,session.health,*(event['minimum_health'] for event in session.teleports))
        return session,minimum

    def refine(self,route,target,iterations=65,allow_void=False,tail_count=3,initial_controls=None,prefix_operations=None):
        goal=xy(target['Position'])
        # Adjust tail controls using actual engine, keeping prefix fixed.
        initial=[self.actions[i][1] for i in route] if initial_controls is None else list(initial_controls)
        if len(initial)!=len(route) or any(not math.isfinite(v) or not 0<=v<=1 for v in initial):
            raise ValueError('Initial controls must contain one finite fraction per ingredient')
        if initial_controls is None and not self.world.ingredients[self.actions[route[-1]][0]]['is_teleportation']:
            minimum=self.world.ingredients[self.actions[route[-1]][0]]['grinded_path_starts_from']
            initial[-1]=minimum+initial[-1]*(1-minimum)
        tail=route[-min(tail_count,len(route)):]
        prefix_operations=list(prefix_operations or [])
        prefix_ops=prefix_operations+self.operations(route,initial)[:2*(len(route)-len(tail))]
        try:prefix,prefix_min=self.replay(prefix_ops)
        except PotionFailed:return None
        def tail_operations(values):
            if not allow_void:return self.operations(tail,values)
            actions=[]
            for index,(choice,value) in enumerate(zip(tail,values)):
                name,original,path=self.actions[choice]
                item=self.world.ingredients[name]
                if index==len(tail)-1 and not item['is_teleportation']:
                    actions.extend([dict(kind='add',name=name,grind=1.),dict(kind='stir',fraction=value)])
                    continue
                minimum=item['grinded_path_starts_from']
                if value>=minimum:
                    grind=(value-minimum)/(1-minimum) if minimum<1 else 0.
                    actions.append(dict(kind='add',name=name,grind=float(np.clip(grind,0,1))))
                else:
                    actions.append(dict(kind='add',name=name,grind=0.))
                    amount=round((minimum-value)*self.lengths[name]/self.world.salts['Void Salt']['lengthToErase'])
                    if amount:actions.append(dict(kind='salt',salt='void',amount=amount))
                actions.append(dict(kind='stir',fraction=1.))
            return actions
        cache={}
        def evaluate(values):
            values=tuple(round(float(np.clip(v,0,1)),8) for v in values)
            if values in cache:return cache[values]
            session=copy.copy(prefix)
            # Mutable state copied independently; world data shared.
            for key,value in prefix.__dict__.items():
                if key!='world':setattr(session,key,copy.deepcopy(value))
            tail_ops=tail_operations(values[:-1])
            if values[-1]>1e-8:tail_ops.append(dict(kind='pour',seconds=values[-1]*10,strength=1.))
            try:
                for action in tail_ops:
                    apply_action(session, action)
                score=distance(session.position,goal)
            except PotionFailed:score=100+distance(session.position,goal)
            cache[values]=(score,session,values)
            return cache[values]
        x=np.array(initial[-len(tail):]+[0.])
        if allow_void:
            for index,choice in enumerate(tail):
                name=self.actions[choice][0]
                if index==len(tail)-1 and not self.world.ingredients[name]['is_teleportation']:continue
                minimum=self.world.ingredients[name]['grinded_path_starts_from']
                x[index]=minimum+x[index]*(1-minimum)
        simplex=[x]+[np.clip(x+np.eye(len(x))[i]*(-.12 if x[i]>.8 else .12),0,1) for i in range(len(x))]
        for iteration in range(iterations):
            simplex.sort(key=lambda p:evaluate(p)[0])
            if evaluate(simplex[0])[0]<.025:break
            centroid=np.mean(simplex[:-1],axis=0)
            reflected=np.clip(centroid+(centroid-simplex[-1]),0,1)
            if evaluate(reflected)[0]<evaluate(simplex[0])[0]:
                expanded=np.clip(centroid+2*(reflected-centroid),0,1)
                simplex[-1]=expanded if evaluate(expanded)[0]<evaluate(reflected)[0] else reflected
            elif evaluate(reflected)[0]<evaluate(simplex[-2])[0]:simplex[-1]=reflected
            else:
                contracted=np.clip(centroid+.5*(simplex[-1]-centroid),0,1)
                if evaluate(contracted)[0]<evaluate(simplex[-1])[0]:simplex[-1]=contracted
                else:simplex=[simplex[0]]+[simplex[0]+.5*(p-simplex[0]) for p in simplex[1:]]
        best=min(cache.values(),key=lambda result:result[0])
        # Piecewise-smooth local correction: finite-difference Jacobian and
        # bounded damped least squares. Collision switches remain nonsmooth,
        # so accept only actual engine improvements and keep all cache points.
        current=np.array(best[2])
        for _ in range(24):
            value,session,point=evaluate(current)
            if value<.025 or value>=100:break
            residual=np.array(session.position)-np.array(goal)
            columns=[]
            for index in range(len(current)):
                trial=current.copy()
                step=.002 if current[index]<.998 else -.002
                trial[index]=np.clip(trial[index]+step,0,1)
                actual=trial[index]-current[index]
                candidate=evaluate(trial)
                columns.append((np.array(candidate[1].position)-np.array(session.position))/actual if actual and candidate[0]<100 else np.zeros(2))
            jacobian=np.array(columns).T
            delta=np.linalg.lstsq(jacobian,-residual,rcond=1e-7)[0]
            improved=False
            for factor in (1,.5,.25,.125,.0625):
                trial=np.clip(current+factor*delta,0,1)
                if evaluate(trial)[0]<value-1e-7:
                    current=trial;improved=True;break
            if not improved:break
        best=min(cache.values(),key=lambda result:result[0])
        if best[0]>1.5 or best[1].failed_reason:return None
        controls=initial[:-len(tail)]+list(best[2][:-1])
        operations=prefix_ops+tail_operations(best[2][:-1]) if allow_void else prefix_operations+self.operations(route,controls)
        if best[2][-1]>1e-8:operations.append(dict(kind='pour',seconds=best[2][-1]*10,strength=1.))
        try:session,minimum=self.replay(operations)
        except PotionFailed:return None
        return operations,session,minimum,len(cache)


def capture(planner,operations,target,tier):
    try:
        session,minimum=planner.replay(operations)
        before=session.nearest_effect()
        if before is None or before['name']!=target['name'] or before['tier']!=tier:return None
        if minimum<=.01:return None
        # Repeated short legal downstrokes, stopped as soon as one effect is collected.
        for _ in range(40):
            pump=dict(kind='pump',angle=60.,seconds=.5)
            operations=operations+[pump]
            session.pump_bellows(60,.5)
            if session.effects:break
        if session.effects!=[(target['name'],tier)] or session.failed_reason:return None
        costs=resource_cost(dict(session.ingredients_used),dict(session.salts_used),
                            {name:item['price'] for name,item in planner.world.ingredients.items()})
        return {'base':planner.base,'operations':operations,'ingredients':dict(session.ingredients_used),
                'ingredient_count':sum(session.ingredients_used.values()),
                'ingredient_value':sum(planner.world.ingredients[name]['price']*n for name,n in session.ingredients_used.items()),
                'salts':dict(session.salts_used),'costs':costs,'health':session.health,'minimum_action_endpoint_health':minimum,
                'position':list(session.position),'rotation':session.rotation,
                'effects':[list(e) for e in session.effects],
                'alignment_before_heating':before,'status':'engine_verified_candidate',
                'optimality':'当前最好可行解；未证明全局最优',
                'replay_verified':True,'game_verified':False}
    except (PotionFailed,ValueError):return None


def tier_variants(planner,operations,target,allowed_tiers=None,scan_prefixes=True):
    """Re-evaluate exact grades, never substitute a higher grade for a lower one."""
    results={}
    wanted={1,2,3} if allowed_tiers is None else set(allowed_tiers)
    if not wanted.issubset({1,2,3}):raise ValueError('Invalid requested tiers')
    if not wanted:return results
    for tier in (3,2,1):
        if tier not in wanted:continue
        result=capture(planner,operations,target,tier)
        if result:results[tier]=result
    # Preserve the candidate's ingredients while moving inward through the
    # smaller grade bands. Short separate pours are explicit replay gestures.
    if wanted-set(results):
        try:
            session,_=planner.replay(operations)
            adjusted=list(operations)
            for _ in range(40):
                session.pour(.025,1)
                adjusted.append(dict(kind='pour',seconds=.025,strength=1.))
                score=session.nearest_effect()
                if score and score['name']==target['name'] and score['tier'] in wanted and score['tier'] not in results:
                    result=capture(planner,adjusted,target,score['tier'])
                    if result:results[score['tier']]=result
                if wanted.issubset(results):break
        except PotionFailed:pass
    if wanted.issubset(results):return results
    if not scan_prefixes:return results
    # A fully traversed intermediate prefix can be dropped: fewer ingredients
    # may suffice for a lower grade. Scan every ordinary final stroke.
    for end,op in enumerate(operations):
        if op['kind']!='stir':continue
        ingredient=operations[end-1]
        if ingredient['kind']!='add':continue
        if planner.world.ingredients[ingredient['name']]['is_teleportation']:continue
        prefix=operations[:end]
        try:session,_=planner.replay(prefix)
        except PotionFailed:continue
        nearest=xy(target['Position'])
        # Engine queries on a single last stroke, split by fine arc-length samples.
        total=session.remaining_length
        previous=0.
        for fraction in np.linspace(.02,1,50):
            try:session.stir((float(fraction)-previous)/(1-previous))
            except PotionFailed:break
            previous=float(fraction)
            score=session.nearest_effect()
            if score and score['name']==target['name'] and score['tier'] in wanted:
                candidate_ops=prefix+[dict(kind='stir',fraction=float(fraction))]
                result=capture(planner,candidate_ops,target,score['tier'])
                if result and (score['tier'] not in results or result['ingredient_count']<results[score['tier']]['ingredient_count']):
                    results[score['tier']]=result
            if distance(session.position,nearest)>total+5:break
    return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--objectives',nargs='+',choices=['P1','P2'],default=['P1','P2'])
    parser.add_argument('--effects',nargs='*')
    parser.add_argument('--nodes',type=int,default=800)
    parser.add_argument('--alternatives',type=int,default=5)
    parser.add_argument('--output',default='result/search/no_salt_candidates.json')
    parser.add_argument('--missing-only',action='store_true')
    parser.add_argument('--refine-iterations',type=int,default=65)
    parser.add_argument('--tail-count',type=int,default=3)
    parser.add_argument('--bases',nargs='+',choices=['Water','Oil','Wine'])
    args=parser.parse_args()
    from optimizer.provenance import capture_run_snapshot
    snapshot=capture_run_snapshot()
    world=BrewWorld()
    ui=json.loads((ROOT/'data/ui_manifest.json').read_text(encoding='utf-8'))
    output=(ROOT/args.output).resolve()
    if not output.is_relative_to(ROOT/'result/search'):raise ValueError('Search output must stay in result/search')
    output.parent.mkdir(parents=True,exist_ok=True)
    saved=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {'records':{},'runs':[]}
    delivered=[]
    manifest_path=ROOT/'result/manifest.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        hashes=manifest.get('dataFingerprint',{}).get('files',{})
        physical=[*sorted((ROOT/'data').glob('*.json')),ROOT/'engine/brew.py',ROOT/'playground/serve.py']
        compatible=all(hashes.get(str(p.relative_to(ROOT)).replace('\\','/'))==hashlib.sha256(p.read_bytes()).hexdigest() for p in physical)
        if compatible:
            delivered=[{**row,'ingredient_count':row['costs']['ingredient_count'],'ingredient_value':row['costs']['ingredient_value']}
                       for row in manifest['records'] if row['mode']=='no_salt' and 'operations' in row]
    planners={}
    started=time.time()
    names=list(ui['effects'])
    # Prioritize the two catalysts for future garden optimization.
    names.sort(key=lambda name:(name not in ('WildGrowth','StoneSkin'),name))
    for objective in args.objectives:
        for name in names:
            if args.effects and name not in args.effects:continue
            if args.missing_only:
                existing=json.loads((ROOT/'result/manifest.json').read_text(encoding='utf-8'))
                if all(any(r['objective']==objective and r['mode']=='no_salt' and r['effect']==name and r['tier']==tier
                           and 'operations' in r for r in existing['records']) for tier in (1,2,3)):continue
            options=[(base,effect) for base,data in world.bases.items() for effect in data['effects']
                     if effect['name']==name and (not args.bases or base in args.bases)]
            # Rotated effects can still yield I/II without salt, and slight
            # misalignment may permit III. All legal bases must be searched.
            options.sort(key=lambda item:distance(xy(item[1]['Position']),(0,0)))
            candidates={}
            nodes=0
            for base,target in options:
                if base not in planners:
                    print('Build heuristic raster:',base,flush=True)
                    planners[base]=Planner(world,base)
                planner=planners[base]
                upper=no_salt_search_bound([*saved['records'].values(),*delivered],name,objective)
                routes,expanded=planner.search(target,objective,args.nodes,args.alternatives,upper_bound=upper)
                nodes+=expanded
                for route in routes:
                    refined=planner.refine(route,target,iterations=args.refine_iterations,tail_count=args.tail_count)
                    if refined is None:continue
                    operations,session,minimum,evaluations=refined
                    variants=tier_variants(planner,operations,target)
                    for tier,result in variants.items():
                        key=(result['ingredient_count'],result['ingredient_value'],len(result['operations'])) if objective=='P1' else (result['ingredient_value'],result['ingredient_count'],len(result['operations']))
                        if tier not in candidates or key<candidates[tier][0]:candidates[tier]=(key,result)
            for tier in (1,2,3):
                if tier in candidates:
                    result=candidates[tier][1]
                    for shared_objective in ('P1','P2'):
                        record_key=f'{shared_objective}:{name}:{tier}'
                        previous=saved['records'].get(record_key)
                        rank=lambda r:(r['ingredient_count'],r['ingredient_value']) if shared_objective=='P1' else (r['ingredient_value'],r['ingredient_count'])
                        if previous is None or rank(result)<rank(previous):
                            saved['records'][record_key]={**result,'objective':shared_objective,'effect':name,'tier':tier}
            saved['runs'].append(dict(objective=objective,effect=name,nodes=nodes,node_limit=args.nodes,
                                      snapshot=snapshot,parameters=vars(args),
                                      alternatives=args.alternatives,elapsed_seconds=time.time()-started,
                                      solver_sha256=SOLVER_SHA256,
                                      refine_iterations=args.refine_iterations,tail_count=args.tail_count,
                                      bases=args.bases or list(world.bases),
                                      scope='cold macro routes; endpoint and intermediate stop proposals; exact prefix survival'))
            temporary=output.with_suffix('.tmp')
            temporary.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(output)
            print(objective,name,{tier:(r[1]['ingredient_count'],round(r[1]['ingredient_value'],2)) for tier,r in candidates.items()},'nodes',nodes,flush=True)


if __name__=='__main__':main()
