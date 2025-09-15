
import aiofiles
import asyncio
import os
from typing import Dict, List, Optional, Tuple

try:
    from tqdm import tqdm as tqdm_sync  # type: ignore
except Exception:
    class _Dummy:
        def __init__(self, total=None, desc=None, disable=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def update(self, *a, **k): return None
    tqdm_sync = _Dummy  # type: ignore

DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
STREAM_CHUNK_SIZE = 64 * 1024
# Brief: _is_binary_file
# Brief: _is_binary_file

# Brief: _is_binary_file
async def _is_binary_file(path: str) -> bool:
    try:
        async with aiofiles.open(path, "rb") as f:
            chunk = await f.read(8192)
            if b"\x00" in chunk:
                return True
    except Exception as e:
        print(f"[WARN] Error probing {path}: {e}")
        return True
    return False
# Brief: _read_small_text

# Brief: _read_small_text
async def _read_small_text(path: str) -> Optional[str]:
    try:
        async with aiofiles.open(path, "r", encoding="utf-8", errors="replace") as f:
            return await f.read()
    except Exception as e:
        print(f"[WARN] Error reading {path}: {e}")
        return None
# Brief: _read_large_text_stream

# Brief: _read_large_text_stream
async def _read_large_text_stream(path: str) -> Optional[str]:
    try:
        parts: List[str] = []
        async with aiofiles.open(path, "r", encoding="utf-8", errors="replace") as f:
            while True:
                chunk = await f.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                parts.append(chunk)
        return "".join(parts)
    except Exception as e:
        print(f"[WARN] Error reading {path}: {e}")
        return None
# Brief: read_file_content

# Brief: read_file_content
async def read_file_content(file_path: str, max_file_size: int = DEFAULT_MAX_FILE_SIZE) -> Optional[str]:
    if await _is_binary_file(file_path):
        print(f"[INFO] Skipping binary file: {file_path}")
        return None
    try:
        size = os.path.getsize(file_path)
    except OSError:
        size = 0
    if size > max_file_size:
        return await _read_large_text_stream(file_path)
    return await _read_small_text(file_path)
# Brief: read_files_concurrently

# Brief: read_files_concurrently
async def read_files_concurrently(
    file_paths: List[str],
    base_path: str,
    concurrency: Optional[int] = None,
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    no_progress: bool = False,
) -> Dict[str, str]:
    if concurrency is None:
        cpu = os.cpu_count() or 4
        concurrency = max(8, min(cpu * 2, 128))
    sem = asyncio.Semaphore(concurrency)

    async def _bounded_read(abs_path: str) -> Tuple[str, Optional[str]]:
        async with sem:
            rel_path = os.path.relpath(abs_path, base_path)
            content = await read_file_content(abs_path, max_file_size=max_file_size)
            return rel_path, content

    tasks = [asyncio.create_task(_bounded_read(p)) for p in file_paths]
    results: Dict[str, str] = {}

    with tqdm_sync(total=len(tasks), desc="Reading files", disable=no_progress) as pbar:
        for fut in asyncio.as_completed(tasks):
            rel_path, content = await fut
            if content is not None:
                results[rel_path] = content
            try:
                pbar.update(1)
            except Exception:
                ...
    return results
