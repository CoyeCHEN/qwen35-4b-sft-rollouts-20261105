"""Safety policy behavior, including resumed histories and partial epochs."""
import copy
import unittest
from sft.runtime.training_health import calibforge_validation_health as health


class TrainingHealthTests(unittest.TestCase):
    def test_severe_requires_two_distinct_consecutive_full_epochs(self):
        history=[dict(step=0,eval_loss=1.0),dict(step=10,epoch=1,eval_loss=1.6)]
        self.assertFalse(health(history)['severe_validation_regression'])
        self.assertFalse(health(history+[history[-1]])['severe_validation_regression'])
        self.assertFalse(health(history+[dict(step=30,epoch=3,eval_loss=1.6)])['severe_validation_regression'])
        history.append(dict(step=20,epoch=2,eval_loss=1.6))
        self.assertTrue(health(history)['severe_validation_regression'])

    def test_absolute_and_relative_increases_both_required(self):
        for base,loss in ((0.1,0.3),(2.0,2.8)):
            history=[dict(step=0,eval_loss=base)]+[dict(step=e*10,epoch=e,eval_loss=loss)for e in (1,2)]
            self.assertFalse(health(history)['severe_validation_regression'])

    def test_recovery_and_partial_epoch_do_not_trigger_a_false_stop(self):
        history=[dict(step=0,eval_loss=1),dict(step=10,epoch=1,eval_loss=2),
                 dict(step=15,epoch=1.5,eval_loss=10),dict(step=20,epoch=2,eval_loss=0.9)]
        self.assertFalse(health(history)['severe_validation_regression'])
        self.assertEqual(health(history),health(copy.deepcopy(history)))

    def test_missing_baseline_and_invalid_values_are_explicit_failures(self):
        with self.assertRaisesRegex(RuntimeError,'baseline missing'):
            health([dict(step=1,epoch=1,eval_loss=1)])
        for value in (float('nan'),float('inf'),-1):
            with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,'Invalid'):
                health([dict(step=0,eval_loss=value)])


if __name__=='__main__':
    unittest.main()
