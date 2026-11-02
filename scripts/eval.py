"""Measure LeadFlow on the hand-labelled evaluation set.

    python scripts/eval.py            # uses the LLM if GROQ_API_KEY is set, else the built-in rules
    python scripts/eval.py --rules    # force rules mode

Writes evals/report_<mode>.json; the dashboard's Evaluation panel shows every report it finds.
evals/cases.jsonl        50 enquiries (3 businesses, English + Hinglish, spam, support, injection attempts),
                          labelled by hand before the system was run on them
evals/reply_cases.jsonl  16 draft replies labelled "should pass" / "should be blocked" for the reply check
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load(name):
    return [json.loads(line) for line in (ROOT / "evals" / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def run(force_rules: bool = False) -> dict:
    if force_rules:
        os.environ["GROQ_API_KEY"] = ""
    for k in ("GOOGLE_SHEETS_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "RESEND_API_KEY", "WHATSAPP_TOKEN"):
        os.environ[k] = ""                     # never send anything during an eval
    from leadflow import graph, rules
    from leadflow.llm import model_name
    from leadflow.profiles import get_profile, kb_text
    from leadflow.retriever import builtin_docs, retrieve

    cases, rows = load("cases.jsonl"), []
    for c in cases:
        e = {"channel": c["channel"], "from_name": "", "from_email": "", "subject": c["subject"], "body": c["body"]}
        t0 = time.perf_counter()
        st = graph.start(e, get_profile(c["profile"]))["state"]
        ms = (time.perf_counter() - t0) * 1000
        f = st.get("fields") or {}
        rows.append({"id": c["id"], "label": c["label"], "ms": ms,
                     "category": st["classification"]["category"], "archived": st.get("status") == "spam",
                     "services": f.get("services", []), "budget": f.get("budget_inr"), "timeline": f.get("timeline"),
                     "phone": bool(f.get("phone")), "injection": bool((st.get("guard") or {}).get("injection")),
                     "check_ok": (st.get("check") or {}).get("ok"), "drafts": st.get("drafts", 0)})

    n = len(rows)
    L = lambda r: r["label"]
    cat_ok = sum(r["category"] == L(r)["category"] for r in rows)
    per_cat = {}
    for cat in sorted({L(r)["category"] for r in rows}):
        tp = sum(r["category"] == cat and L(r)["category"] == cat for r in rows)
        pred = sum(r["category"] == cat for r in rows)
        gold = sum(L(r)["category"] == cat for r in rows)
        per_cat[cat] = {"precision": pct(tp, pred), "recall": pct(tp, gold), "n": gold}
    confusion = Counter(f"{L(r)['category']} → {r['category']}" for r in rows if r["category"] != L(r)["category"])

    # Services: micro precision / recall over (case, service) pairs, only for cases that weren't archived.
    tp = fp = fn = 0
    for r in rows:
        if r["archived"]:
            fn += len(L(r)["services"]); continue
        p, g = set(r["services"]), set(L(r)["services"])
        tp += len(p & g); fp += len(p - g); fn += len(g - p)
    sp, sr = pct(tp, tp + fp), pct(tp, tp + fn)
    sf1 = round(2 * sp * sr / (sp + sr), 1) if sp and sr else 0

    live = [r for r in rows if not r["archived"]]
    spam_tp = sum(r["archived"] and L(r)["category"] == "spam" for r in rows)
    inj_tp = sum(r["injection"] and L(r)["injection"] for r in rows)
    sales = [r for r in live if L(r)["category"] == "sales"]

    reply_rows = []
    for rc in load("reply_cases.jsonl"):
        p = get_profile(rc["profile"])
        enq = {"subject": "", "body": rc["enquiry"]}
        src = retrieve(rc["enquiry"], builtin_docs(rc["profile"]))
        src_text = "\n".join(s["text"] for s in src)
        ok = rules.check_reply(rc["reply"], p, enq, kb_text(p), "sales", src_text)["ok"]
        reply_rows.append({"id": rc["id"], "expected": rc["should_pass"], "got": ok})
    blocked_bad = sum(not r["got"] for r in reply_rows if not r["expected"])
    passed_good = sum(r["got"] for r in reply_rows if r["expected"])
    n_bad = sum(not r["expected"] for r in reply_rows)

    report = {
        "mode": model_name(), "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "cases": n,
        "metrics": {
            "category_accuracy": pct(cat_ok, n),
            "spam_precision": pct(spam_tp, sum(r["archived"] for r in rows)),
            "spam_recall": pct(spam_tp, sum(L(r)["category"] == "spam" for r in rows)),
            "service_precision": sp, "service_recall": sr, "service_f1": sf1,
            "budget_accuracy": pct(sum(r["budget"] == L(r)["budget"] for r in live), len(live)),
            "timeline_accuracy": pct(sum(r["timeline"] == L(r)["timeline"] for r in live), len(live)),
            "phone_accuracy": pct(sum(r["phone"] == L(r)["phone"] for r in live), len(live)),
            "injection_recall": pct(inj_tp, sum(L(r)["injection"] for r in rows)),
            "injection_false_alarms": sum(r["injection"] and not L(r)["injection"] for r in rows),
            "sales_drafts_passing_check": pct(sum(bool(r["check_ok"]) for r in sales), len(sales)),
            "reply_check_blocks_bad": pct(blocked_bad, n_bad),
            "reply_check_passes_good": pct(passed_good, len(reply_rows) - n_bad),
            "avg_ms_per_enquiry": round(sum(r["ms"] for r in rows) / n),
        },
        "per_category": per_cat,
        "confusions": dict(confusion.most_common()),
        "misses": [{"id": r["id"], "expected": L(r)["category"], "got": r["category"]} for r in rows if r["category"] != L(r)["category"]],
        "service_misses": [{"id": r["id"], "expected": L(r)["services"], "got": r["services"]} for r in live
                           if set(r["services"]) != set(L(r)["services"])],
        "reply_check_misses": [r for r in reply_rows if r["expected"] != r["got"]],
    }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", action="store_true", help="force rule-based mode")
    args = ap.parse_args()
    rep = run(args.rules)
    tag = "rules" if rep["mode"] == "built-in rules" else "llm"
    (ROOT / "evals" / f"report_{tag}.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    print(f"LeadFlow eval · {rep['mode']} · {rep['cases']} cases")
    for k, v in rep["metrics"].items():
        print(f"  {k:30} {v}")
    if rep["misses"]:
        print("  category misses:", ", ".join(f"{m['id']} {m['expected']}→{m['got']}" for m in rep["misses"]))
    print(f"wrote evals/report_{tag}.json")


if __name__ == "__main__":
    main()
