import sys
import unittest
from engine.brew import BrewWorld,PotionSession,ZoneIndex
from unittest.mock import patch
from optimizer.intervals import Interval,CarriedPathBox
from optimizer.ingredient_intervals import ingredient_path_enclosure
from optimizer.crystal_intervals import crystal_endpoint_enclosure


@unittest.skipUnless(sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12),
                     'Crystal endpoint sum requires CPython 3.12')
class CrystalIntervalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=BrewWorld()
        cls.crystals=[name for name,item in cls.world.ingredients.items() if item['is_teleportation']]

    def test_all_crystal_grinding_paths_use_graphics_spacing(self):
        for name in self.crystals:
            result=ingredient_path_enclosure(self.world,name,Interval(0,1),4096,allow_crystal=True)
            self.assertTrue(result['pathEnclosureComplete'])
            for grind in (0,.25,.5,.75,1):
                actual=self.world.ingredient_path(name,grind,graphics=True)
                self.assertTrue(any(len(path)==len(actual) and all(bound.contains(value)
                    for box,point in zip(path,actual) for bound,value in zip(box,point))
                    for path in result['paths']))

    def test_completed_transit_endpoint_and_unmoved_tail(self):
        with patch.dict(self.world.zones,Water=ZoneIndex({},self.world.geometry['indicator_radius'])):
            for name in self.crystals:
                for grind in (0,.5,1):
                    potion=PotionSession(self.world);potion.add(name,grind)
                    count=len(potion.pending);potion.add('Waterbloom',1)
                    before=CarriedPathBox(potion.position,tuple(potion.pending))
                    result=crystal_endpoint_enclosure(before,count)
                    self.assertTrue(result['endpointEnclosureComplete'])
                    potion.stir(.001)
                    self.assertTrue(any(len(path.pending)==len(potion.pending) and all(bound.contains(value)
                        for box,point in zip((path.position,)+path.pending,
                                             (potion.position,)+tuple(potion.pending))
                        for bound,value in zip(box,point)) for path in result['terminal']))
                    self.assertFalse(result['survivalProved'])
