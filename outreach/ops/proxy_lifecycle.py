"""Private reviewed provider changes; passwords only through lazy hidden/stdin input."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import getpass
import json
import os
import sys
import warnings
from typing import Any

from db.mongo import get_client, close_client
from outreach.core.proxy_lifecycle import ProxyLifecycle, _password
from outreach.ops.proxy_custody import DRAIN_ACK


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Proxy lifecycle arguments are unavailable; secrets require hidden input or explicit stdin\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Record externally performed stopped Webshare changes', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    for name in ('inspect-renew', 'inspect-rotate', 'renew', 'rotate'):
        command = commands.add_parser(name, allow_abbrev=False)
        for field in ('workspace', 'asset'):
            command.add_argument('--' + field, required=True)
        if not name.startswith('inspect'):
            for field in ('operator', 'evidence-digest', 'provider-reference', 'review-digest', 'workers-drained'):
                command.add_argument('--' + field, required=True)
            if name == 'renew':
                command.add_argument('--expires-at', required=True)
            else:
                command.add_argument('--stdin', action='store_true')
    return result


def read_password(from_stdin: bool) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            value = (sys.stdin.read(259).removesuffix('\n').removesuffix('\r') if from_stdin
                else getpass.getpass('New externally changed provider password: '))
        return _password(value)
    except (ValueError, getpass.GetPassWarning):
        raise ValueError('A bounded hidden password or explicit stdin is required') from None


async def run_db(args: argparse.Namespace, db: Any) -> dict:
    service = ProxyLifecycle(db)
    if args.command in ('inspect-renew', 'inspect-rotate'):
        return await service.inspect(args.workspace, args.asset, args.command.removeprefix('inspect-'))
    options = {'workers_drained': args.workers_drained == DRAIN_ACK}
    if args.command == 'renew':
        options['expires_at'] = datetime.fromisoformat(args.expires_at.replace('Z', '+00:00'))
    elif args.command == 'rotate':
        options['password_supplier'] = lambda: read_password(args.stdin)
    else:
        raise ValueError('Unsupported private proxy lifecycle operation')
    return await service.apply(args.workspace, args.asset, args.command, args.operator, args.evidence_digest,
        args.provider_reference, args.review_digest, **options)


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
        print('Proxy lifecycle is unavailable; inspect original provider evidence and local records before retry.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
