"""CI must not silently certify empty or skipped native runs."""
import pytest

from scripts.check_native_results import check_results


@pytest.mark.parametrize('body,minimum', [
    ('<testsuites/>', 1), ('<testsuites><testcase/></testsuites>', 2),
    ('<testsuites><testcase><skipped/></testcase></testsuites>', 1),
    ('<testsuites><testcase><failure/></testcase></testsuites>', 1),
    ('<testsuites><testcase><error/></testcase></testsuites>', 1),
])
def test_gate_rejects_unexecuted_or_unsuccessful_runs(tmp_path, body, minimum):
    path = tmp_path / 'results.xml'; path.write_text(body)
    with pytest.raises(ValueError):
        check_results(path, minimum)


def test_gate_accepts_successful_nested_pytest_report(tmp_path):
    path = tmp_path / 'results.xml'
    path.write_text('<testsuites><testsuite><testcase name="a"/><testcase name="b"/></testsuite></testsuites>')
    assert check_results(path, 2) == 2
