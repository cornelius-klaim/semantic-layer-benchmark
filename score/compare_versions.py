#!/usr/bin/env python3
"""Print the v1 (pre-promotion) vs v2 (architect-promoted metrics) deltas from the two
paper_numbers.json snapshots. Demonstrates the compounding-governance result: promoting a
metric once permanently lifts the layer on every query that touches it."""
import json, os
HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..")
v1 = json.load(open(os.path.join(ROOT, "results_v1", "paper_numbers.json")))
v2 = json.load(open(os.path.join(ROOT, "results", "paper_numbers.json")))

def line(label, a, b):
    d = b - a
    arrow = "▲" if d > 0.05 else ("▼" if d < -0.05 else "=")
    print(f"  {label:28} {a:6.1f}%  →  {b:6.1f}%   {arrow} {d:+5.1f}")

print("="*64)
print("  v1 (before promotion)  →  v2 (architect promoted 3 metrics)")
print("="*64)
print("\nPooled ladder:")
for c in ["U","D","G","S"]:
    line(f"{c}", v1["ladder"][c], v2["ladder"][c])

print("\nCondition S by affected suite (D1 ad-hoc metrics):")
names = {"2":"Suite 2 grain/fan-out","3":"Suite 3 compound keys","5":"Suite 5 synthesis",
         "8":"Suite 8 time"}
for s in ["2","3","5","8"]:
    if s in v1["by_suite"] and s in v2["by_suite"]:
        line(names[s]+" (S)", v1["by_suite"][s]["S"], v2["by_suite"][s]["S"])

print("\nSemantic-layer (S) by model:")
for m in sorted(set(v1.get("by_model",{})) & set(v2.get("by_model",{}))):
    line(m+" (S)", v1["by_model"][m]["S"], v2["by_model"][m]["S"])

print("\nOther conditions unchanged where no metric was promoted — U should be ~flat:")
line("U pooled (control)", v1["ladder"]["U"], v2["ladder"]["U"])

# token accounting (gemini arm)
if "cost" in v2:
    print("\nTokens per layer (Gemini arm; mean prompt / mean output / total output):")
    for c in ["U","D","G","S"]:
        ci = v2["cost"].get(c, {})
        print(f"  {c}: prompt~{ci.get('prompt_tokens',0):.0f}  out~{ci.get('out_tokens',0):.0f}  "
              f"total_out={ci.get('total_out_tokens',0):,}  lat={ci.get('latency_s',0)}s")
