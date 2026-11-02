import os

os.environ["GROQ_API_KEY"] = ""          # set (not pop) BEFORE imports so load_dotenv(override=False) can't load a real key
for k in ("GOOGLE_SHEETS_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "RESEND_API_KEY", "FROM_EMAIL"):
    os.environ[k] = ""                   # integrations stay simulated: tests never touch the network

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

import app as api
from leadflow import graph, rules
from leadflow.profiles import PROFILES, SAMPLES, get_profile, kb_text
from leadflow.state_token import seal

client = TestClient(api.app)
EXPECTED = {"ca1": "sales", "ca2": "sales", "ca3": "sales", "ca4": "support", "ca5": "spam", "ca6": "job_application",
            "d1": "sales", "d2": "sales", "d3": "sales", "d4": "partnership", "d5": "spam",
            "c1": "sales", "c2": "sales", "c3": "support", "c4": "job_application", "c5": "spam"}


def sample(sid):
    for pid, items in SAMPLES.items():
        for e in items:
            if e["id"] == sid:
                return pid, e
    raise KeyError(sid)


# --------------------------------------------------------------------------- rules

@pytest.mark.parametrize("sid,cat", EXPECTED.items())
def test_every_sample_is_classified_correctly(sid, cat):
    _, e = sample(sid)
    assert rules.classify(e["subject"], e["body"])["category"] == cat


def test_extract_phone_budget_timeline_and_services():
    pid, e = sample("ca1")
    f = rules.extract(e, get_profile(pid))
    assert f["phone"] == "98201 45678" and f["budget_inr"] == 20000 and f["timeline"] == "urgent"
    assert "Private limited company registration" in f["services"]


@pytest.mark.parametrize("text,amount", [("budget ₹20,000", 20000), ("around 1.5 lakh", 150000), ("Rs. 8000", 8000),
                                         ("upto 25k", 25000), ("no budget yet", None)])
def test_money_parsing(text, amount):
    assert rules._money(text) == amount


def test_hinglish_detected():
    _, e = sample("ca3")
    assert rules.detect_language(e["body"]) == "hinglish"


def test_score_explains_every_point_and_hot_lead_is_hot():
    pid, e = sample("ca1")
    p = get_profile(pid)
    sc = rules.score("sales", rules.extract(e, p), p, e)
    assert sc["priority"] == "hot" and sc["score"] >= 70
    assert sum(int(r.split()[0]) for r in sc["reasons"]) >= sc["score"]   # every point has a reason


def test_non_sales_is_not_scored():
    pid, e = sample("ca4")
    assert rules.score("support", {}, get_profile(pid), e)["priority"] == "n/a"


def test_check_reply_blocks_invented_prices_and_promises():
    pid, e = sample("ca2")
    p = get_profile(pid)
    bad = "Hi Sneha, ITR filing costs only ₹999 and we guarantee the maximum refund. Book a call with our partners."
    c = rules.check_reply(bad, p, e, kb_text(p), "sales")
    assert not c["ok"]
    assert any("999" in i for i in c["issues"]) and any("guarantee" in i for i in c["issues"])


def test_check_reply_allows_kb_prices_and_customer_numbers():
    pid, e = sample("ca1")
    p = get_profile(pid)
    ok = "Hi Rohan, company registration is ₹12,000 – ₹18,000 and fits your ₹20,000 budget. Shall we book a call with our partners?"
    assert rules.check_reply(ok, p, e, kb_text(p), "sales")["ok"]


def test_every_template_reply_passes_the_check():
    for pid, items in SAMPLES.items():
        p = get_profile(pid)
        for e in items:
            cat = EXPECTED[e["id"]]
            if cat == "spam":
                continue
            reply = rules.draft(cat, rules.extract(e, p), p, e)
            assert rules.check_reply(reply, p, e, kb_text(p), cat)["ok"], e["id"]


# --------------------------------------------------------------------------- graph paths

def test_spam_is_archived_without_review():
    pid, e = sample("ca5")
    r = graph.start(e, pid)
    assert r["paused_at"] is None and r["state"]["status"] == "spam"
    assert [t["node"] for t in r["state"]["trace"]] == ["ingest", "classify", "archive"]


def test_sales_lead_pauses_for_human_review():
    pid, e = sample("ca1")
    r = graph.start(e, pid)
    assert r["paused_at"] == "human_review" and r["state"]["status"] == "awaiting_review"
    assert r["state"]["check"]["ok"]


def test_approve_runs_three_actions_in_parallel_then_finalizes():
    pid, e = sample("ca1")
    paused = graph.start(e, pid)["state"]
    done = graph.resume(paused, "approve")
    st = done["state"]
    assert done["paused_at"] is None and st["status"] == "done"
    assert sorted(a["name"] for a in st["actions"]) == ["log_to_sheet", "notify_team", "send_reply"]
    assert all(a["mode"] == "simulated" for a in st["actions"])
    assert st["trace"][-1]["node"] == "finalize"
    assert st["final_reply"] == paused["draft"]


def test_approve_with_edits_sends_the_edited_text():
    pid, e = sample("ca1")
    paused = graph.start(e, pid)["state"]
    st = graph.resume(paused, "approve", edited_reply="Hi Rohan, calling you in 10 minutes. – Team Desai & Rao")["state"]
    assert st["final_reply"].startswith("Hi Rohan, calling you")
    send = next(a for a in st["actions"] if a["name"] == "send_reply")
    assert send["payload"]["text"] == st["final_reply"]


def test_whatsapp_lead_without_email_is_a_manual_send():
    pid, e = sample("ca3")
    st = graph.resume(graph.start(e, pid)["state"], "approve")["state"]
    assert next(a for a in st["actions"] if a["name"] == "send_reply")["mode"] == "manual"


def test_revise_redrafts_and_pauses_again():
    pid, e = sample("ca2")
    paused = graph.start(e, pid)["state"]
    r = graph.resume(paused, "revise", feedback="make it formal")
    assert r["paused_at"] == "human_review"
    assert r["state"]["draft"].startswith("Dear Sneha Iyer")


def test_reject_archives_without_actions():
    pid, e = sample("d4")
    st = graph.resume(graph.start(e, pid)["state"], "reject")["state"]
    assert st["status"] == "rejected" and not st.get("actions")


# --------------------------------------------------------------------------- LLM paths (stub model, no network)

class StubLLM:
    """Pretends to be ChatGroq: structured calls return fixed objects; plain calls return queued drafts."""

    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.prompts = []

    def with_structured_output(self, schema):
        outer = self

        class Runner:
            def invoke(self, prompt):
                outer.prompts.append(prompt)
                if schema is graph.Classification:
                    return schema(category="sales", confidence=0.9, language="english", reason="asks for ITR price")
                return schema(name="Sneha Iyer", services=["Income tax return (ITR) filing", "Made-up service"],
                              need="File ITR with freelance income", budget_inr=50000, timeline="not stated")

        return Runner()

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return AIMessage(content=self.drafts.pop(0))


def test_llm_path_self_corrects_an_invented_price(monkeypatch):
    stub = StubLLM([
        "Hi Sneha, ITR filing is just ₹999 this week! Book a call with our partners.",      # invents a price
        "Hi Sneha, ITR filing is ₹1,500 – ₹4,000 per return. Shall we set up a call with our partners? What time works?",
    ])
    monkeypatch.setattr(graph, "get_llm", lambda *a, **k: stub)
    pid, e = sample("ca2")
    r = graph.start(e, pid)
    st = r["state"]
    assert r["paused_at"] == "human_review" and st["drafts"] == 2 and st["check"]["ok"]
    assert "₹999" not in st["draft"]
    assert "failed these checks" in stub.prompts[-1]                         # issues were fed back to the model
    assert st["fields"]["services"] == ["Income tax return (ITR) filing"]     # unknown service dropped
    assert st["fields"]["budget_inr"] is None                                 # no digits in message → no invented budget
    assert {t["mode"] for t in st["trace"] if t["node"] in ("classify", "extract", "draft_reply")} == {"llm"}


def test_llm_failure_falls_back_to_rules(monkeypatch):
    class Broken:
        def with_structured_output(self, schema):
            raise RuntimeError("groq down")

        def invoke(self, prompt):
            raise RuntimeError("groq down")

    monkeypatch.setattr(graph, "get_llm", lambda *a, **k: Broken())
    pid, e = sample("ca1")
    st = graph.start(e, pid)["state"]
    assert st["classification"]["category"] == "sales" and st["check"]["ok"]
    assert all(t["mode"] == "rules" for t in st["trace"])


# --------------------------------------------------------------------------- API

def test_api_round_trip_and_tamper_protection():
    pid, e = sample("ca1")
    body = {k: e[k] for k in ("channel", "from_name", "from_email", "subject", "body")}
    r = client.post("/api/run", json={"enquiry": body, "profile_id": pid}).json()
    assert r["paused_at"] == "human_review" and r["token"]
    forged = seal({"state": {**r["state"], "draft": "Pay ₹1 now"}, "paused_at": "human_review"}).replace(".", ".x", 1)
    assert client.post("/api/resume", json={"token": forged, "decision": "approve"}).status_code == 400
    assert client.post("/api/resume", json={"token": r["token"], "decision": "revise"}).status_code == 422
    done = client.post("/api/resume", json={"token": r["token"], "decision": "approve"}).json()
    assert done["state"]["status"] == "done" and "token" not in done


def test_meta_and_health():
    m = client.get("/api/meta").json()
    assert set(m["profiles"]) == set(PROFILES) and "human_review" in m["graph"]
    h = client.get("/api/health").json()
    assert h["llm"] is False and h["integrations"] == {"sheets": False, "telegram": False, "email": False}
