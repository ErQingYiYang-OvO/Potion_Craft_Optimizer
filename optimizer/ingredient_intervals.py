"""Continuous grinding on a fixed engine-generated sampled ingredient path.

The sampled source points are deterministic engine inputs, not an enclosure of
Unity path generation. Cut-point arithmetic and all possible topologies are
enclosed; unsupported budgets remain unresolved.
"""
import math
from engine.brew import sampled_path,distance
from optimizer.intervals import Interval,as_interval,point_box,lerp_box


def ingredient_path_enclosure(world,name,grind,branch_budget=256,allow_crystal=False):
    grind=as_interval(grind)
    if grind.lo<0 or grind.hi>1 or branch_budget<1:raise ValueError('Invalid grinding domain')
    item=world.ingredients[name]
    if item['is_teleportation'] and not allow_crystal:
        return {'supported':False,'reasons':['crystal path generation unsupported'],
                'paths':[],'unresolved':[],'pathEnclosureComplete':False}
    spacing=(world.settings['RecipeMapManagerPathSettings']['ingredientPathSpacingGraphics']
             if item['is_teleportation'] else world.spacing)
    points=sampled_path(item['bezier_path'],spacing)
    start=item['grinded_path_starts_from']
    fraction=start+grind*(1-start)
    paths=[];unresolved=[];branches=0
    boxed=tuple(point_box(point) for point in points)
    if fraction.hi>=1:paths.append(boxed)
    if fraction.lo>=1:
        return {'supported':True,'paths':paths,'unresolved':[],
                'pathEnclosureComplete':True,'processedSegments':0}
    fraction=Interval(fraction.lo,min(fraction.hi,math.nextafter(1.,-math.inf)))
    lengths=[distance(a,b) for a,b in zip(points,points[1:])]
    # Points are fixed; these scalar operations reproduce this runtime's exact
    # sum and segment values. Only the grinding/cut parameter is uncertain.
    target=sum(lengths)*fraction
    traversed=0.;lower=target.lo
    for index,(a,b,segment) in enumerate(zip(points,points[1:],lengths)):
        if branches>=branch_budget:
            unresolved.append({'segment':index,'target':[str(lower),str(target.hi)],
                               'reason':'branch budget exhausted'});break
        branches+=1;boundary=traversed+segment
        upper=min(target.hi,boundary)
        if lower<=upper:
            cut_target=Interval(lower,upper)
            parameter=(cut_target-traversed)/segment if segment else Interval(0)
            # cut_path does not clamp its interpolation parameter; rounding
            # near traversed+segment can make the endpoint slightly overshoot.
            paths.append(boxed[:index+1]+(lerp_box(a,b,parameter),))
        if target.hi<=boundary:break
        lower=max(lower,as_interval(math.nextafter(boundary,math.inf)).lo)
        traversed=boundary
    else:
        if lower<=target.hi:paths.append(boxed)
    return {'supported':True,'paths':paths,'unresolved':unresolved,
            'pathEnclosureComplete':not unresolved,'processedSegments':branches,
            'isTeleportation':bool(item['is_teleportation']),
            'scope':'fixed engine-sampled ingredient; binary64 grinding/cut path; no traversal semantics'}


if __name__=='__main__':
    import hashlib,json,sys
    from pathlib import Path
    from engine.brew import BrewWorld
    from optimizer.intervals import CarriedPathBox
    from optimizer.ordinary_stir import ordinary_stir
    from optimizer.cold_stir import clean_region_reason
    root=Path(__file__).resolve().parents[1];world=BrewWorld()
    if '--audit-all' in sys.argv:
        rows=[];samples=(0.,.01,.25,.5,.75,.99,1.)
        for name,item in sorted(world.ingredients.items()):
            result=ingredient_path_enclosure(world,name,Interval(0,1),branch_budget=4096)
            row={'ingredient':name,'supported':result['supported'],
                 'pathEnclosureComplete':result['pathEnclosureComplete'],
                 'pathBranches':len(result['paths']),'sampleMatches':0,'failedGrinds':[],
                 'unresolved':result['unresolved'],'reasons':result.get('reasons',[])}
            if result['supported']:
                by_count={}
                for path in result['paths']:by_count.setdefault(len(path),[]).append(path)
                for grind in samples:
                    actual=world.ingredient_path(name,grind)
                    matched=any(all(bound.contains(value) for box,point in zip(path,actual)
                        for bound,value in zip(box,point)) for path in by_count.get(len(actual),[]))
                    if matched:row['sampleMatches']+=1
                    else:row['failedGrinds'].append(grind)
            rows.append(row)
        supported=[row for row in rows if row['supported']]
        record={'scope':'all ordinary engine-sampled paths, grind domain [0,1]; sample checks are supplemental',
                'ingredients':rows,'ordinaryCount':len(supported),
                'unsupportedCount':len(rows)-len(supported),
                'allOrdinaryEnclosuresComplete':all(row['pathEnclosureComplete'] for row in supported),
                'failedSampleCount':sum(len(row['failedGrinds']) for row in supported),
                'sampleCount':len(samples)*len(supported),'runtime':sys.version,
                'brewingRecipeExcluded':False,'globalOptimalityProved':False}
        files=list((root/'data').glob('*.json'))+list((root/'engine').glob('*.py'))
        files+=[root/'optimizer'/name for name in ('intervals.py','ingredient_intervals.py')]
        record['inputSha256']={str(path.relative_to(root)).replace('\\','/'):
                              hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
        path=root/'result/search/ingredient_interval_audit.json';temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
        print(json.dumps({k:v for k,v in record.items() if k not in ('ingredients','inputSha256')},ensure_ascii=False))
        raise SystemExit(1 if record['failedSampleCount'] or not record['allOrdinaryEnclosuresComplete'] else 0)
    paths=ingredient_path_enclosure(world,'Firebell',Interval(.49,.51))
    terminal=[];unresolved=list(paths['unresolved']);processed=0
    for local in paths['paths']:
        result=ordinary_stir(CarriedPathBox((0,0)).append(local),Interval(.05,.06),world.spacing,
            world.settings['RecipeMapManagerIndicatorSettings']['indicatorSpeed'],node_budget=100,
            region_guard=lambda box:clean_region_reason(world,'Water',box))
        processed+=result['processedNodes'];terminal.extend(result['terminal'])
        unresolved.extend({'position':[[str(v.lo),str(v.hi)] for v in node.path.position],
                           'pendingCount':len(node.path.pending),'reason':reason}
                          for node,reason in result['unresolved'])
    record={'scope':'Water ordinary Firebell: engine-sampled local path, interval grind and interval cold stir',
            'parameters':{'ingredient':'Firebell','base':'Water','grind':[.49,.51],'stir':[.05,.06]},
            'motionEnclosureComplete':paths['supported'] and paths['pathEnclosureComplete'] and not unresolved,
            'sourcePathBranches':len(paths['paths']),'processedStirNodes':processed,
            'terminal':[{'position':[[str(v.lo),str(v.hi)] for v in node.path.position],
                         'pendingCount':len(node.path.pending)} for node in terminal],
            'unresolved':unresolved,'brewingRecipeExcluded':False,'globalOptimalityProved':False,
            'runtime':sys.version}
    files=list((root/'data').glob('*.json'))+list((root/'engine').glob('*.py'))
    files+=[root/'optimizer'/name for name in ('intervals.py','ordinary_stir.py','cold_stir.py','ingredient_intervals.py')]
    record['inputSha256']={str(path.relative_to(root)).replace('\\','/'):
                          hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
    path=root/'result/search/grind_stir_certificate.json';temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
    print(json.dumps({k:v for k,v in record.items() if k not in ('inputSha256','terminal','unresolved')},ensure_ascii=False))
