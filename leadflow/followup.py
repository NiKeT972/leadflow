"""Follow-ups for leads that went quiet after we replied. The draft goes through the same reply check and still
needs a human to send it."""
from __future__ import annotations

from . import rules
from .llm import get_llm, llm_failed


def draft_followup(state: dict, days: int) -> dict:
    p, f, e = state["profile"], state.get("fields", {}), state["enquiry"]
    first = (f.get("name") or "there").split()[0]
    services = ", ".join(f.get("services") or []) or "your enquiry"
    text, mode = "", "rules"
    llm = get_llm(0.4)
    if llm:
        try:
            text = llm.invoke(
                f"Write a short, polite follow-up from {p['name']} to {f.get('name') or 'a customer'} who asked about "
                f"{services} {days} days ago and hasn't replied to our answer.\n"
                f"Our earlier reply:\n{state.get('final_reply', '')}\n\nKnowledge base (the only facts you may use):\n"
                f"{state.get('kb', '')}\n\nUnder 70 words, no pressure, no new prices or discounts, offer {p['next_step']}, "
                f"reply in the customer's language ({state.get('classification', {}).get('language', 'english')}). "
                f"Sign off as:\n{p['signature']}").content.strip()
            mode = "llm"
        except Exception as err:
            llm_failed("followup", err)
    if not text:
        text = (f"Hi {first},\n\nJust following up on your message about {services}. "
                f"If you still need help, we'd be happy to set up {p['next_step']}. "
                "Just reply with a convenient time.\n\n"
                f"Regards,\n{p['signature']}")
    check = rules.check_reply(text, p, e, state.get("kb", ""), "sales",
                              "\n".join(x["text"] for x in state.get("sources") or []))
    return {"draft": text, "check": check, "mode": mode}
