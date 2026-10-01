import unittest
from optimizer.costs import resource_cost, no_salt_search_bound, competitive_tiers


class CostTests(unittest.TestCase):
    prices={'Watercap':26.4, 'Lifeleaf':6., 'Firebell':8.2}

    def test_fixed_inventory_pruning_keeps_expensive_grade_and_ties(self):
        cheap=resource_cost({'Lifeleaf':1},{},self.prices)
        high=resource_cost({'Lifeleaf':2},{},self.prices)
        bounds={(o,t):cheap if t<3 else high for o in ('P1','P2') for t in (1,2,3)}
        salted=resource_cost({'Lifeleaf':1},{'moon':1},self.prices)
        self.assertEqual(competitive_tiers(salted,bounds),{3})
        self.assertEqual(competitive_tiers(cheap,bounds),{1,2,3})
        self.assertEqual(competitive_tiers(salted,{}),{1,2,3})

    def test_four_salt_equivalents(self):
        cost=resource_cost({'Lifeleaf':2},{'void':200,'sun':100,'moon':100,'life':50},self.prices)
        self.assertEqual(cost['P1'],6)
        self.assertAlmostEqual(cost['P2'],117.6)

    def test_no_rounding_up(self):
        cost=resource_cost({'Firebell':1},{'void':1},self.prices)
        self.assertEqual(cost['P1_exact'],'201/200')
        self.assertAlmostEqual(cost['P2'],8.332)

    def test_resource_objectives_can_choose_different_recipes(self):
        one=resource_cost({'Watercap':1},{},self.prices)
        two=resource_cost({'Lifeleaf':2},{},self.prices)
        self.assertLess(one['P1'],two['P1'])
        self.assertGreater(one['P2'],two['P2'])

    def test_forbidden_and_invalid_resources(self):
        for salt in ('philosopher','unknown'):
            with self.assertRaises(ValueError):resource_cost({}, {salt:1},self.prices)
        for amount in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):resource_cost({}, {'sun':amount},self.prices)
        with self.assertRaises(ValueError):resource_cost({'Lifeleaf':.5},{},self.prices)

    def test_cheaper_low_grade_does_not_prune_higher_grade(self):
        records=[{'effect':'Fire','tier':tier,'ingredient_count':count,'ingredient_value':value,'salts':{}}
                 for tier,count,value in [(1,1,6),(2,2,12),(3,3,20)]]
        self.assertEqual(no_salt_search_bound(records,'Fire','P1'),3)
        self.assertEqual(no_salt_search_bound(records,'Fire','P2'),20)
        self.assertIsNone(no_salt_search_bound(records[:2],'Fire','P1'))


if __name__=='__main__':unittest.main()
