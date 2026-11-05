import unittest
from types import SimpleNamespace

from sft.runtime.eval_gather import preserve_loss_only_gather


class EvaluationGatherTests(unittest.TestCase):
    def trainer(self, generate=False):
        return SimpleNamespace(args=SimpleNamespace(predict_with_generate=generate, prediction_loss_only=False, eval_use_gather_object=False),
                               accelerator=SimpleNamespace(gather_for_metrics=lambda *a, **k:'unique'),
                               gather_function='raw')

    def test_loss_only_restores_metric_gather_without_changing_loss(self):
        def original(self, data, description, **kwargs):
            self.asserted_gather=self.gather_function(None); return data['loss']
        for generate, loss_only in [(False, False), (True, True)]:
            trainer=self.trainer(generate)
            result=preserve_loss_only_gather(original)(trainer, {'loss':3.5}, 'eval', loss_only)
            self.assertEqual(result, 3.5)
            self.assertEqual(trainer.asserted_gather, 'unique')

    def test_generation_path_retains_native_gather(self):
        def original(self, *args, **kwargs): return 'generated'
        trainer=self.trainer(True)
        self.assertEqual(preserve_loss_only_gather(original)(trainer, None, 'eval', False), 'generated')
        self.assertEqual(trainer.gather_function, 'raw')

    def test_loss_only_defaults_to_arguments_when_none(self):
        trainer=self.trainer(True);trainer.args.prediction_loss_only=True
        def original(self, *args, **kwargs):return self.gather_function(None)
        self.assertEqual(preserve_loss_only_gather(original)(trainer,None,'eval'), 'unique')

    def test_error_propagates(self):
        def original(self, *args, **kwargs):
            raise OSError('test: data IO failure')
        trainer=self.trainer()
        with self.assertRaisesRegex(OSError, 'data IO'):
            preserve_loss_only_gather(original)(trainer, None, 'eval', True)
