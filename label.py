"""
label.py — short theme labels for risk-factor clusters via Groq.

Temperature is 0 for determinism: a gap-finder that surfaces different
labels each run is dead on arrival for credibility. Cache + temp=0
= reproducible output.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


def label_theme(example_texts: list[str]) -> str:
    if not GROQ_KEY:
        return "(set GROQ_API_KEY for theme labels)"

    joined = "\n\n---\n\n".join(t[:600] for t in example_texts[:4])

    messages = [
        {
            "role": "system",
            "content": (
                "You label risk-factor themes from 10-K filings. Given several "
                "risk paragraphs that cluster together semantically, output a "
                "short noun phrase (2-6 words) naming the underlying theme. "
                "Examples: 'Dealer franchise exposure', 'Lithium supply "
                "concentration', 'Defined-benefit pension obligations', "
                "'Union labour relations', 'Goodwill impairment risk'. "
                "Output the label only. No explanation, quotes, or punctuation."
            ),
        },
        {
            "role": "user",
            "content": f"Risks that cluster together:\n\n{joined}\n\nTheme label:",
        },
    ]

    try:
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": messages,
                "max_tokens": 30,
                "temperature": 0,  # deterministic
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(label error: {e})"
