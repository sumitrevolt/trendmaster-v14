"""Unit tests for tools.cpcv."""
from __future__ import annotations

import numpy as np
import pytest

from tools.cpcv import CPCVSplit, purged_walk_forward


def test_split_yields_expected_fold_count():
    cv = CPCVSplit(n_groups=6, n_test=2)
    # C(6, 2) = 15 folds
    X = np.arange(300)
    folds = list(cv.split(X))
    assert len(folds) == 15
    assert cv.get_n_splits() == 15


def test_no_overlap_between_train_and_test():
    cv = CPCVSplit(n_groups=5, n_test=1)
    X = np.arange(200)
    for train, test in cv.split(X):
        assert len(np.intersect1d(train, test)) == 0


def test_embargo_removes_post_test_samples():
    cv = CPCVSplit(n_groups=4, n_test=1, embargo_bars=5)
    X = np.arange(40)
    # First test fold is [0..9] — embargo should drop [10..14] from train.
    # (Only relevant when test fold is NOT the last one.)
    for train, test in cv.split(X):
        last_test = int(test.max())
        # No training index should sit in the embargo window immediately
        # after the test block.
        for i in range(last_test + 1, min(last_test + 1 + 5, len(X))):
            assert i not in train


def test_purge_by_label_times_removes_overlapping_train():
    n = 60
    # Stamp label times every 10 samples monotonically.
    lt = np.arange(n)
    cv = CPCVSplit(n_groups=6, n_test=1, label_times=lt)
    for train, test in cv.split(np.arange(n)):
        t_start, t_end = float(lt[test[0]]), float(lt[test[-1]])
        # No training label-time should fall inside the test range.
        for i in train:
            assert lt[i] < t_start or lt[i] > t_end


def test_invalid_n_test_raises():
    with pytest.raises(ValueError):
        CPCVSplit(n_groups=3, n_test=0)
    with pytest.raises(ValueError):
        CPCVSplit(n_groups=3, n_test=3)


def test_small_n_groups_raises():
    with pytest.raises(ValueError):
        CPCVSplit(n_groups=1, n_test=1)


def test_purged_walk_forward_shape():
    n = 100
    folds = list(purged_walk_forward(n=n, n_splits=4, embargo=2))
    assert len(folds) > 0
    for train, test in folds:
        # Train comes strictly before test (walk-forward).
        assert int(train.max()) < int(test.min())


def test_empty_folds_are_skipped():
    # label_times too dense ⇒ purge might empty some training folds.
    # Those should be silently skipped, not yielded empty.
    cv = CPCVSplit(n_groups=3, n_test=1, label_times=np.arange(30))
    for train, test in cv.split(np.arange(30)):
        assert len(train) > 0 and len(test) > 0
