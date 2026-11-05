import unittest


class MinLRSchedulerTests(unittest.TestCase):
    def test_ratio_preserves_curve_when_optimizer_has_no_defaults_api(self):
        import torch
        from transformers.optimization import get_cosine_with_min_lr_schedule_with_warmup

        class WrappedOptimizerContract(torch.optim.AdamW):
            def __getattribute__(self, name):
                if name == 'defaults' and object.__getattribute__(self, '__dict__').get('hide_defaults'):
                    raise AttributeError('ZeRO optimizer does not expose defaults')
                return super().__getattribute__(name)

        a = torch.optim.AdamW([torch.nn.Parameter(torch.ones(1))], lr=1e-5)
        b = WrappedOptimizerContract([torch.nn.Parameter(torch.ones(1))], lr=1e-5)
        b.hide_defaults = True
        with self.assertRaises(AttributeError):
            get_cosine_with_min_lr_schedule_with_warmup(b, 5, 100, min_lr=1e-6)
        absolute = get_cosine_with_min_lr_schedule_with_warmup(a, 5, 100, min_lr=1e-6)
        ratio = get_cosine_with_min_lr_schedule_with_warmup(b, 5, 100, min_lr_rate=0.1)
        for _ in range(100):
            a._opt_called = b._opt_called = True
            absolute.step()
            ratio.step()
            self.assertAlmostEqual(absolute.get_last_lr()[0], ratio.get_last_lr()[0], places=16)
        self.assertAlmostEqual(ratio.get_last_lr()[0], 1e-6, places=16)
