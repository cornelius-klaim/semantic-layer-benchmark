#!/usr/bin/env python3
"""Condition S — the deterministic semantic compiler.

Input: a JSON query plan selecting fields from the semantic model (never SQL).
Output: fan-out-safe SQL generated from the model, or a structured REFUSAL.

Guarantees (the paper's "fail-safe by construction"):
  - Each measure is aggregated at ITS declared base grain, then measures are combined on
    shared dimensions via FULL OUTER JOIN — so order-grain measures never fan out over lines.
  - A measure requested with a dimension finer than its grain (not reachable many-to-one
    from its base) is REFUSED, not silently inflated.
  - Unknown fields are refused. Vocabulary filters resolve business terms to stored values.
  - Certified filters (e.g. status IN shipped/delivered) are applied automatically, always.

SQL emission goes through a pluggable DIALECT (see compiler/dialects.py). The compiler
decides WHAT to emit; the dialect decides how it is spelled for a warehouse. The default
dialect is DuckDB and is the identity transform, so the DuckDB arm is byte-for-byte what
it was before the seam existed.
"""
import os
import re
import sys
import yaml

try:
    from dialects import DUCKDB, DialectError, dim_ref, get_dialect
except ImportError:  # imported without compiler/ on sys.path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from dialects import DUCKDB, DialectError, dim_ref, get_dialect

def load_model(path):
    return yaml.safe_load(open(path))

def _coerce_date(v):
    """A bare calendar value on a date dimension -> a full ISO date the layer can compare.
    2024 / '2024' -> '2024-01-01';  '2024-05' -> '2024-05-01';  '2024-05-01' -> unchanged."""
    s = str(v).strip()
    if re.fullmatch(r"\d{4}", s): return f"{s}-01-01"
    if re.fullmatch(r"\d{4}-\d{2}", s): return f"{s}-01"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s): return s
    return s

def _adj(model):
    a = {}
    for e in model.get("join_graph", []):
        a.setdefault(e["from"], []).append((e["to"], e["on_sql"]))
    return a

def reachable(model, base):
    """Tables reachable from base by following many-to-one (child->parent) edges."""
    a = _adj(model); seen = {base}; stack = [base]
    while stack:
        n = stack.pop()
        for to, _ in a.get(n, []):
            if to not in seen:
                seen.add(to); stack.append(to)
    return seen

def _edges_to(model, base, target):
    """Return list of ON-clauses for the path base -> target (many-to-one)."""
    a = _adj(model)
    # DFS for a path
    def dfs(node, path):
        if node == target: return path
        for to, on in a.get(node, []):
            r = dfs(to, path + [(to, on)])
            if r is not None: return r
        return None
    return dfs(base, []) or []

def _joins_for(model, base, needed_tables, D=DUCKDB):
    """Assemble LEFT JOIN clauses covering all needed tables reachable from base."""
    clauses, joined = [], {base}
    for t in needed_tables:
        if t == base: continue
        for to, on in _edges_to(model, base, t):
            if to not in joined:
                clauses.append(f"LEFT JOIN {D.table_ref(to)} ON {D.expr(on)}"); joined.add(to)
    return clauses

def resolve_value(model, field, value):
    """Resolve a business term to the stored value list via the field's vocabulary map."""
    dim = model["dimensions"].get(field, {})
    vname = dim.get("vocabulary")
    if not vname: return [value]
    vmap = model["vocabulary"][vname]["map"]
    # exact business-term match, else case-insensitive, else the raw value
    if value in vmap: return vmap[value]
    for k, vs in vmap.items():
        if k.lower() == str(value).lower(): return vs
    return [value]

class Refusal(Exception): ...

# tolerate the small vocabulary differences models use when naming a filter's parts, so a
# well-formed intent isn't rejected on a key name. field: field|dimension|name|column;
# op: op|operator with eq/ne/gt.. normalized to SQL operators.
_OP_MAP = {"eq": "=", "equals": "=", "=": "=", "ne": "!=", "neq": "!=", "!=": "!=",
           "gt": ">", ">": ">", "lt": "<", "<": "<", "gte": ">=", ">=": ">=",
           "lte": "<=", "<=": "<=", "in": "in", "=in": "in"}
def _filter_field(f):
    return f.get("field") or f.get("dimension") or f.get("name") or f.get("column")
def _filter_op(f):
    raw = str(f.get("op") or f.get("operator") or "=").lower()
    return _OP_MAP.get(raw, "=")

def _dim_source(model, name):
    if name not in model["dimensions"]:
        raise Refusal(f"unknown dimension '{name}'")
    return model["dimensions"][name]["source"]

def _measure(model, name):
    if name not in model["measures"]:
        raise Refusal(f"unknown measure '{name}'")
    return model["measures"][name]

def _measure_subquery(model, mname, dims, filters, D=DUCKDB):
    """Aggregate one measure at its base grain, grouped by dims, with certified + plan filters."""
    m = _measure(model, mname)
    if "ratio" in m or "expr" in m:  # composite measures are assembled by the caller
        return None
    base = m["base"]
    reach = reachable(model, base)
    # grain safety: every dim must be reachable many-to-one from this measure's base
    for d in dims:
        src = _dim_source(model, d)
        if src not in reach:
            raise Refusal(f"measure '{mname}' (grain: {base}) cannot be broken down by "
                          f"dimension '{d}' (from {src}) — finer grain would fan out")
    needed = ({base} | {_dim_source(model, d) for d in dims}
              | set(m.get("join_required", [])) | set(m.get("requires", [])))
    where = []
    if m.get("filter_sql"): where.append(D.expr(m["filter_sql"]))
    for f in filters:
        field = _filter_field(f)
        if not field or "value" not in f:
            continue  # skip a malformed filter rather than crash the whole plan
        src = _dim_source(model, field)
        needed.add(src)
        dim = model["dimensions"][field]
        vals = resolve_value(model, field, f["value"])
        col = D.expr(dim["sql"])
        op = _filter_op(f)
        # date dimensions (year/month/day truncations) accept a bare calendar value:
        # 2024 or "2024" -> DATE '2024-01-01'; "2024-05" -> DATE '2024-05-01'. A governed
        # layer must handle "filter year = 2024" without the caller knowing the storage format.
        # The literal's TYPE is dialect business: DuckDB coerces TIMESTAMP<->DATE, BigQuery
        # does not, so the dialect gets the raw model expression and types the literal to match.
        if dim.get("type") == "date":
            cv = _coerce_date(vals[0])
            dop = "=" if op == "in" else op   # a single calendar value is an equality, not IN
            where.append(D.date_predicate(dim["sql"], dop, cv))
            continue
        if op in ("=", "in") and len(vals) > 1:
            inlist = ", ".join("'" + str(v).replace("'", "''") + "'" for v in vals)
            where.append(f"{col} IN ({inlist})")
        else:
            v = vals[0]
            vlit = v if isinstance(v, (int, float)) else "'" + str(v).replace("'", "''") + "'"
            where.append(f"{col} {op} {vlit}")
    joins = _joins_for(model, base, needed, D)
    dim_sel = [f'{D.expr(model["dimensions"][d]["sql"])} AS {d}' for d in dims]
    sel = dim_sel + [f'{D.expr(m["agg_sql"])} AS {mname}']
    sql = f"SELECT {', '.join(sel)}\nFROM {D.table_ref(base)}\n" + "\n".join(joins)
    if where: sql += "\nWHERE " + " AND ".join(where)
    if dims:  sql += "\nGROUP BY " + ", ".join(str(i+1) for i in range(len(dims)))
    return sql

def compile_plan(model, plan, dialect=None):
    """Compile a query plan to SQL, or return a structured refusal.

    `dialect` defaults to DuckDB (the identity dialect); pass a Dialect from
    compiler/dialects.py — or a spec string like 'bigquery:my-project.my_dataset' — to
    target another warehouse. A DialectError propagates: an unsupported warehouse
    construct is a compiler gap, not a governed refusal, and must not be scored as one.
    """
    D = dialect if hasattr(dialect, "table_ref") else get_dialect(dialect)
    try:
        if plan.get("refuse"):
            return {"refuse": plan["refuse"]}
        measures = plan.get("measures", [])
        dims = plan.get("dimensions", [])
        filters = plan.get("filters", [])
        if not measures:
            raise Refusal("a query must request at least one measure")
        # expand ratio + expression measures into their component base measures
        comp_sqls, out_cols = {}, []
        needed_measures = []
        ratio_defs = {}
        expr_defs = {}
        for mn in measures:
            m = _measure(model, mn)
            if "ratio" in m:
                ratio_defs[mn] = m["ratio"]
                needed_measures += [m["ratio"]["numerator"], m["ratio"]["denominator"]]
            elif "expr" in m:
                comps = m.get("components") or []
                if not comps:
                    raise Refusal(f"expr measure '{mn}' must declare its components")
                expr_defs[mn] = {"expr": m["expr"], "components": comps}
                needed_measures += comps
            else:
                needed_measures.append(mn)
        needed_measures = list(dict.fromkeys(needed_measures))  # dedupe, keep order
        # one subquery per base measure
        for mn in needed_measures:
            comp_sqls[mn] = _measure_subquery(model, mn, dims, filters, D)
        # combine subqueries via FULL OUTER JOIN on dims (the cartesian no-dimension case
        # is spelled differently per dialect — see Dialect.combine_measures)
        aliases = {mn: f"m{i}" for i, mn in enumerate(needed_measures)}
        first = needed_measures[0]
        frm = f"({comp_sqls[first]}) {aliases[first]}"
        # Each subquery is joined against EVERY subquery already in the FROM clause, on a
        # key COALESCE'd across them; the dimension is then read back through the same
        # COALESCE. Measure subqueries have different domains (different base grains,
        # different certified filters), so a group present in m1 but not in m0 must still
        # find its partners in m2, m3, ... and must still carry its label. Joining
        # everything to m0 alone loses that label with two measures and splits the group
        # into one row per measure with three or more.
        joined = [aliases[first]]
        for mn in needed_measures[1:]:
            frm += D.combine_measures(joined, dims, comp_sqls[mn], aliases[mn])
            joined.append(aliases[mn])
        # SELECT list: dims + requested measures (ratios computed here)
        sel = [f"{dim_ref(joined, d)} AS {d}" for d in dims]
        for mn in measures:
            if mn in ratio_defs:
                num, den = ratio_defs[mn]["numerator"], ratio_defs[mn]["denominator"]
                sel.append(f"({aliases[num]}.{num} * 1.0 / NULLIF({aliases[den]}.{den},0)) AS {mn}")
            elif mn in expr_defs:
                # substitute each component measure name with its qualified subquery column,
                # longest names first so a name that is a prefix of another isn't half-replaced
                e = D.expr(expr_defs[mn]["expr"])
                for comp in sorted(expr_defs[mn]["components"], key=len, reverse=True):
                    e = re.sub(rf"\b{re.escape(comp)}\b", f"{aliases[comp]}.{comp}", e)
                sel.append(f"({e}) AS {mn}")
            else:
                sel.append(f"{aliases[mn]}.{mn} AS {mn}")
        sql = f"SELECT {', '.join(sel)}\nFROM {frm}"
        # order / limit  (tolerate the model returning order_by as a list or a bare string)
        ob = plan.get("order_by")
        if isinstance(ob, list):
            ob = ob[0] if ob else None
        if isinstance(ob, str):
            ob = {"field": ob, "dir": "desc"}
        if isinstance(ob, dict):
            fld = (ob.get("field") or ob.get("measure") or ob.get("name")
                   or ob.get("dimension") or ob.get("column"))
            d = str(ob.get("dir") or ob.get("order") or ob.get("direction") or "desc")
            if fld in set(measures) | set(dims):
                # NULLS LAST is explicit, not decorative. The combine step MANUFACTURES NULLs
                # (a group present in one measure's subquery but not another's), and engines
                # disagree on where they sort: DuckDB puts NULLs last in both directions,
                # BigQuery puts them FIRST for ASC. Without this, the same plan returns a
                # different row per warehouse under ORDER BY ... ASC + LIMIT. Emitting
                # NULLS LAST matches DuckDB's existing behaviour exactly (so published
                # DuckDB results are unchanged) and makes BigQuery agree.
                _dir = 'ASC' if d.lower().startswith('asc') else 'DESC'
                sql += f"\nORDER BY {fld} {_dir} NULLS LAST"
        if plan.get("limit"):
            try: sql += f"\nLIMIT {int(plan['limit'])}"
            except (TypeError, ValueError): pass
        return {"sql": sql}
    except Refusal as r:
        return {"refuse": str(r)}
    except DialectError:
        # a warehouse-coverage gap, NOT a governance decision — never disguise it as one
        raise
    except Exception as e:
        return {"refuse": f"invalid plan ({type(e).__name__}: {str(e)[:120]})"}

def run_plan(model, plan, con, dialect=None):
    c = compile_plan(model, plan, dialect)
    if "refuse" in c:
        return {"refuse": c["refuse"]}
    rows = con.execute(c["sql"]).fetchall()
    cols = [d[0] for d in con.description]
    return {"sql": c["sql"], "rows": rows, "columns": cols}

if __name__ == "__main__":
    import duckdb, json
    HERE = os.path.dirname(__file__)
    model = load_model(os.path.join(HERE, "..", "semantic_models", "d1.yaml"))
    con = duckdb.connect(os.path.join(HERE, "..", "warehouse", "d1.duckdb"), read_only=True)
    tests = [
        {"measures": ["net_revenue"]},                                              # scalar
        {"measures": ["net_revenue"], "dimensions": ["ship_region"]},               # by region
        {"measures": ["aov"]},                                                      # ratio
        {"measures": ["net_revenue"], "filters": [{"field": "order_channel", "op": "=", "value": "Paid Search"}]},
        {"measures": ["shipping_fee_total"], "dimensions": ["product_category"]},    # SHOULD REFUSE (fan-out)
        {"measures": ["net_revenue", "shipping_fee_total"], "dimensions": ["ship_region"]},  # mixed grain, safe
    ]
    for p in tests:
        r = run_plan(model, p, con)
        if "refuse" in r:
            print("REFUSE:", r["refuse"])
        else:
            print("OK:", p.get("measures"), p.get("dimensions", ""), "->", r["rows"][:3])
    # `python compiler/compile.py bigquery:<project>.<dataset>` prints the same plans as
    # BigQuery SQL without executing anything (no credentials, no API calls).
    if len(sys.argv) > 1:
        D = get_dialect(sys.argv[1])
        print(f"\n--- {D.name} ---")
        for p in tests + [{"measures": ["net_revenue"], "dimensions": ["order_month"]},
                          {"measures": ["net_revenue"],
                           "filters": [{"field": "fiscal_year", "op": "=", "value": 2024}]}]:
            c = compile_plan(model, p, D)
            print("\n" + (c.get("sql") or "REFUSE: " + c["refuse"]))
