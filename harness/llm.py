#!/usr/bin/env python3
"""Gemini adapter via the Generative Language REST API. Records tokens + latency."""
import os, json, time, urllib.request, urllib.error

KEY = os.environ["GEMINI_API_KEY"]
BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# capability-tier ladder (single vendor; the tier spread tests "scale != meaning")
MODELS = {
    "gemini-2.5-flash-lite": "gemini-2.5-flash-lite",
    "gemini-2.5-flash":      "gemini-2.5-flash",
    "gemini-2.5-pro":        "gemini-2.5-pro",
    "gemini-3.5-flash":      "gemini-3.5-flash",
    "gemini-3.1-pro":        "gemini-3.1-pro-preview",
    "gemini-3.7-flash":      "gemini-3.7-flash",
}

def call(model_id, prompt, temperature=0.0, max_tokens=2048, retries=4):
    return call_chat(model_id, [("user", prompt)], temperature, max_tokens, retries)

def call_chat(model_id, turns, temperature=0.0, max_tokens=2048, retries=4):
    """turns: list of (role, text) where role in {'user','model'}. Multi-turn conversation."""
    contents = [{"role": r, "parts": [{"text": t}]} for r, t in turns]
    body = json.dumps({
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }).encode()
    url = f"{BASE}/{model_id}:generateContent?key={KEY}"
    last = None
    for attempt in range(retries):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=120))
            dt = time.time() - t0
            cand = (r.get("candidates") or [{}])[0]
            parts = cand.get("content", {}).get("parts", []) or []
            text = "".join(p.get("text", "") for p in parts)
            um = r.get("usageMetadata", {})
            return {"text": text, "in_tokens": um.get("promptTokenCount", 0),
                    "out_tokens": um.get("candidatesTokenCount", 0),
                    "finish": cand.get("finishReason", ""), "latency": round(dt, 2), "error": None}
        except urllib.error.HTTPError as e:
            code = e.code; last = f"HTTP {code}: {e.read()[:200]}"
            if code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt + 1); continue
            return {"text": "", "in_tokens": 0, "out_tokens": 0, "finish": "", "latency": round(time.time()-t0,2), "error": last}
        except Exception as e:
            last = str(e)[:200]
            if attempt < retries - 1: time.sleep(2 ** attempt + 1); continue
            return {"text": "", "in_tokens": 0, "out_tokens": 0, "finish": "", "latency": round(time.time()-t0,2), "error": last}
    return {"text": "", "in_tokens": 0, "out_tokens": 0, "finish": "", "latency": 0, "error": last}
