"""Private reference/digest-only stop of unsubmitted Studio input jobs."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from db.mongo import get_client, close_client
from outreach.core.voice_studio_input_cutover import VoiceStudioInputCutover
from outreach.ops.proxy_custody import DRAIN_ACK


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Studio input cutover accepts original references and review digests only\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Inspect and stop unsubmitted Studio input jobs', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect', 'stop'):
        command = commands.add_parser(name, allow_abbrev=False)
        for field in ('workspace', 'job'): command.add_argument('--' + field, required=True)
        if name == 'stop':
            for field in ('operator', 'evidence-digest', 'review-digest', 'workers-drained'):
                command.add_argument('--' + field, required=True)
    return result


async def run_db(args: argparse.Namespace, db: Any) -> dict:
    service = VoiceStudioInputCutover(db)
    if args.command == 'inspect': return await service.inspect(args.workspace, args.job)
    if args.command != 'stop': raise ValueError('Unsupported Studio input cutover')
    return await service.stop(args.workspace, args.job, args.operator, args.evidence_digest,
        args.review_digest, workers_drained=args.workers_drained == DRAIN_ACK)


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
        print('Studio input cutover is unavailable; retain the original job for review.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
