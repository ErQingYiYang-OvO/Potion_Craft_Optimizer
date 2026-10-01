import unittest

from engine.brew import PotionSession
from playground.serve import WORLD
from optimizer.state import future_state_key


class StateTests(unittest.TestCase):
    def test_rotation_before_or_after_adding_has_different_remaining_path(self):
        first=PotionSession(WORLD);first.add('Waterbloom',1);first.rotate_salt('moon',100)
        second=PotionSession(WORLD);second.rotate_salt('moon',100);second.add('Waterbloom',1)
        self.assertEqual(first.position,second.position)
        self.assertEqual(first.rotation,second.rotation)
        self.assertEqual(first.ingredients_used,second.ingredients_used)
        self.assertNotEqual(future_state_key(first),future_state_key(second))

    def test_irrelevant_history_does_not_duplicate_a_cold_center_state(self):
        first=PotionSession(WORLD)
        second=PotionSession(WORLD);second.wait(.2)
        self.assertNotEqual(first.actions,second.actions)
        self.assertEqual(future_state_key(first),future_state_key(second))


if __name__=='__main__':unittest.main()
