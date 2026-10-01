import sys
import unittest
from unittest.mock import patch
from engine.brew import BrewWorld,PotionSession,ZoneIndex
from optimizer.intervals import Interval,CarriedPathBox
from optimizer.crystal_timing import cold_crystal_timing
from optimizer.crystal_damage import fade_damage_enclosure,zone_contact_sets


@unittest.skipUnless(sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12),
                     'Fade damage sum requires CPython 3.12')
class CrystalDamageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world=BrewWorld()

    def test_possible_and_guaranteed_contacts_keep_boundary_uncertain(self):
        index=ZoneIndex({'strong_danger':[['circle',0.,0.,1.]]},.1)
        possible,guaranteed=zone_contact_sets(index,(Interval(-.1,.1),Interval(-.1,.1)),.05)
        self.assertIn('strong_danger',guaranteed)
        possible,guaranteed=zone_contact_sets(index,(Interval(.9,1.2),Interval(0)),.05)
        self.assertIn('strong_danger',possible);self.assertNotIn('strong_danger',guaranteed)

    def test_fade_damage_matches_original_loop_with_health_abort_disabled(self):
        index=ZoneIndex({'strong_danger':[['circle',0.,0.,100.]]},self.world.geometry['indicator_radius'])
        with patch.dict(self.world.zones,Water=index):
            name=next(name for name,item in self.world.ingredients.items() if item['is_teleportation'])
            potion=PotionSession(self.world);potion.add(name,1)
            path=CarriedPathBox(potion.position,tuple(potion.pending))
            timing=cold_crystal_timing(self.world,path,len(potion.pending))
            fade=fade_damage_enclosure(self.world,'Water',path.position,timing['fadeOutProgress'])
            original=potion._health_step;extra=[]
            def observe(position,zones=None,extra_damage=0.):
                extra.append(extra_damage)
                original(position,zones=set(),extra_damage=0.)
            potion._health_step=observe;potion.stir(.001)
            for frame,value in zip(fade['frames'],extra):self.assertTrue(frame['extraDamage'].contains(value))
            fade_in=fade_damage_enclosure(self.world,'Water',
                (Interval(potion.position[0]),Interval(potion.position[1])),
                timing['fadeInProgress'],fade_out=False)
            phases=potion.teleports[0]['frames']
            transit_count=sum(frame['phase']=='transit' for frame in phases)
            observed_in=extra[timing['fadeOutFrames']+transit_count:]
            self.assertEqual(len(observed_in),len(fade_in['frames']))
            for frame,value in zip(fade_in['frames'],observed_in):self.assertTrue(frame['extraDamage'].contains(value))
            self.assertEqual(float(fade['frames'][-1]['extraDamage'].hi),0.)
            self.assertFalse(fade['survivalProved'])
