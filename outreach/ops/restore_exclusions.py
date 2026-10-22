"""Private bounded exclusion files; no identity/content material in CLI output."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any
from db.mongo import get_client, close_client
from outreach.core.restore_exclusions import MAX_BYTES, RestoreExclusions, export_manifest
from outreach.ops.restore_epoch import PrivateParser


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Export or restore selected deletion exclusions', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('export', 'inspect', 'apply'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--workspace', required=True)
        if name == 'export':
            command.add_argument('--identity-digest', action='append', required=True)
            command.add_argument('--output-file', required=True)
        else:
            source = command.add_mutually_exclusive_group(required=True)
            source.add_argument('--manifest-file')
            source.add_argument('--manifest-stdin', action='store_true')
        if name == 'apply':
            for field in ('operator', 'source-digest', 'evidence-digest', 'review-digest'):
                command.add_argument('--' + field, required=True)
            command.add_argument('--all-writers-and-caches-drained', action='store_true', required=True)
    return result


def read_manifest(args: argparse.Namespace) -> bytes:
    if args.manifest_stdin:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    else:
        fd = os.open(args.manifest_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as file:
            before = os.fstat(file.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) & 0o077 or not 1 <= before.st_size <= MAX_BYTES):
                raise ValueError('An owned private bounded regular file is required')
            raw = file.read(MAX_BYTES + 1)
            after = os.fstat(file.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError('Source file changed')
    if not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('A bounded deletion manifest is required')
    return raw


def write_manifest(target: str, document: dict) -> bytes:
    raw = (json.dumps(document, sort_keys=True, separators=(',', ':')) + '\n').encode()
    if not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('Deletion manifest exceeds capacity')
    path = Path(target)
    parent = path.parent.stat()
    if (not stat.S_ISDIR(parent.st_mode) or path.parent.is_symlink() or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) & 0o077):
        raise ValueError('An owned private output directory is required')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    owned = os.fstat(fd)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(raw); file.flush(); os.fsync(file.fileno())
    except BaseException:
        try:
            current = path.lstat()
            if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                path.unlink()
        except FileNotFoundError:
            pass
        raise
    return raw


async def run_db(args: argparse.Namespace, db: Any, raw: bytes | None = None) -> dict:
    if args.command == 'export':
        document = await export_manifest(db, args.workspace, args.identity_digest)
        saved = write_manifest(args.output_file, document)
        return {'exported': True, 'source_digest': hashlib.sha256(saved).hexdigest(),
                'selected_identity_count': len(document['identities']), 'activation_allowed': False}
    raw = read_manifest(args) if raw is None else raw
    service = RestoreExclusions(db)
    if args.command == 'inspect':
        return await service.inspect(args.workspace, raw)
    if args.command == 'apply':
        return await service.apply(args.workspace, raw, operator=args.operator, evidence_digest=args.evidence_digest,
            source_digest=args.source_digest, review_digest=args.review_digest,
            workers_drained=args.all_writers_and_caches_drained)
    raise ValueError('Unsupported exclusion control')


async def run(args: argparse.Namespace) -> dict:
    raw = None if args.command == 'export' else read_manifest(args)
    client = await get_client()
    try:
        return await run_db(args, client[os.environ['DB_NAME']], raw)
    finally:
        await close_client()


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(asyncio.run(run(args)), sort_keys=True))
        return 0
    except Exception:
        print('Deletion exclusions are unavailable; keep execution stopped and review the private source.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
