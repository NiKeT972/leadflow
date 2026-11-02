"""Optional server-side storage in Supabase (Postgres), used by real intake (Gmail, website form, WhatsApp).

Enabled only when SUPABASE_URL and SUPABASE_SERVICE_KEY are set. It talks to Supabase's REST API (PostgREST)
with httpx, so there's no extra SDK. Create the tables with scripts/supabase_schema.sql.
The service key bypasses row-level security, so it must only ever live in server env vars, never in the browser.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx

TIMEOUT = 10


def enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


def _req(method: str, path: str, prefer: str = "return=minimal", **kw) -> httpx.Response:
    key = os.environ["SUPABASE_SERVICE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": prefer}
    r = httpx.request(method, os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + path, headers=headers,
                      timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_lead(business_id: str, enquiry: dict, result: dict) -> str:
    lead_id = str(uuid.uuid4())
    _req("POST", "leads", json={"id": lead_id, "business_id": business_id, "enquiry": enquiry,
                                "result": result, "status": result["state"].get("status", ""),
                                "created_at": now(), "updated_at": now()})
    return lead_id


def update_lead(lead_id: str, result: dict) -> None:
    _req("PATCH", f"leads?id=eq.{lead_id}", json={"result": result, "status": result["state"].get("status", ""),
                                                  "updated_at": now()})


def list_leads(business_id: str, limit: int = 50) -> list[dict]:
    r = _req("GET", f"leads?business_id=eq.{business_id}&order=created_at.desc&limit={limit}"
                    "&select=id,business_id,enquiry,result,status,created_at")
    return r.json()


def get_business(business_id: str) -> dict | None:
    rows = _req("GET", f"businesses?id=eq.{business_id}&select=profile,docs").json()
    return rows[0] if rows else None


def save_business(business_id: str, profile: dict, docs: list[dict]) -> None:
    # on_conflict + merge-duplicates = insert, or update the row if this id already exists (an "upsert").
    _req("POST", "businesses?on_conflict=id", prefer="resolution=merge-duplicates",
         json={"id": business_id, "profile": profile, "docs": docs, "updated_at": now()})
