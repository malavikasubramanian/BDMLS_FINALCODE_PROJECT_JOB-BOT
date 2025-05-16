#!/usr/bin/env python
"""
A standalone local RAG + LLM outreach generator with no CLI,
using sshleifer/tiny-gpt2 (~3 M params) and MiniLM for embeddings.
Better chunking & filtering so you don't re-mail yourself!

1. Chunk résumé into 100-word pieces
2. Filter out contact-info chunks
3. Embed résumé & JD locally via SentenceTransformer
4. Retrieve top-k most similar snippets
5. Clean those snippets (remove emails, URLs, phones)
6. Build & truncate prompt to fit context window
7. Generate outreach via tiny-gpt2
8. Fallback to template if generation empty
9. Print subject + message
"""

from pathlib import Path
from typing import List, Tuple
import re
import textwrap
import torch
import PyPDF2
import docx
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForCausalLM

# ─────── Configuration ───────
EMBEDDING_MODEL    = "all-MiniLM-L6-v2"    # ~22 M params
LLM_MODEL          = "sshleifer/tiny-gpt2" # ~2.8 M params
DEVICE             = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CHUNK_SIZE_WORDS   = 100
DEFAULT_TOP_K      = 10
DEFAULT_MAX_TOKENS = 64

# ─────── Load models ───────
_embedder   = SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)
_tokenizer  = AutoTokenizer.from_pretrained(LLM_MODEL)
_llm        = AutoModelForCausalLM.from_pretrained(LLM_MODEL).to(DEVICE)
_llm.eval()
CONTEXT_WINDOW = _tokenizer.model_max_length  # e.g. 1024

# ─────── Helpers ───────
def read_file(p: Path) -> str:
    suf = p.suffix.lower()
    if suf == ".pdf":
        with p.open("rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suf in {".docx", ".doc"}:
        return "\n".join(par.text for par in docx.Document(p).paragraphs)
    return p.read_text(errors="ignore")

def chunk(txt: str, w: int = CHUNK_SIZE_WORDS) -> List[str]:
    words = txt.split()
    return [" ".join(words[i : i + w]) for i in range(0, len(words), w)]

_CONTACT_REGEX = re.compile(
    r"(\S+@\S+)|(https?://\S+)|(\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b)"
)

def is_contact_chunk(chunk: str) -> bool:
    return bool(_CONTACT_REGEX.search(chunk))

def clean_snippet(snip: str) -> str:
    # remove any emails, urls, phones:
    return _CONTACT_REGEX.sub("", snip).strip()

def guess_name(txt: str) -> str:
    for line in txt.splitlines():
        parts = line.split()
        if 1 < len(parts) <= 4 and sum(w[0].isupper() for w in parts) >= len(parts)-1:
            return line.strip()
    return "Let's Connect"

# ─────── Core RAG + Generation ───────
def generate_outreach(
    resume_txt: str,
    jd_txt: str,
    recipient: str = "Hiring Manager",
    company:   str = "",
    top_k:     int = DEFAULT_TOP_K,
    max_new_tokens: int = DEFAULT_MAX_TOKENS,
    extra:     str = "",
) -> Tuple[str, str]:
    # 1) Chunk résumé and filter out contact-info chunks
    all_chunks = [c for c in chunk(resume_txt) if not is_contact_chunk(c)]
    if not all_chunks:
        return "Let's Connect", ""
    # 2) Embed chunks + JD
    chunk_embs = _embedder.encode(all_chunks, convert_to_tensor=True)
    jd_emb     = _embedder.encode([jd_txt], convert_to_tensor=True)[0]

    # 3) Retrieve top-k
    sims     = torch.nn.functional.cosine_similarity(chunk_embs, jd_emb.unsqueeze(0))
    topk     = torch.topk(sims, k=min(top_k, len(all_chunks)))
    snippets = [clean_snippet(all_chunks[i]) for i in topk.indices.tolist()]

    # 4) Build prompt
    prompt = textwrap.dedent(f"""
        You are a recruiting assistant. Write a concise, friendly outreach message.

        Recipient: {recipient}
        Company: {company or 'the company'}

        Job description (excerpt):
        {jd_txt[:500]}

        Top résumé snippets:
        {'; '.join(snippets)}

        Additional note: {extra}

        Message:
    """).strip()

    # 5) Truncate prompt to fit
    max_prompt_tokens = CONTEXT_WINDOW - max_new_tokens
    inputs = _tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=max_prompt_tokens,
    ).to(DEVICE)

    # 6) Generate
    outputs = _llm.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        top_p=0.9,
        temperature=0.7,
        pad_token_id=_tokenizer.eos_token_id,
    )
    full = _tokenizer.decode(outputs[0], skip_special_tokens=True)
    message = full[len(prompt) :].strip()

    # 7) Fallback template
    if not message:
        first_snip = snippets[0] if snippets else "my background"
        second_snip = snippets[1] if len(snippets)>1 else ""
        template = textwrap.dedent(f"""
            Hi {recipient},

            I’m {guess_name(resume_txt)}, currently a software engineer.  
            I’m excited about the opportunity at {company or 'your company'}.  
            With {first_snip}{' and ' + second_snip if second_snip else ''}, I believe I can add immediate value to your team.  
            {extra+' ' if extra else ''}I’d love to connect and discuss further.

            Thanks for your time!
        """).strip()
        message = template

    # 8) Subject
    subject = guess_name(resume_txt)
    return subject, message

# ─────── Example usage ───────
if __name__ == "__main__":
    RESUME_PATH = Path("your/path/to/resume.pdf")
    JD_PATH     = Path("D:/NYU/Sem 2/BDML/Project/rag_email/jd.txt")

    resume_text = read_file(RESUME_PATH)
    jd_text     = read_file(JD_PATH)

    subject, message = generate_outreach(
        resume_txt=resume_text,
        jd_txt=jd_text,
        recipient="Jane Doe",
        company="Acme Corp",
        top_k=5,
        max_new_tokens=64,
        extra="Mention my ML background"
    )

    print(f"Subject: {subject}\n")
    print(message)
