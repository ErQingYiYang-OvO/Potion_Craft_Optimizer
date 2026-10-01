"""Cold crystal model survival from phase damage and map containment.

No active rotation, no external input during transit, fixed cold timing.
This is an engine-model certificate, not a Unity validation.
"""
from optimizer.intervals import (Interval,as_interval,hull,distance_box,
                                 float_sum_box,lerp_box,UnresolvedArithmetic)
from optimizer.intervals import roundoff_radius
from optimizer.crystal_intervals import crystal_endpoint_enclosure
from optimizer.crystal_timing import cold_crystal_timing
from optimizer.crystal_damage import fade_damage_enclosure


def stationary_fade_health(base,profile,health):
    health=as_interval(health);minimum=health
    relevant={'strong_danger','weak_danger','heal'}
    for frame in profile['frames']:
        possible=set(frame['possibleZones']);guaranteed=set(frame['guaranteedZones'])
        damaged=health-frame['extraDamage']
        if base['instant_regeneration']:
            if not possible.intersection(relevant):damaged=Interval(1)
            elif not guaranteed.intersection(relevant):damaged=hull(damaged,1)
        health=Interval(min(1,max(0,damaged.lo)),min(1,max(0,damaged.hi)))
        minimum=Interval(min(minimum.lo,health.lo),min(minimum.hi,health.hi))
    return health,minimum


def map_contains_box(world,base,box):
    size=world.bases[base]['map_size']
    return all(-size[key]/2<=box[axis].lo and box[axis].hi<size[key]/2
               for axis,key in enumerate(('x','y')))


def transit_map_enclosure(world,base,path,count):
    points=(path.position,)+path.pending[:count]
    lengths=[distance_box(a,b) for a,b in zip(points,points[1:])]
    total=float_sum_box(lengths);start=Interval(0)
    if not map_contains_box(world,base,path.position):return False
    for index,(a,b,length) in enumerate(zip(points,points[1:],lengths)):
        boundary=start+length
        # All interpolation positions queried by _health_step: the current
        # segment's sequential boundary limits traversed except on the last.
        limit=total.hi if index==len(lengths)-1 else min(total.hi,boundary.hi)
        if start.lo<=limit:
            parameter=(Interval(start.lo,limit)-start)/length if length.hi else Interval(1)
            if not map_contains_box(world,base,lerp_box(a,b,parameter)):return False
        start=boundary
    return True


def wine_arrival_lower(world,base,start,end,health,frames):
    """Triangle-inequality regeneration bound with explicit rounding losses.

    For successful transit all positions are inside the map rectangle. Sum of
    real step distances is at least start/end distance. Each source distance,
    multiplication and health addition has a bounded binary64 error. Reaching
    health 1 is absorbing under nonnegative regeneration.
    """
    size=world.bases[base]['map_size'];coefficient=world.bases[base]['regeneration_coefficient']
    extent=(Interval(-size['x']/2,size['x']/2),Interval(-size['y']/2,size['y']/2))
    differences=tuple(extent[a]-extent[a] for a in (0,1))
    max_distance=distance_box(extent,extent).hi
    norm_error=sum(roundoff_radius(value) for value in differences)+4*roundoff_radius(Interval(max_distance))
    displacement=max(0,distance_box(start,end).lo-(frames+1)*norm_error)
    increment=Interval(0,max_distance)*coefficient
    arithmetic_error=roundoff_radius(increment)+roundoff_radius(Interval(0,1)+increment)
    gain=coefficient*Interval(displacement)-frames*arithmetic_error
    candidate=health+gain
    return max(health.lo,min(1,candidate.lo))


def cold_crystal_survival(world,base,path,count,health=1.,dt=1/60):
    health=as_interval(health)
    if health.lo<0 or health.hi>1:raise ValueError('Health outside [0,1]')
    unresolved=[];out_health=None;minimum=health;final=[];branch_minima=[]
    try:
        if not transit_map_enclosure(world,base,path,count):
            unresolved.append('map containment not certified')
        endpoints=crystal_endpoint_enclosure(path,count)
        if not endpoints['endpointEnclosureComplete']:unresolved.append('endpoint unresolved')
        timing=cold_crystal_timing(world,path,count,dt)
        out_profile=fade_damage_enclosure(world,base,path.position,timing['fadeOutProgress'])
        out_health,out_min=stationary_fade_health(world.bases[base],out_profile,health)
        minimum=out_min
        if world.bases[base]['instant_regeneration'] and timing['transitFrames'][0]>0:
            arrival=Interval(1)
        elif world.bases[base]['regeneration_coefficient']>=0:
            arrival=Interval(out_health.lo,1)
        else:raise UnresolvedArithmetic('Negative transit regeneration')
        for endpoint in endpoints['terminal']:
            if not map_contains_box(world,base,endpoint.position):unresolved.append('arrival map containment unresolved')
            endpoint_arrival=arrival
            if not world.bases[base]['instant_regeneration']:
                lower=wine_arrival_lower(world,base,path.position,endpoint.position,out_health,timing['transitFrames'][1])
                endpoint_arrival=Interval(lower,1)
            profile=fade_damage_enclosure(world,base,endpoint.position,timing['fadeInProgress'],False)
            end_health,end_min=stationary_fade_health(world.bases[base],profile,endpoint_arrival)
            final.append(end_health)
            branch_minima.append(Interval(min(out_min.lo,end_min.lo),min(out_min.hi,end_min.hi)))
    except UnresolvedArithmetic as error:unresolved.append(str(error))
    if not final:unresolved.append('no completed endpoint health enclosure')
    if branch_minima:minimum=hull(*branch_minima)
    if unresolved:minimum=hull(minimum,Interval(0,health.hi))
    return {'scope':'fixed cold crystal engine model, no rotation/input during transit',
            'survivalProvedUnderModel':not unresolved and minimum.lo>0,
            'minimumHealth':minimum,
            'finalHealthConditionalOnCompletion':hull(*final,Interval(0,1)) if final and unresolved else hull(*final) if final else None,
            'unresolved':unresolved,'actualGameVerified':False,
            'brewingRecipeExcluded':False,'globalOptimalityProved':False}
