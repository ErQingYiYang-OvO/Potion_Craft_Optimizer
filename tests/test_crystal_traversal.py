"""Crystal geometry/state regressions, with explicit approximate timing."""

import unittest
from unittest.mock import patch

from engine.brew import BrewWorld, PotionSession, ZoneIndex, distance, rotate_about
from playground.serve import session_from_state, session_state


class CrystalTraversalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = BrewWorld()
        cls.crystals = [name for name, item in cls.world.ingredients.items() if item["is_teleportation"]]

    def empty_zones(self):
        return ZoneIndex({}, self.world.geometry["indicator_radius"])

    def test_all_nine_crystals_land_at_ground_and_unground_endpoints(self):
        self.assertEqual(len(self.crystals), 9)
        with patch.dict(self.world.zones, Water=self.empty_zones()):
            for name in self.crystals:
                for grind in (0, .5, 1):
                    with self.subTest(name=name, grind=grind):
                        potion = PotionSession(self.world)
                        potion.add(name, grind)
                        expected = potion.pending[-1]
                        potion.stir(.001)
                        self.assertLess(distance(potion.position, expected), 1e-9)
                        self.assertFalse(potion.pending)
                        self.assertFalse(potion.path_sections)
                        self.assertEqual({frame["phase"] for frame in potion.teleports[0]["frames"]},
                                         {"fade_out", "transit", "fade_in"})

    def test_consecutive_crystals_and_following_herb_need_separate_stirs(self):
        with patch.dict(self.world.zones, Water=self.empty_zones()):
            potion = PotionSession(self.world)
            potion.add(self.crystals[0], 1)
            first_end = potion.pending[-1]
            potion.add(self.crystals[1], 1)
            second_end = potion.pending[-1]
            potion.add("Waterbloom", 1)
            final_end = potion.pending[-1]
            tail = list(potion.pending[potion.path_sections[0]["point_count"]:])
            potion.stir()
            self.assertLess(distance(potion.position, first_end), 1e-9)
            self.assertEqual(potion.pending, tail)
            potion.stir()
            self.assertLess(distance(potion.position, second_end), 1e-9)
            self.assertEqual(len(potion.teleports), 2)
            self.assertEqual(potion.path_sections[0]["name"], "Waterbloom")
            potion.stir()
            self.assertLess(distance(potion.position, final_end), 1e-9)

    def test_rotation_pouring_and_gui_roundtrip_keep_crystal_sections(self):
        with patch.dict(self.world.zones, Water=self.empty_zones()):
            potion = PotionSession(self.world)
            potion.add(self.crystals[0], .5)
            initial_end = potion.pending[-1]
            potion.rotate_salt("sun", 250)
            expected = rotate_about(initial_end, potion.position, -90.00000357627869)
            self.assertLess(distance(expected, potion.pending[-1]), 1e-9)
            potion.pour(.1)
            potion.add("Waterbloom", 1)
            count = potion.path_sections[0]["point_count"]
            tail = potion.pending[count:]
            potion.stir()
            self.assertEqual(potion.pending, tail)
            restored = session_from_state(session_state(potion))
            self.assertEqual(restored.pending, potion.pending)
            self.assertEqual(restored.path_sections, potion.path_sections)
            self.assertEqual(restored.teleports, potion.teleports)

    def test_void_salt_shortens_crystal_landing(self):
        with patch.dict(self.world.zones, Water=self.empty_zones()):
            potion = PotionSession(self.world)
            potion.add(self.crystals[0], 1)
            original = potion.pending[-1]
            potion.void_salt(100)
            expected = potion.pending[-1]
            self.assertGreater(distance(original, expected), .1)
            potion.stir()
            self.assertLess(distance(potion.position, expected), 1e-9)

    def synthetic_crystal(self, base="Water"):
        return PotionSession(self.world, base=base, pending=[(2., 0.), (4., 0.)],
                             path_sections=[{"name": "synthetic", "grind": 1,
                                             "teleport": True, "point_count": 2}])

    def test_transit_bypasses_hazards_and_swamp(self):
        zones = ZoneIndex({"strong_danger": [["circle", 2, 0, .5]],
                           "swamp": [["circle", 2, 0, .5]]}, self.world.geometry["indicator_radius"])
        with patch.dict(self.world.zones, Water=zones):
            potion = self.synthetic_crystal()
            potion.stir()
            self.assertEqual(potion.position, (4., 0.))
            self.assertEqual(potion.health, 1)
            self.assertTrue(all(not frame["zones"] for frame in potion.teleports[0]["frames"]
                                if frame["phase"] == "transit"))
            # Traversal uses the whole polyline length, not a frame per vertex.
            duration = sum(frame["phase"] == "transit" for frame in potion.teleports[0]["frames"]) / 60
            self.assertAlmostEqual(duration, 4 / 23.200000047683716, delta=1/60)

    def test_landing_danger_damages_fade_in(self):
        zones = ZoneIndex({"strong_danger": [["circle", 4, 0, .5]]}, self.world.geometry["indicator_radius"])
        with patch.dict(self.world.zones, Water=zones):
            potion = self.synthetic_crystal()
            potion.stir()
            self.assertGreater(potion.health, .39)
            self.assertLess(potion.health, .5)
            self.assertEqual(potion.teleports[0]["frames"][-1]["phase"], "fade_in")


if __name__ == "__main__":
    unittest.main()
