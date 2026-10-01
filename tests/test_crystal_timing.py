import sys
import unittest
from collections import Counter
from unittest.mock import patch
from engine.brew import BrewWorld,PotionSession,ZoneIndex
from optimizer.intervals import CarriedPathBox,UnresolvedArithmetic
from optimizer.crystal_timing import cold_crystal_timing


@unittest.skipUnless(sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12),
                     'Crystal timing sum requires CPython 3.12')
class CrystalTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world=BrewWorld()

    def test_all_crystals_cold_phase_counts_and_duration(self):
        with patch.dict(self.world.zones,Water=ZoneIndex({},self.world.geometry['indicator_radius'])):
            for name,item in self.world.ingredients.items():
                if not item['is_teleportation']:continue
                for grind in (0,.5,1):
                    potion=PotionSession(self.world);potion.add(name,grind)
                    result=cold_crystal_timing(self.world,CarriedPathBox(potion.position,tuple(potion.pending)),len(potion.pending))
                    potion.stir(.001);record=potion.teleports[0]
                    phases=Counter(frame['phase'] for frame in record['frames'])
                    self.assertEqual(phases['fade_out'],result['fadeOutFrames'])
                    self.assertEqual(phases['fade_in'],result['fadeInFrames'])
                    self.assertLessEqual(result['transitFrames'][0],phases['transit'])
                    self.assertGreaterEqual(result['transitFrames'][1],phases['transit'])
                    self.assertTrue(result['elapsed'].contains(record['duration']))

    def test_frame_budget_is_unresolved(self):
        potion=PotionSession(self.world)
        name=next(name for name,item in self.world.ingredients.items() if item['is_teleportation'])
        potion.add(name,1)
        with self.assertRaises(UnresolvedArithmetic):
            cold_crystal_timing(self.world,CarriedPathBox(potion.position,tuple(potion.pending)),len(potion.pending),frame_budget=1)
