"""Private metadata-only stopped financial/resource and operation inventory."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
import argparse
import asyncio
import json
import os
import sys
from db.mongo import get_client, close_client
from outreach.core.restore_inventory import RestoreInventory
from outreach.ops.restore_epoch import PrivateParser


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Inspect stopped local resource and operation metadata', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    command = commands.add_parser('inspect', allow_abbrev=False)
    command.add_argument('--workspace', required=True)
    command.add_argument('--all-writers-and-caches-drained', action='store_true', required=True)
    return result


async def run(args: argparse.Namespace) -> dict:
    client = await get_client()
    try:
        return await RestoreInventory(client[os.environ['DB_NAME']]).inspect(args.workspace,
            workers_drained=args.all_writers_and_caches_drained)
    finally:
        await close_client()


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(asyncio.run(run(args)), sort_keys=True))
        return 0
    except Exception:
        print('Restore inventory is unavailable; keep execution stopped and review locally.', file=sys.stderr)
        return 2


if __name__ == '__main__': raise SystemExit(main())
