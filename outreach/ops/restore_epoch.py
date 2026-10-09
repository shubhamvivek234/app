"""Private metadata-only restore inspection and stopped preparation."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
from typing import Any
from db.mongo import get_client, close_client
from outreach.core.restore_epoch import RestoreEpoch


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Restore control accepts bounded references and review digests only\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Inspect or prepare a stopped restore epoch', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect', 'prepare'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--workspace', required=True)
        if name == 'prepare':
            for field in ('operator', 'evidence-digest', 'review-digest'):
                command.add_argument('--'+field, required=True)
            command.add_argument('--all-writers-and-caches-drained', action='store_true', required=True)
    return result


async def run_db(args: argparse.Namespace, db: Any) -> dict:
    service = RestoreEpoch(db)
    if args.command == 'inspect': return await service.inspect(args.workspace)
    if args.command == 'prepare': return await service.prepare(args.workspace, args.operator,
        args.evidence_digest, args.review_digest, workers_drained=args.all_writers_and_caches_drained)
    raise ValueError('Unsupported restore control')


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
        print('Restore preparation is unavailable; keep execution stopped and inspect again.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
