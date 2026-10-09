"""Private digest-only ip exclusion CLI; never echo raw ip or provider material."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
import sys
from typing import Any
from db.mongo import get_client, close_client
from outreach.core.restore_proxy_exclusions import RestoreProxyExclusions, export_manifest
from outreach.ops.restore_epoch import PrivateParser
from outreach.ops.restore_exclusions import read_manifest, write_manifest


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Export or restore selected ip reuse exclusions', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('export', 'inspect', 'apply'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--workspace', required=True)
        if name == 'export':
            command.add_argument('--ip-digest', action='append', required=True)
            command.add_argument('--output-file', required=True)
        else:
            source = command.add_mutually_exclusive_group(required=True)
            source.add_argument('--manifest-file')
            source.add_argument('--manifest-stdin', action='store_true')
        if name == 'apply':
            for field in ('operator', 'source-digest', 'evidence-digest', 'review-digest'):
                command.add_argument('--' + field, required=True)
        if name in {'export', 'apply'}:
            command.add_argument('--all-writers-and-caches-drained', action='store_true', required=True)
    return result


async def run_db(args: argparse.Namespace, db: Any, raw: bytes | None = None) -> dict:
    if args.command == 'export':
        document = await export_manifest(db, args.workspace, args.ip_digest,
                                        workers_drained=args.all_writers_and_caches_drained)
        saved = write_manifest(args.output_file, document)
        return {'exported': True, 'source_digest': hashlib.sha256(saved).hexdigest(),
                'selected_ip_count': len(document['ips']), 'activation_allowed': False}
    raw = read_manifest(args) if raw is None else raw
    service = RestoreProxyExclusions(db)
    if args.command == 'inspect': return await service.inspect(args.workspace, raw)
    if args.command == 'apply':
        return await service.apply(args.workspace, raw, operator=args.operator, evidence_digest=args.evidence_digest,
            source_digest=args.source_digest, review_digest=args.review_digest,
            workers_drained=args.all_writers_and_caches_drained)
    raise ValueError('Unsupported ip exclusion control')


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
        print('Proxy IP exclusions are unavailable; keep execution stopped and review the private source.', file=sys.stderr)
        return 2


if __name__ == '__main__': raise SystemExit(main())
