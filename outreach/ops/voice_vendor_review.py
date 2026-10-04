"""Private reference-only vendor evidence; capture explicitly makes one GET."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from db.mongo import get_client, close_client
from outreach.core.voice_vendor_evidence import VoiceVendorEvidence

DRAIN_ACK = 'I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES'


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Vendor review arguments are unavailable; use bounded record references\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Private vendor metadata evidence and voice hold review', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect', 'capture', 'release', 'close-read'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--workspace', required=True)
        command.add_argument('--voice', required=True)
        if name != 'capture': command.add_argument('--job', required=name != 'inspect')
        if name != 'inspect':
            for argument in ('operator', 'evidence', 'review-digest', 'workers-drained'):
                command.add_argument('--' + argument, required=True)
    return result


async def run_db(args: argparse.Namespace, db) -> dict:
    service = VoiceVendorEvidence(db)
    if args.command == 'inspect': return await service.inspect(args.workspace, args.voice, args.job)
    options = {'workers_drained': args.workers_drained == DRAIN_ACK}
    if args.command == 'capture':
        return await service.capture(args.workspace, args.voice, args.operator, args.evidence, args.review_digest, **options)
    method = service.release if args.command == 'release' else service.close_read if args.command == 'close-read' else None
    if method is None: raise ValueError('Unsupported vendor review command')
    return await method(args.workspace, args.voice, args.job, args.operator, args.evidence, args.review_digest, **options)


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
        print('Vendor voice review is unavailable; inspect original records before retry.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
