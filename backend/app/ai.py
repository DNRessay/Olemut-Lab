import json
import os
import urllib.request

from fastapi import HTTPException

URL = "https://api.groq.com/openai/v1/chat/completions"
SYSTEM = (
    "You are a careful research assistant for scientists. Be precise and concise. "
    "State uncertainty plainly. Never invent citations, DOIs, authors or numbers; "
    "only cite what appears in the provided text."
)


def chat(user: str, system: str = SYSTEM, json_mode: bool = False, max_tokens: int = 1200) -> str:
    payload = {
        "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        URL,
        json.dumps(payload).encode(),
        {
            "Authorization": "Bearer " + os.environ["GROQ_API_KEY"],
            "Content-Type": "application/json",
            "User-Agent": "scilab/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=24) as r:
            return json.load(r)["choices"][0]["message"]["content"]
    except Exception:
        raise HTTPException(502, "AI service unavailable, try again")


def summarize_paper(text: str) -> dict:
    out = chat(
        "Analyze this paper text and return JSON with keys: title (string), takeaways (list), "
        "methods (list), findings (list), limitations (list), references (list of reference "
        "strings exactly as they appear in the text, max 25), keywords (list of 3-6 search terms).\n\n"
        + text[:24000],
        json_mode=True,
        max_tokens=1800,
    )
    try:
        return json.loads(out)
    except Exception:
        return {"takeaways": [out]}
