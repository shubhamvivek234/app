"""Private database-only integration review/migration; no secrets or HTTP arguments."""
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
from outreach.core.integration_review import IntegrationReview
from outreach.core.integration_migration import IntegrationMigration

DRAIN_ACK = 'I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES'


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Integration control arguments are unavailable; use bounded record references\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Private stopped integration control', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect-delivery', 'resolve-delivery', 'inspect-credential', 'migrate-credential'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--workspace', required=True)
        if name.endswith('delivery'):
            command.add_argument('--delivery', required=True)
            if name == 'resolve-delivery': command.add_argument('--decision', choices=['stop_local', 'use_receipt'], required=True)
        else:
            command.add_argument('--kind', choices=['webhook', 'slack', 'hubspot'], required=True)
            command.add_argument('--resource', required=True)
        if not name.startswith('inspect'):
            for field in ('operator', 'evidence', 'review-digest', 'workers-drained'):
                command.add_argument('--'+field, required=True)
    return result


async def run_db(args: argparse.Namespace, db: Any) -> dict:
    if args.command == 'inspect-delivery': return await IntegrationReview(db).inspect(args.workspace, args.delivery)
    if args.command == 'inspect-credential': return await IntegrationMigration(db).inspect(args.workspace, args.kind, args.resource)
    options = {'workers_drained': args.workers_drained == DRAIN_ACK}
    if args.command == 'resolve-delivery':
        return await IntegrationReview(db).resolve(args.workspace, args.delivery, args.decision, args.operator,
            args.evidence, expected_digest=args.review_digest, **options)
    if args.command == 'migrate-credential':
        return await IntegrationMigration(db).migrate(args.workspace, args.kind, args.resource, args.operator,
            args.evidence, args.review_digest, **options)
    raise ValueError('Unsupported integration control command')


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
        print('Integration control is unavailable; inspect original records before retry.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
