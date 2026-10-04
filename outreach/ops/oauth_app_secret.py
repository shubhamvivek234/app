"""Private local OAuth app-secret sealer. Never pass a secret in CLI arguments.

No database, OAuth or deployment operation occurs. Uses the pinned KMS adapter
only when an operator explicitly runs this command with scoped custody configured.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from pathlib import Path
import sys
import warnings

from outreach.core.credential_custody import MAX_SECRET_BYTES, PREFIX
from outreach.core.oauth_app_custody import seal_app_secret
from outreach.core.session_custody import custody_mode


class SealerUnavailable(ValueError):
    """Static error without secret, key service or filesystem details."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Seal one application OAuth secret into a new private file")
    result.add_argument("--provider", choices=("gmail", "microsoft"), required=True)
    result.add_argument("--generation", required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--stdin", action="store_true", help="Read bounded secret input instead of a hidden terminal prompt")
    return result


def read_secret(from_stdin: bool) -> str:
    try:
        with warnings.catch_warnings():
            # getpass otherwise falls back to echoing input on an unsuitable
            # terminal. Require the operator to explicitly select --stdin.
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = (sys.stdin.read(MAX_SECRET_BYTES + 3).removesuffix("\n").removesuffix("\r") if from_stdin
                     else getpass.getpass("OAuth application client secret: "))
    except getpass.GetPassWarning:
        raise SealerUnavailable("A hidden terminal prompt or explicit stdin input is required") from None
    if not value or len(value.encode()) > MAX_SECRET_BYTES or "\n" in value or "\r" in value:
        raise SealerUnavailable("OAuth application input is unavailable")
    return value


def write_envelope(path: Path, envelope: str) -> None:
    """Exclusive mode-0600 output; remove only our own partial inode on failure."""
    if not isinstance(envelope, str) or not envelope.startswith(PREFIX) or len(envelope.encode()) > 60000:
        raise SealerUnavailable("OAuth application envelope is unavailable")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    identity = os.fstat(fd)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            fd = None
            output.write(envelope + "\n")
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        if fd is not None:
            os.close(fd)
        try:
            current = path.lstat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                path.unlink()
        except OSError:
            pass
        raise


async def run(args: argparse.Namespace) -> dict:
    """Seal locally without persisting plaintext or altering deployment config."""
    try:
        if custody_mode() != "kms_v1" or args.output.exists() or args.output.is_symlink():
            raise SealerUnavailable("Scoped custody and a new output file are required")
        client_id_name = f"OUTREACH_{args.provider.upper()}_CLIENT_ID"
        client_id = os.getenv(client_id_name, "").strip()
        if not client_id:
            raise SealerUnavailable("OAuth application identity is unavailable")
        secret = read_secret(args.stdin)
        if not secret or len(secret.encode()) > MAX_SECRET_BYTES:
            raise SealerUnavailable("OAuth application input is unavailable")
        envelope = await seal_app_secret(secret, args.provider, client_id, args.generation)
        del secret
        if os.getenv(client_id_name, "").strip() != client_id:
            raise SealerUnavailable("OAuth application identity changed during sealing")
        write_envelope(args.output, envelope)
        return {"status": "encrypted_file_ready", "provider": args.provider, "generation": args.generation}
    except Exception:
        raise SealerUnavailable("OAuth application sealing is unavailable; no configuration was installed") from None


def main() -> int:
    args = parser().parse_args()
    try:
        asyncio.run(run(args))
        return 0
    except SealerUnavailable:
        print("OAuth application sealing is unavailable; no configuration was installed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
