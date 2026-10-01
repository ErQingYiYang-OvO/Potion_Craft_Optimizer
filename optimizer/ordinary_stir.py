"""Budgeted interval relaxation of the ordinary geometric stir loop.

No forcefields, crystals, environmental evolution, survival or heat. This
module cannot issue a full-game recipe exclusion or optimality certificate.
"""
from dataclasses import dataclass
from optimizer.intervals import (Interval, as_interval, distance_box,
                                 UnresolvedArithmetic, hull)


@dataclass(frozen=True)
class StirNode:
    path: object
    remaining: Interval
    elapsed: Interval


def minimum_cases(*values):
    """Cover each possible winning operand and propagate its ordering bounds.

    Ties can belong to multiple branches; no strict inequality is assumed.
    Each output encloses values satisfying selected <= every other operand.
    """
    values=tuple(as_interval(value) for value in values)
    ceiling=min(value.hi for value in values)
    for winner,value in enumerate(values):
        if value.lo>ceiling:continue
        selected=Interval(value.lo,ceiling)
        conditioned=tuple(selected if index==winner else
                          Interval(max(other.lo,selected.lo),other.hi)
                          for index,other in enumerate(values))
        yield winner,conditioned


def merge_topology_nodes(nodes):
    """Coordinatewise hulls preserve all states; they never prove equivalence.

    Only this geometric loop is modeled, so equal point count suffices for
    compatible vector dimensions. This is not full brewing state merging.
    """
    groups={}
    for node in nodes:groups.setdefault(len(node.path.pending),[]).append(node)
    merged=[]
    for group in groups.values():
        position=tuple(hull(*(node.path.position[a] for node in group)) for a in (0,1))
        pending=tuple(tuple(hull(*(node.path.pending[i][a] for node in group)) for a in (0,1))
                      for i in range(len(group[0].path.pending)))
        merged.append(StirNode(type(group[0].path)(position,pending),
                               hull(*(node.remaining for node in group)),
                               hull(*(node.elapsed for node in group))))
    return merged


def ordinary_stir(path,fraction,spacing,speed,factor=1,node_budget=256,region_guard=None):
    fraction=as_interval(fraction);spacing=as_interval(spacing)
    speed=as_interval(speed);factor=as_interval(factor)
    if fraction.lo<0 or fraction.hi>1 or spacing.lo<=0 or speed.lo<=0:
        raise ValueError('Invalid stirring domain')
    if factor.lo<0 or factor.hi>1 or node_budget<1:
        raise ValueError('Invalid factor or node budget')
    start=StirNode(path,path.remaining_length()*fraction,Interval(0))
    queue=[start];following=[];terminal=[];unresolved=[];processed=0
    epsilon=Interval(1e-10)
    while (queue or following) and processed<node_budget:
        if not queue:
            queue=merge_topology_nodes(following);following=[]
        node=queue.pop();processed+=1
        if region_guard is not None:
            reason=region_guard(node.path.position)
            if reason:
                unresolved.append((node,reason));continue
        if not node.path.pending or node.remaining.hi<=epsilon.lo:
            terminal.append(node);continue
        if node.remaining.lo<=epsilon.hi:terminal.append(node)
        active=Interval(max(node.remaining.lo,epsilon.lo),node.remaining.hi)
        try:
            segment=distance_box(node.path.position,node.path.pending[0])
            # A near-zero segment is popped without spending target or time.
            if segment.lo<epsilon.hi:
                following.append(StirNode(type(path)(node.path.position,node.path.pending[1:]),
                                      active,node.elapsed))
            if segment.hi<epsilon.lo:continue
            segment=Interval(max(segment.lo,epsilon.lo),segment.hi)
            for winner,(target_bound,segment_bound,spacing_bound) in minimum_cases(active,segment,spacing):
                consumed=(target_bound,segment_bound,spacing_bound)[winner]
                consumes_segment=winner==1 or segment_bound.hi<=min(target_bound.lo,spacing_bound.lo)
                if consumes_segment:
                    # Identical finite nonzero float operands divide to 1.
                    parameter=Interval(1)
                else:
                    quotient=consumed/segment_bound
                    parameter=Interval(max(0,quotient.lo),min(1,quotient.hi))
                retained,removed,_=node.path.stir_step(parameter,factor)
                if region_guard is not None:
                    from optimizer.intervals import lerp_box
                    reason=region_guard(lerp_box(node.path.position,node.path.pending[0],parameter))
                    if reason:
                        unresolved.append((node,reason));continue
                # When target wins, target -= consumed subtracts the same
                # float even when it shares a range with other winning cases.
                consumes_all=winner==0 or target_bound.hi<=min(segment_bound.lo,spacing_bound.lo)
                difference=target_bound-consumed
                remaining=Interval(0) if consumes_all else Interval(max(0,difference.lo),difference.hi)
                elapsed=node.elapsed+consumed/speed
                threshold=segment_bound-epsilon
                if not consumes_segment and consumed.lo<threshold.hi:
                    following.append(StirNode(retained,remaining,elapsed))
                if consumes_segment or consumed.hi>=threshold.lo:
                    following.append(StirNode(removed,remaining,elapsed))
        except UnresolvedArithmetic as error:
            unresolved.append((node,str(error)))
    unresolved.extend((node,'node budget exhausted') for node in queue+following)
    return {'scope':'ordinary geometric stir loop with supplied speed/factor; no environment or forcefields',
            'terminal':terminal,'unresolved':unresolved,'processedNodes':processed,
            'loopEnclosureComplete':not unresolved,
            'brewingRecipeExcluded':False,'globalOptimalityProved':False}
