"""Source-derived forcefield, thermal and vortex regression cases."""

import json
import unittest
from unittest.mock import patch

from engine.brew import BrewWorld, PotionSession, PotionFailed, Forcefield, ZoneIndex, distance, xy, DATA
from playground.serve import session_state, session_from_state, perform


def rectangle():
    return Forcefield([{"position": {"x": 0, "y": 0}, "offset": {"x": 0, "y": 0},
                        "paths": [[{"x": x, "y": y} for x, y in [(-1, -1), (1, -1), (1, 1), (-1, 1)]]]}])


class EnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = BrewWorld()

    def test_polygon_closest_point_and_correction_use_circle_radius(self):
        field = rectangle()
        self.assertEqual(field.closest_point((0, 0)), (0, 0))
        self.assertEqual(field.closest_point((3, 2)), (1, 1))
        point, correction = field.correct((2, 0), .74)
        self.assertAlmostEqual(point[0], 1.74)
        self.assertAlmostEqual(correction, .26)

    def test_stirring_spends_path_when_forcefield_blocks_progress(self):
        with patch.dict(self.world.forcefields, Water=rectangle()), patch.dict(self.world.zones, Water=ZoneIndex({}, .74)):
            potion = PotionSession(self.world, pending=[(3., 0.)])
            potion.stir()
            self.assertAlmostEqual(potion.position[0], 1+self.world.geometry["indicator_radius"], places=8)
            self.assertFalse(potion.pending)

    def test_background_bounds_are_half_open(self):
        half = self.world.bases["Water"]["map_size"]["x"]/2
        potion = PotionSession(self.world, position=(-half, 0))
        potion._check_bounds()
        potion.position = (half, 0)
        with self.assertRaises(PotionFailed):
            potion._check_bounds()
        self.assertIn("地图背景矩形", potion.failed_reason)

    def test_parent_transforms_match_local_map_geometry(self):
        for number in (6, 7, 8):
            records = json.loads((DATA/f"level{number}_transform_audit.json").read_text())
            for record in records:
                chain = record["chain"]
                self.assertEqual(chain[-1]["name"], "MapItemsContainer")
                for entry in chain:
                    self.assertEqual(entry["rotation"], {"x": 0, "y": 0, "z": 0, "w": 1})
                    self.assertEqual(entry["scale"]["x"], 1)
                    self.assertEqual(entry["scale"]["y"], 1)
                for entry in chain[1:-1]:
                    self.assertEqual(entry["position"]["x"], 0)
                    self.assertEqual(entry["position"]["y"], 0)

    def test_bellows_heat_and_natural_cooling_instance_values(self):
        potion = PotionSession(self.world)
        potion.pump_bellows(25, 1)
        self.assertAlmostEqual(potion.heat, .42, places=7)
        potion.wait(1)
        self.assertAlmostEqual(potion.heat, .34, places=7)

    def test_pouring_adds_instance_cooling_to_natural_cooling(self):
        potion = PotionSession(self.world, heat=1)
        potion.pour(.5)
        self.assertAlmostEqual(potion.heat, .51, places=7)

    def test_pumping_collects_effect_and_instance_collection_cools_to_zero(self):
        effect = self.world.bases["Water"]["effects"][0]
        potion = PotionSession(self.world, position=xy(effect["Position"]), rotation=effect["Rotation"])
        potion.pump_bellows(60, .5)
        self.assertIn(effect["name"], potion.collected)
        self.assertEqual(potion.effects, [(effect["name"], 3)])
        self.assertEqual(self.world.bellows["heatOnEffectApply"], 0)

    def test_cold_vortex_does_not_move_and_warm_vortex_spirals_clockwise(self):
        v = min(self.world.vortices["Water"], key=lambda v: distance(xy(v["entry"]), (0, 0)))
        center = xy(v["entry"])
        start = (center[0]+.5, center[1])
        potion = PotionSession(self.world, position=start)
        potion.wait(.1)
        self.assertEqual(potion.position, start)
        potion.heat = .8
        potion.wait(1/60)
        self.assertLess(distance(potion.position, center), .5)
        self.assertLess(potion.position[1], start[1])

    def test_all_99_vortices_carry_unconsumed_path_to_their_exit(self):
        count = 0
        for base, vortices in self.world.vortices.items():
            with patch.dict(self.world.zones, **{base: ZoneIndex({}, self.world.geometry["indicator_radius"])}):
                for v in vortices:
                    with self.subTest(base=base, name=v["name"]):
                        center = xy(v["entry"])
                        potion = PotionSession(self.world, base=base, position=center, heat=.8, rotation=45)
                        potion.add("Waterbloom")
                        expected_relative = (potion.pending[-1][0]-center[0], potion.pending[-1][1]-center[1])
                        length = potion.remaining_length
                        potion.wait(1/60)
                        expected = (center[0]+v["exit_local"]["x"], center[1]+v["exit_local"]["y"])
                        self.assertLess(distance(potion.position, expected), 1e-8)
                        self.assertAlmostEqual(potion.remaining_length, length, places=8)
                        self.assertAlmostEqual(potion.pending[-1][0]-potion.position[0], expected_relative[0], places=8)
                        self.assertAlmostEqual(potion.pending[-1][1]-potion.position[1], expected_relative[1], places=8)
                        self.assertEqual(potion.rotation, 45)
                        self.assertEqual(potion.teleports[0]["kind"], "vortex")
                        count += 1
        self.assertEqual(count, 99)

    def test_failed_teleport_has_inspectable_frames_and_failed_state_roundtrip(self):
        zones = ZoneIndex({"strong_danger": [["circle", 0, 0, 2]]}, self.world.geometry["indicator_radius"])
        with patch.dict(self.world.zones, Wine=zones):
            potion = PotionSession(self.world, base="Wine", health=.1, pending=[(5, 0)],
                                   path_sections=[{"name": "synthetic", "point_count": 1, "teleport": True}])
            with self.assertRaises(PotionFailed):
                potion.stir()
            self.assertEqual(potion.teleports[0]["minimum_health"], 0)
            restored = session_from_state(session_state(potion))
            self.assertEqual(restored.failed_reason, potion.failed_reason)
            self.assertEqual(restored.heat, potion.heat)
            with self.assertRaises(ValueError):
                perform(restored, {"kind": "salt", "salt": "life", "amount": 100})


if __name__ == "__main__":
    unittest.main()
