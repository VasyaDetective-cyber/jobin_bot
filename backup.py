from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile

import config
from timeutil import now_local


def _make_copy(dst_path: str) -> None:
    src = sqlite3.connect(config.DB_PATH)
    dst = sqlite3.connect(dst_path)
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()


async def create_backup() -> tuple[str, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await asyncio.to_thread(_make_copy, path)
    return path, f"jobin_backup_{now_local():%Y-%m-%d_%H-%M}.db"