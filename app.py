"""LeadFlow API (FastAPI on Vercel). The dashboard is served from public/."""
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from leadflow import graph
from leadflow import integrations as io
from leadflow.llm import llm_available, model_name
from leadflow.profiles import PROFILES, SAMPLES, kb_text
from leadflow.state_token import InvalidToken, seal, signing_configured, unseal

app = FastAPI(title="LeadFlow")
ROOT = Path(__file__).parent


class Enquiry(BaseModel):
    channel: str = Field("email", max_length=30)
    from_name: str = Field("", max_length=100)
    from_email: str = Field("", max_length=200)
    subject: str = Field("", max_length=200)
    body: str = Field(min_length=10, max_length=4_000)   # caps keep a public demo's LLM cost and latency bounded


class RunReq(BaseModel):
    enquiry: Enquiry
    profile_id: Literal["ca", "dental", "coaching"] = "ca"
    tone: Literal["friendly", "formal"] = "friendly"


class ResumeReq(BaseModel):
    token: str                                            # signed paused state from the previous response
    decision: Literal["approve", "revise", "reject"]
    feedback: str = Field("", max_length=500)
    edited_reply: str = Field("", max_length=2_000)


def _respond(result: dict) -> dict:
    """When the graph is paused for review, attach a signed token; the browser sends only that token back."""
    if result["paused_at"]:
        result["token"] = seal({"state": result["state"], "paused_at": result["paused_at"]})
    return result


@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm_available(), "model": model_name(), "state_signing": signing_configured(),
            "integrations": io.status()}


@app.get("/api/meta")
def meta():
    profiles = {k: {**{x: v[x] for x in ("id", "name", "kind", "city", "hours", "next_step")},
                    "services": [{"name": s["name"], "price": s["price"]} for s in v["services"]],
                    "kb": kb_text(v)} for k, v in PROFILES.items()}
    return {"profiles": profiles, "samples": SAMPLES, "graph": graph.mermaid()}


@app.post("/api/run")
def run(req: RunReq):
    return _respond(graph.start(req.enquiry.model_dump(), req.profile_id, req.tone))


@app.post("/api/resume")
def resume(req: ResumeReq):
    try:
        paused = unseal(req.token)
    except InvalidToken as e:
        raise HTTPException(400, str(e))
    if req.decision == "revise" and not req.feedback.strip():
        raise HTTPException(422, "Say what to change in the reply.")
    return _respond(graph.resume(paused["state"], req.decision, req.feedback, req.edited_reply))


@app.get("/")
def index():
    return FileResponse(ROOT / "public" / "index.html")
