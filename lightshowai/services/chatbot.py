import os
import pathlib
import re

CHATBOT_URL = os.getenv("OMNIXAS_CHATBOT_URL", "https://localhost:8445")
CHATBOT_PLOT_ROOT = pathlib.Path(
    os.getenv("CHATBOT_PLOT_ROOT", str(pathlib.Path.home() / "tmp"))
).expanduser()
CHATBOT_SRCDOC_MAX_BYTES = int(os.getenv("CHATBOT_SRCDOC_MAX_BYTES", "1500000"))

def _chatbot_turn_roots() -> list[pathlib.Path]:
    """Candidate roots where chatbot turn artifacts may be written."""
    roots = [
        CHATBOT_PLOT_ROOT / "turns",
        pathlib.Path("/tmp/lightshowai_plots/turns"),
    ]
    out = []
    seen = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out

def _latest_chatbot_scores_file(session_started_at: float | None = None) -> pathlib.Path | None:
    """Return the most recently updated chatbot-generated matching_scores.json."""
    latest_path = None
    latest_mtime = -1.0
    for root in _chatbot_turn_roots():
        if not root.exists():
            continue
        for path in root.rglob("matching_scores.json"):
            try:
                if not path.is_file():
                    continue
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if session_started_at is not None and mtime < float(session_started_at):
                continue
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_path = path
    return latest_path

def _latest_chatbot_structure_file() -> pathlib.Path | None:
    """Return the most recently updated chatbot-generated structure HTML file."""
    latest_path = None
    latest_mtime = -1.0
    for root in _chatbot_turn_roots():
        if not root.exists():
            continue
        for path in root.rglob("*_structure.html"):
            try:
                if not path.is_file():
                    continue
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_path = path
    return latest_path

def _read_chatbot_structure_srcdoc(path: pathlib.Path) -> str | None:
    """Read structure HTML into srcDoc payload for same-page embedding."""
    try:
        size = path.stat().st_size
        if size <= 0 or size > CHATBOT_SRCDOC_MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"Could not read chatbot structure HTML {path}: {exc}")
        return None

def _extract_mpid_from_chatbot_meta(meta: dict | None) -> str | None:
    """Extract an MP ID from chatbot structure metadata/path fields."""
    if not isinstance(meta, dict):
        return None

    candidates = [
        str(meta.get("file") or ""),
        str(meta.get("key") or ""),
        str(meta.get("srcdoc") or "")[:2000],
    ]

    for text in candidates:
        match = re.search(r"mp-\d+", text, flags=re.IGNORECASE)
        if match:
            return match.group(0).lower()

    return None
