"""Private stopped managed-proxy conversion; no credential or provider arguments."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from db.mongo import get_client, close_client
from outreach.core.proxy_migration import ProxyMigration

DRAIN_ACK = 'I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES'


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Proxy custody arguments are unavailable; use bounded record references and digests\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Private stopped managed proxy custody', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect', 'migrate'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--workspace', required=True)
        command.add_argument('--asset', required=True)
        if name == 'migrate':
            for field in ('operator', 'evidence-digest', 'review-digest', 'workers-drained'):
                command.add_argument('--' + field, required=True)
    return result


async def run_db(args: argparse.Namespace, db: Any) -> dict:
    service = ProxyMigration(db)
    if args.command == 'inspect':
        return await service.inspect(args.workspace, args.asset)
    if args.command == 'migrate':
        return await service.migrate(args.workspace, args.asset, args.operator, args.review_digest,
            evidence_digest=args.evidence_digest, workers_drained=args.workers_drained == DRAIN_ACK)
    raise ValueError('Unsupported private proxy custody operation')


async def run(args: argparse.Namespace) -> dict:
    client = await get_client()
    try:
        return await run_db(args, client[os.environ['DB_NAME']])
    finally:
        await close_client()


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(asyncio.run(run(args)), sort_keys=True))
        return 0
    except Exception:
        print('Proxy custody is unavailable; inspect original local records before retry.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
