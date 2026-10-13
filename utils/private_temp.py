"""Private scratch files and stable shared quarantine for same-UID workers."""
import os
import stat
import tempfile
from functools import lru_cache
from typing import BinaryIO


def _component(value: str) -> str:
    if not isinstance(value, str) or not value or value in ('.', '..') or '/' in value or '\\' in value or '\x00' in value:
        raise ValueError('Invalid temporary file component')
    return value


def _private_directory(path: str, *, parent_fd: int | None = None) -> int:
    try:
        os.mkdir(path, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        current = os.fstat(fd)
        if not stat.S_ISDIR(current.st_mode) or current.st_uid != os.getuid():
            raise PermissionError('Temporary directory ownership is not trusted')
        # Owner-only directory traversal is required; group/other have no permissions.
        os.fchmod(fd, 0o700)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
        return fd
    except BaseException:
        os.close(fd)
        raise


def create_quarantine_file(base: str, actor: str, filename: str) -> tuple[BinaryIO, str]:
    """Exclusively create0600 under an owned0700 stable shared root; never follow links."""
    actor, filename = _component(actor), _component(filename)
    root_fd = _private_directory(base)
    try:
        actor_fd = _private_directory(actor, parent_fd=root_fd)
        try:
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=actor_fd)
        finally:
            os.close(actor_fd)
    finally:
        os.close(root_fd)
    try:
        return os.fdopen(fd, 'wb'), os.path.join(base, actor, filename)
    except BaseException:
        os.close(fd)
        raise


@lru_cache(maxsize=None)
def _scratch_root(pid: int) -> str:
    # PID is part of the cache key so prefork workers create their own private root.
    return tempfile.mkdtemp(prefix='unravler-scratch-')


def private_scratch_path(suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, dir=_scratch_root(os.getpid()))
    os.close(fd)
    return path
