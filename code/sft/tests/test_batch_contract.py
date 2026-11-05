"""CPU mock tests of the measured native DP contract, never GPU evidence."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from sft.runtime.batch_contract import measure_data_parallel


class BatchContractTests(unittest.TestCase):
    def setUp(self):
        self.group=object()
        self.engine=SimpleNamespace(data_parallel_group=self.group,dp_world_size=4,
            train_micro_batch_size_per_gpu=lambda:1,
            gradient_accumulation_steps=lambda:32,train_batch_size=lambda:128)
        self.distributed=Mock()
        self.distributed.is_initialized.return_value=True
        self.distributed.get_world_size.return_value=4
        self.distributed.get_process_group_ranks.return_value=[0,1,2,3]

    def test_measures_native_group_and_engine_batch(self):
        result=measure_data_parallel(self.engine,self.distributed)
        self.assertEqual(result['effective_global_batch'],128)
        self.assertEqual(result['data_parallel_group_size'],4)
        self.assertEqual(self.distributed.get_world_size.call_args_list[0].args,(self.group,))

    def test_gpu_count_cannot_replace_dp_group_or_initialized_collectives(self):
        self.distributed.is_initialized.return_value=False
        with self.assertRaisesRegex(RuntimeError,'not initialized'):
            measure_data_parallel(self.engine,self.distributed)
        self.distributed.is_initialized.return_value=True
        self.distributed.get_world_size.side_effect=lambda group=None:2 if group is self.group else 4
        with self.assertRaisesRegex(RuntimeError,'pure data-parallel'):
            measure_data_parallel(self.engine,self.distributed)

    def test_rejects_inconsistent_engine_batch_and_group_membership(self):
        self.engine.train_batch_size=lambda:16
        with self.assertRaisesRegex(RuntimeError,'global batch'):
            measure_data_parallel(self.engine,self.distributed)
        self.engine.train_batch_size=lambda:128
        self.distributed.get_process_group_ranks.return_value=[0,1,2,4]
        with self.assertRaisesRegex(RuntimeError,'membership'):
            measure_data_parallel(self.engine,self.distributed)


if __name__=='__main__':
    unittest.main()
