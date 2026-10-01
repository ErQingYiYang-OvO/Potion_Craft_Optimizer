import sys
import unittest
from engine.brew import BrewWorld,PotionSession,Forcefield,overlaps_circle
from engine.rotation import RotationTween
from optimizer.intervals import Interval,CarriedPathBox
from optimizer.cold_stir import (cold_stir_enclosure,adaptive_cold_stir_enclosure,
                                polygon_contains_box,shape_disjoint,clean_region_reason)


@unittest.skipUnless(sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12),
                     'Cold stir enclosure requires CPython 3.12')
class ColdStirTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world=BrewWorld()

    def test_polygon_contains_and_ambiguous_edges(self):
        polygon=[(-2.,-2.),(2.,-2.),(2.,2.),(-2.,2.)]
        self.assertTrue(polygon_contains_box(polygon,(Interval(-.3,.4),Interval(-.2,.5))))
        self.assertFalse(polygon_contains_box(polygon,(Interval(1.,3.),Interval(0))))
        self.assertFalse(polygon_contains_box(polygon,(Interval(0),Interval(-3.,0))))
        self.assertFalse(polygon_contains_box(polygon,(Interval(3),Interval(0))))

    def test_polygon_vertex_level_strips_match_engine_ray_test(self):
        import math
        polygon=[(-2.,-2.),(2.,-2.),(2.,0.),(2.,2.),(-2.,2.),(-2.,0.)]
        box=(Interval(-.2,.2),Interval(-.1,.1))
        self.assertTrue(polygon_contains_box(polygon,box))
        field=Forcefield([]);field.polygons=[polygon]
        for y in (-.1,math.nextafter(0.,-math.inf),0.,math.nextafter(0.,math.inf),.1):
            for x in (-.2,0.,.2):self.assertEqual(field.closest_point((x,y)),(x,y))
        # A concavity at the same vertex height must not be certified inside.
        concave=[(-2.,-2.),(2.,-2.),(2.,0.),(0.,0.),(0.,2.),(-2.,2.)]
        self.assertFalse(polygon_contains_box(concave,box))
        self.assertFalse(polygon_contains_box(polygon,box,strip_budget=1))

    def test_zone_contact_never_certified_disjoint(self):
        shapes=(('circle',1.,2.,.4),('box',1.,2.,.8,1.2,.7))
        for shape in shapes:
            box=(Interval(.7,1.3),Interval(1.7,2.3))
            self.assertFalse(shape_disjoint(shape,box,.2))
            far=(Interval(20,21),Interval(20,21))
            self.assertTrue(shape_disjoint(shape,far,.2))
            for x in (20,20.5,21):
                for y in (20,20.5,21):self.assertFalse(overlaps_circle(shape,(x,y),.2))

    def test_real_cold_stir_control_interval_encloses_replays(self):
        source=PotionSession(self.world);source.add('Firebell',1)
        result=cold_stir_enclosure(source,Interval(.0005,.001),node_budget=60)
        self.assertTrue(result['supported'])
        self.assertTrue(result['loopEnclosureComplete'])
        for fraction in (.0005,.00075,.001):
            potion=PotionSession(self.world);potion.add('Firebell',1);potion.stir(fraction)
            self.assertTrue(any(len(node.path.pending)==len(potion.pending) and
                all(bound.contains(value) for box,point in zip(
                    (node.path.position,)+node.path.pending,(potion.position,)+tuple(potion.pending))
                    for bound,value in zip(box,point)) for node in result['terminal']))
        self.assertFalse(result['brewingRecipeExcluded'])

    def test_unsupported_physics_is_explicit(self):
        potion=PotionSession(self.world);potion.add('Firebell',1)
        potion.heat=.2
        self.assertIn('nonzero heat',cold_stir_enclosure(potion,.001)['reasons'])
        potion.heat=0;potion.rotation_tween=RotationTween()
        self.assertIn('rotation controller present',cold_stir_enclosure(potion,.001)['reasons'])
        potion.rotation_tween=None;potion.path_sections[0]['teleport']=True
        self.assertIn('crystal path',cold_stir_enclosure(potion,.001)['reasons'])
        box=(Interval(-100,100),Interval(-100,100))
        self.assertIsNotNone(clean_region_reason(self.world,'Water',box))
        zone,shape=self.world.zones['Water'].shapes[0]
        self.assertIsNotNone(clean_region_reason(self.world,'Water',
            (Interval(shape[1]),Interval(shape[2]))))

    def test_adaptive_budget_keeps_full_parameter_domain(self):
        source=PotionSession(self.world);source.add('Firebell',1)
        domain=Interval(.0005,.06)
        result=adaptive_cold_stir_enclosure(source,domain,node_budget=2,box_budget=3)
        self.assertLessEqual(result['parameterBoxesAttempted'],3)
        from fractions import Fraction
        leaves=sorted((Fraction(leaf['parameter'][0]),Fraction(leaf['parameter'][1]))
                      for leaf in result['parameterLeaves'])
        self.assertEqual(leaves[0][0],domain.lo);self.assertEqual(leaves[-1][1],domain.hi)
        for left,right in zip(leaves,leaves[1:]):self.assertEqual(left[1],right[0])
        self.assertFalse(result['loopEnclosureComplete'])
        self.assertTrue(result['unresolved'])

    def test_wide_cold_stir_enclosure_matches_actual_replays(self):
        source=PotionSession(self.world);source.add('Firebell',1)
        result=cold_stir_enclosure(source,Interval(.05,.06),node_budget=100)
        self.assertTrue(result['loopEnclosureComplete'])
        for fraction in (.05,.05323,.06):
            potion=PotionSession(self.world);potion.add('Firebell',1);potion.stir(fraction)
            self.assertTrue(any(len(node.path.pending)==len(potion.pending) and
                all(bound.contains(value) for box,point in zip(
                    (node.path.position,)+node.path.pending,(potion.position,)+tuple(potion.pending))
                    for bound,value in zip(box,point)) for node in result['terminal']))


if __name__=='__main__':unittest.main()
