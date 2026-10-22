"""Private reference/digest-only installed recording storage conversion."""
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
from outreach.core.voice_artifact_migration import VoiceArtifactMigration
from outreach.ops.proxy_custody import DRAIN_ACK


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Recording migration requires record references and digests; no audio or credential arguments\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Review stored received campaign recordings', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect', 'migrate'):
        command = commands.add_parser(name, allow_abbrev=False)
        for field in ('workspace', 'artifact'):
            command.add_argument('--' + field, required=True)
        if name == 'migrate':
            for field in ('operator', 'evidence-digest', 'review-digest', 'workers-drained'):
                command.add_argument('--' + field, required=True)
    return result


async def run_db(args: argparse.Namespace, db: Any) -> dict:
    service = VoiceArtifactMigration(db)
    if args.command == 'inspect':
        return await service.inspect(args.workspace, args.artifact)
    if args.command != 'migrate': raise ValueError('Unsupported recording migration')
    return await service.migrate(args.workspace, args.artifact, args.operator, args.evidence_digest,
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
        print('Recording migration is unavailable; preserve the original clip and receipt before retry.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
