"""Private reference-only legacy proxy review; no new provider facts or secrets."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from db.mongo import get_client, close_client
from outreach.core.proxy_adoption import ProxyAdoption
from outreach.ops.proxy_custody import DRAIN_ACK


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Legacy proxy review requires bounded record references and digests; no credential arguments\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Review retained original legacy Webshare evidence', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect', 'adopt'):
        command = commands.add_parser(name, allow_abbrev=False)
        for field in ('workspace', 'asset'):
            command.add_argument('--' + field, required=True)
        if name == 'adopt':
            for field in ('operator', 'evidence-digest', 'review-digest', 'workers-drained'):
                command.add_argument('--' + field, required=True)
    return result


async def run_db(args: argparse.Namespace, db: Any) -> dict:
    service = ProxyAdoption(db)
    if args.command == 'inspect':
        return await service.inspect(args.workspace, args.asset)
    if args.command != 'adopt':
        raise ValueError('Unsupported private legacy proxy review')
    return await service.adopt(args.workspace, args.asset, args.operator, args.evidence_digest,
        args.review_digest, workers_drained=args.workers_drained == DRAIN_ACK)


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
        print('Legacy proxy review is unavailable; preserve original records and evidence before retry.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
