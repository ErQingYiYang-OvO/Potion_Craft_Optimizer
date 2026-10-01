import unittest

try:
    from optimizer.rotated_single import RotatedPlanner
    from optimizer.single_ingredient import seeds, ingredient_seed_path
    from optimizer.search import tier_variants
except ModuleNotFoundError as error:
    if error.name != 'numpy': raise
    RotatedPlanner = None

from playground.serve import WORLD, replay
from engine.brew import PotionSession
import copy


@unittest.skipIf(RotatedPlanner is None, 'Numerical optimizer requires its NumPy runtime')
class TimedRefineTests(unittest.TestCase):
    def test_one_item_seed_geometry_matches_actual_add_for_all_materials(self):
        for name, item in WORLD.ingredients.items():
            for grind in (0., .25, .5, .75, 1.):
                with self.subTest(name=name, grind=grind):
                    path = ingredient_seed_path(WORLD, name, grind)
                    potion = PotionSession(WORLD)
                    potion.add(name, grind)
                    self.assertEqual(path[1:], potion.pending)
        # Current assets use equal spacings; exercise distinct spacings without
        # mutating the shared world or claiming current recipes were affected.
        different = copy.copy(WORLD)
        different.spacing = WORLD.spacing * 2
        different._ingredient_samples = {}
        for name, item in WORLD.ingredients.items():
            if not item['is_teleportation']:
                continue
            path = ingredient_seed_path(different, name, .5)
            self.assertNotEqual(path, different.ingredient_path(name, .5))
            potion = PotionSession(different)
            potion.add(name, .5)
            self.assertEqual(path[1:], potion.pending)

    def test_empty_grade_request_does_not_run_expensive_simulation(self):
        self.assertEqual(tier_variants(None,[],{},allowed_tiers=set()),{})

    def test_curve_seeds_stay_within_valid_stirring_bounds(self):
        path=[(i*.1,0.) for i in range(1001)]
        starts=seeds(path,path[-1])
        self.assertTrue(starts)
        self.assertTrue(all(0 <= value <= 1 for value in starts))

    def test_refinement_uses_same_timed_actions_as_final_dispatcher(self):
        planner=RotatedPlanner.__new__(RotatedPlanner)
        planner.world=WORLD;planner.base='Water';planner.salt='moon';planner.units=10;planner.wait_seconds=.06
        planner.actions=[('Waterbloom',.4,WORLD.ingredient_path('Waterbloom',1))]
        sequence=planner.operations((0,),[.4])
        reference,_=planner.replay(sequence)
        target={'Position':{'x':reference.position[0],'y':reference.position[1]}}
        refined=planner.refine((0,),target,iterations=1,tail_count=1,initial_controls=[.4])
        self.assertIsNotNone(refined)
        actual=replay('Water',refined[0])['state']
        self.assertEqual(actual['pos'], {'x':refined[1].position[0],'y':refined[1].position[1]})
        self.assertEqual(actual['salts'], {'moon':10})
        self.assertEqual(actual['rotation_tween']['target'],refined[1].target_rotation)
        self.assertEqual(actual['rotation_tween']['visual'],refined[1].rotation)

    def test_partial_stir_then_rotation_is_refined_and_replayed_from_origin(self):
        planner=RotatedPlanner.__new__(RotatedPlanner)
        planner.world=WORLD;planner.base='Water';planner.salt='moon';planner.units=25;planner.wait_seconds=.06;planner.pre_stir=.25
        planner.actions=[('Waterbloom',.4,WORLD.ingredient_path('Waterbloom',1))]
        operations=planner.operations((0,),[.4])
        reference,_=planner.replay(operations)
        target={'Position':{'x':reference.position[0],'y':reference.position[1]}}
        refined=planner.refine((0,),target,iterations=1,initial_controls=[.4],tail_count=1)
        self.assertIsNotNone(refined)
        self.assertEqual(refined[0][1],dict(kind='stir',fraction=.25))
        actual=replay('Water',refined[0])['state']
        self.assertEqual(actual['pos'],{'x':refined[1].position[0],'y':refined[1].position[1]})
        self.assertEqual(actual['used'],['Waterbloom'])


if __name__=='__main__':unittest.main()
