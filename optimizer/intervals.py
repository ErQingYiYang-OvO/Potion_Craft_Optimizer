"""Outward binary64 interval arithmetic and elementary geometry exclusion.

This is a building block for proof work, not full brewing reachability. Salt,
collision corrections, heat and free-action closure are absent. Carried paths
support zero-angle external movement and appending supplied local path boxes.
Unsupported arithmetic leaves a branch unresolved rather than excluding it.
"""
from dataclasses import dataclass
from fractions import Fraction
from decimal import Decimal, localcontext
import math
import sys


class UnresolvedArithmetic(ValueError): pass


def rational(value):
    if isinstance(value,float):
        if not math.isfinite(value): raise UnresolvedArithmetic('Nonfinite endpoint')
        return Fraction.from_float(value)
    return Fraction(value)


def outward(value,upper):
    value=rational(value)
    try: approximate=float(value)
    except OverflowError: raise UnresolvedArithmetic('Endpoint overflow')
    if not math.isfinite(approximate): raise UnresolvedArithmetic('Endpoint overflow')
    if (upper and rational(approximate)<value) or (not upper and rational(approximate)>value):
        approximate=math.nextafter(approximate,math.inf if upper else -math.inf)
    return rational(approximate)


@dataclass(frozen=True)
class Interval:
    lo: Fraction
    hi: Fraction=None

    def __post_init__(self):
        object.__setattr__(self,'lo',rational(self.lo))
        object.__setattr__(self,'hi',self.lo if self.hi is None else rational(self.hi))
        if self.lo>self.hi: raise ValueError('Reversed interval')

    @classmethod
    def rounded(cls,lo,hi):return cls(outward(lo,False),outward(hi,True))

    def __add__(self,other):
        other=as_interval(other);return self.rounded(self.lo+other.lo,self.hi+other.hi)
    __radd__=__add__
    def __neg__(self):return Interval(-self.hi,-self.lo)
    def __sub__(self,other):return self+-as_interval(other)
    def __rsub__(self,other):return as_interval(other)+-self
    def __mul__(self,other):
        other=as_interval(other)
        products=[a*b for a in (self.lo,self.hi) for b in (other.lo,other.hi)]
        return self.rounded(min(products),max(products))
    __rmul__=__mul__
    def __truediv__(self,other):
        other=as_interval(other)
        if other.lo<=0<=other.hi:raise UnresolvedArithmetic('Denominator crosses zero')
        reciprocal=self.rounded(1/other.hi,1/other.lo)
        return self*reciprocal

    def square(self):
        lower=0 if self.lo<=0<=self.hi else min(self.lo*self.lo,self.hi*self.hi)
        return self.rounded(lower,max(self.lo*self.lo,self.hi*self.hi))

    def sqrt(self):
        if self.lo<0:raise UnresolvedArithmetic('Square root domain crosses negative values')
        # Convert after taking the high-precision root, so an endpoint smaller
        # than binary64's minimum value does not produce a zero starting guess.
        with localcontext() as context:
            context.prec=80
            root=lambda value:float((Decimal(value.numerator)/Decimal(value.denominator)).sqrt())
            lower=root(self.lo);upper=root(self.hi)
        if not math.isfinite(upper):raise UnresolvedArithmetic('Square root endpoint overflow')
        # Verify the bracket using exact squares, independently of sqrt's
        # initial approximation and the rounding of the Fraction -> float cast.
        while rational(lower)**2>self.lo:lower=math.nextafter(lower,-math.inf)
        while rational(upper)**2<self.hi:upper=math.nextafter(upper,math.inf)
        return Interval(lower,upper)

    def contains(self,value):return self.lo<=rational(value)<=self.hi


def as_interval(value):return value if isinstance(value,Interval) else Interval(value)


def point_box(point):
    return tuple(as_interval(coordinate) for coordinate in point)


def lerp_box(a,b,parameter):
    """Match engine.lerp's operation order, without clamping the parameter."""
    a=point_box(a);b=point_box(b);t=as_interval(parameter)
    return tuple(a[axis]+(b[axis]-a[axis])*t for axis in (0,1))


def hull(*values):
    values=[as_interval(value) for value in values]
    return Interval(min(value.lo for value in values),max(value.hi for value in values))


def roundoff_radius(result):
    """Nearest binary64 rounding error bound from a finite result enclosure."""
    magnitude=max(abs(result.lo),abs(result.hi))
    upper=outward(magnitude,True)
    return rational(math.ulp(float(upper)))/2


def distance_box(a,b):
    """CPython 3.10+ hypot error contract, not Unity's distance function.

    https://docs.python.org/3.12/library/math.html#math.hypot documents <1 ulp
    error. Two adjacent values each way conservatively cover binade changes.
    """
    if sys.implementation.name!='cpython' or sys.version_info<(3,10):
        raise UnresolvedArithmetic('Unsupported hypot runtime')
    a=point_box(a);b=point_box(b)
    delta=tuple(a[i]-b[i] for i in (0,1))
    root=(delta[0].square()+delta[1].square()).sqrt()
    lower=float(root.lo);upper=float(root.hi)
    for _ in range(2):
        lower=math.nextafter(lower,-math.inf)
        upper=math.nextafter(upper,math.inf)
    return Interval(max(0.,lower),upper)


def float_sum_box(values):
    """Enclose finite float-only CPython 3.12 sum compensation branches.

    Matches Python/bltinmodule.c v3.12.14; other versions remain unresolved.
    This is an enclosure of the implementation, not an exact real sum.
    """
    if sys.implementation.name!='cpython' or sys.version_info[:2]!=(3,12):
        raise UnresolvedArithmetic('Float sum requires CPython 3.12')
    values=iter(values)
    first=next(values,None)
    if first is None:return Interval(0)
    total=as_interval(first);compensation=Interval(0)
    absolute=lambda v:Interval(0 if v.lo<=0<=v.hi else min(abs(v.lo),abs(v.hi)),
                               max(abs(v.lo),abs(v.hi)))
    for value in values:
        value=as_interval(value);updated=total+value
        left=absolute(total);right=absolute(value);corrections=[]
        # In exact arithmetic either compensation expression equals zero.
        # Its actual value is -error(add) + error(subtract) + error(add).
        # Preserve that identity to avoid compensation exploding with input
        # uncertainty; still intersect with the original operation enclosure.
        for possible,first,second in ((left.hi>=right.lo,total,value),
                                      (left.lo<right.hi,value,total)):
            if not possible:continue
            subtraction=first-updated;correction=subtraction+second
            error=roundoff_radius(updated)+roundoff_radius(subtraction)+roundoff_radius(correction)
            corrections.append(Interval(max(correction.lo,-error),min(correction.hi,error)))
        compensation=compensation+hull(*corrections)
        total=updated
    return total+compensation


@dataclass(frozen=True)
class CarriedPathBox:
    """One fixed pending-point topology; not a complete brewing state.

    Local input paths must already conservatively enclose ingredient_path.
    Their generation, point consumption, timing, and survival are not proved
    here. An unsupported rotation raises instead of discarding a branch.
    """
    position: tuple
    pending: tuple=()

    def __post_init__(self):
        object.__setattr__(self,'position',point_box(self.position))
        object.__setattr__(self,'pending',tuple(point_box(p) for p in self.pending))

    def move(self,position,angle_delta=0):
        angle=as_interval(angle_delta)
        if angle.lo!=0 or angle.hi!=0:
            raise UnresolvedArithmetic('Carried rotation has no certified trig enclosure')
        position=point_box(position)
        shift=tuple(position[a]-self.position[a] for a in (0,1))
        points=[]
        for point in self.pending:
            # rotate_about(..., 0) still subtracts and re-adds the pivot in
            # binary64. Preserve those operations, including multiplication
            # by the exact sin(0)=0 and cos(0)=1 values.
            relative=tuple((point[a]+shift[a])-position[a] for a in (0,1))
            points.append((position[0]+relative[0]*1-relative[1]*0,
                           position[1]+relative[0]*0+relative[1]*1))
        return CarriedPathBox(position,tuple(points))

    def append(self,local_path):
        """Append path[1:] at the old endpoint, independent of bottle angle."""
        local_path=tuple(point_box(p) for p in local_path)
        start=self.pending[-1] if self.pending else self.position
        added=tuple(tuple(start[a]+p[a] for a in (0,1)) for p in local_path[1:])
        return CarriedPathBox(self.position,self.pending+added)

    def remaining_length(self):
        points=(self.position,)+self.pending
        bound=float_sum_box(distance_box(a,b) for a,b in zip(points,points[1:]))
        # Actual path lengths are nonnegative. Intervals lose correlation in
        # the compensated sum, which can otherwise create a negative lower.
        return Interval(max(0,bound.lo),bound.hi)

    def stir_step(self,parameter=Interval(0,1),factor=1,correction=None):
        """Relax one ordinary stir iteration, retaining both point topologies.

        parameter encloses consumed/segment; factor encloses the swamp factor.
        Non-None correction is reserved and currently rejected. This method does not
        derive these inputs from timing/geometry, update health, or advance
        the environment. In particular it is not valid for a crystal step.
        """
        parameter=as_interval(parameter);factor=as_interval(factor)
        if parameter.lo<0 or parameter.hi>1 or factor.lo<0 or factor.hi>1:
            raise UnresolvedArithmetic('Stir control enclosure outside [0,1]')
        if not self.pending:return (self,)
        intended=lerp_box(self.position,self.pending[0],parameter)
        actual=lerp_box(self.position,intended,factor)
        if correction is not None:
            # Both subtraction and reconstruction rounding require a caller
            # supplied enclosure. Omit this operation for no correction.
            raise UnresolvedArithmetic('Forcefield correction enclosure not implemented')
        if factor.lo==factor.hi==1:
            # actual = fl(position + fl(intended - position)). Relative to
            # intended, this differs only by the two rounding errors. Preserve
            # that dependency rather than treating actual/intended as unrelated
            # boxes; otherwise zero swamp shift expands every later path point.
            errors=tuple(roundoff_radius(intended[a]-self.position[a])+
                         roundoff_radius(actual[a]) for a in (0,1))
            shift=tuple(Interval.rounded(-error,error) for error in errors)
            actual=tuple(intended[a]+Interval(-errors[a],errors[a]) for a in (0,1))
        else:
            shift=tuple(actual[a]-intended[a] for a in (0,1))
        shifted=tuple(tuple(p[a]+shift[a] for a in (0,1)) for p in self.pending)
        # Consumed >= segment - 1e-10 can remove a point before t reaches 1.
        # Retain both outcomes until a certified segment/budget test exists.
        branches=[CarriedPathBox(actual,shifted),CarriedPathBox(actual,shifted[1:])]
        # Near-zero segments are removed without moving or shifting the rest.
        branches.append(CarriedPathBox(self.position,self.pending[1:]))
        return tuple(branches)


def bezier_box(curve,parameter):
    """Enclose engine.bezier's Bernstein operation order for an input interval."""
    t=as_interval(parameter);u=1-t
    points=[curve[k] for k in ('PFirst','P1','P2','PLast')]
    return tuple(u*u*u*p[0][axis]+3*u*u*t*p[1][axis]+3*u*t*t*p[2][axis]+t*t*t*p[3][axis]
                 for axis in ('x','y') for p in [points])


def disk_distance_box(box,target):
    dx=box[0]-target[0];dy=box[1]-target[1]
    return (dx.square()+dy.square()).sqrt()


def exclude_bezier(curve,target,radius,budget=2048,min_width=Fraction(1,2**30)):
    if budget<1 or radius<0 or min_width<=0:raise ValueError('Invalid proof budget or domain')
    queue=[Interval(0,1)];unresolved=[];excluded=[];processed=0
    while queue and processed<budget:
        parameter=queue.pop();processed+=1
        try:
            bound=disk_distance_box(bezier_box(curve,parameter),target)
            if bound.lo>rational(radius):excluded.append(parameter);continue
        except UnresolvedArithmetic:
            unresolved.append(parameter);continue
        if parameter.hi-parameter.lo<=min_width:unresolved.append(parameter);continue
        middle=(parameter.lo+parameter.hi)/2
        queue.extend([Interval(parameter.lo,middle),Interval(middle,parameter.hi)])
    unresolved+=queue
    serialize=lambda intervals:[[str(i.lo),str(i.hi)] for i in intervals]
    return {'scope':'one binary64 Bernstein curve evaluation over t in [0,1]; real Euclidean disk',
            'curveDiskIntersectionExcluded':not unresolved,'processedBoxes':processed,
            'excludedParameters':serialize(excluded),'unresolvedParameters':serialize(unresolved),
            'brewingRecipeExcluded':False,'globalOptimalityProved':False}
