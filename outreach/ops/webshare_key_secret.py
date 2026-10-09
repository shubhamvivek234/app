"""Private Webshare key sealer: hidden/bounded input, no installation."""
from __future__ import annotations

import argparse
import asyncio
import getpass
from pathlib import Path
import sys
import warnings

from outreach.core.session_custody import custody_mode
from outreach.core.webshare_key_custody import MAX_KEY_BYTES, seal_key, _validate_key
from outreach.ops.oauth_app_secret import write_envelope


class SealerUnavailable(ValueError):
    """Static error without key service, secret or filesystem details."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, 'Webshare sealer arguments are unavailable; use hidden input or explicit stdin\n')


def parser() -> argparse.ArgumentParser:
    result = PrivateParser(description='Seal one Webshare key into a new private file', allow_abbrev=False)
    result.add_argument('--generation', required=True)
    result.add_argument('--output', type=Path, required=True)
    result.add_argument('--stdin', action='store_true', help='Read bounded input instead of a hidden prompt')
    return result


def read_secret(from_stdin: bool) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            value = (
                sys.stdin.read(MAX_KEY_BYTES + 3).removesuffix('\n').removesuffix('\r')
                if from_stdin else getpass.getpass('Webshare API key: ')
            )
        _validate_key(value)
        return value
    except (ValueError, getpass.GetPassWarning):
        raise SealerUnavailable('A bounded key and hidden prompt or explicit stdin are required') from None


async def run(args: argparse.Namespace) -> dict:
    try:
        if custody_mode() != 'kms_v1' or args.output.exists() or args.output.is_symlink():
            raise SealerUnavailable('Scoped custody and a new output file are required')
        value = read_secret(args.stdin)
        _validate_key(value)
        envelope = await seal_key(value, args.generation)
        del value
        write_envelope(args.output, envelope)
        return {'status': 'encrypted_file_ready', 'generation': args.generation}
    except Exception:
        raise SealerUnavailable('Webshare sealing is unavailable; no configuration was installed') from None


def main() -> int:
    args = parser().parse_args()
    try:
        asyncio.run(run(args))
        return 0
    except SealerUnavailable:
        print('Webshare sealing is unavailable; no configuration was installed', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
