import unittest
from playground.serve import WORLD
from engine.brew import PotionSession
from optimizer.stabilize import control_candidates


class WeakerPouringTests(unittest.TestCase):
    def test_cold_pour_rescaling_preserves_displacement_without_paid_resources(self):
        original=[dict(kind='pour',seconds=.2,strength=1.)]
        reference=PotionSession(WORLD,position=(2.,0.));reference.pour(.2,1.)
        proposals=[p for p in control_candidates(original) if p[0]['strength']<1]
        self.assertEqual(len(proposals),4)
        for sequence in proposals:
            session=PotionSession(WORLD,position=(2.,0.))
            operation=sequence[0];session.pour(operation['seconds'],operation['strength'])
            self.assertAlmostEqual(session.position[0],reference.position[0],places=10)
            self.assertAlmostEqual(session.position[1],reference.position[1],places=10)
            self.assertFalse(session.ingredients_used)
            self.assertFalse(session.salts_used)
        self.assertEqual(original[0]['strength'],1.)


if __name__=='__main__':unittest.main()
