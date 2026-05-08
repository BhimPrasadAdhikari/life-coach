"""Simple cross-platform atomic JSON read/write with a lockfile.

This provides `read_json_atomic` and `write_json_atomic` helpers which
acquire an exclusive lock implemented by creating a `.lock` file using
O_EXCL semantics. It is not a full-featured locking library but is
sufficient for simple atomicity in this project without extra deps.
"""
import os
import time
import json
import errno


def _acquire_lock(lock_path: str, timeout: float = 5.0, poll: float = 0.05) -> bool:
    start = time.time()
    while True:
        try:
            # Use O_CREAT | O_EXCL to atomically create the lockfile
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            # Write PID and timestamp for debugging
            try:
                os.write(fd, f"{os.getpid()}\n{time.time()}\n".encode("utf-8"))
            finally:
                os.close(fd)
            return True
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            # Lock exists — check for staleness
            try:
                stat = os.stat(lock_path)
                # If lock older than timeout*2, consider it stale
                if time.time() - stat.st_mtime > timeout * 2:
                    try:
                        os.remove(lock_path)
                    except OSError:
                        pass
            except OSError:
                pass

            if time.time() - start >= timeout:
                return False
            time.sleep(poll)


def _release_lock(lock_path: str) -> None:
    try:
        os.remove(lock_path)
    except OSError:
        pass


def write_json_atomic(path: str, data, timeout: float = 5.0) -> None:
    dirname = os.path.dirname(path)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname, exist_ok=True)

    lock_path = f"{path}.lock"
    if not _acquire_lock(lock_path, timeout=timeout):
        raise TimeoutError(f"Could not acquire lock for {path}")

    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        # atomic replace
        os.replace(tmp_path, path)
    finally:
        # cleanup tmp if exists
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        _release_lock(lock_path)


def read_json_atomic(path: str, timeout: float = 5.0):
    # If file doesn't exist, return None
    if not os.path.exists(path):
        return None

    lock_path = f"{path}.lock"
    if not _acquire_lock(lock_path, timeout=timeout):
        raise TimeoutError(f"Could not acquire lock for {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        _release_lock(lock_path)
