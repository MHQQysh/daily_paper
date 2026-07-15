from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

try:
    from scripts import paper_service
except ImportError:
    import paper_service


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
FETCH_SCRIPT = ROOT / "scripts" / "fetch_papers.py"
MAX_BODY_BYTES = 1_000_000
MAX_OUTPUT_LINES = 30
OPERATION_LOCK = threading.Lock()


def _bounded_int(payload: dict[str, Any], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(payload.get(name, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def validate_run_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    target_date = str(payload.get("target_date", "") or "").strip()
    if target_date:
        try:
            dt.date.fromisoformat(target_date)
        except ValueError as exc:
            raise ValueError("target_date must use YYYY-MM-DD") from exc

    topics = payload.get("topics", [])
    if not isinstance(topics, list):
        raise ValueError("topics must be a list")
    if len(topics) > 100:
        raise ValueError("topics cannot contain more than 100 directions")

    api_key = str(payload.get("deepseek_api_key", "") or "").strip()
    if len(api_key) > 500:
        raise ValueError("deepseek_api_key is too long")

    return {
        "lookback_days": _bounded_int(payload, "lookback_days", 3, 1, 365),
        "target_date": target_date,
        "max_results": _bounded_int(payload, "max_results", 80, 1, 1000),
        "min_score": _bounded_int(payload, "min_score", 18, 0, 100),
        "topics": topics,
        "deepseek_api_key": api_key,
    }


def build_fetch_command(request: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        str(FETCH_SCRIPT),
        "--days",
        str(request["lookback_days"]),
        "--max-results",
        str(request["max_results"]),
        "--min-score",
        str(request["min_score"]),
    ]
    if request["target_date"]:
        command.extend(["--date", request["target_date"]])
    if request["topics"]:
        command.extend(["--topics-json", json.dumps({"topics": request["topics"]}, ensure_ascii=False)])
    return command


def sanitize_output(value: str, api_key: str) -> str:
    clean = value.strip()
    if api_key:
        clean = clean.replace(api_key, "[redacted]")
    return clean


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "state": "idle",
            "message": "Ready for a local search.",
            "output": [],
            "started_at": "",
            "finished_at": "",
            "return_code": None,
            "request": {},
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._status)

    def start(self, request: dict[str, Any]) -> dict[str, Any]:
        if not OPERATION_LOCK.acquire(blocking=False):
            raise RuntimeError("Another paper operation is already running.")
        public_request = {key: value for key, value in request.items() if key != "deepseek_api_key"}
        with self._lock:
            if self._status["state"] == "running":
                OPERATION_LOCK.release()
                raise RuntimeError("A local search is already running.")
            self._status = {
                "state": "running",
                "message": "Starting local search...",
                "output": [],
                "started_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
                "finished_at": "",
                "return_code": None,
                "request": public_request,
            }

        worker = threading.Thread(target=self._run, args=(request,), daemon=True)
        worker.start()
        return self.snapshot()

    def _append_output(self, line: str) -> None:
        if not line:
            return
        with self._lock:
            self._status["output"].append(line)
            self._status["output"] = self._status["output"][-MAX_OUTPUT_LINES:]
            self._status["message"] = line

    def _finish(self, state: str, return_code: int, message: str) -> None:
        with self._lock:
            self._status["state"] = state
            self._status["return_code"] = return_code
            self._status["finished_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            self._status["message"] = message

    def _run(self, request: dict[str, Any]) -> None:
        api_key = request.get("deepseek_api_key", "")
        env = os.environ.copy()
        if api_key:
            env["DEEPSEEK_API_KEY"] = api_key
        else:
            env.pop("DEEPSEEK_API_KEY", None)

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(
                build_fetch_command(request),
                cwd=ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
            assert process.stdout is not None
            for raw_line in process.stdout:
                self._append_output(sanitize_output(raw_line, api_key))
            return_code = process.wait()
            if return_code == 0:
                self._finish("succeeded", return_code, "Local search completed.")
            else:
                self._finish("failed", return_code, f"Local search failed with exit code {return_code}.")
        except Exception as exc:
            self._append_output(sanitize_output(str(exc), api_key))
            self._finish("failed", -1, "Could not start the local search.")
        finally:
            OPERATION_LOCK.release()


JOB_MANAGER = JobManager()


class LocalRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/api/status", "/api/health"}:
            self._send_json(JOB_MANAGER.snapshot())
            return
        if path.startswith("/api/"):
            self._send_json({"error": "API endpoint not found"}, HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {
            "/api/run",
            "/api/papers/resolve",
            "/api/papers/analyze",
            "/api/papers/add",
            "/api/papers/delete",
        }:
            self._send_json({"error": "API endpoint not found"}, HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError("request body is empty or too large")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            if path == "/api/run":
                request = validate_run_payload(payload)
                response_payload = JOB_MANAGER.start(request)
                response_status = HTTPStatus.ACCEPTED
            elif path == "/api/papers/resolve":
                input_value = str(payload.get("input", ""))
                if paper_service.is_pdf_url_input(input_value):
                    if not OPERATION_LOCK.acquire(blocking=False):
                        raise RuntimeError("Another paper operation is already running.")
                    try:
                        candidates = paper_service.resolve_paper_input(input_value)
                    finally:
                        OPERATION_LOCK.release()
                else:
                    candidates = paper_service.resolve_paper_input(input_value)
                response_payload = {"candidates": candidates}
                response_status = HTTPStatus.OK
            elif path == "/api/papers/analyze":
                api_key = str(payload.get("deepseek_api_key", "") or "").strip()
                if len(api_key) > 500:
                    raise ValueError("deepseek_api_key is too long")
                topics = payload.get("topics", [])
                if not isinstance(topics, list):
                    raise ValueError("topics must be a list")
                response_payload = {
                    "paper": paper_service.analyze_paper(
                        payload.get("paper", {}),
                        topics,
                        api_key,
                        str(payload.get("model", "deepseek-chat")),
                    )
                }
                response_status = HTTPStatus.OK
            elif path == "/api/papers/add":
                if not OPERATION_LOCK.acquire(blocking=False):
                    raise RuntimeError("Another paper operation is already running.")
                try:
                    selected_topics = payload.get("selected_topics", [])
                    if not isinstance(selected_topics, list):
                        raise ValueError("selected_topics must be a list")
                    response_payload = paper_service.add_paper(payload.get("paper", {}), selected_topics)
                finally:
                    OPERATION_LOCK.release()
                response_status = HTTPStatus.OK
            else:
                if not OPERATION_LOCK.acquire(blocking=False):
                    raise RuntimeError("Another paper operation is already running.")
                try:
                    response_payload = paper_service.delete_paper(payload.get("paper", {}))
                finally:
                    OPERATION_LOCK.release()
                response_status = HTTPStatus.OK
        except json.JSONDecodeError:
            self._send_json({"error": "request body must be valid JSON"}, HTTPStatus.BAD_REQUEST)
            return
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except LookupError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        except RuntimeError as exc:
            self._send_json({"error": str(exc), "status": JOB_MANAGER.snapshot()}, HTTPStatus.CONFLICT)
            return
        except Exception as exc:
            api_key = str(payload.get("deepseek_api_key", "") or "") if isinstance(payload, dict) else ""
            message = sanitize_output(str(exc), api_key) or exc.__class__.__name__
            self._send_json({"error": f"External service request failed: {message}"}, HTTPStatus.BAD_GATEWAY)
            return

        self._send_json(response_payload, response_status)

    def log_message(self, format_string: str, *args: Any) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve Daily Paper with local run controls.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), LocalRequestHandler)
    print(f"Daily Paper local server: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
