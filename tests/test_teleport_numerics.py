"""Source-derived numeric checks; these do not claim full teleport parity."""

import unittest
from unittest.mock import patch
from engine.brew import BrewWorld, ZoneIndex, curve_value


class TeleportNumericsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = BrewWorld()

    def test_installed_unity_physics_timestep_and_layers(self):
        self.assertAlmostEqual(self.world.fixed_dt, .005, places=7)
        self.assertTrue(self.world.layers_collide(8, 8))
        self.assertFalse(self.world.layers_collide(0, 8))
        self.assertFalse(self.world.layers_collide(8, 0))

    def test_weighted_curve_known_bezier_point(self):
        curve = {"m_Curve": [
            {"time": 0, "value": 0, "outSlope": 2, "inSlope": 0,
             "weightedMode": 2, "outWeight": .8, "inWeight": 0},
            {"time": 1, "value": 1, "inSlope": 0, "outSlope": 0,
             "weightedMode": 1, "inWeight": .1, "outWeight": 0}]}
        # Parametric Bezier midpoint: x=.7625, y=1.1.
        self.assertAlmostEqual(curve_value(curve, .7625), 1.1, places=12)

    def test_shrunken_indicator_leaves_edge_contact(self):
        index = ZoneIndex({"strong_danger": [["circle", .7, 0, .1]]}, .74)
        self.assertEqual(index.at((0, 0)), {"strong_danger"})
        self.assertEqual(index.at((0, 0), .5), set())

    def test_strong_and_weak_fade_damage_resource_totals(self):
        for zone, expected in (("strong_danger", .6), ("weak_danger", .2)):
            index = ZoneIndex({zone: [["circle", 0, 0, 10]]}, self.world.geometry["indicator_radius"])
            with patch.dict(self.world.zones, Water=index):
                for fade_out in (True, False):
                    result = self.world.teleport_fade_profile("Water", (0, 0), fade_out)
                    self.assertAlmostEqual(result["damage"], expected, places=7)

    def test_fade_edge_damage_accounts_for_collider_shrink(self):
        index = ZoneIndex({"strong_danger": [["circle", .7, 0, .1]]}, self.world.geometry["indicator_radius"])
        with patch.dict(self.world.zones, Water=index):
            result = self.world.teleport_fade_profile("Water", (0, 0), True, 1000)
            self.assertGreater(result["damage"], 0)
            self.assertLess(result["damage"], .6)
            self.assertEqual(result["profile"][-1]["zones"], [])

    def test_all_extracted_animation_curves_can_be_evaluated(self):
        for settings in self.world.settings.values():
            for value in settings.values():
                if isinstance(value, dict) and value.get("m_Curve"):
                    keys = value["m_Curve"]
                    middle = (keys[0]["time"] + keys[-1]["time"]) / 2
                    self.assertIsInstance(curve_value(value, middle), (float, int))


if __name__ == "__main__":
    unittest.main()
