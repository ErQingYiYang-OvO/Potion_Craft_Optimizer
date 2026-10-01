"""Conditional cold crystal frame counts; not Unity timing or survival proof."""
import math
from engine.brew import curve_value
from optimizer.intervals import Interval,distance_box,float_sum_box,UnresolvedArithmetic


def cold_crystal_timing(world,path,count,dt=1/60,stirring=1.,frame_budget=100000):
    if not 1<=count<=len(path.pending) or not math.isfinite(dt) or dt<=0 or frame_budget<1:
        raise ValueError('Invalid crystal timing domain')
    settings=world.settings['RecipeMapManagerTeleportationSettings']
    speed=(settings['baseIndicatorSpeed']*curve_value(settings['baseSpeedMultiplierHeatDependence'],0)
           +stirring*world.settings['RecipeMapManagerIndicatorSettings']['indicatorSpeed']
           *settings['indicatorSpeedMultiplier'])
    if not math.isfinite(speed) or speed<=0:raise UnresolvedArithmetic('Nonpositive transit speed')
    phases=[]
    for key in ('indicatorDisappearTime','indicatorAppearTime'):
        progress=0.;increments=[]
        for _ in range(frame_budget):
            if progress>=1:break
            previous=progress
            progress=min(1.,progress+speed/settings['baseIndicatorSpeed']*dt/settings[key])
            if progress<=previous:raise UnresolvedArithmetic('Fade progress stagnates')
            increments.append((previous,progress))
        else:raise UnresolvedArithmetic('Fade frame budget exhausted')
        phases.append(increments)
    points=(path.position,)+path.pending[:count]
    length=float_sum_box(distance_box(a,b) for a,b in zip(points,points[1:]))
    threshold=length-1e-10;nominal=0.;lower=None;upper=None
    for frames in range(frame_budget+1):
        if lower is None and nominal>=threshold.lo:lower=frames
        if nominal>=threshold.hi:upper=frames;break
        updated=nominal+speed*dt
        if updated<=nominal:raise UnresolvedArithmetic('Transit progress stagnates')
        nominal=updated
    if upper is None:raise UnresolvedArithmetic('Transit frame budget exhausted')
    fade_out=len(phases[0]);fade_in=len(phases[1])
    # Match elapsed += dt, rather than multiplying frame count by dt.
    elapsed=0.;elapsed_lower=None
    for frames in range(fade_out+upper+fade_in+1):
        if frames==fade_out+lower+fade_in:elapsed_lower=elapsed
        if frames<fade_out+upper+fade_in:elapsed+=dt
    return {'scope':'completed cold crystal transit at fixed dt/stirring; health aborts excluded',
            'fadeOutFrames':fade_out,'transitFrames':[lower,upper],'fadeInFrames':fade_in,
            'elapsed':Interval(elapsed_lower,elapsed),'fadeOutProgress':phases[0],
            'fadeInProgress':phases[1],'speed':speed,'timingEnclosureComplete':True,
            'survivalProved':False,'actualGameVerified':False}
