import unittest
from fractions import Fraction
from engine.brew import bezier, lerp, BrewWorld, PotionSession
from optimizer.intervals import (Interval, UnresolvedArithmetic, bezier_box,
                                exclude_bezier, CarriedPathBox, lerp_box)


class IntervalTests(unittest.TestCase):
    curve={'PFirst':{'x':0.,'y':0.},'P1':{'x':1.,'y':2.},'P2':{'x':2.,'y':2.},'PLast':{'x':3.,'y':0.}}

    def test_arithmetic_encloses_real_and_binary64_results(self):
        self.assertTrue((Interval(.1)+.2).contains(.1+.2))
        self.assertTrue((Interval(.1)+.2).contains(Fraction.from_float(.1)+Fraction.from_float(.2)))
        self.assertTrue((Interval(1)/10).contains(Fraction(1,10)))
        self.assertTrue(Interval(-2,3).square().contains(0))
        root=Interval(2).sqrt()
        self.assertLessEqual(root.lo**2,2);self.assertGreaterEqual(root.hi**2,2)
        tiny=Fraction(1,10**600);root=Interval(tiny).sqrt()
        self.assertLessEqual(root.lo**2,tiny);self.assertGreaterEqual(root.hi**2,tiny)
        with self.assertRaises(UnresolvedArithmetic):Interval(1)/Interval(-1,1)

    def test_curve_enclosure_includes_actual_bernstein_samples(self):
        domain=Interval(.2,.4);box=bezier_box(self.curve,domain)
        for index in range(101):
            parameter=.2+.2*index/100
            point=bezier(self.curve,parameter)
            self.assertTrue(box[0].contains(point[0]));self.assertTrue(box[1].contains(point[1]))

    def test_exclusion_and_budget_exhaustion_are_distinct(self):
        excluded=exclude_bezier(self.curve,(30,30),.1)
        self.assertTrue(excluded['curveDiskIntersectionExcluded'])
        uncertain=exclude_bezier(self.curve,(1.5,1.5),.1,budget=1)
        self.assertFalse(uncertain['curveDiskIntersectionExcluded'])
        self.assertTrue(uncertain['unresolvedParameters'])
        self.assertFalse(excluded['brewingRecipeExcluded'])

    def assertEnclosed(self,boxes,points):
        self.assertEqual(len(boxes),len(points))
        for box,point in zip(boxes,points):
            for bound,value in zip(box,point):self.assertTrue(bound.contains(value))

    def test_uncertain_motion_encloses_intermediate_positions_and_path(self):
        world=BrewWorld();potion=PotionSession(world)
        potion.add('Firebell',1);potion.stir(.4)
        initial=potion.position;pending=potion.pending[:]
        destination=lerp_box(initial,(0,0),Interval(.1,.7))
        moved=CarriedPathBox(initial,tuple(pending)).move(destination)
        for fraction in (.1,.2,.4,.7):
            potion.position=initial;potion.pending=pending[:]
            potion.move_remaining_path(lerp(initial,(0,0),fraction))
            self.assertEnclosed((moved.position,), (potion.position,))
            self.assertEnclosed(moved.pending,potion.pending)

    def test_actual_pour_then_append_uses_carried_endpoint(self):
        world=BrewWorld();potion=PotionSession(world)
        potion.add('Firebell',1);potion.stir(.4)
        bound=CarriedPathBox(potion.position,tuple(potion.pending))
        # Observe each actual pour movement. This verifies the propagation
        # primitive, not the unimplemented interval pouring integrator.
        original=potion.move_remaining_path;movements=[]
        def observed(position,angle_delta=0):
            nonlocal bound
            bound=bound.move(position,angle_delta)
            original(position,angle_delta)
            movements.append(position)
            self.assertEnclosed(bound.pending,potion.pending)
        potion.move_remaining_path=observed
        potion.pour(.12)
        self.assertGreater(len(movements),1)
        bound=bound.append(world.ingredient_path('Waterbloom',.35))
        potion.add('Waterbloom',.35)
        self.assertEnclosed(bound.pending,potion.pending)
        # Addition must not rotate the newly supplied local offsets.
        potion.rotation=75
        bound=bound.append(world.ingredient_path('Firebell',.5))
        potion.add('Firebell',.5)
        self.assertEnclosed(bound.pending,potion.pending)

    def test_rotation_requires_a_certified_extension(self):
        state=CarriedPathBox((1,2),((3,4),))
        for angle in (1,Interval(-1,1)):
            with self.assertRaises(UnresolvedArithmetic):state.move((2,3),angle)

    def test_stir_step_encloses_swamp_shift_and_both_point_counts(self):
        position=(1.234,-.45);pending=((2.3,.85),(3.7,-1.2),(5.1,2.6))
        state=CarriedPathBox(position,pending)
        branches=state.stir_step(Interval(.1,1),Interval(.2,1))
        self.assertEqual([len(b.pending) for b in branches],[3,2,2])
        for parameter in (.1,.37,.99,1):
            for factor in (.2,.7,1):
                intended=lerp(position,pending[0],parameter)
                actual=lerp(position,intended,factor)
                shift=(actual[0]-intended[0],actual[1]-intended[1])
                for removed in (False,True):
                    points=pending[1:] if removed else pending
                    shifted=tuple((p[0]+shift[0],p[1]+shift[1]) for p in points)
                    branch=branches[int(removed)]
                    self.assertEnclosed((branch.position,),(actual,))
                    self.assertEnclosed(branch.pending,shifted)
        self.assertEnclosed((branches[2].position,),(position,))
        self.assertEnclosed(branches[2].pending,pending[1:])

    def test_stir_step_unsupported_inputs_remain_unresolved(self):
        state=CarriedPathBox((0,0),((1,1),))
        for kwargs in ({'parameter':Interval(-.01,1)}, {'factor':1.01},
                       {'correction':(0,0)}):
            with self.assertRaises(UnresolvedArithmetic):state.stir_step(**kwargs)
        empty=CarriedPathBox((0,0))
        self.assertEqual(empty.stir_step(),(empty,))

    def test_actual_cold_ordinary_stir_iterations_are_enclosed(self):
        world=BrewWorld();potion=PotionSession(world)
        potion.add('Firebell',1)
        before=CarriedPathBox(potion.position,tuple(potion.pending))
        original=potion._health_step;checked=[]
        def observed(position,*args,**kwargs):
            nonlocal before
            branches=before.stir_step()
            matching=[b for b in branches if len(b.pending)==len(potion.pending)]
            self.assertTrue(any(all(bound.contains(value) for box,point in
                zip((b.position,)+b.pending,(position,)+tuple(potion.pending))
                for bound,value in zip(box,point)) for b in matching))
            checked.append(position)
            original(position,*args,**kwargs)
            before=CarriedPathBox(potion.position,tuple(potion.pending))
        potion._health_step=observed
        potion.stir(.4)
        self.assertGreater(len(checked),5)

    def test_no_swamp_shift_retains_roundoff_scale(self):
        state=CarriedPathBox((1.234,-.45),((2.3,.85),(3.7,-1.2)))
        retained=state.stir_step(Interval(.1,.9),factor=1)[0]
        for point in retained.pending:
            for bound in point:self.assertLess(float(bound.hi-bound.lo),1e-10)
        for parameter in (.1,.5,.9):
            intended=lerp((1.234,-.45),(2.3,.85),parameter)
            actual=lerp((1.234,-.45),intended,1)
            shift=(actual[0]-intended[0],actual[1]-intended[1])
            points=tuple((p[0]+shift[0],p[1]+shift[1]) for p in ((2.3,.85),(3.7,-1.2)))
            self.assertEnclosed(retained.pending,points)


if __name__=='__main__':unittest.main()
