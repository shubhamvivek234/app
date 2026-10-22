"""Private metadata-only finite health renewal authorization and stop."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from db.mongo import get_client, close_client
from outreach.core.health_monitor import HealthMonitor


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Health control accepts bounded references and review digests only\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Inspect, authorize a finite health window, or stop', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect', 'arm', 'stop'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--workspace', required=True)
        command.add_argument('--control' if name == 'stop' else '--sender', required=True)
        if name in {'arm', 'stop'}:
            for field in ('operator', 'evidence-digest'): command.add_argument('--'+field, required=True)
        if name == 'arm':
            command.add_argument('--review-digest', required=True)
            command.add_argument('--window-seconds', required=True, type=int)
    return result


async def run_db(args: argparse.Namespace, db: Any) -> dict:
    service = HealthMonitor(db)
    if args.command == 'inspect': return await service.inspect(args.workspace, args.sender)
    if args.command == 'arm': return await service.arm(args.workspace, args.sender, args.operator,
        args.evidence_digest, args.review_digest, window_seconds=args.window_seconds)
    if args.command == 'stop': return await service.stop(args.workspace, args.control, args.operator, args.evidence_digest)
    raise ValueError('Unsupported health control')


async def run(args: argparse.Namespace) -> dict:
    client = await get_client()
    try: return await run_db(args, client[os.environ['DB_NAME']])
    finally: await close_client()


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(asyncio.run(run(args)), sort_keys=True))
        return 0
    except Exception:
        print('Health authorization is unavailable; retain the control for review.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
