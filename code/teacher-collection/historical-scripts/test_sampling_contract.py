import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('sampling', Path(__file__).with_name('sample_task_pools.py'))
sampling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampling)


def test_largest_remainders_preserve_seats_and_rare_fraction():
    assert sampling.allocate(10, {'a': 15, 'b': 8, 'c': 1}) == {'a': 6, 'b': 3, 'c': 1}
    assert sampling.allocate(10, {'a': 100, 'b': 1}, {'a': 3, 'b': 10}) == {'a': 3, 'b': 7}
    with pytest.raises(ValueError, match='insufficient capacity'):
        sampling.allocate(10, {'a': 1}, {'a': 9})


def test_family_transitivity_keeps_retries_and_template_members_together():
    groups = sampling.Families(5)
    groups.join(0, 2)
    groups.join(1, 4)
    groups.join(2, 4)
    assert len({groups.find(i) for i in [0, 1, 2, 4]}) == 1
    assert groups.find(3) != groups.find(0)


def test_template_screen_detects_path_and_value_variants():
    one = 'Read `/app/first.csv` and select 42 records then save the exact requested column names.'
    two = 'Read `/tmp/second.csv` and select 91 records then save the exact requested column names.'
    assert sampling.grams(one) != sampling.grams(two)
    assert sampling.grams(one, True) == sampling.grams(two, True)
