"""Scalar port of IndicatorRotationSubManager's linear salt tween.

PotionSession supports this controller for explicit deferred salt batches.
Callers supply grain arrival timing; Unity callback scheduling is approximate.
"""
from dataclasses import dataclass
import math
import struct


def f32(value):
    return struct.unpack('<f',struct.pack('<f',value))[0]


def normalize(value):
    value=f32(value)
    if not math.isfinite(value) or abs(value)>1_000_000:raise ValueError('Invalid rotation angle')
    while value<0:value=f32(value+360.)
    return f32(value%360.)


@dataclass
class RotationTween:
    target:float=0.
    visual:float=0.
    start_unwrapped:float=0.
    end_unwrapped:float=0.
    elapsed:float=0.
    duration:float=0.
    active:bool=False

    def __post_init__(self):
        self.target=normalize(self.target);self.visual=normalize(self.visual)

    def rotate_to(self,target,duration):
        if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid rotation duration')
        self.target=normalize(target)
        start,end=self.visual,self.target
        if f32(end-start)>180:start=f32(start+360.)
        elif f32(start-end)>180:end=f32(end+360.)
        self.start_unwrapped,self.end_unwrapped=start,end
        self.duration=f32(duration)
        if not self.duration>0:raise ValueError('Rotation duration underflows float32')
        self.elapsed=0.;self.active=True

    def rotate_by(self,angle,duration):
        self.rotate_to(f32(self.target-f32(angle)),duration)

    def salt_batch(self,settings,salt,units):
        if salt not in ('sun','moon') or isinstance(units,bool) or not isinstance(units,int) or not 0<=units<=10000:
            raise ValueError('Salt batch requires an allowed salt and whole grains')
        angle=settings[f'{salt}SaltIndicatorRotationAngle']
        duration=settings[f'{salt}SaltIndicatorRotationTime']
        # Each particle invokes RotateBy separately, even in one instant batch.
        for _ in range(units):self.rotate_by(angle,duration)

    def advance(self,seconds):
        if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid elapsed time')
        previous=self.visual
        if not self.active:return previous,self.visual
        self.elapsed=min(self.duration,f32(self.elapsed+f32(seconds)))
        progress=f32(self.elapsed/self.duration)
        value=f32(self.start_unwrapped+f32(f32(self.end_unwrapped-self.start_unwrapped)*progress))
        self.visual=normalize(self.target if self.elapsed>=self.duration else value)
        if self.elapsed>=self.duration:self.active=False
        return previous,self.visual
