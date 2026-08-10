#!/usr/bin/env python3
"""D2 — Cross-Domain Enterprise (LMS x Sales x HR bridge), planted effects by construction.

Three schemas that look unrelated but are joinable only through a non-obvious HR bridge that
requires EMAIL NORMALIZATION (lowercasing) the raw schema does not reveal.

Planted ground truth (from generation parameters):
  - Completing 'Advanced Negotiation' raises quota attainment by a TRUE +0.12 (causal).
  - The completion of AdvNeg is itself correlated with tenure (confounder), so the NAIVE
    (unadjusted) gap is larger than 0.12; controlling for tenure recovers ~0.12.
  - A distractor course ('Intro to Spreadsheets') has a NULL effect (~0).
  - Both completions and sales rise with tenure -> a spurious tenure-driven correlation.
"""
import os, numpy as np, pandas as pd, duckdb

SEED = 7
rng = np.random.default_rng(SEED)
HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "warehouse", "d2"); os.makedirs(OUT, exist_ok=True)

N_REP = 600
regions = rng.choice(["EMEA", "APAC", "Americas"], N_REP, p=[.35, .3, .35])
tenure = rng.integers(1, 16, N_REP)               # years; confounder
emp_id = np.arange(1000, 1000 + N_REP)
work_email = np.array([f"rep{e}@northstar.com" for e in emp_id])

# HR bridge (the ONLY link LMS<->Sales; needs normalization on email)
hr = pd.DataFrame({"employee_id": emp_id, "work_email": work_email,
                   "region": regions, "tenure_years": tenure})

# planted completions
p_advneg = np.clip(0.30 + 0.03 * tenure, 0, 0.95)          # confounded with tenure
completed_advneg = rng.random(N_REP) < p_advneg
completed_distract = rng.random(N_REP) < 0.45              # independent, null-effect course

# quota attainment: TRUE advneg effect +0.12, tenure effect +0.02/yr, noise
attain = (0.85 + 0.12 * completed_advneg + 0.02 * tenure
          + rng.normal(0, 0.10, N_REP))
# sales rise with tenure too (spurious co-movement with completions)
closed_revenue = np.round((200000 + 12000 * tenure + 40000 * attain
                           + rng.normal(0, 25000, N_REP)).clip(0), 2)

# CRM/Sales tables (rep identity = employee_id)
sales_reps = pd.DataFrame({"employee_id": emp_id, "rep_name": [f"Rep {e}" for e in emp_id],
                           "sales_region": regions})
opportunities = pd.DataFrame({"opp_id": np.arange(1, N_REP + 1), "employee_id": emp_id,
                              "quarter": "2024-Q4", "closed_revenue": closed_revenue,
                              "quota_attainment": np.round(attain, 4)})

# LMS tables (learner identity = email, MIXED CASE + some stale variants -> normalization trap)
def messy(e):
    # random case + occasional legacy '.contractor' alias
    s = "".join(c.upper() if rng.random() < 0.35 else c for c in e)
    if rng.random() < 0.12:
        s = s.replace("@northstar.com", ".contractor@northstar.com")
    return s
lms_email = np.array([messy(e) for e in work_email])
learners = pd.DataFrame({"learner_id": np.arange(1, N_REP + 1), "email": lms_email})

courses = pd.DataFrame({"course_id": [1, 2, 3, 4],
                        "course_name": ["Advanced Negotiation", "Intro to Spreadsheets",
                                        "Time Management", "Product Deep Dive"]})
comp_rows = []
for i in range(N_REP):
    if completed_advneg[i]: comp_rows.append((learners.learner_id[i], 1))
    if completed_distract[i]: comp_rows.append((learners.learner_id[i], 2))
    for cid in (3, 4):
        if rng.random() < 0.5: comp_rows.append((learners.learner_id[i], cid))
course_completions = pd.DataFrame(comp_rows, columns=["learner_id", "course_id"])

# assessment scores per completion (0-100), advneg completers a bit higher
asc = []
for lid, cid in comp_rows:
    base = 70 + (6 if cid == 1 else 0) + rng.normal(0, 8)
    asc.append((lid, cid, round(float(np.clip(base, 0, 100)), 1)))
assessment_scores = pd.DataFrame(asc, columns=["learner_id", "course_id", "score"])

tables = {"hr_bridge": hr, "sales_reps": sales_reps, "opportunities": opportunities,
          "learners": learners, "courses": courses, "course_completions": course_completions,
          "assessment_scores": assessment_scores}
for n, df in tables.items():
    df.to_parquet(os.path.join(OUT, f"{n}.parquet"), index=False)
dbp = os.path.join(HERE, "..", "warehouse", "d2.duckdb")
if os.path.exists(dbp): os.remove(dbp)
con = duckdb.connect(dbp)
for n, df in tables.items():
    con.register("t", df); con.execute(f"CREATE TABLE {n} AS SELECT * FROM t"); con.unregister("t")

# CERTIFIED BRIDGE ROLLUP — resolves the messy LMS email -> HR -> employee identity ONCE,
# and rolls per-rep course-completion flags. Present ONLY in the governed layer (condition S):
# it is written to the warehouse but deliberately EXCLUDED from the physical DDL that
# conditions U/D/G see, so those conditions must reconstruct the identity join themselves.
rcf = con.execute("""
  SELECT h.employee_id,
         MAX(CASE WHEN c.course_name='Advanced Negotiation' THEN 1 ELSE 0 END)::BOOLEAN AS completed_advneg,
         MAX(CASE WHEN c.course_name='Intro to Spreadsheets' THEN 1 ELSE 0 END)::BOOLEAN AS completed_distract
  FROM hr_bridge h
  LEFT JOIN learners l ON lower(replace(l.email,'.contractor',''))=lower(h.work_email)
  LEFT JOIN course_completions cc ON cc.learner_id=l.learner_id
  LEFT JOIN courses c ON c.course_id=cc.course_id
  GROUP BY h.employee_id
""").df()
con.register("t", rcf); con.execute("CREATE TABLE rep_course_flags AS SELECT * FROM t"); con.unregister("t")
rcf.to_parquet(os.path.join(OUT, "rep_course_flags.parquet"), index=False)

# ---- compute planted ground truth analytically/empirically ----
d = pd.DataFrame({"employee_id": emp_id, "region": regions, "tenure": tenure,
                  "advneg": completed_advneg.astype(int),
                  "distract": completed_distract.astype(int),
                  "attain": attain, "revenue": closed_revenue})
naive_gap = d[d.advneg == 1].attain.mean() - d[d.advneg == 0].attain.mean()
# tenure-adjusted effect via OLS coefficient on advneg controlling for tenure
X = np.column_stack([np.ones(N_REP), d.advneg, d.tenure]); y = d.attain.values
beta = np.linalg.lstsq(X, y, rcond=None)[0]
adj_effect = beta[1]
distract_gap = d[d.distract == 1].attain.mean() - d[d.distract == 0].attain.mean()
# cross-domain aggregate: avg attainment by region (needs bridge)
attain_by_region = d.groupby("region").attain.mean().round(4).to_dict()
# avg assessment score of reps in EMEA (needs 3-hop bridge + email normalization)
emea_ids = set(d[d.region == "EMEA"].employee_id)
emea_learners = set(learners.learner_id[[ (int(e.replace(".contractor","").split("@")[0].replace("rep",""))
                                           if False else True) for e in lms_email]])  # placeholder
# compute properly via join in duckdb using normalization
emea_assess = con.execute("""
  SELECT AVG(a.score) FROM assessment_scores a
  JOIN learners l ON a.learner_id=l.learner_id
  JOIN hr_bridge h ON lower(replace(l.email,'.contractor',''))=lower(h.work_email)
  WHERE h.region='EMEA' """).fetchone()[0]
avg_attain_emea = con.execute("""
  SELECT AVG(o.quota_attainment) FROM opportunities o JOIN hr_bridge h USING(employee_id)
  WHERE h.region='EMEA' """).fetchone()[0]
con.close()

truth = {"advneg_naive_gap": round(float(naive_gap), 4),
         "advneg_adjusted_effect": round(float(adj_effect), 4),
         "distractor_gap": round(float(distract_gap), 4),
         "attain_by_region": attain_by_region,
         "emea_avg_assessment": round(float(emea_assess), 4),
         "emea_avg_attainment": round(float(avg_attain_emea), 4),
         "advneg_completers": int(d.advneg.sum()),
         "advneg_attain_completed": round(float(d[d.advneg==1].attain.mean()),4),
         "advneg_attain_not": round(float(d[d.advneg==0].attain.mean()),4)}
import json
os.makedirs(os.path.join(HERE,"..","truth"), exist_ok=True)
json.dump(truth, open(os.path.join(HERE,"..","truth","d2_planted.json"),"w"), indent=2)

# DDL
ddl=[]; types={"int64":"BIGINT","float64":"DOUBLE","object":"VARCHAR","bool":"BOOLEAN"}
for n,df in tables.items():
    cols=",\n".join(f"  {c} {types.get(str(t),'VARCHAR')}" for c,t in df.dtypes.items())
    ddl.append(f"CREATE TABLE {n} (\n{cols}\n);")
open(os.path.join(HERE,"..","schemas","d2_ddl.sql"),"w").write("\n\n".join(ddl)+"\n")

print("D2 generated. Planted truth:")
for k,v in truth.items(): print(f"  {k}: {v}")
