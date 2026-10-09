"""Private manual Webshare import; credentials arrive only through hidden input."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import getpass
import json
import os
import sys
import warnings

from motor.motor_asyncio import AsyncIOMotorClient

from outreach.core.webshare_provisioning import import_webshare_proxy


class ImportUnavailable(ValueError):
    """Sanitized private operation failure."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Webshare import arguments are unavailable; proxy credentials require hidden input or explicit stdin\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Import one manually verified dedicated static Webshare ISP IP', allow_abbrev=False)
    for name in ('workspace', 'plan', 'resource', 'order', 'country', 'expires-at', 'operator', 'evidence-digest'):
        result.add_argument('--' + name, required=True)
    result.add_argument('--confirm-dedicated-static-isp', action='store_true', required=True)
    result.add_argument('--stdin', action='store_true')
    return result


def read_proxy(from_stdin: bool) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            value = (sys.stdin.read(2051).removesuffix('\n').removesuffix('\r')
                     if from_stdin else getpass.getpass('Authenticated Webshare proxy URL: '))
        if not isinstance(value, str) or not 1 <= len(value) <= 2048:
            raise ValueError('bounds')
        return value
    except (ValueError, getpass.GetPassWarning):
        raise ImportUnavailable('A bounded hidden URL or explicit stdin is required') from None


async def run(args: argparse.Namespace) -> dict:
    client = None
    try:
        expiry = datetime.fromisoformat(args.expires_at.replace('Z', '+00:00'))
        if expiry.tzinfo is None:
            raise ValueError('timezone')
        proxy_url = read_proxy(args.stdin)
        uri = os.environ.get('MONGODB_URI') or os.environ['MONGO_URL']
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)
        result = await import_webshare_proxy(client[os.environ['DB_NAME']], proxy_url=proxy_url,
            country_code=args.country, plan_id=args.plan, resource_id=args.resource,
            provider_order_id=args.order, workspace_id=args.workspace, expires_at=expiry,
            verified_by=args.operator, evidence_digest=args.evidence_digest,
            dedicated_isp_confirmed=args.confirm_dedicated_static_isp)
        return result
    except Exception:
        raise ImportUnavailable('Webshare import is unavailable; inspect local evidence before retry') from None
    finally:
        if client is not None:
            client.close()


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(asyncio.run(run(args)), default=str))
        return 0
    except ImportUnavailable:
        print('Webshare import is unavailable; inspect local evidence before retry', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
