"""Region-checked enclosure of fixed-state cold ordinary engine stirring.

This certifies neither arbitrary ingredient grinding nor future free actions.
"""
import math
from engine.brew import curve_value
from optimizer.intervals import (Interval,CarriedPathBox,as_interval,
                                 distance_box,UnresolvedArithmetic)
from optimizer.ordinary_stir import ordinary_stir


def absolute_box(value):
    value=as_interval(value)
    return Interval(0 if value.lo<=0<=value.hi else min(abs(value.lo),abs(value.hi)),
                    max(abs(value.lo),abs(value.hi)))


def shape_disjoint(shape,box,radius):
    """Conservative non-contact test matching overlaps_circle operations."""
    kind,x,y,*rest=shape
    if kind=='circle':
        return distance_box(box,(x,y)).lo>(Interval(rest[0])+radius).hi
    if kind!='box':return False
    width,height,angle=rest
    cosine=math.cos(angle);sine=math.sin(angle)
    dx=box[0]-x;dy=box[1]-y
    lx=dx*cosine+dy*sine;ly=-dx*sine+dy*cosine
    q=[]
    for local,size in ((lx,width),(ly,height)):
        excess=absolute_box(local)-Interval(abs(size))/2
        q.append(Interval(max(0,excess.lo),max(0,excess.hi)))
    return (q[0]*q[0]+q[1]*q[1]).lo>(Interval(radius)*radius).hi


def _polygon_contains_strip(polygon,box):
    """Certify fixed ray-test parity in a strip without vertex ambiguity.

    Ambiguous vertex or edge comparisons return False, not outside proof.
    """
    inside=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        def above(y):
            if y>box[1].hi:return True
            if y<=box[1].lo:return False
            return None
        left=above(a[1]);right=above(b[1])
        if left is None or right is None:return False
        if left==right:continue
        crossing=Interval(a[0])+(box[1]-a[1])*(Interval(b[0])-a[0])/(Interval(b[1])-a[1])
        if box[0].hi<crossing.lo:inside=not inside
        elif box[0].lo<crossing.hi:return False
    return inside


def polygon_contains_box(polygon,box,strip_budget=256):
    """Certify every binary64 engine point in a box, including vertex levels.

    Split at vertex y values into singleton levels and between-vertex strips.
    nextafter gaps contain no binary64 positions. This is not a claim about
    all real-valued points inside the omitted sub-ULP gaps.
    """
    levels=sorted(set(p[1] for p in polygon if box[1].lo<=p[1]<=box[1].hi))
    if 2*len(levels)+1>strip_budget:return False
    strips=[];cursor=box[1].lo
    for level in levels:
        previous=math.nextafter(level,-math.inf)
        following=math.nextafter(level,math.inf)
        if not math.isfinite(previous) or not math.isfinite(following):return False
        if cursor<=previous:strips.append(Interval(cursor,previous))
        strips.append(Interval(level))
        cursor=as_interval(following).lo
    if cursor<=box[1].hi:strips.append(Interval(cursor,box[1].hi))
    return bool(strips) and all(_polygon_contains_strip(polygon,(box[0],strip)) for strip in strips)


def clean_region_reason(world,base,box):
    size=world.bases[base]['map_size']
    for axis,key in enumerate(('x','y')):
        if box[axis].lo < -size[key]/2 or box[axis].hi >= size[key]/2:
            return 'map boundary enclosure unresolved'
    try:
        index=world.zones[base]
        ranges=[]
        for axis in (0,1):
            cells=box[axis]/index.cell_size
            ranges.append(range(math.floor(cells.lo),math.floor(cells.hi)+1))
        if len(ranges[0])*len(ranges[1])>400:
            return 'zone cell footprint too wide'
        candidates=set()
        for x in ranges[0]:
            for y in ranges[1]:candidates.update(index.cells.get((x,y),()))
        # Match the engine's own index membership, covering every possible
        # rounded division/floor cell. This certifies this engine's queries,
        # not the fidelity of its spatial index to Unity colliders.
        for candidate in sorted(candidates):
            zone,shape=index.shapes[candidate]
            if not shape_disjoint(shape,box,world.geometry['indicator_radius']):
                return f'possible {zone} contact'
        if not any(polygon_contains_box(polygon,box) for polygon in world.forcefields[base].polygons):
            return 'forcefield interior not certified'
    except UnresolvedArithmetic as error:return str(error)
    return None


def cold_stir_enclosure(session,fraction,node_budget=256):
    """Fixed source state -> conservative terminal paths, or unresolved.

    Zone-free, positive-health, zero-heat, no active rotation, ordinary path
    only. Checking every starting/interpolated/final box ensures the excluded
    environment cannot influence these branches. Bounds refer to this engine.
    """
    reasons=[]
    if session.failed_reason or session.health<=0:reasons.append('failed starting state')
    if session.heat!=0:reasons.append('nonzero heat')
    if session.rotation_tween is not None:reasons.append('rotation controller present')
    if not session.path_sections and session.pending:reasons.append('missing path provenance')
    if sum(s['point_count'] for s in session.path_sections)!=len(session.pending):
        reasons.append('path topology metadata mismatch')
    if any(s['teleport'] for s in session.path_sections):reasons.append('crystal path')
    control=session.world.bellows
    if curve_value(control['heatIncreasingSpeed'],0)>0:
        reasons.append('zero bellows input increases heat')
    if not control['disableCoolingDown'] and curve_value(control['heatDecreasingSpeed'],0)<0:
        reasons.append('zero heat cooling increases heat')
    scope='fixed current engine state; cold ordinary stir; no future action or full recipe exclusion'
    if reasons:return {'scope':scope,'supported':False,'reasons':reasons,
                       'brewingRecipeExcluded':False,'globalOptimalityProved':False}
    path=CarriedPathBox(session.position,tuple(session.pending))
    result=ordinary_stir(path,fraction,session.world.spacing,
                         session.world.settings['RecipeMapManagerIndicatorSettings']['indicatorSpeed'],
                         node_budget=node_budget,
                         region_guard=lambda box:clean_region_reason(session.world,session.base,box))
    return {**result,'scope':scope,'supported':True}


def adaptive_cold_stir_enclosure(session,fraction,node_budget=256,box_budget=32):
    """Split uncertain control domains; retain every unfinished leaf."""
    if box_budget<1:raise ValueError('Invalid parameter box budget')
    queue=[as_interval(fraction)];terminal=[];unresolved=[];leaves=[]
    attempts=0;processed=0
    while queue and attempts<box_budget:
        parameter=queue.pop();attempts+=1
        result=cold_stir_enclosure(session,parameter,node_budget)
        if not result['supported']:return result
        processed+=result['processedNodes']
        if result['loopEnclosureComplete']:
            terminal.extend(result['terminal'])
            leaves.append({'parameter':[str(parameter.lo),str(parameter.hi)],'complete':True})
        elif parameter.lo<parameter.hi and attempts+len(queue)+2<=box_budget:
            middle=(parameter.lo+parameter.hi)/2
            queue.extend((Interval(parameter.lo,middle),Interval(middle,parameter.hi)))
        else:
            # Successful terminal branches from this leaf remain useful, but
            # its unresolved states prevent a complete enclosure assertion.
            terminal.extend(result['terminal']);unresolved.extend(result['unresolved'])
            leaves.append({'parameter':[str(parameter.lo),str(parameter.hi)],'complete':False})
    # Reservation above guarantees enough attempts for every pending child.
    if queue:raise AssertionError('Parameter budget lost a pending leaf')
    return {'scope':'adaptive fixed-state cold ordinary stir; no recipe exclusion',
            'supported':True,'terminal':terminal,'unresolved':unresolved,
            'parameterLeaves':leaves,'parameterBoxesAttempted':attempts,
            'processedNodes':processed,'loopEnclosureComplete':not unresolved,
            'brewingRecipeExcluded':False,'globalOptimalityProved':False}


if __name__=='__main__':
    import argparse,hashlib,json
    from pathlib import Path
    from engine.brew import BrewWorld,PotionSession
    parser=argparse.ArgumentParser(description='Fixed-state cold stir interval example; no recipe exclusion')
    parser.add_argument('--base',choices=('Water','Oil','Wine'),default='Water')
    parser.add_argument('--ingredient',default='Firebell')
    parser.add_argument('--grind',type=float,default=1.)
    parser.add_argument('--fractions',type=float,nargs=2,default=(.0005,.001))
    parser.add_argument('--nodes',type=int,default=60)
    parser.add_argument('--subdivisions',type=int,default=1)
    parser.add_argument('--output',default='result/search/cold_stir_certificate.json')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    if output.parent!=root/'result/search' or output.suffix!='.json' or output.name.endswith('candidates.json'):
        parser.error('Output must be a non-candidate JSON directly under result/search')
    if not 0<=args.grind<=1:parser.error('Grind outside [0,1]')
    world=BrewWorld();session=PotionSession(world,args.base)
    session.add(args.ingredient,args.grind)
    result=adaptive_cold_stir_enclosure(session,Interval(*args.fractions),args.nodes,args.subdivisions)
    def bounds(value):return [str(value.lo),str(value.hi)]
    def node_summary(node):
        return {'position':[bounds(v) for v in node.path.position],
                'remainingBudget':bounds(node.remaining),'elapsed':bounds(node.elapsed),
                'pendingCount':len(node.path.pending)}
    record={k:v for k,v in result.items() if k not in ('terminal','unresolved')}
    record['parameters']={k:v for k,v in vars(args).items() if k!='output'}
    record['terminal']=[node_summary(node) for node in result.get('terminal',[])]
    record['unresolved']=[{**node_summary(node),'reason':reason}
                          for node,reason in result.get('unresolved',[])]
    files=list((root/'data').glob('*.json'))+list((root/'engine').glob('*.py'))
    files+=[root/'optimizer'/name for name in ('intervals.py','ordinary_stir.py','cold_stir.py')]
    record['inputSha256']={str(path.relative_to(root)).replace('\\','/'):
                          hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
    record['runtime']={'implementation':__import__('sys').implementation.name,
                       'version':__import__('sys').version}
    output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={k:v for k,v in record.items() if k not in ('inputSha256','terminal','unresolved','parameterLeaves')}
    summary['parameterLeavesComplete']=sum(leaf['complete'] for leaf in record.get('parameterLeaves',[]))
    summary['parameterLeavesTotal']=len(record.get('parameterLeaves',[]))
    print(json.dumps(summary,ensure_ascii=False))
