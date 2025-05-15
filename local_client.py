"""
local_client.py
Decorator that can transparently run a local Python function on a remote
Flask “/exec” endpoint. Whether a call is executed locally or remotely
is controlled at runtime with the environment variable USE_REMOTE_EXEC.

Key features
============
* The remote URL can be provided per-function
  (`@remote_if_enabled(remote_url=...)`) or via the environment variable
  REMOTE_EXEC_URL.
* Remote stdout and traceback can be printed locally.
* The JSON response is always parsed—even for HTTP 4xx / 5xx—so we can
  surface remote errors cleanly.
"""

from __future__ import annotations

import inspect
import os
import textwrap
import requests
from typing import Callable, List

# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def _remote_enabled() -> bool:
    """
    Return True only if USE_REMOTE_EXEC is set to a truthy value
    ('true', '1', 'yes').  This check is performed at *call time*, so
    you can export the env-var after the module has been imported.
    """
    return os.getenv("USE_REMOTE_EXEC", "false").lower() in ("true", "1", "yes")


def _strip_decorators(src: str) -> str:
    """
    Remove any leading decorator lines ('@…') so that the code sent to
    the server never references the local @remote_if_enabled decorator.
    """
    lines: List[str] = src.splitlines()
    while lines and lines[0].lstrip().startswith("@"):
        lines.pop(0)
    return "\n".join(lines)

# ────────────────────────────────────────────────────────────────
# ① Marker decorator for helper functions / classes
# ────────────────────────────────────────────────────────────────

REMOTE_EXPORTS: list[Callable] = []

def remote_func(obj: Callable):
    """
    Decorate a *helper* function or class with @remote_func to have its
    source automatically bundled and uploaded alongside the entry
    function.  No other behaviour is changed.
    """
    REMOTE_EXPORTS.append(obj)
    return obj

# ────────────────────────────────────────────────────────────────
# ② Main decorator
# ────────────────────────────────────────────────────────────────

def remote_if_enabled(
    *,
    remote_url: str | None = None,
    print_stdout: bool = True,
    print_traceback: bool = True,
    timeout: int = 30,
):
    """
    Parameters
    ----------
    remote_url : str | None
        Absolute URL of the remote “/exec” endpoint.  If None, fallback
        to the REMOTE_EXEC_URL environment variable, and finally to
        'http://localhost:5005/exec'.
    print_stdout : bool
        Whether to echo remote stdout locally.
    print_traceback : bool
        Whether to echo the full remote traceback on error.
    timeout : int
        `requests` timeout (seconds).

    Usage example
    -------------
    @remote_if_enabled(remote_url="http://10.0.0.8:5005/exec")
    def my_func(...): ...
    """
    env_default_url = os.getenv("REMOTE_EXEC_URL", "http://localhost:5005/exec")
    remote_url = remote_url or env_default_url

    def decorator(func: Callable):
        # Source code of the entry function (without decorators)
        func_source = textwrap.dedent(_strip_decorators(inspect.getsource(func)))

        # Combine all @remote_func helper sources
        dep_sources = [
            textwrap.dedent(_strip_decorators(inspect.getsource(obj)))
            for obj in REMOTE_EXPORTS
        ]
        bundle_deps_code = "\n\n".join(dep_sources)

        # Final code string that will be exec’d remotely
        full_code = f"{bundle_deps_code}\n\n{func_source}"

        # --------------------------------------------------------
        # Actual wrapper that replaces the original function
        # --------------------------------------------------------
        def wrapper(*args, **kwargs):
            # Local execution (default) ───────────────────────────
            if not _remote_enabled():
                return func(*args, **kwargs)

            # Remote execution path ──────────────────────────────
            payload = {
                "code": full_code,
                "func_name": func.__name__,
                "args": args,
                "kwargs": kwargs,
            }

            resp = requests.post(remote_url, json=payload, timeout=timeout)

            # Always try to decode JSON—even on non-200 responses
            try:
                data = resp.json()
            except Exception:
                raise RuntimeError(f"Remote returned non-JSON body: {resp.text}")

            # ---------- Success ---------------------------------
            if resp.status_code == 200 and data.get("status") == "ok":
                if print_stdout and data.get("stdout"):
                    print("[REMOTE STDOUT]")
                    print(data["stdout"], end="")
                return data["result"]

            # ---------- Failure ---------------------------------
            if print_stdout and data.get("stdout"):
                print("[REMOTE STDOUT]")
                print(data["stdout"], end="")
            if print_traceback and data.get("traceback"):
                print("[REMOTE TRACEBACK]")
                print(data["traceback"], end="")

            err_msg = data.get("error") or f"HTTP {resp.status_code}"
            raise RuntimeError(f"Remote execution failed: {err_msg}")

        return wrapper

    return decorator
