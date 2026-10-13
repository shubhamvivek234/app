"""Reject empty, failed or skipped native acceptance runs in CI."""
import argparse
from pathlib import Path

from defusedxml import ElementTree


def check_results(path: Path, minimum: int) -> int:
    root = ElementTree.parse(path, forbid_dtd=True).getroot()
    cases = list(root.iter('testcase'))
    if minimum < 1 or len(cases) < minimum:
        raise ValueError('Native checks did not meet the required minimum')
    if any(case.find(kind) is not None for case in cases for kind in ('skipped', 'failure', 'error')):
        raise ValueError('Native checks contain skipped or unsuccessful cases')
    return len(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    parser.add_argument('--minimum', type=int, required=True)
    args = parser.parse_args()
    print(f'Verified {check_results(args.result, args.minimum)} native checks with no skips')


if __name__ == '__main__':
    main()
