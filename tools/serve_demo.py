"""Local-only review console; all workflow actions still go through IRIS.

Run from the repository: python tools/serve_demo.py
Windows with Docker in WSL: add --wsl-distro Ubuntu-24.04
No third-party Python packages, shell interpolation, or model calls here.
"""
import argparse
import base64
import json
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
COMMAND = []


def iris_request(payload):
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=True).encode()).decode()
    script = ('zn "QUEUECARE"\n'
              f'set request=$SYSTEM.Encryption.Base64Decode("{encoded}")\n'
              'set reply=##class(QueueCare.Demo).Dispatch(request)\n'
              'write !,"QUEUECARE_RESULT_BEGIN",!,reply,!,"QUEUECARE_RESULT_END",!\n'
              'halt\n')
    with LOCK:
        result = subprocess.run(COMMAND, input=script, text=True, capture_output=True,
                                cwd=ROOT, timeout=180, encoding="utf-8", errors="replace")
    start = result.stdout.find("\nQUEUECARE_RESULT_BEGIN\n")
    end = result.stdout.find("\nQUEUECARE_RESULT_END", start)
    if result.returncode or start < 0 or end < 0:
        raise RuntimeError("IRIS did not return a result. Start the containers and compile the latest source.")
    return json.loads(result.stdout[start + len("\nQUEUECARE_RESULT_BEGIN\n"):end])


class Handler(BaseHTTPRequestHandler):
    def allowed_host(self):
        return self.headers.get("Host") in {
            f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def respond(self, status, value, content_type="application/json"):
        data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.allowed_host():
            return self.respond(403, {"ok": False, "error": "local_host_required"})
        if self.path != "/":
            return self.respond(404, {"ok": False, "error": "not_found"})
        page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.respond(200, page.replace("__LOCAL_REQUEST_TOKEN__", TOKEN), "text/html")

    def do_POST(self):
        origin = self.headers.get("Origin")
        allowed_origins = {f"http://127.0.0.1:{self.server.server_port}",
                           f"http://localhost:{self.server.server_port}"}
        if (not self.allowed_host() or self.headers.get("X-QueueCare-Token") != TOKEN
                or (origin is not None and origin not in allowed_origins)):
            return self.respond(403, {"ok": False, "error": "local_request_required"})
        if self.path != "/api":
            return self.respond(404, {"ok": False, "error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise ValueError("Invalid request length")
            payload = json.loads(self.rfile.read(length))
            if type(payload) is not dict or payload.get("action") not in {
                    "list", "detail", "create", "approve", "deny", "duplicate"}:
                raise ValueError("Invalid action")
            if not set(payload) <= {"action", "scenario", "mode", "id", "source"}:
                raise ValueError("Unexpected request fields")
            for key, value in payload.items():
                if type(value) is not str or len(value) > 128:
                    raise ValueError("Invalid request field")
            self.respond(200, iris_request(payload))
        except (ValueError, json.JSONDecodeError) as exc:
            self.respond(400, {"ok": False, "error": str(exc)})
        except subprocess.TimeoutExpired:
            self.respond(504, {"ok": False, "error": "Inference timed out. Refresh to inspect the existing event before retrying."})
        except (RuntimeError, OSError) as exc:
            self.respond(503, {"ok": False, "error": str(exc)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8075)
    parser.add_argument("--wsl-distro", help="Use Docker in this WSL distribution")
    args = parser.parse_args()
    if args.wsl_distro:
        linux_root = subprocess.run(["wsl", "-d", args.wsl_distro, "--", "wslpath", "-u", ROOT.as_posix()],
                                    capture_output=True, text=True, check=True).stdout.strip()
        COMMAND.extend(["wsl", "-d", args.wsl_distro, "--cd", linux_root, "--"])
    COMMAND.extend(["docker", "compose", "exec", "-T", "iris", "iris", "session", "IRIS"])
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"QueueCare local console: http://127.0.0.1:{args.port}", flush=True)
    print("Synthetic data and local sink only. Stop with Ctrl+C.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
