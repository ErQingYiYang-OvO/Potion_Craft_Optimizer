import copy
import unittest

from engine.brew import PotionSession, rotate_about
from optimizer.state import future_state_key
from playground.serve import WORLD, session_state, session_from_state, replay


class RotationSessionTests(unittest.TestCase):
    def test_partial_animation_rotates_pending_and_roundtrips(self):
        session = PotionSession(WORLD)
        session.add('Waterbloom', 1)
        initial = copy.deepcopy(session.pending)
        session.rotate_salt('moon', 100, deferred=True)
        self.assertEqual(session.rotation, 0)
        self.assertGreater(session.target_rotation, 35.99)
        self.assertEqual(session.pending, initial)
        session.wait(.025)
        self.assertAlmostEqual(session.rotation, session.target_rotation/2, places=4)
        for point, original in zip(session.pending, initial):
            expected = rotate_about(original, session.position, session.rotation)
            self.assertAlmostEqual(point[0], expected[0], places=8)
            self.assertAlmostEqual(point[1], expected[1], places=8)
        restored = session_from_state(session_state(session))
        self.assertEqual(future_state_key(session), future_state_key(restored))
        session.wait(.04); restored.wait(.04)
        self.assertEqual(session_state(session), session_state(restored))
        self.assertFalse(session.rotation_tween.active)

    def test_add_during_animation_has_original_direction_then_follows_callbacks(self):
        session = PotionSession(WORLD)
        session.rotate_salt('moon', 100, deferred=True)
        session.wait(.025)
        session.add('Waterbloom', 1)
        normal = PotionSession(WORLD); normal.add('Waterbloom', 1)
        self.assertEqual(session.pending, normal.pending)
        angle_before = session.rotation
        session.wait(.04)
        for point, original in zip(session.pending, normal.pending):
            expected = rotate_about(original, session.position, session.rotation-angle_before)
            self.assertAlmostEqual(point[0], expected[0], places=8)
            self.assertAlmostEqual(point[1], expected[1], places=8)

    def test_target_angle_drives_grade_before_visual_catches_up(self):
        effect = next(e for e in WORLD.bases['Oil']['effects'] if abs(e['Rotation']) > 1)
        session = PotionSession(WORLD, base='Oil', position=(effect['Position']['x'], effect['Position']['y']))
        session.rotate_salt('moon', 100, deferred=True)
        actual = session.nearest_effect()
        expected = next(e for e in WORLD.effect_scores('Oil', session.position, session.target_rotation)
                        if e['name'] not in session.collected)
        self.assertEqual(actual, expected)
        self.assertNotEqual(actual, next(iter(WORLD.effect_scores('Oil', session.position, session.rotation))))

    def test_dispatcher_replay_preserves_timing_and_rejects_fractional_grains(self):
        operations = [dict(kind='salt',salt='moon',amount=100,deferred=True),
                      dict(kind='wait',seconds=.025),dict(kind='add',name='Waterbloom',grind=1)]
        state = replay('Water', operations)['state']
        self.assertTrue(state['rotation_tween']['active'])
        self.assertAlmostEqual(state['rotation'], 18, places=3)
        with self.assertRaises(ValueError):
            replay('Water', [dict(kind='salt',salt='moon',amount=.5,deferred=True)])

    def test_active_animation_is_part_of_future_state(self):
        session = PotionSession(WORLD); session.rotate_salt('moon',100,deferred=True)
        cold = PotionSession(WORLD)
        self.assertEqual(session.position, cold.position)
        self.assertEqual(session.rotation, cold.rotation)
        self.assertNotEqual(future_state_key(session), future_state_key(cold))

    def test_crystal_animation_also_advances_rotation_time(self):
        session = PotionSession(WORLD)
        session.add('CloudCrystal', 0)
        session.rotate_salt('moon', 1, deferred=True)
        session.stir(1)
        self.assertFalse(session.rotation_tween.active)
        self.assertEqual(session.rotation, session.target_rotation)
        self.assertEqual(len(session.teleports), 1)


if __name__ == '__main__': unittest.main()
