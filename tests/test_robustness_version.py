import unittest
from optimizer.robustness import current_result, MODEL_FINGERPRINT, SAMPLER_VERSION, check


class RobustnessVersionTests(unittest.TestCase):
    def test_old_engine_or_sampler_statistics_are_not_current_evidence(self):
        self.assertFalse(current_result({'passed':8,'samples':8}))
        self.assertFalse(current_result({'model_fingerprint':'old','sampler_version':SAMPLER_VERSION}))
        self.assertTrue(current_result({'model_fingerprint':MODEL_FINGERPRINT,'sampler_version':SAMPLER_VERSION}))

    def test_wait_perturbation_and_model_are_recorded(self):
        result=check({'base':'Water','effect':'Healing','tier':1,'operations':[dict(kind='wait',seconds=.025)]},2)
        self.assertEqual(result['parameters']['wait_seconds'],.005)
        self.assertTrue(current_result(result))
        self.assertEqual(result['samples'],2)


if __name__=='__main__': unittest.main()
