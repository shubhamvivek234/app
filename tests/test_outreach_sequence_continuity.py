"""Strict recorded version representations; native tests cover query semantics."""
from bson import Code, Int64
import pytest

from outreach.core.sequence_continuity import current_version, MAX_VERSION


@pytest.mark.parametrize('value', [1, 2, Int64(2), MAX_VERSION, Int64(MAX_VERSION)])
def test_current_version_accepts_positive_exact_safe_integers(value):
    assert current_version({'version': value}) == int(value)


@pytest.mark.parametrize('value', [None, True, False, 0, -1, 2.0, '2', Code('2'), [], [2], {}, MAX_VERSION + 1])
def test_current_version_rejects_unproven_representations(value):
    assert current_version({'version': value}) is None


def test_missing_legacy_sequence_version_retains_existing_version_one_default():
    assert current_version({}) == 1
