import math
import sys
import unittest
from engine.brew import BrewWorld,PotionSession,lerp,distance
from optimizer.intervals import Interval,CarriedPathBox,distance_box,float_sum_box
from optimizer.ordinary_stir import ordinary_stir,minimum_cases


@unittest.skipUnless(sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12),
                     'Interval compensated sum models CPython 3.12')
class OrdinaryStirTests(unittest.TestCase):
    def test_distance_and_compensated_path_length(self):
        for a,b in (((0,0),(3,4)),((1e-300,0),(0,0)),((1e150,-1e150),(0,0))):
            self.assertTrue(distance_box(a,b).contains(distance(a,b)))
        for values in ((1e16,1.,-1e16),(1e16,-1e16,1.),(1.,)*100,()):
            self.assertTrue(float_sum_box(values).contains(sum(values)))
        uncertain=float_sum_box([Interval(0,1)]*100)
        self.assertLess(float(uncertain.hi),100.0000001)
        self.assertGreater(float(uncertain.lo),-.0000001)
        world=BrewWorld();potion=PotionSession(world)
        potion.add('Firebell',1);potion.stir(.4)
        bound=CarriedPathBox(potion.position,tuple(potion.pending)).remaining_length()
        self.assertTrue(bound.contains(potion.remaining_length))

    def test_complete_short_loop_covers_all_sampled_controls(self):
        initial=(0.,0.);pending=((.12,.05),(.2,.1))
        path=CarriedPathBox(initial,pending)
        result=ordinary_stir(path,Interval(.1,.2),1.,2.,node_budget=100)
        self.assertTrue(result['loopEnclosureComplete'])
        for fraction in (.1,.13,.2):
            position=initial;points=list(pending)
            target=sum(distance(a,b) for a,b in zip((position,)+pending,pending))*fraction
            elapsed=0.
            while points and target>1e-10:
                segment=distance(position,points[0])
                if segment<1e-10:points.pop(0);continue
                consumed=min(target,segment,1.)
                intended=lerp(position,points[0],consumed/segment)
                if consumed>=segment-1e-10:points.pop(0)
                actual=lerp(position,intended,1.)
                shift=(actual[0]-intended[0],actual[1]-intended[1])
                points=[(p[0]+shift[0],p[1]+shift[1]) for p in points]
                position=actual;target-=consumed;elapsed+=consumed/2.
            matching=[node for node in result['terminal'] if len(node.path.pending)==len(points)]
            self.assertTrue(any(node.remaining.contains(target) and node.elapsed.contains(elapsed)
                and all(bound.contains(value) for box,point in zip(
                    (node.path.position,)+node.path.pending,(position,)+tuple(points))
                    for bound,value in zip(box,point)) for node in matching))
        self.assertFalse(result['brewingRecipeExcluded'])

    def test_budget_exhaustion_and_near_zero_segment(self):
        path=CarriedPathBox((0,0),((0,0),(.1,0)))
        limited=ordinary_stir(path,.5,.01,1.,node_budget=1)
        self.assertFalse(limited['loopEnclosureComplete'])
        self.assertTrue(limited['unresolved'])
        complete=ordinary_stir(path,.5,1.,1.,node_budget=100)
        self.assertTrue(complete['loopEnclosureComplete'])
        self.assertTrue(any(len(node.path.pending)==1 for node in complete['terminal']))

    def test_certain_full_segment_does_not_create_partial_branch(self):
        path=CarriedPathBox((0,0),((.01,0),(.02,0),(.2,0)))
        result=ordinary_stir(path,Interval(.25,.3),1.,1.,node_budget=12)
        self.assertTrue(result['loopEnclosureComplete'])
        self.assertEqual(len(result['terminal']),1)
        self.assertEqual(len(result['terminal'][0].path.pending),1)
        for fraction in (.25,.3):
            self.assertTrue(result['terminal'][0].path.position[0].contains(.2*fraction))

    def test_minimum_case_constraints_cover_ties_and_switching_operands(self):
        cases=list(minimum_cases(Interval(.1,.3),Interval(.2,.4),Interval(.25)))
        self.assertEqual({winner for winner,_ in cases},{0,1,2})
        for target in (.1,.2,.25,.3):
            for segment in (.2,.25,.3,.4):
                actual=(target,segment,.25);smallest=min(actual)
                self.assertTrue(any(actual[winner]==smallest and
                    all(bound.contains(value) for bound,value in zip(bounds,actual))
                    for winner,bounds in cases))
        # An operand whose minimum already exceeds another operand's maximum
        # cannot win; possible equality must still remain covered.
        self.assertEqual([winner for winner,_ in minimum_cases(Interval(1),Interval(2,3))],[0])
        self.assertEqual({winner for winner,_ in minimum_cases(Interval(1),Interval(1))},{0,1})


if __name__=='__main__':unittest.main()
