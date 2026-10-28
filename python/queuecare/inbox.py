"""Bounded local file transport for the IRIS inbound adapter.

Writers publish by renaming a finished temporary file to incoming/*.json.
Claimed files are never automatically replayed after an interrupted process.
"""
import json
import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 16384
LANES = ("incoming", "processing", "processed", "rejected", "receipts")


def initialize(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("Inbox root must not be a symlink")
    for lane in LANES:
        directory = root / lane
        directory.mkdir(exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Inbox lanes must be regular directories")
    return root.resolve()


def _leaf(token):
    if not token or token != Path(token).name or token in {".", ".."} or "/" in token or "\\" in token:
        raise ValueError("Invalid inbox token")
    return token


def claim(root):
    root = initialize(root)
    for path in sorted((root / "incoming").glob("*.json")):
        if path.is_dir() and not path.is_symlink():
            continue
        # UUID avoids overwriting earlier inputs with the same original name.
        short_name = path.name.encode('utf-8')[:160].decode('utf-8', errors='ignore')
        token = uuid.uuid4().hex + "__" + short_name
        try:
            path.rename(root / "processing" / token)
            return token
        except FileNotFoundError:
            continue  # Another worker claimed the file first.
    return ""


def read_event(root, token):
    path = initialize(root) / "processing" / _leaf(token)
    if path.is_symlink():
        raise ValueError("Symlinks are not accepted")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Only regular files are accepted")
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Event exceeds 16384 bytes")
    return data.decode("utf-8")


def finish(root, token, result_json, rejected=False):
    root = initialize(root)
    token = _leaf(token)
    result = json.loads(result_json)
    lane = "rejected" if rejected else "processed"
    receipt = {"token": token, "original_name": token.partition("__")[2],
               "disposition": lane, "at": datetime.now(timezone.utc).isoformat(),
               "result": result, "external_delivery": False}
    temporary = root / "receipts" / (token + ".part")
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    # Preserve the input even when parsing or workflow handling failed.
    (root / "processing" / token).rename(root / lane / token)
    temporary.replace(root / "receipts" / (token + ".json"))
    return json.dumps(receipt, ensure_ascii=False)


def publish(root, event_json):
    root = initialize(root)
    name = uuid.uuid4().hex
    temporary = root / "incoming" / (name + ".part")
    temporary.write_text(event_json, encoding="utf-8")
    temporary.rename(root / "incoming" / (name + ".json"))
    return name + ".json"
