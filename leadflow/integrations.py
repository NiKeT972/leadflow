"""Side effects run after a human approves a lead: log it to Google Sheets, alert the team on Telegram, email the reply.

Each one runs for real only when its environment variables are set. Otherwise it returns mode="simulated" with
exactly what it would have sent, so the public demo never emails a stranger or writes to someone's sheet.

  Google Sheets  GOOGLE_SHEETS_WEBHOOK_URL   Apps Script web app (see scripts/sheets_webhook.gs)
  Telegram       TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  Email          RESEND_API_KEY + FROM_EMAIL (Resend's HTTP API)
  WhatsApp       WHATSAPP_TOKEN + WHATSAPP_PHONE_ID (Meta WhatsApp Cloud API) for enquiries that came in on WhatsApp
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx

IST = timezone(timedelta(hours=5, minutes=30))
TIMEOUT = 10


def _now() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M")


def sheet_row(s: dict) -> dict:
    f, sc = s.get("fields", {}), s.get("lead_score", {})
    return {
        "received_at": _now(),
        "business": s.get("profile_name", ""),
        "channel": s.get("enquiry", {}).get("channel", ""),
        "name": f.get("name", ""),
        "email": f.get("email", ""),
        "phone": f.get("phone", ""),
        "category": s.get("classification", {}).get("category", ""),
        "services": ", ".join(f.get("services", [])),
        "budget_inr": f.get("budget_inr") or "",
        "timeline": f.get("timeline", ""),
        "score": sc.get("score", ""),
        "priority": sc.get("priority", ""),
        "status": "replied" if s.get("decision") == "approve" else s.get("decision", ""),
    }


def log_to_sheet(s: dict) -> dict:
    row = sheet_row(s)
    url = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")
    if not url:
        return {"mode": "simulated", "ok": True, "detail": "would append 1 row to the Leads sheet", "payload": row}
    try:
        # Apps Script answers with a 302 to the result page, so follow redirects.
        r = httpx.post(url, json=row, timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        return {"mode": "live", "ok": True, "detail": "row appended to Google Sheets", "payload": row}
    except Exception as e:  # never let a failed side effect lose the lead
        return {"mode": "live", "ok": False, "detail": f"Sheets error: {type(e).__name__}", "payload": row}


def alert_text(s: dict) -> str:
    f, sc = s.get("fields", {}), s.get("lead_score", {})
    cat = s.get("classification", {}).get("category", "")
    icon = {"hot": "🔥", "warm": "🟠", "cold": "🔵"}.get(sc.get("priority"), "📩")
    lines = [f"{icon} New {sc.get('priority', '')} {cat} lead – {s.get('profile_name', '')}".replace("  ", " "),
             f"{f.get('name', '')} · {f.get('phone') or f.get('email') or 'no contact'}"]
    if f.get("services"):
        lines.append("Needs: " + ", ".join(f["services"]))
    if f.get("budget_inr"):
        lines.append(f"Budget: ₹{f['budget_inr']:,}")
    lines.append(f"Score {sc.get('score', 0)}/100 · timeline: {f.get('timeline', '')}")
    lines.append("Reply sent ✅" if s.get("decision") == "approve" else "")
    return "\n".join(x for x in lines if x)


def notify_team(s: dict) -> dict:
    text = alert_text(s)
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return {"mode": "simulated", "ok": True, "detail": "would send this Telegram alert", "payload": {"text": text}}
    try:
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text},
                       timeout=TIMEOUT)
        r.raise_for_status()
        return {"mode": "live", "ok": True, "detail": "Telegram alert sent", "payload": {"text": text}}
    except Exception as e:
        return {"mode": "live", "ok": False, "detail": f"Telegram error: {type(e).__name__}", "payload": {"text": text}}


def send_whatsapp(s: dict) -> dict:
    """Reply on WhatsApp. Allowed as free text because the customer messaged first (WhatsApp's 24-hour window)."""
    to = s.get("enquiry", {}).get("reply_to", "")
    payload = {"to": to, "subject": "WhatsApp reply", "text": s.get("final_reply", "")}
    token, phone_id = os.getenv("WHATSAPP_TOKEN"), os.getenv("WHATSAPP_PHONE_ID")
    if not (token and phone_id):
        return {"mode": "simulated", "ok": True, "detail": f"would send this WhatsApp reply to +{to}", "payload": payload}
    try:
        r = httpx.post(f"https://graph.facebook.com/v21.0/{phone_id}/messages",
                       headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT,
                       json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": payload["text"]}})
        r.raise_for_status()
        return {"mode": "live", "ok": True, "detail": f"WhatsApp reply sent to +{to}", "payload": payload}
    except Exception as e:
        return {"mode": "live", "ok": False, "detail": f"WhatsApp error: {type(e).__name__}", "payload": payload}


def send_reply(s: dict) -> dict:
    if s.get("enquiry", {}).get("channel") == "whatsapp" and s.get("enquiry", {}).get("reply_to"):
        return send_whatsapp(s)
    to = s.get("fields", {}).get("email", "")
    subject = "Re: " + (s.get("enquiry", {}).get("subject") or "your enquiry")
    payload = {"to": to, "subject": subject, "text": s.get("final_reply", "")}
    if not to:
        ch = s.get("enquiry", {}).get("channel", "")
        return {"mode": "manual", "ok": True, "detail": f"no email address – copy the reply into {ch or 'the original channel'}",
                "payload": payload}
    key, sender = os.getenv("RESEND_API_KEY"), os.getenv("FROM_EMAIL")
    if not (key and sender):
        return {"mode": "simulated", "ok": True, "detail": f"would email the reply to {to}", "payload": payload}
    try:
        r = httpx.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {key}"},
                       json={"from": sender, **payload}, timeout=TIMEOUT)
        r.raise_for_status()
        return {"mode": "live", "ok": True, "detail": f"reply emailed to {to}", "payload": payload}
    except Exception as e:
        return {"mode": "live", "ok": False, "detail": f"Email error: {type(e).__name__}", "payload": payload}


def status() -> dict:
    return {
        "sheets": bool(os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")),
        "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
        "email": bool(os.getenv("RESEND_API_KEY") and os.getenv("FROM_EMAIL")),
        "whatsapp": bool(os.getenv("WHATSAPP_TOKEN") and os.getenv("WHATSAPP_PHONE_ID")),
    }


def review_alert(s: dict, lead_id: str = "") -> dict:
    """Telegram ping when a real enquiry arrives and is waiting for approval (intake), before any reply is sent."""
    sc, f = s.get("lead_score", {}), s.get("fields", {})
    text = (f"📥 New {sc.get('priority', '')} {s.get('classification', {}).get('category', '')} enquiry – "
            f"{s.get('profile_name', '')}\n{f.get('name', '')}: {f.get('need', '')}\nWaiting for your approval in LeadFlow.")
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return {"mode": "simulated", "ok": True}
    try:
        httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text},
                   timeout=TIMEOUT).raise_for_status()
        return {"mode": "live", "ok": True}
    except Exception as e:
        return {"mode": "live", "ok": False, "detail": type(e).__name__}
