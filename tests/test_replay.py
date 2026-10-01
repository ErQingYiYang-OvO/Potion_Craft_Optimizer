"""Replay serialized GUI operations through the same backend."""

import unittest

from engine.brew import PotionSession
from playground.serve import WORLD, perform, replay, session_state


class ReplayTests(unittest.TestCase):
    def test_replay_reproduces_mixed_operations_and_retains_machine_commands(self):
        operations = [
            {"kind": "add", "name": "CloudCrystal", "grind": 0},
            {"kind": "add", "name": "Waterbloom", "grind": 0},
            {"kind": "stir", "fraction": 1},
            {"kind": "pour", "seconds": .25, "strength": 1},
            {"kind": "salt", "salt": "moon", "amount": 25},
            {"kind": "pump", "angle": 25, "seconds": 1},
            {"kind": "wait", "seconds": .1},
        ]
        session = PotionSession(WORLD)
        for action in operations:
            perform(session, action)
        result = replay("Water", operations)
        self.assertEqual(result["state"], session_state(session))
        self.assertEqual(result["operations"], operations)
        self.assertIsNone(result["failure"])

    def test_replay_keeps_observation_origin_separate_from_recipe_start(self):
        v = min(WORLD.vortices["Water"], key=lambda v: v["entry"]["x"]**2+v["entry"]["y"]**2)
        result = replay("Water", [{"kind": "vortex_demo", "name": v["name"]},
                                  {"kind": "wait", "seconds": 12}])
        self.assertEqual(result["state"]["start_mode"], "vortex_demo")
        self.assertEqual(result["state"]["teleports"][0]["kind"], "vortex")
        self.assertIsNone(result["failure"])


if __name__ == "__main__":
    unittest.main()
