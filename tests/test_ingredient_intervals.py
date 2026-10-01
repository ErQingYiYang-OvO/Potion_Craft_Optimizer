import unittest
from engine.brew import BrewWorld
from engine.brew import PotionSession
from optimizer.intervals import Interval,CarriedPathBox
from optimizer.ingredient_intervals import ingredient_path_enclosure
from optimizer.ordinary_stir import ordinary_stir
from optimizer.cold_stir import clean_region_reason


class IngredientIntervalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world=BrewWorld()

    def test_continuous_grinding_covers_changing_path_topology(self):
        result=ingredient_path_enclosure(self.world,'Firebell',Interval(.49,.51))
        self.assertTrue(result['pathEnclosureComplete'])
        self.assertGreater(len({len(path) for path in result['paths']}),1)
        for grind in (.49,.495,.5,.505,.51):
            actual=self.world.ingredient_path('Firebell',grind)
            self.assertTrue(any(len(path)==len(actual) and all(bound.contains(value)
                for box,point in zip(path,actual) for bound,value in zip(box,point))
                for path in result['paths']))

    def test_full_grind_and_budget_failure_are_not_confused(self):
        result=ingredient_path_enclosure(self.world,'Firebell',Interval(.999,1))
        self.assertTrue(result['pathEnclosureComplete'])
        actual=self.world.ingredient_path('Firebell',1)
        self.assertTrue(any(len(path)==len(actual) and all(bound.contains(value)
            for box,point in zip(path,actual) for bound,value in zip(box,point)) for path in result['paths']))
        limited=ingredient_path_enclosure(self.world,'Firebell',Interval(0,1),branch_budget=1)
        self.assertFalse(limited['pathEnclosureComplete']);self.assertTrue(limited['unresolved'])
        crystal=next(name for name,item in self.world.ingredients.items() if item['is_teleportation'])
        self.assertFalse(ingredient_path_enclosure(self.world,crystal,Interval(0,1))['supported'])

    def test_grinding_and_stirring_intervals_compose(self):
        import sys
        if sys.implementation.name!='cpython' or sys.version_info[:2]!=(3,12):
            self.skipTest('Interval action runtime is CPython 3.12')
        paths=ingredient_path_enclosure(self.world,'Firebell',Interval(.49,.51))
        terminals=[]
        for local in paths['paths']:
            state=CarriedPathBox((0,0)).append(local)
            result=ordinary_stir(state,Interval(.05,.06),self.world.spacing,
                self.world.settings['RecipeMapManagerIndicatorSettings']['indicatorSpeed'],
                node_budget=100,region_guard=lambda box:clean_region_reason(self.world,'Water',box))
            self.assertTrue(result['loopEnclosureComplete']);terminals.extend(result['terminal'])
        for grind in (.49,.5,.51):
            for stir in (.05,.055,.06):
                potion=PotionSession(self.world);potion.add('Firebell',grind);potion.stir(stir)
                self.assertTrue(any(len(node.path.pending)==len(potion.pending) and all(bound.contains(value)
                    for box,point in zip((node.path.position,)+node.path.pending,
                                         (potion.position,)+tuple(potion.pending))
                    for bound,value in zip(box,point)) for node in terminals))
