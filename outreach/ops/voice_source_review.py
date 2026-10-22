"""Trusted private same-key review: no raw key arguments or vendor calls."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import argparse
import asyncio
import json
import os
from pathlib import Path
import stat
import sys

from db.mongo import get_client, close_client
from outreach.core.credential_custody import PREFIX
from outreach.core.voice_source_review import PreviousKey, VoiceSourceReview
from outreach.ops.voice_key_secret import read_secret


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Source review arguments are unavailable; use hidden input or a private envelope file\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Private same-key voice source review', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect', 'migrate'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--workspace', required=True)
        command.add_argument('--voice', required=True)
        if name == 'migrate':
            for argument in ('operator', 'evidence', 'review-digest', 'workers-drained'):
                command.add_argument('--' + argument, required=True)
            previous = command.add_mutually_exclusive_group()
            previous.add_argument('--prior-envelope', type=Path)
            previous.add_argument('--prior-key-stdin', action='store_true')
            command.add_argument('--prior-generation', default='')
    return result


def read_envelope(path: Path) -> str:
    """Read one owned private regular file; never block on special files."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or not 1 <= info.st_size <= 60002):
                raise ValueError('Private original envelope is unavailable')
            value = os.read(descriptor, 60003).decode('ascii').removesuffix('\n').removesuffix('\r')
        finally:
            os.close(descriptor)
        if not value.startswith(PREFIX) or len(value.encode()) > 60000 or any(c.isspace() for c in value):
            raise ValueError('Private original envelope is unavailable')
        return value
    except (OSError, UnicodeError, ValueError):
        raise ValueError('A bounded owned private original envelope file is required') from None


async def run_db(args: argparse.Namespace, db) -> dict:
    service = VoiceSourceReview(db)
    if args.command == 'inspect':
        return await service.inspect(args.workspace, args.voice)
    if args.command != 'migrate' or args.prior_generation and not args.prior_envelope:
        raise ValueError('Original envelope generation is required only for scoped input')
    def previous() -> PreviousKey:
        return (PreviousKey(read_envelope(args.prior_envelope), 'kms_v1', args.prior_generation)
                if args.prior_envelope else PreviousKey(read_secret(args.prior_key_stdin)))
    return await service.migrate(args.workspace, args.voice, args.operator, args.evidence, args.review_digest,
        workers_drained=args.workers_drained == 'I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES',
        previous_key=previous)


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
        print('Voice source review is unavailable; inspect original records before retry.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
