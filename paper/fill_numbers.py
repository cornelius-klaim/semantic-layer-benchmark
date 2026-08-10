#!/usr/bin/env python3
"""Substitute {{dotted.path}} tokens in whitepaper.src.qmd with values from
results/paper_numbers.json, writing whitepaper.qmd. Fails loudly on any unresolved token
so the paper can never ship with a stale or missing number."""
import os, re, json, sys
HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..")
N = json.load(open(os.path.join(ROOT, "results", "paper_numbers.json")))

def resolve(path):
    """Resolve a dotted path, tolerating dict keys that themselves contain dots
    (e.g. model names like 'gemini-2.5-flash-lite') by greedily matching the longest key."""
    parts = path.split(".")
    cur = N; i = 0
    while i < len(parts):
        if isinstance(cur, list):
            cur = cur[int(parts[i])]; i += 1; continue
        # try the longest prefix of remaining parts that is a key
        matched = False
        for j in range(len(parts), i, -1):
            key = ".".join(parts[i:j])
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]; i = j; matched = True; break
        if not matched:
            raise KeyError(".".join(parts[i:]))
    return cur

def fmt(v):
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)

src = open(os.path.join(HERE, "whitepaper.src.qmd")).read()
missing = []
def sub(m):
    path = m.group(1).strip()
    try:
        return fmt(resolve(path))
    except Exception:
        missing.append(path); return m.group(0)
out = re.sub(r"\{\{([^}]+)\}\}", sub, src)
if missing:
    print("UNRESOLVED TOKENS:", sorted(set(missing))); sys.exit(1)
open(os.path.join(HERE, "whitepaper.qmd"), "w").write(out)
print("wrote whitepaper.qmd")
