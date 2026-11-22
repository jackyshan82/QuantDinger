"""Private, text-only bridge to Codex CLI using a saved ChatGPT login."""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_slot = threading.BoundedSemaphore(1)
_MAX_BODY = 2 * 1024 * 1024
_SCHEMA = {"type": "object", "properties": {"response": {"type": "string"}},
           "required": ["response"], "additionalProperties": False}


def login_environment():
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "HOME", "CODEX_HOME", "LANG", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
    binary = os.getenv("CODEX_CLI_BIN", "/usr/local/bin/codex")
    status = subprocess.run([binary, "login", "status"], env=env, capture_output=True, text=True, timeout=10)
    if status.returncode or "ChatGPT" not in status.stdout + status.stderr:
        raise RuntimeError("codexBridge.chatgptLoginRequired")
    return binary, env


def run_codex(messages, model="", json_mode=False, timeout=180):
    deadline = time.monotonic() + timeout
    if not isinstance(messages, list) or not messages:
        raise ValueError("codexBridge.messagesRequired")
    for item in messages:
        if not isinstance(item, dict) or item.get("role") not in {"system", "developer", "user", "assistant", "tool"}:
            raise ValueError("codexBridge.invalidMessage")
        if not isinstance(item.get("content"), str):
            raise ValueError("codexBridge.textMessagesOnly")
    if not isinstance(model, str) or (model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", model)):
        raise ValueError("codexBridge.invalidModel")
    # Only authentication storage is shared with the CLI. API keys and the
    # HTTP bridge credential are never passed to a model-controlled process.
    binary, env = login_environment()
    with tempfile.TemporaryDirectory(prefix="codex-text-") as work:
        output, schema = Path(work) / "reply.json", Path(work) / "schema.json"
        schema.write_text(json.dumps(_SCHEMA))
        command = [binary, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
                   "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never",
                   "-c", 'forced_login_method="chatgpt"', "-c", 'approval_policy="never"',
                   "-c", 'web_search="disabled"']
        for feature in ("shell_tool", "apps", "browser_use", "computer_use", "multi_agent", "code_mode"):
            command += ["--disable", feature]
        if model:
            command += ["--model", model]
        command += ["--output-schema", str(schema), "--output-last-message", str(output), "-"]
        prompt = (
            "You are a text-only assistant for QuantDinger. Complete the application conversation below. "
            "Honor its system/developer instructions. Do not inspect files, execute commands, use tools, "
            "or access external services. Return the final answer in the response string of the output schema. "
            + ("That response string must itself contain one valid JSON object, without markdown fences. "
               if json_mode else "")
            + "\nApplication conversation:\n" + json.dumps(messages, ensure_ascii=False)
        )
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              text=True, cwd=work, env=env, start_new_session=True) as process:
            try:
                _, stderr = process.communicate(prompt, timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise TimeoutError("codexBridge.timeout") from None
            if process.returncode or not output.exists():
                # CLI output may contain account details. Never return or log it.
                raise RuntimeError("codexBridge.executionFailed")
        try:
            answer = json.loads(output.read_text())["response"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError()
            if json_mode and not isinstance(json.loads(answer), dict):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise RuntimeError("codexBridge.invalidResponse") from None
        matched = re.search(r"(?m)^model:\s*(\S+)", stderr)
        return {"content": answer, "model": matched.group(1) if matched else model or "codex-default"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        token = os.getenv("CODEX_BRIDGE_TOKEN", "")
        return len(token) >= 32 and hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

    def do_GET(self):
        if not self.authorized():
            return self.reply(401, {"error": "codexBridge.unauthorized"})
        if self.path != "/health":
            return self.reply(404, {"error": "codexBridge.notFound"})
        try:
            login_environment()
        except Exception:
            return self.reply(503, {"error": "codexBridge.chatgptLoginRequired"})
        return self.reply(200, {"status": "ready", "authentication": "chatgpt"})

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, {"error": "codexBridge.unauthorized"})
        if self.path != "/generate":
            return self.reply(404, {"error": "codexBridge.notFound"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > _MAX_BODY:
                return self.reply(413, {"error": "codexBridge.requestTooLarge"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError()
            timeout = max(1, min(300, int(payload.get("timeout") or 180)))
        except (ValueError, TypeError):
            return self.reply(400, {"error": "codexBridge.invalidRequest"})
        deadline = time.monotonic() + timeout
        if not _slot.acquire(timeout=timeout):
            return self.reply(429, {"error": "codexBridge.busy"})
        try:
            result = run_codex(payload.get("messages"), payload.get("model") or "",
                               payload.get("json_mode") is True, max(0.1, deadline - time.monotonic()))
            self.reply(200, result)
        except ValueError as exc:
            self.reply(400, {"error": str(exc)})
        except (TimeoutError, subprocess.TimeoutExpired):
            self.reply(504, {"error": "codexBridge.timeout"})
        except Exception:
            self.reply(502, {"error": "codexBridge.executionFailed"})
        finally:
            _slot.release()


if __name__ == "__main__":
    if len(os.getenv("CODEX_BRIDGE_TOKEN", "")) < 32:
        raise SystemExit("CODEX_BRIDGE_TOKEN must contain at least 32 characters")
    ThreadingHTTPServer(("0.0.0.0", 8765), Handler).serve_forever()
