import sys
import unittest
from engine.brew import BrewWorld,PotionSession
from optimizer.intervals import Interval
from optimizer.cold_pour import cold_pour_enclosure
from optimizer.ordinary_stir import ordinary_stir
from optimizer.cold_stir import clean_region_reason


@unittest.skipUnless(sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12),
                     'Cold interval actions require CPython 3.12')
class ColdPourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world=BrewWorld()

    def source(self):
        potion=PotionSession(self.world);potion.add('Firebell',1);potion.stir(.06)
        return potion

    def contains(self,path,potion):
        return len(path.pending)==len(potion.pending) and all(bound.contains(value)
            for box,point in zip((path.position,)+path.pending,(potion.position,)+tuple(potion.pending))
            for bound,value in zip(box,point))

    def test_interval_duration_covers_partial_and_full_frames(self):
        result=cold_pour_enclosure(self.source(),Interval(.005,.03),strength=.5)
        self.assertTrue(result['supported']);self.assertTrue(result['loopEnclosureComplete'])
        for seconds in (.005,.015,1/60,.02,.03):
            potion=self.source();potion.pour(seconds,.5)
            self.assertTrue(any(self.contains(node.path,potion) for node in result['terminal']))
        self.assertFalse(result['brewingRecipeExcluded'])

    def test_pouring_then_stirring_preserves_pending_path(self):
        result=cold_pour_enclosure(self.source(),Interval(.005,.015),strength=.5)
        terminals=[]
        for node in result['terminal']:
            stirred=ordinary_stir(node.path,.001,self.world.spacing,
                self.world.settings['RecipeMapManagerIndicatorSettings']['indicatorSpeed'],
                node_budget=100,region_guard=lambda box:clean_region_reason(self.world,'Water',box))
            self.assertTrue(stirred['loopEnclosureComplete'])
            terminals.extend(stirred['terminal'])
        for seconds in (.005,.01,.015):
            potion=self.source();potion.pour(seconds,.5);potion.stir(.001)
            self.assertTrue(any(self.contains(node.path,potion) for node in terminals))

    def test_center_and_unsupported_rotation_or_budget(self):
        centered=PotionSession(self.world)
        self.assertTrue(cold_pour_enclosure(centered,Interval(0,.01))['loopEnclosureComplete'])
        potion=self.source();potion.rotation=10
        self.assertFalse(cold_pour_enclosure(potion,.01)['supported'])
        limited=cold_pour_enclosure(self.source(),.1,node_budget=1)
        self.assertFalse(limited['loopEnclosureComplete']);self.assertTrue(limited['unresolved'])

    def test_max_strength_duration_crosses_speed_growth_threshold(self):
        result=cold_pour_enclosure(self.source(),Interval(.99,1.02),strength=1)
        self.assertTrue(result['loopEnclosureComplete'])
        for seconds in (.99,1.,1.02):
            potion=self.source();potion.pour(seconds,1)
            self.assertTrue(any(self.contains(node.path,potion) for node in result['terminal']))


if __name__=='__main__':unittest.main()
