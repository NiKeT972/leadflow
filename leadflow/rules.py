"""Deterministic (no-LLM) logic. Used when no GROQ_API_KEY is set, when an LLM call fails, and always for
lead scoring and the reply check, which are kept rule-based so they're explainable and testable."""
from __future__ import annotations

import re

CATEGORIES = ["sales", "support", "partnership", "job_application", "spam"]

# --------------------------------------------------------------------------- classify

SPAM_PATTERNS = [
    r"guarantee[d]? (page|returns|ranking)", r"backlinks?", r"lottery", r"lucky draw", r"you have won", r"\bwon\b.*₹",
    r"click here", r"crypto", r"\d{2,3}% (guaranteed|returns|discount)", r"processing fee", r"bank details",
    r"limited (time|seats)", r"!!!", r"seo services", r"telegram vip",
]
SUPPORT_WORDS = ["existing client", "existing patient", "current student", "my account", "my return", "my file",
                 "mismatch", "recording", "missed", "invoice", "refund status", "follow up", "follow-up", "re:",
                 "already", "last month", "my appointment", "reschedule", "complaint", "not received"]
PARTNER_WORDS = ["partner", "partnership", "distributor", "collaborat", "vendor", "supplies", "tie-up", "tie up",
                 "reseller", "affiliate"]
JOB_WORDS = ["articleship", "internship", "job", "opening", "vacancy", "resume", "cv", "apply for", "faculty position",
             "position at", "hiring", "career"]
SALES_WORDS = ["fees", "fee", "charges", "cost", "price", "kitna", "quote", "budget", "need", "want", "chahiye",
               "book", "join", "start", "register", "karwana", "help", "interested", "options"]


def _hits(text: str, words: list[str]) -> int:
    return sum(1 for w in words if w in text)


def classify(subject: str, body: str) -> dict:
    t = f"{subject}\n{body}".lower()
    spam = sum(1 for p in SPAM_PATTERNS if re.search(p, t))
    scores = {
        "spam": spam * 2,
        "job_application": _hits(t, JOB_WORDS) * 1.5,
        "partnership": _hits(t, PARTNER_WORDS) * 1.5,
        "support": _hits(t, SUPPORT_WORDS) * 1.5,
        "sales": _hits(t, SALES_WORDS),
    }
    cat = max(scores, key=scores.get)
    if scores[cat] == 0:
        cat = "sales"                                  # an unclear enquiry is treated as a possible customer
    if spam >= 2:
        cat = "spam"
    total = sum(scores.values()) or 1
    conf = round(min(0.95, 0.5 + scores[cat] / total / 2), 2)
    return {"category": cat, "confidence": conf, "language": detect_language(body),
            "reason": f"keyword signals: " + ", ".join(f"{k} {v:g}" for k, v in scores.items() if v)}


HINGLISH = ["hai", "karna", "karwana", "kitna", "chahiye", "batao", "mera", "mujhe", "ke liye", "bhai", "kya", "jaldi",
            "daant", "dard", "kal", "nahi", "aur"]


def detect_language(text: str) -> str:
    words = re.findall(r"[a-z]+", text.lower())
    hits = sum(1 for w in words if w in HINGLISH) + text.lower().count("ke liye")
    return "hinglish" if hits >= 2 else "english"


# --------------------------------------------------------------------------- guard (prompt injection)

# Messages that try to give the AI instructions instead of asking the business something.
INJECTION_PATTERNS = [
    (r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instruction|rule|prompt|guideline|previous|above)", "tries to override the AI's instructions"),
    (r"\b(system prompt|developer message|your instructions|hidden prompt)\b", "asks about the AI's hidden instructions"),
    (r"\byou are (now|no longer)\b|\bact as\b|\bpretend (to be|you)\b|\bjailbreak\b", "tries to change the AI's role"),
    (r"\b(reply|respond|say|write|confirm)\b.{0,30}\b(free|100% off|\d{2,3}% (off|discount))", "tells the AI to promise a discount"),
    (r"\b(reveal|show|print|leak)\b.{0,30}\b(api key|password|other customers|database|data of)", "asks for private data"),
    (r"<\s*/?\s*(system|assistant|instructions?)\s*>|\[\s*(system|inst)\s*\]", "contains fake system tags"),
]


def detect_injection(text: str) -> list[str]:
    t = text.lower()
    return [why for pat, why in INJECTION_PATTERNS if re.search(pat, t)]


# --------------------------------------------------------------------------- extract

PHONE = re.compile(r"(?:\+?91[\s-]?)?\b([6-9]\d{4})[\s-]?(\d{5})\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
MONEY = re.compile(r"(?:₹|rs\.?|inr)\s?([\d,]+(?:\.\d+)?)\s?(k|l|lakh|lakhs|lac)?|([\d,]+(?:\.\d+)?)\s?(k|lakh|lakhs|lac)\b",
                   re.I)
URGENT = ["urgent", "asap", "today", "this week", "immediately", "jaldi", "right away", "by the 1", "by the 2", "by the 3",
          "tonight", "tomorrow", "kal"]
SOON = ["next week", "this month", "before", "soon", "summer", "next month"]


def _money(text: str) -> int | None:
    for m in MONEY.finditer(text):
        num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        unit = (unit or "").lower()
        if unit == "k":
            v *= 1_000
        elif unit in ("l", "lakh", "lakhs", "lac"):
            v *= 100_000
        if v >= 100:                                   # ignore "₹5" style noise
            return int(v)
    return None


def _has(keyword: str, text: str) -> bool:
    """Keyword match that must start at a word boundary, so 'come' doesn't match 'income' (prefixes like
    'incorporat' still match 'incorporation')."""
    return re.search(r"(?<![a-z0-9])" + re.escape(keyword), text) is not None


def match_services(text: str, profile: dict) -> list[dict]:
    t = text.lower()
    found = []
    for s in profile["services"]:
        hits = [k for k in s["keywords"] if _has(k, t)]
        if hits:
            found.append({**s, "hits": hits})
    return sorted(found, key=lambda s: -len(s["hits"]))


def match_faq(text: str, profile: dict) -> list[dict]:
    t = text.lower()
    return [f for f in profile["faq"] if any(_has(k, t) for k in f["keywords"])]


def timeline(text: str) -> str:
    t = text.lower()
    if any(w in t for w in URGENT):
        return "urgent"
    if any(w in t for w in SOON):
        return "soon"
    return "not stated"


def extract(enquiry: dict, profile: dict) -> dict:
    body = enquiry.get("body", "")
    text = f"{enquiry.get('subject', '')}\n{body}"
    phone = PHONE.search(body)
    emails = [e for e in EMAIL.findall(body)]
    services = match_services(text, profile)
    name = enquiry.get("from_name", "").strip()
    m = re.search(r"(?:my name is|i am|i'm|this is)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", body)
    if m and m.group(1).split()[0].lower() not in {"a", "an", "the", "starting", "looking", "interested", "salaried"}:
        name = m.group(1)
    return {
        "name": name or "there",
        "email": enquiry.get("from_email") or (emails[0] if emails else ""),
        "phone": f"{phone.group(1)} {phone.group(2)}" if phone else "",
        "services": [s["name"] for s in services],
        "need": _need_summary(body),
        "budget_inr": _money(body),
        "timeline": timeline(text),
    }


def _need_summary(body: str) -> str:
    """First sentence that isn't a greeting, cut to 160 characters."""
    parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+|\n+", body) if p.strip()]
    for p in parts:
        if not re.fullmatch(r"(hi|hello|hey|dear [\w/ ]+|respected [\w/ ]+)[,!.]?", p.lower()):
            p = re.sub(r"^(hi|hello|hey)[,!]?\s+", "", p, flags=re.I)
            return p if len(p) <= 160 else p[:157].rsplit(" ", 1)[0] + "…"
    return body[:160]


# --------------------------------------------------------------------------- score (always rules: explainable)

def score(category: str, fields: dict, profile: dict, enquiry: dict) -> dict:
    """0–100 lead score with the reason for every point, so the owner can see why a lead is 'hot'."""
    if category != "sales":
        return {"score": 0, "priority": "n/a", "est_value": 0, "reasons": [f"{category.replace('_', ' ')} – not a sales lead"]}
    pts, why = 20, ["+20 sales enquiry"]
    matched = sorted((s for s in profile["services"] if s["name"] in fields.get("services", [])), key=lambda s: -s["value"])
    value = max([s["value"] for s in matched], default=0)
    if matched:
        pts += 20; why.append(f"+20 asks for a service we offer ({matched[0]['name']})")
    if len(matched) > 1:
        pts += 10; why.append(f"+10 needs {len(matched)} services")
    if fields.get("timeline") == "urgent":
        pts += 20; why.append("+20 wants it urgently")
    elif fields.get("timeline") == "soon":
        pts += 10; why.append("+10 has a near-term timeline")
    budget = fields.get("budget_inr")
    if budget:
        pts += 10; why.append(f"+10 shared a budget (₹{budget:,})")
        if budget >= profile["min_deal"]:
            pts += 5; why.append("+5 budget covers our minimum")
        value = max(value, budget)
    if fields.get("phone"):
        pts += 10; why.append("+10 left a phone number")
    if any(f["q"] == "emergency" for f in match_faq(enquiry.get("body", ""), profile)):
        pts += 15; why.append("+15 possible emergency – respond first")
    if len(enquiry.get("body", "")) > 200:
        pts += 5; why.append("+5 detailed message")
    pts = min(pts, 100)
    priority = "hot" if pts >= 70 else "warm" if pts >= 45 else "cold"
    return {"score": pts, "priority": priority, "est_value": value, "reasons": why}


# --------------------------------------------------------------------------- draft (template fallback)

def draft(category: str, fields: dict, profile: dict, enquiry: dict, tone: str = "friendly",
          sources: list[dict] | None = None) -> str:
    first = fields.get("name", "there").split()[0] if fields.get("name") else "there"
    hi = f"Dear {fields.get('name') or 'Sir/Madam'}," if tone == "formal" else f"Hi {first},"
    text = f"{enquiry.get('subject', '')}\n{enquiry.get('body', '')}"
    sign = f"Regards,\n{profile['signature']}"
    services = [s for s in profile["services"] if s["name"] in fields.get("services", [])]
    faqs = match_faq(text, profile)
    # RAG in rules mode: quote the most relevant sentence of the best document section, with its citation.
    from .retriever import best_sentence
    doc_lines = []
    top = (sources or [{}])[0].get("score", 0)
    for src in [x for x in (sources or [])[:2] if x["score"] >= 0.6 * top]:   # only sections close to the best one
        sent = best_sentence(src, text)
        if sent and sent not in " ".join(f["a"] for f in faqs):
            doc_lines.append(f"{sent} [{src['id']}]")

    if category == "support":
        lines = [hi, "", f"Thanks for reaching out. We've logged your request and the team will get back to you within one "
                         f"working day ({profile['hours']}).", ""]
        # Support: the customer has a specific problem, so quote the documents only (the FAQ is for new customers).
        lines += doc_lines[:1] + ([""] if doc_lines else [])
        return "\n".join(lines + [sign]).replace("\n\n\n", "\n\n")
    if category == "partnership":
        return "\n".join([hi, "", f"Thank you for your proposal. We've shared it with the person who handles purchasing "
                                  f"at {profile['name']}, and they'll reply if it's a fit.", "", sign])
    if category == "job_application":
        return "\n".join([hi, "", f"Thank you for your interest in working with {profile['name']}. We've passed your "
                                  "application to the hiring team, who will contact you if there's a suitable opening.", "", sign])

    lines = [hi, "", "Thanks for getting in touch with " + profile["name"] + "."]
    if services:
        lines.append("")
        lines.append("Here's what this usually costs:")
        lines += [f"• {s['name']}: {s['price']}" for s in services[:3]]
        lines.append("The final quote depends on the details of your case.")
    else:
        lines.append("Could you share a little more about what you need, so we can point you to the right service?")
    if faqs or doc_lines:
        lines.append("")
        lines += [f["a"] for f in faqs] + doc_lines
    if profile.get("guardrail"):
        lines += ["", "We'll confirm what's right for you after a proper consultation."]
    lines += ["", f"The easiest next step is {profile['next_step']}."]
    lines.append("What time works for you?" if fields.get("phone") else "Could you share a phone number and a good time to reach you?")
    lines += ["", sign]
    return "\n".join(lines)


# --------------------------------------------------------------------------- check reply (guardrail, always rules)

BANNED = ["guarantee", "guaranteed", "100%", "lowest price", "cheapest", "definitely cure", "no risk", "promise",
          "diagnos"]
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _nums(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in NUM.findall(text)}


# An offer is only allowed if the same phrase is in the business's facts: "free demo class" is fine for the coaching
# institute, but "ITR filing is free for you" isn't, even though the CA firm's facts contain "free 15-minute call".
OFFER_PHRASES = re.compile(r"\d+\s*%\s*(?:off|discount)|discount\w*(?:\s+\w+)?|free\s+[\w-]+|waive\w*\s+\w+|cashback|complimentary\s+\w+")
CITATION = re.compile(r"\[\d+\]")


def check_reply(reply: str, profile: dict, enquiry: dict, kb: str, category: str, sources_text: str = "") -> dict:
    """The reply may only use numbers that appear in the business's knowledge base, the retrieved documents or the
    customer's own message (so no invented prices, discounts or dates), may only mention offers the business
    actually has, must not over-promise, and must not be empty or huge."""
    issues = []
    facts = kb + "\n" + sources_text
    allowed = _nums(facts) | _nums(enquiry.get("body", "")) | _nums(enquiry.get("subject", ""))
    new_nums = sorted(_nums(CITATION.sub("", reply)) - allowed)     # [1]-style citations aren't claims
    if new_nums:
        issues.append(f"uses numbers not in the knowledge base or the enquiry: {', '.join(new_nums)}")
    low = reply.lower()
    for b in BANNED:
        if b in low and b not in enquiry.get("body", "").lower():
            issues.append(f"over-promises ('{b}')")
    for phrase in OFFER_PHRASES.findall(low):   # a customer asking for "90% off" doesn't make it our offer
        if phrase not in facts.lower():
            issues.append(f"offers something not in the knowledge base ('{phrase}')")
    if len(reply.strip()) < 40:
        issues.append("reply is too short")
    if len(reply) > 1600:
        issues.append("reply is too long for a first response")
    if category == "sales" and profile["next_step"].split()[-1].lower() not in low and "call" not in low:
        issues.append("doesn't offer a next step")
    return {"ok": not issues, "issues": issues}


def strip_issues(reply: str, issues_nums: list[str]) -> str:
    """Rule-based repair: drop sentences that contain an unsupported number or over-promise."""
    out = []
    for line in reply.split("\n"):
        bad_num = any(n in _nums(line) for n in issues_nums)
        bad_word = any(b in line.lower() for b in BANNED)
        if not (bad_num or bad_word):
            out.append(line)
    return "\n".join(out)
