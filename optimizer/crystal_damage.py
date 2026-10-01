"""Cold fixed-progress fade contact/extra-damage bounds, not survival proof."""
import math
from engine.brew import curve_value
from optimizer.intervals import Interval,distance_box,float_sum_box,UnresolvedArithmetic
from optimizer.cold_stir import absolute_box,shape_disjoint


def shape_guaranteed_contact(shape,box,radius):
    kind,x,y,*rest=shape
    if kind=='circle':return distance_box(box,(x,y)).hi<=(Interval(rest[0])+radius).lo
    if kind!='box':return False
    width,height,angle=rest;cosine=math.cos(angle);sine=math.sin(angle)
    dx=box[0]-x;dy=box[1]-y
    locals=(dx*cosine+dy*sine,-dx*sine+dy*cosine);q=[]
    for local,size in zip(locals,(width,height)):
        excess=absolute_box(local)-Interval(abs(size))/2
        q.append(Interval(max(0,excess.lo),max(0,excess.hi)))
    return (q[0]*q[0]+q[1]*q[1]).hi<=(Interval(radius)*radius).lo


def zone_contact_sets(index,box,radius):
    ranges=[]
    for axis in (0,1):
        cells=box[axis]/index.cell_size
        ranges.append(range(math.floor(cells.lo),math.floor(cells.hi)+1))
    if len(ranges[0])*len(ranges[1])>400:raise UnresolvedArithmetic('Fade zone footprint too wide')
    candidate=set();common=None
    for x in ranges[0]:
        for y in ranges[1]:
            members=set(index.cells.get((x,y),()))
            candidate.update(members);common=members if common is None else common&members
    possible=set();guaranteed=set()
    for identifier in candidate:
        zone,shape=index.shapes[identifier]
        if not shape_disjoint(shape,box,radius):possible.add(zone)
        if identifier in common and shape_guaranteed_contact(shape,box,radius):guaranteed.add(zone)
    return possible,guaranteed


def fade_damage_enclosure(world,base,position,progress,fade_out=True):
    settings=world.settings['RecipeMapManagerTeleportationSettings']
    curve=settings['indicatorDisappearingScaleCurve' if fade_out else 'indicatorAppearingScaleCurve']
    frames=[];damages=[]
    for previous,current in progress:
        if not 0<=previous<=current<=1:raise ValueError('Invalid fade progress')
        radius=world.geometry['indicator_radius']*min(1.,max(0.,curve_value(curve,current)))
        possible,guaranteed=(set(),set()) if fade_out and current==1 else zone_contact_sets(world.zones[base],position,radius)
        choices=[]
        if current>=1:choices=[0.]
        else:
            suffix='Out' if fade_out else 'In'
            if 'strong_danger' in possible:
                choices.append(settings[f'totalStrongIndicatorDamageOnFade{suffix}']*(current-previous))
            if 'weak_danger' in possible and 'strong_danger' not in guaranteed:
                choices.append(settings[f'totalWeakIndicatorDamageOnFade{suffix}']*(current-previous))
            if not guaranteed.intersection({'strong_danger','weak_danger'}):choices.append(0.)
        if not choices:raise UnresolvedArithmetic('Contact classification inconsistent')
        damage=Interval(min(choices),max(choices));damages.append(damage)
        frames.append({'progress':current,'radius':radius,'possibleZones':sorted(possible),
                       'guaranteedZones':sorted(guaranteed),'extraDamage':damage})
    return {'scope':'stationary cold fade at supplied fixed progress; extra damage only',
            'frames':frames,'totalExtraDamage':float_sum_box(damages),
            'survivalProved':False,'actualGameVerified':False}
