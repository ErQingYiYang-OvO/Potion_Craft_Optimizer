import sys
import unittest
from unittest.mock import patch
from engine.brew import BrewWorld,PotionSession,ZoneIndex,PotionFailed
from optimizer.intervals import CarriedPathBox,Interval
from optimizer.crystal_survival import cold_crystal_survival,map_contains_box


@unittest.skipUnless(sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12),
                     'Crystal survival uses CPython 3.12 sum bounds')
class CrystalSurvivalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world=BrewWorld()

    def test_all_real_water_crystals_without_disabling_damage(self):
        for name,item in self.world.ingredients.items():
            if not item['is_teleportation']:continue
            for grind in (0,.5,1):
                potion=PotionSession(self.world);potion.add(name,grind)
                result=cold_crystal_survival(self.world,'Water',
                    CarriedPathBox(potion.position,tuple(potion.pending)),len(potion.pending))
                potion.stir(.001)
                self.assertTrue(result['survivalProvedUnderModel'])
                self.assertTrue(result['minimumHealth'].contains(potion.minimum_health))
                self.assertTrue(result['finalHealthConditionalOnCompletion'].contains(potion.health))

    def test_lethal_fade_and_exclusive_upper_map_edge_cannot_pass(self):
        name=next(name for name,item in self.world.ingredients.items() if item['is_teleportation'])
        index=ZoneIndex({'strong_danger':[['circle',0.,0.,100.]]},self.world.geometry['indicator_radius'])
        with patch.dict(self.world.zones,Water=index):
            potion=PotionSession(self.world);potion.add(name,1);potion.health=.01
            result=cold_crystal_survival(self.world,'Water',
                CarriedPathBox(potion.position,tuple(potion.pending)),len(potion.pending),health=.01)
            self.assertFalse(result['survivalProvedUnderModel'])
            with self.assertRaises(PotionFailed):potion.stir(.001)
        size=self.world.bases['Water']['map_size']
        self.assertTrue(map_contains_box(self.world,'Water',(Interval(-size['x']/2),Interval(0))))
        self.assertFalse(map_contains_box(self.world,'Water',(Interval(size['x']/2),Interval(0))))

    def test_oil_and_wine_regeneration_keep_health_enclosed(self):
        name=next(name for name,item in self.world.ingredients.items() if item['is_teleportation'])
        for base in ('Oil','Wine'):
            potion=PotionSession(self.world,base);potion.add(name,.5)
            potion.health=.3;potion.minimum_health=.3
            result=cold_crystal_survival(self.world,base,
                CarriedPathBox(potion.position,tuple(potion.pending)),len(potion.pending),health=.3)
            potion.stir(.001)
            self.assertTrue(result['survivalProvedUnderModel'])
            self.assertTrue(result['minimumHealth'].contains(min(.3,min(frame['health'] for frame in potion.teleports[0]['frames']))))
            self.assertTrue(result['finalHealthConditionalOnCompletion'].contains(potion.health))
