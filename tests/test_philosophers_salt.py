"""Independent resource-budget and target-selection checks for salt pulses."""

import unittest
from unittest.mock import patch

from engine.brew import BrewWorld, PotionSession, ZoneIndex, distance


class PhilosophersSaltTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = BrewWorld()

    def effect(self, name, x, angle=0):
        return {"name": name, "Position": {"x": x, "y": 0}, "Rotation": angle}

    def test_units_have_translation_budget_and_keep_pending_length(self):
        base = {**self.world.bases["Water"], "effects": [self.effect("target", 10)]}
        with patch.dict(self.world.bases, Water=base), patch.dict(self.world.zones, Water=ZoneIndex({}, .74)):
            potion = PotionSession(self.world)
            potion.add("Firebell", 1)
            original_length = potion.remaining_length
            original_end = potion.pending[-1]
            potion.philosophers_salt(10)
            self.assertAlmostEqual(potion.position[0], .225, places=7)
            self.assertAlmostEqual(potion.position[1], 0)
            self.assertAlmostEqual(potion.remaining_length, original_length, places=9)
            self.assertAlmostEqual(potion.pending[-1][0]-original_end[0], .225, places=7)
            self.assertEqual(potion.salts_used["philosopher"], 10)

    def test_at_effect_center_rotation_uses_salt_budget(self):
        base = {**self.world.bases["Water"], "effects": [self.effect("target", 0, 90)]}
        with patch.dict(self.world.bases, Water=base), patch.dict(self.world.zones, Water=ZoneIndex({}, .74)):
            potion = PotionSession(self.world)
            potion.philosophers_salt(10)
            self.assertEqual(potion.position, (0., 0.))
            self.assertAlmostEqual(potion.rotation, 3.6, places=6)

    def test_collected_effect_is_skipped_and_target_does_not_overshoot(self):
        base = {**self.world.bases["Water"], "effects": [self.effect("used", .01), self.effect("target", -.1)]}
        with patch.dict(self.world.bases, Water=base), patch.dict(self.world.zones, Water=ZoneIndex({}, .74)):
            potion = PotionSession(self.world, collected={"used"})
            potion.philosophers_salt(100)
            self.assertLess(distance(potion.position, (-.1, 0)), 1e-12)
            self.assertEqual(potion.salts_used["philosopher"], 100)

    def test_swamp_reduces_translation_and_rotation_budgets(self):
        base = {**self.world.bases["Water"], "effects": [self.effect("target", 10)]}
        zones = ZoneIndex({"swamp": [["circle", 0, 0, 100]]}, .74)
        with patch.dict(self.world.bases, Water=base), patch.dict(self.world.zones, Water=zones):
            potion = PotionSession(self.world)
            potion.philosophers_salt(10)
            self.assertAlmostEqual(potion.position[0], .225*.6777777671813965, places=7)


if __name__ == "__main__":
    unittest.main()
