import unittest

from examples.build_tmax_batch_dataset import _row


class BatchDatasetTests(unittest.TestCase):
    def test_row_preserves_provenance_and_mask_counts(self):
        trajectory = {
            "trajectory_id": "traj",
            "task_id": "task",
            "task_group_id": "group",
            "trial_id": "trial",
            "reward": 1.0,
        }
        row = _row({"input_ids": [1, 2, 3], "loss_mask": [0, 1, 1], "call_id": "call"}, trajectory)
        self.assertEqual(row["n_trained_tokens"], 2)
        self.assertEqual(row["task_group_id"], "group")
        self.assertEqual(row["trial_id"], "trial")

