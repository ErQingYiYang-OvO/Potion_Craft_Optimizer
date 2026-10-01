"""Regression cases for interleaved Potion Craft brewing operations."""

import unittest
from engine.brew import BrewWorld, PotionSession, distance, rotate_about
from playground.serve import perform, session_from_state, session_state


class BrewingRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = BrewWorld()

    def partial_potion(self):
        potion = PotionSession(self.world)
        potion.add("Firebell", 1)
        potion.stir(.4)
        return potion

    def assertPointClose(self, a, b):
        self.assertLess(distance(a, b), 1e-8)

    def test_pour_preserves_unconsumed_shape_and_length(self):
        potion = self.partial_potion()
        start, points, length = potion.position, potion.pending[:], potion.remaining_length
        potion.pour(.25)
        self.assertLess(distance(potion.position, (0, 0)), distance(start, (0, 0)))
        self.assertEqual(len(points), len(potion.pending))
        self.assertAlmostEqual(length, potion.remaining_length, places=8)
        shift = (potion.position[0] - start[0], potion.position[1] - start[1])
        for before, after in zip(points, potion.pending):
            self.assertPointClose((before[0] + shift[0], before[1] + shift[1]), after)

    def test_sun_rotates_clockwise_about_current_bottle(self):
        potion = self.partial_potion()
        start, points, length = potion.position, potion.pending[:], potion.remaining_length
        potion.rotate_salt("sun", 250)
        delta = -250 * self.world.settings["RecipeMapManagerIndicatorSettings"]["sunSaltIndicatorRotationAngle"]
        self.assertAlmostEqual(potion.rotation, delta % 360)
        self.assertPointClose(potion.position, start)
        for before, after in zip(points, potion.pending):
            self.assertPointClose(after, rotate_about(before, start, delta))
        self.assertAlmostEqual(length, potion.remaining_length, places=8)

    def test_moon_reverses_sun_path_rotation(self):
        potion = self.partial_potion()
        points = potion.pending[:]
        potion.rotate_salt("sun", 250)
        potion.rotate_salt("moon", 250)
        self.assertAlmostEqual(potion.rotation, 0)
        for before, after in zip(points, potion.pending):
            self.assertPointClose(before, after)

    def test_new_ingredient_is_not_rotated_by_bottle(self):
        potion = self.partial_potion()
        potion.rotate_salt("sun", 250)
        old_tail, count = potion.pending[-1], len(potion.pending)
        displacement = self.world.ingredient_path("Waterbloom", 1)[-1]
        potion.add("Waterbloom", 1)
        self.assertPointClose(potion.pending[count-1], old_tail)
        self.assertPointClose(potion.pending[-1], (old_tail[0] + displacement[0],
                                                   old_tail[1] + displacement[1]))

    def test_partial_stir_then_pour_salt_add_and_finish(self):
        potion = self.partial_potion()
        potion.pour(.25)
        potion.rotate_salt("moon", 80)
        potion.add("Waterbloom", .5)
        endpoint = potion.pending[-1]
        potion.stir()
        self.assertPointClose(potion.position, endpoint)
        self.assertFalse(potion.pending)
        self.assertEqual(sum(potion.ingredients_used.values()), 2)

    def test_pour_rotates_existing_path_towards_upright(self):
        potion = self.partial_potion()
        potion.rotate_salt("moon", 100)
        before = potion.rotation
        length = potion.remaining_length
        potion.pour(.25)
        self.assertLess(potion.rotation, before)
        self.assertAlmostEqual(length, potion.remaining_length, places=8)

    def test_pour_to_center_keeps_pending_path(self):
        potion = self.partial_potion()
        potion.rotate_salt("moon", 250)
        length = potion.remaining_length
        potion.pour_to_center()
        self.assertPointClose(potion.position, (0, 0))
        self.assertAlmostEqual(potion.rotation, 0, places=6)
        self.assertAlmostEqual(potion.remaining_length, length, places=8)

    def test_heat_collects_effect_without_consuming_path(self):
        effect = self.world.bases["Water"]["effects"][0]
        p = effect["Position"]
        potion = PotionSession(self.world, position=(p["x"], p["y"]), rotation=effect["Rotation"])
        potion.add("Firebell", .5)
        points = potion.pending[:]
        potion.heat_effect()
        self.assertEqual(potion.pending, points)
        self.assertEqual(potion.effects, [(effect["name"], 3)])
        with self.assertRaises(ValueError):
            potion.heat_effect(effect["name"])

    def test_actual_life_and_void_salt_asset_values(self):
        potion = self.partial_potion()
        potion.health = .5
        potion.life_salt(10)
        self.assertAlmostEqual(potion.health, .54, places=7)
        length, position = potion.remaining_length, potion.position
        potion.void_salt(10)
        self.assertAlmostEqual(length - potion.remaining_length, .1, places=7)
        self.assertEqual(potion.position, position)

    def test_gui_roundtrip_preserves_pending_state(self):
        potion = self.partial_potion()
        state = session_state(potion)
        restored = session_from_state(state)
        perform(restored, {"kind": "pour", "seconds": .25, "strength": 1})
        state = session_state(restored)
        self.assertEqual(state["path_sections"], potion.path_sections)
        self.assertAlmostEqual(state["remaining_length"], potion.remaining_length, places=8)
        self.assertTrue(state["pending"])
        restored = session_from_state(state)
        perform(restored, {"kind": "salt", "salt": "moon", "amount": 250})
        perform(restored, {"kind": "add", "name": "Waterbloom", "grind": 1})
        endpoint = restored.pending[-1]
        perform(restored, {"kind": "stir", "fraction": 1})
        self.assertPointClose(restored.position, endpoint)

    def test_sections_survive_partial_stir_and_void_salt(self):
        potion = self.partial_potion()
        potion.add("Waterbloom", .5)
        self.assertEqual([s["name"] for s in potion.path_sections], ["Firebell", "Waterbloom"])
        potion.stir(.1)
        potion.void_salt(10)
        self.assertEqual(sum(s["point_count"] for s in potion.path_sections), len(potion.pending))
        potion.stir()
        self.assertEqual(potion.path_sections, [])


if __name__ == "__main__":
    unittest.main()
