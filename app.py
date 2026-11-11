"""LeadFlow API (FastAPI on Vercel). The dashboard is served from public/."""
import hmac
import io
import json
import os
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from leadflow import graph, storage
from leadflow import integrations as io_
from leadflow.followup import draft_followup
from leadflow.llm import llm_available, model_name, tracing_enabled
from leadflow.profiles import PROFILES, SAMPLES, kb_text, resolve_profile
from leadflow.retriever import builtin_docs
from leadflow.state_token import InvalidToken, seal, signing_configured, unseal

app = FastAPI(title="LeadFlow")
ROOT = Path(__file__).parent


# --------------------------------------------------------------------------- models

class Enquiry(BaseModel):
    channel: str = Field("email", max_length=30)
    from_name: str = Field("", max_length=100)
    from_email: str = Field("", max_length=200)
    subject: str = Field("", max_length=200)
    body: str = Field(min_length=10, max_length=4_000)   # caps keep a public demo's LLM cost and latency bounded
    reply_to: str = Field("", max_length=30)             # WhatsApp number to answer, set by the WhatsApp webhook


class Doc(BaseModel):
    name: str = Field(max_length=120)
    text: str = Field(max_length=30_000)


class RunReq(BaseModel):
    enquiry: Enquiry
    profile_id: str = Field("ca", max_length=40)   # a built-in business, or "custom" with `profile`
    profile: Optional[dict] = None                  # from the settings page; validated by leadflow.profiles.Profile
    docs: Optional[list[Doc]] = Field(None, max_length=8)   # custom documents for RAG; None = built-in docs
    tone: Literal["friendly", "formal"] = "friendly"


class ResumeReq(BaseModel):
    token: str                                            # signed paused state from the previous response
    decision: Literal["approve", "revise", "reject"]
    feedback: str = Field("", max_length=500)
    edited_reply: str = Field("", max_length=2_000)
    lead_id: str = Field("", max_length=40)               # set for leads stored server-side (real intake)


class IntakeReq(BaseModel):
    business_id: str = Field("ca", max_length=40)
    enquiry: Enquiry


class BusinessReq(BaseModel):
    business_id: str = Field(pattern=r"^[a-z0-9-]{2,40}$")
    profile: dict
    docs: list[Doc] = Field(default_factory=list, max_length=8)


class FollowupReq(BaseModel):
    token: str                                            # done_token of an approved lead
    days: int = Field(2, ge=1, le=60)


class FollowupSendReq(BaseModel):
    token: str
    text: str = Field(min_length=10, max_length=2_000)


# --------------------------------------------------------------------------- helpers

def _respond(result: dict) -> dict:
    """Paused → a signed token to resume with. Finished and approved → a signed done_token for follow-ups."""
    if result["paused_at"]:
        result["token"] = seal({"state": result["state"], "paused_at": result["paused_at"]})
    elif result["state"].get("status") in ("done", "done_with_errors"):
        result["done_token"] = seal({"state": result["state"], "kind": "done"})
    return result


def _unseal_or_400(token: str) -> dict:
    try:
        return unseal(token)
    except InvalidToken as e:
        raise HTTPException(400, str(e))


def _profile_or_422(profile_id: str, custom: Optional[dict]) -> dict:
    if custom is None and profile_id not in PROFILES:
        raise HTTPException(422, f"Unknown business '{profile_id}'.")
    try:
        return resolve_profile(profile_id, custom)
    except ValidationError as e:
        raise HTTPException(422, "Business settings are invalid: " + "; ".join(
            f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:3]))


def _require(secret_env: str, given: Optional[str]) -> None:
    """Shared-secret check for the endpoints that touch real data. Disabled (403) until the env var is set."""
    secret = os.getenv(secret_env)
    if not secret:
        raise HTTPException(403, f"{secret_env} is not set on the server, so this endpoint is turned off.")
    if not given or not hmac.compare_digest(given, secret):
        raise HTTPException(401, "Wrong or missing key.")


def _business(business_id: str) -> tuple[dict, Optional[list]]:
    """A built-in demo business, or one saved from the settings page into Supabase."""
    if business_id in PROFILES:
        return PROFILES[business_id], None
    if storage.enabled():
        row = storage.get_business(business_id)
        if row:
            return resolve_profile("custom", row["profile"]), row.get("docs") or []
    raise HTTPException(404, f"Unknown business '{business_id}'.")


# --------------------------------------------------------------------------- demo endpoints

@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm_available(), "model": model_name(), "state_signing": signing_configured(),
            "integrations": io_.status(), "storage": storage.enabled(),
            "intake": bool(os.getenv("INTAKE_KEY")), "admin": bool(os.getenv("ADMIN_TOKEN")), "tracing": tracing_enabled()}


@app.get("/api/meta")
def meta():
    profiles = {k: {**{x: v[x] for x in ("id", "name", "kind", "city", "hours", "next_step")},
                    "services": [{"name": s["name"], "price": s["price"]} for s in v["services"]],
                    "kb": kb_text(v), "docs": [d["name"] for d in builtin_docs(k)], "full": v} for k, v in PROFILES.items()}
    return {"profiles": profiles, "samples": SAMPLES, "graph": graph.mermaid()}


@app.post("/api/run")
def run(req: RunReq):
    profile = _profile_or_422(req.profile_id, req.profile)
    docs = [d.model_dump() for d in req.docs] if req.docs is not None else None
    return _respond(graph.start(req.enquiry.model_dump(), profile, req.tone, docs))


@app.post("/api/resume")
def resume(req: ResumeReq, x_admin_token: Optional[str] = Header(None)):
    paused = _unseal_or_400(req.token)
    if req.decision == "revise" and not req.feedback.strip():
        raise HTTPException(422, "Say what to change in the reply.")
    if req.lead_id:
        _require("ADMIN_TOKEN", x_admin_token)
    out = _respond(graph.resume(paused["state"], req.decision, req.feedback, req.edited_reply))
    if req.lead_id and storage.enabled():
        storage.update_lead(req.lead_id, out)
    return out


@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    """Turn an uploaded PDF / TXT / MD into plain text for the settings page's documents (RAG)."""
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "File is larger than 2 MB.")
    name = (file.filename or "document").rsplit("/", 1)[-1]
    if name.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            text = "\n\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages[:40])
        except Exception:
            raise HTTPException(422, "Couldn't read this PDF. Try a text-based PDF or paste the text.")
    elif name.lower().endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise HTTPException(422, "Upload a .pdf, .txt or .md file.")
    if not text.strip():
        raise HTTPException(422, "No text found (scanned PDFs need OCR first).")
    return {"name": name.rsplit(".", 1)[0], "text": text[:30_000]}


@app.post("/api/followup")
def followup(req: FollowupReq):
    st = _unseal_or_400(req.token)
    if st.get("kind") != "done":
        raise HTTPException(400, "Follow-ups are for leads you've already replied to.")
    return draft_followup(st["state"], req.days)


@app.post("/api/followup/send")
def followup_send(req: FollowupSendReq):
    st = _unseal_or_400(req.token)
    if st.get("kind") != "done":
        raise HTTPException(400, "Follow-ups are for leads you've already replied to.")
    s = {**st["state"], "final_reply": req.text}
    sent = io_.send_reply(s)
    return {"action": {"name": "send_reply", **sent}}


@app.get("/api/eval")
def eval_reports():
    out = {}
    for p in sorted((ROOT / "evals").glob("report_*.json")):
        out[p.stem.replace("report_", "")] = json.loads(p.read_text(encoding="utf-8"))
    return out


# --------------------------------------------------------------------------- real intake (needs env vars)

@app.post("/api/intake")
def intake(req: IntakeReq, x_intake_key: Optional[str] = Header(None)):
    """Entry point for real enquiries: the Gmail script, a website form or the WhatsApp webhook.
    Runs the workflow up to the approval pause, stores the lead (if Supabase is set up) and pings Telegram."""
    _require("INTAKE_KEY", x_intake_key)
    return _ingest(req.business_id, req.enquiry.model_dump())


def _ingest(business_id: str, enquiry: dict) -> dict:
    profile, docs = _business(business_id)
    out = _respond(graph.start(enquiry, profile, "friendly", docs))
    lead_id = storage.save_lead(business_id, enquiry, out) if storage.enabled() else ""
    if out["state"].get("status") == "awaiting_review":
        io_.review_alert(out["state"], lead_id)
    return {"lead_id": lead_id, "status": out["state"].get("status"), "stored": bool(lead_id)}


@app.get("/api/leads")
def leads(business_id: str = Query("ca", max_length=40), x_admin_token: Optional[str] = Header(None)):
    _require("ADMIN_TOKEN", x_admin_token)
    if not storage.enabled():
        raise HTTPException(503, "Supabase isn't configured (SUPABASE_URL, SUPABASE_SERVICE_KEY).")
    return storage.list_leads(business_id)


@app.post("/api/business")
def save_business(req: BusinessReq, x_admin_token: Optional[str] = Header(None)):
    _require("ADMIN_TOKEN", x_admin_token)
    if not storage.enabled():
        raise HTTPException(503, "Supabase isn't configured (SUPABASE_URL, SUPABASE_SERVICE_KEY).")
    profile = _profile_or_422("custom", req.profile)
    storage.save_business(req.business_id, {**profile, "id": req.business_id}, [d.model_dump() for d in req.docs])
    return {"ok": True, "business_id": req.business_id}


@app.get("/api/whatsapp")
def whatsapp_verify(mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
                    challenge: str = Query("", alias="hub.challenge")):
    """Meta calls this once when you register the webhook; we echo the challenge if the verify token matches."""
    expected = os.getenv("WHATSAPP_VERIFY_TOKEN")
    if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
        return PlainTextResponse(challenge)
    raise HTTPException(403, "Verification failed.")


def parse_whatsapp(payload: dict) -> list[dict]:
    """Pull text messages out of a WhatsApp Cloud API webhook payload as LeadFlow enquiries."""
    out = []
    for entry in payload.get("entry", []):
        for ch in entry.get("changes", []):
            v = ch.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in v.get("contacts", [])}
            for m in v.get("messages", []):
                if m.get("type") != "text":
                    continue
                body = (m.get("text") or {}).get("body", "").strip()
                if len(body) < 2:
                    continue
                out.append({"channel": "whatsapp", "from_name": names.get(m.get("from"), ""), "from_email": "",
                            "subject": "WhatsApp message", "body": body.ljust(10)[:4000], "reply_to": m.get("from", "")})
    return out


@app.post("/api/whatsapp")
async def whatsapp_incoming(request: Request, x_hub_signature_256: Optional[str] = Header(None)):
    """Incoming WhatsApp messages. Meta signs each request with your app secret; we verify it before trusting it."""
    raw = await request.body()
    secret = os.getenv("WHATSAPP_APP_SECRET")
    if not secret:
        raise HTTPException(403, "WHATSAPP_APP_SECRET is not set on the server, so this endpoint is turned off.")
    expected = "sha256=" + hmac.new(secret.encode(), raw, "sha256").hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(x_hub_signature_256, expected):
        raise HTTPException(401, "Bad signature.")
    business_id = os.getenv("WHATSAPP_BUSINESS_ID", "ca")
    results = [_ingest(business_id, e) for e in parse_whatsapp(json.loads(raw or b"{}"))]
    return {"received": len(results)}


@app.get("/")
def index():
    return FileResponse(ROOT / "public" / "index.html")
