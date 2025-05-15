#!/usr/bin/env python3
"""
Very minimal remote-exec service
================================
POST /exec  JSON payload:
    {
        "code":      "<full source string>",
        "func_name": "<entry function name>",
        "args":      [<positional args>],        # optional
        "kwargs":    {<keyword args>}            # optional
    }

Success response (HTTP 200):
    {
        "status": "ok",
        "result":   <return value>,
        "stdout":   "<captured console output>"
    }

Failure response (HTTP 500):
    {
        "status":    "error",
        "error":      "<str(exc)>",
        "traceback":  "<full Python traceback>",
        "stdout":     "<output emitted before the exception>"
    }
"""

from __future__ import annotations
import io
import contextlib
import logging
import traceback

from flask import Flask, request, jsonify

# ───────────── basic logging ─────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ───────────── Flask app ─────────────
app = Flask(__name__)

@app.route("/exec", methods=["POST"])
def exec_code():
    # create stdout buffer early so we still have it on errors
    stdout_buf = io.StringIO()
    try:
        payload   = request.get_json(force=True)
        code      = payload["code"]
        func_name = payload["func_name"]
        args      = payload.get("args", [])
        kwargs    = payload.get("kwargs", {})

        log.info("Executing %s", func_name)

        # Use ONE dictionary for both globals and locals
        # so helper functions can see each other.
        env: dict[str, object] = {}
        with contextlib.redirect_stdout(stdout_buf):
            exec(code, env, env)                 # ← single shared namespace
            result = env[func_name](*args, **kwargs)

        log.info("Execution of %s succeeded", func_name)

        return jsonify({
            "status": "ok",
            "result": result,
            "stdout": stdout_buf.getvalue(),
        })

    except Exception as exc:
        tb = traceback.format_exc()
        log.error("Execution error: %s", exc)
        return jsonify({
            "status": "error",
            "error": str(exc),
            "traceback": tb,
            "stdout": stdout_buf.getvalue(),
        }), 500
    
@app.route("/", methods=["GET"])
def index():
    return "Evalmode remote-exec server is running."

# ───────────── entry point ─────────────
if __name__ == "__main__":
    log.info("Starting remote-exec server on :5005")
    app.run(host="0.0.0.0", port=5005, threaded=True)
