"""Where your settings and trades are saved: JSON files next to the app by default, or a private GitHub Gist when
[storage] github_token + gist_id are in secrets — needed on Streamlit Community Cloud, whose disk is wiped every
time the app restarts."""
import json
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ON_CLOUD = str(HERE.resolve()).startswith("/mount/src/")   # Streamlit Community Cloud checks apps out there
_lock = threading.Lock()
_gist_cache: list = [0.0, None]   # [fetched at, {file name: object}] — the whole gist, asked for at most every 5 s


def _cfg() -> dict | None:
    try:
        import streamlit as st
        s = dict(st.secrets.get("storage", {}))
        return s if s.get("github_token") and s.get("gist_id") else None
    except Exception:  # noqa: BLE001 — no secrets file
        return None


def _gist(method: str, cfg: dict, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com/gists/{cfg['gist_id']}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {cfg['github_token']}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "trade-signals-app"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _parse(files: dict) -> dict:
    out = {}
    for name, f in files.items():
        try:
            out[name] = json.loads(f.get("content") or "null")
        except json.JSONDecodeError:
            pass   # a non-JSON file (e.g. the README the gist was created with)
    return out


def _gist_files(cfg: dict) -> dict | None:
    with _lock:
        if _gist_cache[1] is not None and time.time() - _gist_cache[0] < 5:
            return _gist_cache[1]
    for attempt in range(2):
        try:
            files = _parse(_gist("GET", cfg).get("files", {}))
            with _lock:
                _gist_cache[:] = [time.time(), files]
            return files
        except Exception:  # noqa: BLE001 — offline / GitHub hiccup
            if attempt == 0:
                time.sleep(0.5)
    return _gist_cache[1]   # keep using the last copy (None if GitHub never answered)


def backend() -> str:
    return "your private GitHub Gist" if _cfg() else ("the cloud server (temporary)" if ON_CLOUD else "this computer")


def temporary() -> bool:
    """Online without [storage]: everything saved is lost whenever the app restarts or wakes up."""
    return ON_CLOUD and not _cfg()


TEMPORARY_NOTE = ("Online without storage: your settings and trades are lost whenever the app restarts or wakes from "
                  "sleep. Add a **[storage]** section to the app's Secrets to keep them (README → *Use it on your phone*).")


def read(name: str, default):
    """The saved JSON object `name` (e.g. 'profile.json'), or `default` if it doesn't exist yet."""
    cfg = _cfg()
    if not cfg:
        try:
            return json.loads((HERE / name).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return default
    files = _gist_files(cfg)
    return default if files is None or name not in files else files[name]


def write(name: str, obj):
    cfg = _cfg()
    if not cfg:
        p = HERE / name
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, indent=2))
        tmp.replace(p)
        return
    body = {"files": {name: {"content": json.dumps(obj, indent=2)}}}
    for attempt in range(2):
        try:
            files = _parse(_gist("PATCH", cfg, body).get("files", {}))
            break
        except Exception as e:  # noqa: BLE001
            if attempt:
                raise RuntimeError("Couldn't save to your GitHub Gist — check [storage] github_token (needs the "
                                   f"'gist' permission) and gist_id in the app's secrets. ({e})") from e
            time.sleep(0.5)
    files[name] = obj
    with _lock:
        _gist_cache[:] = [time.time(), files]
