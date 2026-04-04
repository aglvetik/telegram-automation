from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback.
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - Linux fallback.
    msvcrt = None


class DuplicateInstanceError(RuntimeError):
    """Raised when another process already holds the service lock."""


class SingleInstanceLock:
    """Cross-platform non-blocking process lock backed by a lock file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: TextIO | None = None

    def acquire(self) -> "SingleInstanceLock":
        """Acquire the lock or fail fast if another process already owns it."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")

        try:
            self._acquire_platform_lock(handle)
        except OSError as exc:
            holder = self._read_holder(handle)
            handle.close()
            message = f"Another instance is already running; lock file: {self.path}"
            if holder:
                message = f"{message}; current holder: {holder}"
            raise DuplicateInstanceError(message) from exc

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        return self

    def release(self) -> None:
        """Release the lock if it is currently held."""

        if self._handle is None:
            return

        try:
            self._handle.seek(0)
            self._handle.truncate()
            self._handle.flush()
            self._release_platform_lock(self._handle)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "SingleInstanceLock":
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()

    @staticmethod
    def _read_holder(handle: TextIO) -> str:
        try:
            handle.seek(0)
            return handle.read().strip()
        except OSError:
            return ""

    @staticmethod
    def _acquire_platform_lock(handle: TextIO) -> None:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return

        if msvcrt is not None:  # pragma: no cover - Windows only.
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return

        raise OSError("No supported file locking implementation is available")

    @staticmethod
    def _release_platform_lock(handle: TextIO) -> None:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return

        if msvcrt is not None:  # pragma: no cover - Windows only.
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
