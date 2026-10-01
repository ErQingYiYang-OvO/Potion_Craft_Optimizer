import unittest

from engine.rotation import RotationTween
from playground.serve import WORLD


class RotationTweenTests(unittest.TestCase):
    settings=WORLD.settings['RecipeMapManagerIndicatorSettings']

    def test_target_changes_before_visual_and_new_grain_restarts_tween(self):
        tween=RotationTween();tween.salt_batch(self.settings,'moon',1)
        self.assertAlmostEqual(tween.target,.36,places=6)
        self.assertEqual(tween.visual,0)
        tween.advance(self.settings['moonSaltIndicatorRotationTime']/2)
        self.assertAlmostEqual(tween.visual,.18,places=6)
        tween.salt_batch(self.settings,'moon',1)
        self.assertAlmostEqual(tween.target,.72,places=6)
        self.assertAlmostEqual(tween.visual,.18,places=6)
        tween.advance(self.settings['moonSaltIndicatorRotationTime']/2)
        self.assertAlmostEqual(tween.visual,.45,places=6)

    def test_short_arc_wraps_at_zero_without_long_rotation(self):
        tween=RotationTween(target=359.9,visual=359.9)
        tween.rotate_to(.1,.05)
        self.assertAlmostEqual(tween.end_unwrapped-tween.start_unwrapped,.2,places=3)
        tween.advance(.1)
        self.assertAlmostEqual(tween.visual,.1,places=6)
        self.assertFalse(tween.active)

    def test_opposite_grains_cancel_target_but_continue_from_current_visual(self):
        tween=RotationTween();tween.salt_batch(self.settings,'moon',1)
        tween.advance(self.settings['moonSaltIndicatorRotationTime']/2)
        tween.salt_batch(self.settings,'sun',1)
        self.assertEqual(tween.target,0)
        self.assertAlmostEqual(tween.visual,.18,places=6)
        tween.advance(.1)
        self.assertEqual(tween.visual,0)


if __name__=='__main__':unittest.main()
