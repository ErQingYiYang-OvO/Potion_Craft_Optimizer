"""Completed crystal transit endpoint enclosure, excluding animated rotation.

Does not establish survival, duration, fade contacts or actual Unity timing.
"""
from optimizer.intervals import (Interval,CarriedPathBox,distance_box,
                                 float_sum_box,lerp_box,UnresolvedArithmetic)


def crystal_endpoint_enclosure(path,point_count):
    if not 1<=point_count<=len(path.pending):raise ValueError('Invalid crystal section count')
    points=(path.position,)+path.pending[:point_count]
    lengths=[distance_box(a,b) for a,b in zip(points,points[1:])]
    total=float_sum_box(lengths);epsilon=Interval(1e-10)
    stopping=total-epsilon
    traversed=Interval(max(0,stopping.lo),max(0,total.hi))
    terminal=[];unresolved=[];start=Interval(0)
    tail=path.pending[point_count:]
    if total.lo<=epsilon.hi:terminal.append(CarriedPathBox(path.position,tail))
    for index,(a,b,length) in enumerate(zip(points,points[1:],lengths)):
        boundary=start+length
        lower=max(traversed.lo,start.lo)
        upper=traversed.hi if index==len(lengths)-1 else min(traversed.hi,boundary.hi)
        if lower<=upper:
            try:
                if length.lo==length.hi==0:parameter=Interval(1)
                else:parameter=(Interval(lower,upper)-start)/length
                # No clamping: compensated total and sequential segment-start
                # summation can put the last interpolation slightly past t=1.
                position=lerp_box(a,b,parameter)
                terminal.append(CarriedPathBox(position,tail))
            except UnresolvedArithmetic as error:
                unresolved.append({'segment':index,'reason':str(error)})
        start=boundary
    return {'scope':'endpoint conditional on completed crystal transit with no rotation animation; remaining tail fixed',
            'terminal':terminal,'unresolved':unresolved,'endpointEnclosureComplete':not unresolved,
            'survivalProved':False,'timingProved':False,
            'brewingRecipeExcluded':False,'globalOptimalityProved':False}


if __name__=='__main__':
    import hashlib,json,sys
    from pathlib import Path
    from engine.brew import BrewWorld,PotionSession
    from optimizer.ingredient_intervals import ingredient_path_enclosure
    from optimizer.crystal_timing import cold_crystal_timing
    from optimizer.crystal_damage import fade_damage_enclosure
    from optimizer.crystal_survival import cold_crystal_survival
    from optimizer.provenance import capture_run_snapshot
    root=Path(__file__).resolve().parents[1];world=BrewWorld();rows=[]
    snapshot=capture_run_snapshot(root)
    for name,item in sorted(world.ingredients.items()):
        if not item['is_teleportation']:continue
        generated=ingredient_path_enclosure(world,name,Interval(0,1),4096,allow_crystal=True)
        matches=0
        for grind in (0,.25,.5,.75,1):
            actual=world.ingredient_path(name,grind,graphics=True)
            matches+=any(len(path)==len(actual) and all(bound.contains(value)
                for box,point in zip(path,actual) for bound,value in zip(box,point))
                for path in generated['paths'])
        endpoints=[]
        for grind in (0,.5,1):
            potion=PotionSession(world);potion.add(name,grind);count=len(potion.pending)
            potion.add('Waterbloom',1)
            path_state=CarriedPathBox(potion.position,tuple(potion.pending))
            result=crystal_endpoint_enclosure(path_state,count)
            timing=None;fade_out=None;fade_in=[];phase_unresolved=[]
            try:
                timing=cold_crystal_timing(world,path_state,count)
                fade_out=fade_damage_enclosure(world,'Water',path_state.position,timing['fadeOutProgress'])
                for endpoint in result['terminal']:
                    fade_in.append(fade_damage_enclosure(world,'Water',endpoint.position,
                                                        timing['fadeInProgress'],fade_out=False))
            except UnresolvedArithmetic as error:phase_unresolved.append(str(error))
            endpoints.append({'grind':grind,'complete':result['endpointEnclosureComplete'],
                              'positionBoxes':[[[str(v.lo),str(v.hi)] for v in path.position]
                                               for path in result['terminal']],
                              'tailCount':len(potion.pending)-count,'unresolved':result['unresolved'],
                              'timing':timing,'fadeOutDamage':fade_out,'fadeInDamage':fade_in,
                              'phaseUnresolved':phase_unresolved,
                              'survival':cold_crystal_survival(world,'Water',path_state,count)})
        rows.append({'ingredient':name,'grindDomain':[0,1],
                     'pathEnclosureComplete':generated['pathEnclosureComplete'],
                     'pathSampleMatches':int(matches),'pathSampleCount':5,
                     'pathUnresolved':generated['unresolved'],'endpoints':endpoints})
    record={'scope':'nine crystal grind-path enclosures and conditional completed-transit endpoints',
            'crystals':rows,'allPathEnclosuresComplete':all(row['pathEnclosureComplete'] for row in rows),
            'sampleMatches':sum(row['pathSampleMatches'] for row in rows),
            'sampleCount':5*len(rows),'endpointCases':sum(len(row['endpoints']) for row in rows),
            'allEndpointEnclosuresComplete':all(case['complete'] for row in rows for case in row['endpoints']),
            'allColdPhaseEnclosuresComplete':all(not case['phaseUnresolved'] for row in rows for case in row['endpoints']),
            'survivalProvedCasesUnderModel':sum(case['survival']['survivalProvedUnderModel']
                                               for row in rows for case in row['endpoints']),
            'sourceSnapshot':snapshot,
            'runtime':sys.version,'survivalProved':False,'timingProved':False,
            'brewingRecipeExcluded':False,'globalOptimalityProved':False}
    files=list((root/'data').glob('*.json'))+list((root/'engine').glob('*.py'))
    files+=[root/'optimizer'/name for name in ('intervals.py','ingredient_intervals.py','crystal_intervals.py',
                                            'crystal_timing.py','crystal_damage.py','crystal_survival.py','cold_stir.py','ordinary_stir.py')]
    record['inputSha256']={str(path.relative_to(root)).replace('\\','/'):
                          hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
    path=root/'result/search/crystal_interval_certificate.json';temporary=path.with_suffix('.tmp')
    def serialize(value):
        if isinstance(value,Interval):return [str(value.lo),str(value.hi)]
        raise TypeError(type(value).__name__)
    temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2,default=serialize),encoding='utf-8');temporary.replace(path)
    print(json.dumps({k:v for k,v in record.items() if k not in ('crystals','inputSha256')},ensure_ascii=False))
