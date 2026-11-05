import unittest

from sft.dataset import split_by_task_group


def row(identifier, group):
    return {"trajectory_id": identifier, "source": "fixture", "task_group_id": group,
            "status": "completed", "reward": 1, "reward_status": "positive", "calls": [{
                "call_id": identifier + "-call", "request_messages": [{"role": "user", "content": "x"}],
                "assistant_response": {"role": "assistant", "content": "y"}, "tool_calls": [],
                "tool_observations": []}]}


class DatasetTests(unittest.TestCase):
    def test_task_group_is_not_split(self):
        train, holdout = split_by_task_group([row("a1", "a"), row("a2", "a"), row("b1", "b")], .5)
        self.assertTrue(not ({r["task_group_id"] for r in train} & {r["task_group_id"] for r in holdout}))
