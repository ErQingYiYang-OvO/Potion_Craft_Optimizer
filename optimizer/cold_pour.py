"""Cold, zero-angle pouring with fixed strength and interval duration.

Current engine only. Unknown contacts, zero-crossing distance, and budgets
remain unresolved. Does not prove arbitrary recipe reachability.
"""
from dataclasses import dataclass
from engine.brew import curve_value
from optimizer.intervals import (Interval,CarriedPathBox,as_interval,distance_box,
                                 lerp_box,hull,roundoff_radius,UnresolvedArithmetic)
from optimizer.cold_stir import cold_stir_enclosure,clean_region_reason


@dataclass(frozen=True)
class PourNode:
    path: object
    elapsed: Interval


def pouring_speed_box(world,strength,elapsed):
    settings=world.settings['RecipeMapManagerPouringSettings']
    base=curve_value(settings['standardSpeedByPouring'],strength)
    speed=Interval(base)
    if strength>1-settings['thresholdForResettingSpeed']:
        growing=elapsed-settings['timeBeforePouringSpeedWillStartGrow']
        if growing.hi>=0:
            rate=settings['speedIncreasingRate']
            increased=base+Interval(max(0,growing.lo),growing.hi)*rate
            cap=settings['maxSpeedByPouring']
            speed=Interval(min(increased.lo,cap),min(increased.hi,cap))
            if growing.lo<0:speed=hull(speed,base)
    if speed.lo<0:raise UnresolvedArithmetic('Negative pouring speed')
    return speed


def pour_path_enclosure(world,base,path,duration,strength=.5,dt=1/60,node_budget=256):
    """Geometry core; caller must establish cold ordinary state at angle zero."""
    duration=as_interval(duration)
    if duration.lo<0 or duration.hi>120 or not 0<=strength<=1 or dt<=0 or node_budget<1:
        raise ValueError('Invalid pouring domain')
    terminal=[];unresolved=[];processed=0;elapsed=0.;epsilon=Interval(1e-10)
    if strength==0:return {'terminal':[PourNode(path,Interval(0))],'unresolved':[],
                          'processedNodes':0,'loopEnclosureComplete':True}
    def frame(path,step,new_elapsed):
        reason=clean_region_reason(world,base,path.position)
        if reason:raise UnresolvedArithmetic(reason)
        movement=pouring_speed_box(world,strength,new_elapsed)*step
        norm=distance_box(path.position,(0,0))
        if all(coordinate.lo==coordinate.hi==0 for coordinate in path.position) or movement.lo>=norm.hi:
            fraction=Interval(1)
        elif norm.lo<=0:
            raise UnresolvedArithmetic('Pouring distance may cross zero')
        else:
            quotient=movement/norm
            fraction=Interval(min(1,quotient.lo),min(1,quotient.hi))
        if fraction.lo==fraction.hi==1:
            # lerp(a, 0, 1) cancels a with its exact negation in binary64.
            position=(Interval(0),Interval(0))
        elif fraction.lo==fraction.hi==0:
            position=path.position
        else:position=lerp_box(path.position,(0,0),fraction)
        reason=clean_region_reason(world,base,position)
        if reason:raise UnresolvedArithmetic(reason)
        return path.move(position)
    while processed<node_budget:
        processed+=1
        threshold=duration-epsilon
        if elapsed>=threshold.lo:terminal.append(PourNode(path,Interval(elapsed)))
        if elapsed>=threshold.hi:break
        difference=duration-elapsed
        # The final partial frame can have any remaining duration up to dt.
        if difference.lo<=dt:
            step=Interval(max(0,difference.lo),min(dt,difference.hi))
            new_elapsed=Interval(elapsed)+step
            try:
                error=roundoff_radius(difference)+roundoff_radius(new_elapsed)+roundoff_radius(threshold)
                if error>epsilon.lo:raise UnresolvedArithmetic('Final-frame stop comparison not certified')
                terminal.append(PourNode(frame(path,step,new_elapsed),new_elapsed))
            except UnresolvedArithmetic as error:
                unresolved.append((PourNode(path,Interval(elapsed)),str(error)))
        if difference.hi<dt:break
        # Full-frame elapsed is a deterministic binary64 value; duration only
        # affects which of these full frames actually happen. Extra states are
        # a relaxation, never grounds for excluding a real branch.
        new_elapsed=elapsed+dt
        try:path=frame(path,Interval(dt),Interval(new_elapsed))
        except UnresolvedArithmetic as error:
            unresolved.append((PourNode(path,Interval(elapsed)),str(error)));break
        elapsed=new_elapsed
    else:unresolved.append((PourNode(path,Interval(elapsed)),'node budget exhausted'))
    return {'terminal':terminal,'unresolved':unresolved,'processedNodes':processed,
            'loopEnclosureComplete':not unresolved}


def cold_pour_enclosure(session,duration,strength=.5,dt=1/60,node_budget=256):
    scope='fixed cold ordinary state at zero rotation; fixed strength, interval pouring duration'
    if session.rotation!=0:
        return {'scope':scope,'supported':False,'reasons':['nonzero rotation'],
                'brewingRecipeExcluded':False,'globalOptimalityProved':False}
    prerequisite=cold_stir_enclosure(session,0,node_budget=1)
    if not prerequisite['supported']:
        return {**prerequisite,'scope':scope}
    if not prerequisite['loopEnclosureComplete']:
        return {'scope':scope,'supported':False,'reasons':[reason for _,reason in prerequisite['unresolved']],
                'brewingRecipeExcluded':False,'globalOptimalityProved':False}
    cooling=curve_value(session.world.pouring_controls['heatCoolingDependence'],strength)
    if cooling<0:
        return {'scope':scope,'supported':False,'reasons':['pour cooling can increase zero heat'],
                'brewingRecipeExcluded':False,'globalOptimalityProved':False}
    result=pour_path_enclosure(session.world,session.base,
                              CarriedPathBox(session.position,tuple(session.pending)),
                              duration,strength,dt,node_budget)
    return {**result,'scope':scope,'supported':True,
            'brewingRecipeExcluded':False,'globalOptimalityProved':False}


if __name__=='__main__':
    import hashlib,json,sys
    from pathlib import Path
    from engine.brew import BrewWorld,PotionSession
    from optimizer.ordinary_stir import ordinary_stir
    root=Path(__file__).resolve().parents[1]
    world=BrewWorld();source=PotionSession(world)
    source.add('Firebell',1);source.stir(.06)
    poured=cold_pour_enclosure(source,Interval(.005,.015),strength=.5)
    terminal=[];unresolved=[];processed=poured.get('processedNodes',0)
    if poured.get('supported'):
        unresolved.extend(poured['unresolved'])
        for node in poured['terminal']:
            result=ordinary_stir(node.path,.001,world.spacing,
                world.settings['RecipeMapManagerIndicatorSettings']['indicatorSpeed'],
                node_budget=100,region_guard=lambda box:clean_region_reason(world,'Water',box))
            processed+=result['processedNodes'];unresolved.extend(result['unresolved'])
            terminal.extend((child.path,node.elapsed+child.elapsed) for child in result['terminal'])
    bounds=lambda value:[str(value.lo),str(value.hi)]
    record={'scope':'fixed Water Firebell path: partial stir, interval cold pour, then fixed cold stir',
            'parameters':{'base':'Water','ingredient':'Firebell','grind':1.,'preStir':.06,
                          'pourSeconds':[.005,.015],'pourStrength':.5,'dt':1/60,'postStir':.001},
            'motionEnclosureComplete':bool(poured.get('supported')) and not unresolved,
            'processedNodes':processed,'unsupportedReasons':poured.get('reasons',[]),
            'terminal':[{'position':[bounds(v) for v in path.position],
                         'pendingCount':len(path.pending),'elapsedFromPourStart':bounds(elapsed)}
                        for path,elapsed in terminal],
            'unresolved':[{'position':[bounds(v) for v in node.path.position],
                           'pendingCount':len(node.path.pending),'reason':reason}
                          for node,reason in unresolved],
            'brewingRecipeExcluded':False,'globalOptimalityProved':False,
            'runtime':sys.version}
    files=list((root/'data').glob('*.json'))+list((root/'engine').glob('*.py'))
    files+=[root/'optimizer'/name for name in ('intervals.py','ordinary_stir.py','cold_stir.py','cold_pour.py')]
    record['inputSha256']={str(path.relative_to(root)).replace('\\','/'):
                          hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
    path=root/'result/search/cold_pour_stir_certificate.json';temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
    print(json.dumps({k:v for k,v in record.items() if k not in ('inputSha256','terminal','unresolved')},ensure_ascii=False))
