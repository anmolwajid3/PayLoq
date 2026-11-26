"""Session-only company data uploads (Excel/CSV/JSON). Discarded on logout / TTL."""

from __future__ import annotations

import csv
import io
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

# username -> session blob (in-process; intentional: no durable store for real data)
_LOCK = threading.Lock()
_SESSIONS: dict[str, "CompanySession"] = {}

DEFAULT_TTL_S = 4 * 3600


@dataclass
class ChatTurn:
    role: str
    content: str
    at: float = field(default_factory=time.time)


@dataclass
class CompanySession:
    username: str
    created_at: float
    expires_at: float
    filenames: list[str] = field(default_factory=list)
    figures: dict[str, Any] = field(default_factory=dict)
    chat: list[ChatTurn] = field(default_factory=list)
    situation_report: str | None = None
    model: str | None = None
    notes: list[str] = field(default_factory=list)

    def expired(self) -> bool:
        return time.time() >= self.expires_at


def _purge_expired() -> None:
    now = time.time()
    dead = [k for k, v in _SESSIONS.items() if v.expires_at <= now]
    for k in dead:
        del _SESSIONS[k]


def get_session(username: str) -> CompanySession | None:
    with _LOCK:
        _purge_expired()
        sess = _SESSIONS.get(username)
        if sess is None or sess.expired():
            _SESSIONS.pop(username, None)
            return None
        return sess


def clear_session(username: str) -> bool:
    with _LOCK:
        return _SESSIONS.pop(username, None) is not None


def _sheet_to_rows(ws) -> list[dict[str, Any]]:
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = next(rows_iter)
    except StopIteration:
        return []
    headers = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(headers)]
    out: list[dict[str, Any]] = []
    for row in rows_iter:
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        item: dict[str, Any] = {}
        for i, h in enumerate(headers):
            item[h] = row[i] if i < len(row) else None
        out.append(item)
    return out


def _parse_xlsx(data: bytes, name: str) -> dict[str, Any]:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets: dict[str, Any] = {}
    for sheet_name in wb.sheetnames:
        sheets[sheet_name] = _sheet_to_rows(wb[sheet_name])
    wb.close()
    return {"source": name, "kind": "xlsx", "sheets": sheets}


def _parse_csv(data: bytes, name: str) -> dict[str, Any]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(r) for r in reader]
    return {"source": name, "kind": "csv", "rows": rows}


def _parse_json(data: bytes, name: str) -> dict[str, Any]:
    payload = json.loads(data.decode("utf-8"))
    return {"source": name, "kind": "json", "data": payload}


def parse_upload(filename: str, data: bytes) -> dict[str, Any]:
    lower = filename.lower()
    if lower.endswith(".xlsx") or lower.endswith(".xlsm"):
        return _parse_xlsx(data, filename)
    if lower.endswith(".csv"):
        return _parse_csv(data, filename)
    if lower.endswith(".json"):
        return _parse_json(data, filename)
    raise ValueError(f"Unsupported file type: {filename} (use .xlsx, .csv, or .json)")


def _merge_figures(parsed_files: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a chat-ready figures dict from uploaded pieces (code-owned summary)."""
    figures: dict[str, Any] = {
        "uploads": [{"source": p["source"], "kind": p["kind"]} for p in parsed_files],
        "tables": {},
        "pack_like": {},
    }
    for p in parsed_files:
        src = Path(p["source"]).name
        if p["kind"] == "xlsx":
            figures["tables"][src] = p.get("sheets") or {}
        elif p["kind"] == "csv":
            figures["tables"][src] = {"csv": p.get("rows") or []}
        elif p["kind"] == "json":
            data = p.get("data")
            key = src.replace(".json", "")
            if isinstance(data, dict):
                # Recognise work-order pack fragments by filename.
                if key in ("cash_and_invoices", "monthly_reports", "input", "answer_key"):
                    figures["pack_like"][key] = data
                else:
                    figures["tables"][src] = data
            else:
                figures["tables"][src] = data

    # Compact numeric peek for the model (avoid dumping entire sheets when huge).
    peek: dict[str, Any] = {}
    for name, table in figures["tables"].items():
        if isinstance(table, dict):
            peek[name] = {
                sheet: (rows[:12] if isinstance(rows, list) else rows)
                for sheet, rows in list(table.items())[:8]
            }
        else:
            peek[name] = table
    figures["peek"] = peek
    if figures["pack_like"]:
        # Prefer pack-shaped figures for the virtual accountant when present.
        cash = figures["pack_like"].get("cash_and_invoices") or {}
        monthly = figures["pack_like"].get("monthly_reports") or {}
        figures["summary"] = {
            "has_cash_and_invoices": bool(cash),
            "has_monthly_reports": bool(monthly),
            "open_invoices": len((cash.get("open_invoices") or [])) if isinstance(cash, dict) else 0,
            "balance_history_points": len((cash.get("balance_history") or []))
            if isinstance(cash, dict)
            else 0,
            "months": len((monthly.get("months") or [])) if isinstance(monthly, dict) else 0,
            "cash_and_invoices": cash,
            "monthly_reports": monthly,
            "input": figures["pack_like"].get("input"),
        }
    else:
        figures["summary"] = {"tables": peek}
    return figures


def upsert_uploads(
    username: str,
    files: list[tuple[str, bytes]],
    *,
    ttl_s: float = DEFAULT_TTL_S,
    replace: bool = True,
) -> CompanySession:
    parsed: list[dict[str, Any]] = []
    names: list[str] = []
    notes: list[str] = []
    for name, raw in files:
        try:
            parsed.append(parse_upload(name, raw))
            names.append(name)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{name}: {exc}")

    if not parsed and notes:
        raise ValueError("; ".join(notes))

    figures = _merge_figures(parsed)
    now = time.time()
    with _LOCK:
        _purge_expired()
        prev = _SESSIONS.get(username) if not replace else None
        if prev and not prev.expired() and not replace:
            names = list(dict.fromkeys([*prev.filenames, *names]))
            # re-parse not stored; keep previous figures merged shallowly
            figures = {**prev.figures, **figures}
            sess = prev
            sess.filenames = names
            sess.figures = figures
            sess.expires_at = now + ttl_s
            sess.notes = [*prev.notes, *notes]
            sess.chat = prev.chat
            sess.situation_report = prev.situation_report
            sess.model = prev.model
        else:
            sess = CompanySession(
                username=username,
                created_at=now,
                expires_at=now + ttl_s,
                filenames=names,
                figures=figures,
                notes=notes,
            )
            _SESSIONS[username] = sess
        return sess


def append_chat(username: str, role: str, content: str) -> CompanySession:
    with _LOCK:
        sess = _SESSIONS.get(username)
        if sess is None or sess.expired():
            raise KeyError("No active company-data session")
        sess.chat.append(ChatTurn(role=role, content=content))
        return sess


def set_report(username: str, report: str, *, model: str | None) -> CompanySession:
    with _LOCK:
        sess = _SESSIONS.get(username)
        if sess is None or sess.expired():
            raise KeyError("No active company-data session")
        sess.situation_report = report
        sess.model = model
        return sess


def session_public(sess: CompanySession) -> dict[str, Any]:
    return {
        "username": sess.username,
        "created_at": sess.created_at,
        "expires_at": sess.expires_at,
        "ttl_remaining_s": max(0, int(sess.expires_at - time.time())),
        "filenames": list(sess.filenames),
        "notes": list(sess.notes),
        "model": sess.model,
        "has_figures": bool(sess.figures),
        "figure_summary": sess.figures.get("summary")
        if isinstance(sess.figures.get("summary"), dict)
        else {"keys": list((sess.figures or {}).keys())},
        "situation_report": sess.situation_report,
        "chat": [{"role": t.role, "content": t.content, "at": t.at} for t in sess.chat],
    }
