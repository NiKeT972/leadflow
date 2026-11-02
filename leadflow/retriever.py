"""RAG over a business's own documents: split into sections, then rank them for an enquiry with BM25.

BM25 is a keyword-ranking formula (what search engines used before embeddings). It needs no model download
and no vector database, which keeps the serverless function small and fast, and its scores are easy to explain:
a section ranks high when it contains the enquiry's rarer words several times.
Swapping in embeddings later only means replacing `Retriever.search`.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

DOCS_DIR = Path(__file__).parent / "docs"
STOP = set("""a an and are as at be but by can could do does for from had has have hello hi how i i'm if in is it
its me my no not of on or our please so that the their them then there these this to us was we what when where which
who will with would you your hai ka ki ke ko me se bhi aur kya""".split())

# Hinglish / everyday words → the words our documents use, so "kaagaz" or "papers" still finds "documents".
SYNONYMS = {"papers": "documents", "kagaz": "documents", "kaagaz": "documents", "docs": "documents",
            "charges": "fee", "fees": "fee", "cost": "fee", "price": "fee", "kitna": "fee",
            "timing": "timings", "time": "timings", "recording": "recorded", "recordings": "recorded",
            "notes": "notes", "instalment": "instalments", "installment": "instalments", "emi": "emi",
            "refund": "refund", "kids": "children", "child": "children", "daughter": "children", "son": "children"}


def tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9₹]+", text.lower()):
        if w in STOP or len(w) < 2:
            continue
        w = SYNONYMS.get(w, w)
        out.append(_singular(w))
    return out


def _singular(w: str) -> str:
    """Crude plural folding so 'batches' finds 'batch' and 'returns' finds 'return'."""
    if len(w) > 4 and w.endswith(("ches", "shes", "sses", "xes")):
        return w[:-2]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def split_sections(name: str, text: str, max_chars: int = 900) -> list[dict]:
    """One chunk per markdown section (## heading); long sections are split by paragraph."""
    title, chunks, cur = name, [], []
    doc_title = name
    for line in text.splitlines():
        if line.startswith("# "):
            doc_title = line[2:].strip()
            continue
        if line.startswith("## "):
            if cur:
                chunks.append((title, "\n".join(cur).strip()))
            title, cur = line[3:].strip(), []
            continue
        cur.append(line)
    if cur:
        chunks.append((title, "\n".join(cur).strip()))
    out = []
    for t, body in chunks:
        if not body:
            continue
        parts = [body] if len(body) <= max_chars else [p for p in re.split(r"\n\s*\n", body) if p.strip()]
        for p in parts:
            out.append({"doc": doc_title, "section": t, "text": p.strip()[:max_chars]})
    return out


class Retriever:
    def __init__(self, sections: list[dict], k1: float = 1.4, b: float = 0.75):
        self.sections = sections
        self.toks = [tokens(s["section"] + " " + s["text"]) for s in sections]
        self.avg = sum(map(len, self.toks)) / max(len(self.toks), 1)
        df = Counter(w for t in self.toks for w in set(t))
        n = len(self.toks)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, k: int = 3, min_score: float | None = None) -> list[dict]:
        q = set(tokens(query))
        if min_score is None:
            # IDF is tiny when there are only a few sections (every word is "common"), so relax the cut-off.
            min_score = 1.5 if len(self.sections) >= 5 else 0.25
        scored = []
        for sec, t in zip(self.sections, self.toks):
            tf = Counter(t)
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(t) / self.avg))
            if s >= min_score:
                scored.append({**sec, "score": round(s, 2)})
        scored.sort(key=lambda x: -x["score"])
        return [{**x, "id": i + 1} for i, x in enumerate(scored[:k])]


def builtin_docs(profile_id: str) -> list[dict]:
    folder = DOCS_DIR / profile_id
    if not folder.is_dir():
        return []
    return [{"name": p.stem, "text": p.read_text(encoding="utf-8")} for p in sorted(folder.glob("*.md"))]


def retrieve(query: str, docs: list[dict], k: int = 3) -> list[dict]:
    sections = [s for d in docs for s in split_sections(d["name"], d["text"])]
    return Retriever(sections).search(query, k) if sections else []


def best_sentence(source: dict, query: str) -> str:
    """The sentence of a retrieved section that shares the most words with the enquiry (for the rules-mode reply)."""
    q = set(tokens(query))
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", source["text"]) if s.strip()]
    if not sents:
        return ""
    best = max(sents, key=lambda s: len(q & set(tokens(s))))
    return best if len(q & set(tokens(best))) >= 2 else ""
