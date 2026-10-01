"""Reject false solver claims using an actual, independent GUI replay."""
import copy
import unittest

from optimizer.verify import verify_record
from engine.brew import PotionSession
from playground.serve import WORLD, perform


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.record={'base':'Water','effect':'Healing','tier':3,
                     'ingredients':{'Lifeleaf':2},'salts':{},'operations':[
                         {'kind':'add','name':'Lifeleaf','grind':.97097412},
                         {'kind':'stir','fraction':1},
                         {'kind':'add','name':'Lifeleaf','grind':1},
                         {'kind':'stir','fraction':.54057373},
                         {'kind':'pump','angle':60,'seconds':.5}]}

    def test_actual_replay_validates_target_and_recomputes_cost(self):
        self.record['costs']={'P1':0,'P2':0}
        verified=verify_record(self.record,details=True)
        self.assertEqual(verified['costs']['P1'],2)
        self.assertEqual(verified['costs']['P2'],12)
        self.assertGreater(verified['minimum_health'],0)

    def test_wrong_grade_and_uncollected_effect_are_rejected(self):
        wrong=copy.deepcopy(self.record);wrong['tier']=2
        missing=copy.deepcopy(self.record);missing['operations'].pop()
        for record in (wrong,missing):
            with self.assertRaises(ValueError):verify_record(record)

    def test_forged_resource_inventory_is_rejected(self):
        wrong=copy.deepcopy(self.record);wrong['ingredients']={'Lifeleaf':1}
        with self.assertRaises(ValueError):verify_record(wrong)
        wrong=copy.deepcopy(self.record);wrong['salts']={'moon':1}
        with self.assertRaises(ValueError):verify_record(wrong)

    def test_forbidden_salt_and_observation_origin_are_rejected(self):
        for action in ({'kind':'salt','salt':'philosopher','amount':1},
                       {'kind':'vortex_demo','name':'invented'}):
            wrong=copy.deepcopy(self.record);wrong['operations'].insert(0,action)
            with self.assertRaises(ValueError):verify_record(wrong)

    def test_zero_ingredient_center_invariant_on_every_legal_base(self):
        actions=[{'kind':'pump','angle':120,'seconds':.2},
                 {'kind':'wait','seconds':2},
                 {'kind':'pour','seconds':2,'strength':1},
                 {'kind':'stir','fraction':1},
                 *[{'kind':'salt','salt':salt,'amount':1000} for salt in ('moon','sun','life','void')],
                 {'kind':'center'}, {'kind':'pump','angle':120,'seconds':.2}]
        for base in WORLD.bases:
            session=PotionSession(WORLD,base=base)
            self.assertIsNone(session.touching_vortex())
            for action in actions:
                perform(session,action)
                self.assertEqual(session.position,(0,0))
                self.assertEqual(session.effects,[])
                self.assertEqual(dict(session.ingredients_used),{})


if __name__=='__main__':unittest.main()
