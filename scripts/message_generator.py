#!/usr/bin/env python
"""
Wraps your existing resume_outreach_local logic
into a function so we never hit argparse inside Streamlit.
"""
from __future__ import annotations
import os, sys, math, collections, textwrap
from pathlib import Path
import PyPDF2, docx
from typing import List, Dict, Tuple
from dotenv import load_dotenv

load_dotenv()


def chars_to_tokens(n: int, ratio: float = 3.3) -> int:
    """≈ 1 token per 3.3 chars → add 4-token cushion."""
    return max(10, math.ceil(n / ratio) + 4)


def read_file(p: Path) -> str:
    suf = p.suffix.lower()
    if suf == ".pdf":
        with open(p, "rb") as f:
            return "\n".join(pg.extract_text() or "" for pg in PyPDF2.PdfReader(f).pages)
    if suf in {".docx", ".doc"}:
        return "\n".join(par.text for par in docx.Document(p).paragraphs)
    return p.read_text(errors="ignore")


def chunk(txt: str, w: int = 250):
    words = txt.split()
    for i in range(0, len(words), w):
        yield " ".join(words[i : i + w])


def tfidf_vecs(docs: List[str]) -> List[Dict[str, float]]:
    toks = [d.lower().split() for d in docs]
    df   = collections.Counter(t for d in toks for t in set(d))
    N    = len(toks)
    vecs = []
    for tok in toks:
        tf = collections.Counter(tok)
        vecs.append({w: (c/len(tok)) * (math.log((N+1)/(df[w]+1))+1) for w, c in tf.items()})
    return vecs


def cos(a: Dict[str, float], b: Dict[str, float]) -> float:
    num = sum(a[w] * b[w] for w in set(a) & set(b))
    den = math.sqrt(sum(x * x for x in a.values())) * math.sqrt(sum(y * y for y in b.values()))
    return num / den if den else 0.0


def guess_name(txt: str) -> str | None:
    for line in txt.splitlines():
        if line and 1 < len(line.split()) <= 4:
            if sum(w[0].isupper() for w in line.split()) >= len(line.split()) - 1:
                return line.strip()
    return None


def guess_current(txt: str) -> str | None:
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    for key in ("experience", "education"):
        for i, l in enumerate(lines):
            if key in l.lower() and i + 1 < len(lines):
                return lines[i + 1]
    return lines[1] if len(lines) > 1 else None


def generate_outreach(
    resume_txt: str,
    jd_txt: str,
    recipient: str = "Hiring Manager",
    company: str = "",
    top_k: int = 10,
    max_chars: int = 0,
    extra: str = "",
) -> Tuple[str, str]:
    """
    Returns (subject, message), exactly as your CLI did:
      1. snippet‐selection (embeddings → TFIDF)
      2. build prompt
      3. OpenRouter → OpenAI → local template
      4. truncate
      5. subject = guess_name or fallback
    """
    unlimited = max_chars <= 0

    # 1️⃣ Snippet selection
    name    = guess_name(resume_txt) or "I"
    pitch   = guess_current(resume_txt) or "a software engineer"
    chunks_ = list(chunk(resume_txt))

    scores = []
    OPENAI_KEY = os.getenv("OPENAI_API_KEY")
    try:
        if OPENAI_KEY:
            import openai

            openai.api_key = OPENAI_KEY
            emb     = "text-embedding-3-small"
            res_emb = openai.Embedding.create(model=emb, input=chunks_).data
            jd_emb  = openai.Embedding.create(model=emb, input=[jd_txt]).data[0].embedding

            def cosL(a, b):
                num = sum(x * y for x, y in zip(a, b))
                den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
                return num / den if den else 0

            scores = [cosL(d.embedding, jd_emb) for d in res_emb]
        else:
            raise RuntimeError("no key")
    except Exception:
        vecs  = tfidf_vecs(chunks_ + [jd_txt])
        jdvec = vecs[-1]
        scores = [cos(v, jdvec) for v in vecs[:-1]]

    top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    snips   = [chunks_[i] for i in top_idx]

    # 2️⃣ Build prompt helper
    def build_prompt() -> str:
        first = (
            "Write a warm, professional outreach message."
            if unlimited
            else f"ABSOLUTE LIMIT: {max_chars} characters (including spaces). Write a warm, professional outreach message within this limit."
        )
        return "\n".join(
            [
                first,
                f"Sender: {name}, currently {pitch}.",
                f"Recipient: {recipient} at {company or 'the company'}.",
                "",
                "Job description:",
                jd_txt[:1800],
                "",
                "Relevant résumé snippets:",
                "\n\n".join(snips),
            ]
        )

    # 3️⃣ Message generation
    msg = None
    OR_KEY = os.getenv("OPENROUTER_API_KEY")
    token_limit = None if unlimited else chars_to_tokens(max_chars)

    # — OpenRouter
    if OR_KEY:
        try:
            from openai import OpenAI

            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OR_KEY)
            chat   = client.chat.completions.create(
                model="mistralai/mistral-7b-instruct",
                messages=[{"role": "user", "content": build_prompt()}],
                **({"max_tokens": token_limit} if token_limit else {}),
                temperature=0.7,
                extra_headers={"X-Title": "resume-outreach"},
            )
            msg = chat.choices[0].message.content.strip()
        except Exception:
            msg = None

    # — OpenAI Chat
    if msg is None and OPENAI_KEY:
        try:
            import openai

            chat = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": build_prompt()}],
                **({"max_tokens": token_limit} if token_limit else {}),
                temperature=0.7,
            )
            msg = chat.choices[0].message.content.strip()
        except Exception:
            msg = None

    # — Local template fallback
    if msg is None:
        intro = snips[0][:120] if snips else "my background"
        fit   = snips[1][:120] if len(snips) > 1 else "my relevant experience"
        msg = textwrap.dedent(
            f"""
            Hi {recipient},

            I’m {name}, currently {pitch}. I’m excited about the opportunity at {company or 'your company'}. With {intro} and {fit}, I believe I can add immediate value to your team. {extra + ' ' if extra else ""}
            I’d love to connect and discuss further.

            Thanks for your time!
            """
        ).strip()

    # 4️⃣ Truncate
    if not unlimited and len(msg) > max_chars:
        msg = msg[: max_chars - 3].rsplit(" ", 1)[0] + "..."

    # 5️⃣ Subject
    subject = guess_name(resume_txt) or (f"Opportunity at {company}" if company else "Let's Connect")
    return subject, msg


if __name__ == "__main__":
    # preserve your CLI exactly as before
    cli = argparse.ArgumentParser(prog="resume_outreach_local")
    cli.add_argument("--resume",   required=True)
    cli.add_argument("--job",      required=True)
    cli.add_argument("--recipient", default="Hiring Manager")
    cli.add_argument("--company",   default="")
    cli.add_argument("-k", "--top_k",     type=int, default=10)
    cli.add_argument("-m", "--max_chars", type=int, default=0, help="0 = unlimited length")
    cli.add_argument("--extra")
    args = cli.parse_args()
    resume_txt = read_file(Path(args.resume))
    jd_txt     = read_file(Path(args.job))
    subj, text = generate_outreach(
        resume_txt=resume_txt,
        jd_txt=jd_txt,
        recipient=args.recipient,
        company=args.company,
        top_k=args.top_k,
        max_chars=args.max_chars,
        extra=args.extra or "",
    )
    print(text)
    Path("generated_message.txt").write_text(text, encoding="utf-8")
    print(f"Saved to {Path('generated_message.txt').resolve()}")
