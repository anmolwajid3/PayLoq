"""PL-56 session-only company upload helpers + API smoke."""

from __future__ import annotations

import io
import json

from openpyxl import Workbook

from payloq_api.services import session_upload as su


def test_parse_csv_and_clear():
    su.clear_session("tester")
    csv_bytes = b"week,balance\n1,1000\n2,900\n"
    sess = su.upsert_uploads(
        "tester",
        [("cash.csv", csv_bytes)],
        ttl_s=60,
    )
    assert sess.filenames == ["cash.csv"]
    assert "cash.csv" in sess.figures["tables"]
    pub = su.session_public(sess)
    assert pub["ttl_remaining_s"] > 0
    assert su.clear_session("tester") is True
    assert su.get_session("tester") is None


def test_parse_xlsx_and_json_pack_like():
    su.clear_session("xlsx-user")
    wb = Workbook()
    ws = wb.active
    ws.title = "History"
    ws.append(["date", "balance"])
    ws.append(["2024-01-01", 50000])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx = buf.getvalue()

    cash = {
        "open_invoices": [{"id": 1}, {"id": 2}],
        "balance_history": [{"week": 1}, {"week": 2}, {"week": 3}],
    }
    sess = su.upsert_uploads(
        "xlsx-user",
        [
            ("scenario.xlsx", xlsx),
            ("cash_and_invoices.json", json.dumps(cash).encode()),
        ],
        ttl_s=120,
    )
    assert "scenario.xlsx" in sess.filenames
    assert sess.figures["summary"]["open_invoices"] == 2
    assert sess.figures["summary"]["balance_history_points"] == 3
    su.clear_session("xlsx-user")
