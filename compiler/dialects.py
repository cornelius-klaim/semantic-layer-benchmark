#!/usr/bin/env python3
"""Pluggable SQL dialects for the deterministic semantic compiler.

`compile.py` decides WHAT to emit (which measures, at which grain, with which joins and
filters — the governance part). A DIALECT decides HOW that is spelled in a given warehouse.
Everything the compiler emits that is not pure structure goes through one of four hooks:

    table_ref(table)                     FROM / LEFT JOIN target
    expr(sql)                            any SQL string that came from the semantic MODEL
                                         (dimension sql, agg_sql, filter_sql, join on_sql,
                                          composite measure expr)
    date_predicate(dim_sql, op, iso)     a date dimension compared to a calendar literal
    combine_measures(...)                how per-measure subqueries are stitched together

`DUCKDB` is the identity dialect: every hook returns exactly the bytes the pre-dialect
compiler produced, so the DuckDB arm of the benchmark is unchanged (verified byte-for-byte
against the stored condition-S plans — see compiler/README-dialects.md).

`BigQueryDialect` qualifies table names, rewrites DuckDB-only date expressions, and fixes
the two places where BigQuery is stricter than DuckDB (the cartesian measure join, and
TIMESTAMP/DATE literal typing).

A construct the target dialect cannot express raises DialectError. That is deliberate and
it is NOT a Refusal: a refusal is a governance decision about the QUESTION, while a
DialectError is a gap in the compiler's coverage of the WAREHOUSE. `compile.py` re-raises
DialectError instead of folding it into a refusal, so a dialect gap can never be scored as
the semantic layer correctly declining to answer.
"""
import re


class DialectError(Exception):
    """The target dialect has no faithful spelling for this construct."""


# --------------------------------------------------------------------------------------
# tiny SQL-aware scanning helpers (quote- and paren-aware; not a parser, deliberately)
# --------------------------------------------------------------------------------------
_QUOTES = ("'", '"', "`")


def _skip_quoted(s, i):
    """s[i] opens a quoted run. Return the index just past its closing quote."""
    q = s[i]
    i += 1
    while i < len(s):
        if s[i] == "\\" and q == "'":      # backslash escape (DuckDB accepts it)
            i += 2
            continue
        if s[i] == q:
            if i + 1 < len(s) and s[i + 1] == q:   # doubled quote = literal quote
                i += 2
                continue
            return i + 1
        i += 1
    raise DialectError(f"unterminated string literal in: {s[:80]!r}")


def _match_paren(s, i):
    """s[i] == '('. Return the index of its matching ')'."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c in _QUOTES:
            i = _skip_quoted(s, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise DialectError(f"unbalanced parentheses in: {s[:80]!r}")


def _split_args(s):
    """Split a call's argument text on top-level commas."""
    out, depth, start, i = [], 0, 0, 0
    while i < len(s):
        c = s[i]
        if c in _QUOTES:
            i = _skip_quoted(s, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            out.append(s[start:i])
            start = i + 1
        i += 1
    out.append(s[start:])
    return [a.strip() for a in out]


def _find_keyword(s, word):
    """Indices of a word-bounded keyword at paren depth 0, outside string literals."""
    hits, depth, i, n, w = [], 0, 0, len(s), word.upper()
    while i < n:
        c = s[i]
        if c in _QUOTES:
            i = _skip_quoted(s, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 0 and s[i:i + len(w)].upper() == w:
            before_ok = i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")
            j = i + len(w)
            after_ok = j >= n or not (s[j].isalnum() or s[j] == "_")
            if before_ok and after_ok:
                hits.append(i)
                i = j
                continue
        i += 1
    return hits


def _mask_quoted(s):
    """Blank the *interior* of every quoted run, preserving length and quote positions.

    Lets the BigQuery deny-list scan look at SQL code only: a value like
    'date_trunc(''month'')' inside a vocabulary map is data, not a call to translate.
    """
    out, i, n = [], 0, len(s)
    while i < n:
        if s[i] in _QUOTES:
            j = _skip_quoted(s, i)
            out.append(s[i] + "\x00" * (j - i - 2) + s[j - 1])
            i = j
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _unquote(tok):
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] in _QUOTES and tok[-1] == tok[0]:
        return tok[1:-1]
    return tok


def dim_ref(aliases, dim):
    """How a grouping dimension is referenced across the per-measure subqueries.

    One subquery: the column itself. SEVERAL: COALESCE across every alias. Measure
    subqueries do NOT share a domain — each sits at its own base grain and carries its own
    certified filter — so a group can be absent from one subquery and present in another.
    Reading the label from a single alias emits NULL for every group that alias never
    produced, and (with three or more measures) splits such a group across one row per
    measure. COALESCE is ANSI and spelled identically in DuckDB and BigQuery, so this
    needs no per-dialect hook.
    """
    if isinstance(aliases, str):
        aliases = [aliases]
    if len(aliases) == 1:
        return f"{aliases[0]}.{dim}"
    return "COALESCE(" + ", ".join(f"{a}.{dim}" for a in aliases) + ")"


# --------------------------------------------------------------------------------------
# base / DuckDB dialect  — the identity dialect
# --------------------------------------------------------------------------------------
class Dialect:
    """Identity dialect. Emits exactly what the pre-dialect compiler emitted (DuckDB)."""

    name = "duckdb"

    # --- table references -------------------------------------------------------------
    def table_ref(self, table):
        """How a base table is named in FROM / LEFT JOIN."""
        return table

    # --- model-supplied SQL -----------------------------------------------------------
    def expr(self, sql):
        """Translate a SQL fragment that came from the semantic model."""
        return sql

    # --- date dimension compared to a calendar literal --------------------------------
    def date_predicate(self, dim_sql, op, iso):
        """`dim_sql` is the RAW model expression (untranslated); `iso` is 'YYYY-MM-DD'."""
        return f"{self.expr(dim_sql)} {op} DATE '{iso}'"

    # --- stitching per-measure subqueries together ------------------------------------
    def combine_measures(self, left_aliases, dims, sub_sql, alias):
        """Join one measure subquery onto the accumulated FROM clause.

        With dimensions this is an equi FULL OUTER JOIN on the shared dims. With no
        dimensions every subquery yields exactly one row and the join is a cartesian
        product of two 1-row relations.

        `left_aliases` is EVERY subquery already in the FROM clause, not just the first
        one, and the join key is COALESCE'd across them (see `dim_ref`). Chaining every
        join back to the first subquery alone would leave the key NULL for any group that
        subquery does not produce, so the group would match nothing afterwards and split
        into one row per measure. A bare string is accepted as a one-element list.
        """
        on = " AND ".join(f"{dim_ref(left_aliases, d)} = {alias}.{d}" for d in dims) or "TRUE"
        return f"\nFULL OUTER JOIN ({sub_sql}) {alias} ON {on}"


DUCKDB = Dialect()


# --------------------------------------------------------------------------------------
# BigQuery
# --------------------------------------------------------------------------------------
_IDENT_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_DATE_TRUNC_CALL = re.compile(r"date_trunc\s*\(", re.I)

# BigQuery *_TRUNC parts
_BQ_TRUNC_UNITS = {"MICROSECOND", "MILLISECOND", "SECOND", "MINUTE", "HOUR", "DAY",
                   "WEEK", "MONTH", "QUARTER", "YEAR", "ISOWEEK", "ISOYEAR"}
# units TIMESTAMP_ADD/SUB accept (sub-day + DAY) — these keep the TIMESTAMP type
_BQ_TS_INTERVAL_UNITS = {"MICROSECOND", "MILLISECOND", "SECOND", "MINUTE", "HOUR", "DAY"}
# units DATE_ADD/SUB accept — these force a DATE, dropping any time-of-day
_BQ_DATE_INTERVAL_UNITS = {"DAY", "WEEK", "MONTH", "QUARTER", "YEAR"}

_INTERVAL_TAIL = re.compile(
    r"""^INTERVAL\s+(?:
            '(?P<qn>\d+)\s*(?P<qu>[A-Za-z]+)'      # INTERVAL '11 months'
          | '(?P<sn>\d+)'\s*(?P<su>[A-Za-z]+)      # INTERVAL '11' MONTH
          | (?P<pn>\d+)\s+(?P<pu>[A-Za-z]+)        # INTERVAL 11 MONTH
        )\s*$""",
    re.I | re.X,
)

# Constructs that must not survive translation. Each is checked against the OUTPUT, so a
# gap in the translator surfaces as a loud DialectError instead of invalid BigQuery SQL.
# The *_TRUNC entries key on a QUOTED first argument, which is the DuckDB argument order
# (date_trunc('month', x)); BigQuery's own order (TIMESTAMP_TRUNC(x, MONTH)) never matches.
_BQ_DENY = [
    (re.compile(r"\b(?:DATE|TIMESTAMP|DATETIME)_TRUNC\s*\(\s*['\"]", re.I),
     "date_trunc('unit', x) — DuckDB argument order"),
    (re.compile(r"\bDATE_DIFF\s*\(\s*['\"]", re.I),
     "date_diff('unit', a, b) — DuckDB argument order"),
    (re.compile(r"::"), "'::' cast — BigQuery uses CAST(x AS t)"),
    (re.compile(r"\bdate_part\s*\(", re.I), "date_part() — BigQuery uses EXTRACT()"),
    (re.compile(r"\bstrftime\s*\(", re.I), "strftime() — BigQuery uses FORMAT_TIMESTAMP()"),
    (re.compile(r"\bstrptime\s*\(", re.I), "strptime() — BigQuery uses PARSE_TIMESTAMP()"),
    (re.compile(r"\bepoch\s*\(", re.I), "epoch()"),
    (re.compile(r"\bdatediff\s*\(", re.I), "datediff()"),
    (re.compile(r"\bage\s*\(", re.I), "age()"),
    (re.compile(r"\btry_cast\b", re.I), "TRY_CAST — BigQuery uses SAFE_CAST"),
    (re.compile(r"\bilike\b", re.I), "ILIKE"),
    (re.compile(r"~~"), "'~~' pattern operator"),
    (re.compile(r"\blist_[a-z_]+\s*\(", re.I), "DuckDB list_*() function"),
    (re.compile(r"\bregexp_matches\s*\(", re.I),
     "regexp_matches() — BigQuery uses REGEXP_CONTAINS()"),
]


class BigQueryDialect(Dialect):
    """BigQuery (GoogleSQL).

    Differences from the DuckDB arm, all of them forced by BigQuery being stricter:

    1. Tables are `project.dataset.table`, emitted with an explicit `AS <table>` alias so
       every `orders.column` reference in the semantic model keeps resolving unchanged.
    2. DuckDB's `date_trunc('month', ts)` becomes `TIMESTAMP_TRUNC(ts, MONTH)`, and
       `ts + INTERVAL n MONTH` — which BigQuery cannot do on a TIMESTAMP at all — becomes
       `DATE_ADD(DATE(ts), INTERVAL n MONTH)`.
    3. Because (2) leaves some date dimensions TIMESTAMP-typed and others DATE-typed, the
       calendar literal is typed to match the column instead of always being `DATE '...'`
       (DuckDB coerces TIMESTAMP<->DATE implicitly; BigQuery does not).

    The JOIN STRUCTURE is deliberately identical to the DuckDB arm, including
    `FULL OUTER JOIN (...) mN ON TRUE` for the no-dimension case — BigQuery accepts it.

    Both `TIMESTAMP_TRUNC` and `DATE(timestamp)` interpret their argument in UTC unless a
    zone is passed, which is what makes this arm agree with DuckDB's naive timestamps.

    `column_types` optionally maps a bare column reference to its BigQuery type, e.g.
    {"orders.order_ts": "TIMESTAMP"}. It only matters for a bare column handed straight to
    date_trunc(); without it such a column is assumed TIMESTAMP (true of this benchmark's
    warehouse). Supply it if a model ever truncates a DATE column.
    """

    name = "bigquery"

    def __init__(self, project, dataset, column_types=None):
        for part, label in ((project, "project"), (dataset, "dataset")):
            if not part or not _IDENT_RE.match(str(part)):
                raise DialectError(f"invalid BigQuery {label} id: {part!r}")
        self.project = str(project)
        self.dataset = str(dataset)
        self.column_types = {k.lower(): v.upper() for k, v in (column_types or {}).items()}
        self._cache = {}

    # --- hooks ------------------------------------------------------------------------
    def table_ref(self, table):
        if not _IDENT_RE.match(str(table)):
            raise DialectError(f"invalid BigQuery table id: {table!r}")
        # The explicit alias is what keeps model SQL ("orders.order_id = ...") valid.
        # BigQuery's implicit alias for a qualified path is the table name anyway; saying
        # it out loud costs nothing and does not depend on that implicit rule.
        return f"`{self.project}.{self.dataset}.{table}` AS {table}"

    def expr(self, sql):
        return self._translate(sql)[0]

    def date_predicate(self, dim_sql, op, iso):
        col, typ = self._translate(dim_sql)
        lit = {"DATE": "DATE", "DATETIME": "DATETIME"}.get(typ, "TIMESTAMP")
        return f"{col} {op} {lit} '{iso}'"

    # combine_measures is deliberately NOT overridden. An earlier draft of this dialect
    # rewrote the no-dimension case `FULL OUTER JOIN (...) m1 ON TRUE` into `CROSS JOIN`,
    # on the belief that BigQuery rejects a non-equality outer-join predicate. It does
    # not: a constant `ON TRUE` is accepted (verified against joon-sandbox — BigQuery's
    # restriction is on correlated/non-equality predicates that reference both sides, and
    # `TRUE` references neither). The rewrite was therefore an UNFORCED divergence between
    # the two arms: it changed the join structure of every scalar multi-measure query
    # (aov, shipping_pct_of_revenue, net_revenue_after_refunds, advneg_attainment_lift)
    # and so weakened exactly the comparison this dialect exists to support. Both arms now
    # emit the same join structure and only the spelling of leaves differs.

    # --- translation ------------------------------------------------------------------
    def _translate(self, sql):
        """Return (bigquery_sql, type) for a model SQL fragment. type may be None."""
        if sql in self._cache:
            return self._cache[sql]
        out, typ = self._expr(sql)
        code = _mask_quoted(out)   # scan SQL code, not the contents of string literals
        for pat, why in _BQ_DENY:
            if pat.search(code):
                raise DialectError(f"cannot translate to BigQuery ({why}): {sql!r}")
        self._check_intervals(code, sql)
        self._cache[sql] = (out, typ)
        return out, typ

    @staticmethod
    def _check_intervals(out, original):
        """Every surviving INTERVAL must be a function argument (`..., INTERVAL n UNIT)`).

        A leftover `x + INTERVAL n MONTH` is the DuckDB spelling and is invalid BigQuery.
        """
        for m in re.finditer(r"\bINTERVAL\b", out, re.I):
            j = m.start() - 1
            while j >= 0 and out[j].isspace():
                j -= 1
            if j < 0 or out[j] != ",":
                raise DialectError(
                    f"cannot translate to BigQuery (INTERVAL used as an operand; BigQuery "
                    f"needs DATE_ADD/TIMESTAMP_ADD): {original!r}")

    def _expr(self, s):
        """Recursive translation. Returns (sql, type|None)."""
        s = s.strip()
        iv = self._split_interval(s)
        if iv:
            lhs, sign, n, unit = iv
            base, base_t = self._expr(lhs)
            return self._interval(base, base_t, sign, n, unit)
        m = _DATE_TRUNC_CALL.match(s)
        if m:
            close = _match_paren(s, m.end() - 1)
            if close == len(s) - 1:                       # the whole expression is the call
                return self._trunc_call(s[m.end():close])
        return self._rewrite_calls(s), self._type_of(s)

    def _type_of(self, s):
        """Type of a leaf expression, if we can know it. Bare columns only."""
        key = s.strip().lower()
        if key in self.column_types:
            return self.column_types[key]
        if re.fullmatch(r"[A-Za-z_][\w]*\.[A-Za-z_][\w]*", key):
            return None   # an unannotated column: unknown, treated as TIMESTAMP downstream
        return None

    def _rewrite_calls(self, s):
        """Rewrite every embedded date_trunc(...) call, leaving the rest of `s` alone."""
        out, i, n = [], 0, len(s)
        while i < n:
            c = s[i]
            if c in _QUOTES:
                j = _skip_quoted(s, i)
                out.append(s[i:j])
                i = j
                continue
            m = _DATE_TRUNC_CALL.match(s, i)
            if m and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")):
                close = _match_paren(s, m.end() - 1)
                out.append(self._trunc_call(s[m.end():close])[0])
                i = close + 1
                continue
            out.append(c)
            i += 1
        return "".join(out)

    def _trunc_call(self, inner):
        args = _split_args(inner)
        if len(args) != 2:
            raise DialectError(f"date_trunc() needs 2 arguments, got {len(args)}: {inner!r}")
        unit = _unquote(args[0]).strip().upper()
        if unit.endswith("S"):
            unit = unit[:-1]
        if unit not in _BQ_TRUNC_UNITS:
            raise DialectError(f"BigQuery has no truncation part '{unit}'")
        val, vtyp = self._expr(args[1])
        if vtyp == "DATE":
            return f"DATE_TRUNC({val}, {unit})", "DATE"
        if vtyp == "DATETIME":
            return f"DATETIME_TRUNC({val}, {unit})", "DATETIME"
        # unknown or TIMESTAMP: this benchmark's date columns are TIMESTAMP
        return f"TIMESTAMP_TRUNC({val}, {unit})", "TIMESTAMP"

    @staticmethod
    def _split_interval(s):
        """Detect `<expr> +/- INTERVAL n UNIT` at top level -> (lhs, sign, n, unit)."""
        hits = _find_keyword(s, "INTERVAL")
        if not hits:
            return None
        i = hits[0]
        m = _INTERVAL_TAIL.match(s[i:])
        if not m:
            raise DialectError(f"unsupported INTERVAL expression: {s!r}")
        j = i - 1
        while j >= 0 and s[j].isspace():
            j -= 1
        if j < 0 or s[j] not in "+-":
            raise DialectError(f"INTERVAL without a +/- operand: {s!r}")
        n = m.group("qn") or m.group("sn") or m.group("pn")
        unit = (m.group("qu") or m.group("su") or m.group("pu")).upper().rstrip("S")
        return s[:j].strip(), s[j], n, unit

    @staticmethod
    def _interval(base, base_t, sign, n, unit):
        if unit in _BQ_TS_INTERVAL_UNITS and base_t in (None, "TIMESTAMP"):
            fn = "TIMESTAMP_ADD" if sign == "+" else "TIMESTAMP_SUB"
            return f"{fn}({base}, INTERVAL {n} {unit})", "TIMESTAMP"
        if unit in _BQ_DATE_INTERVAL_UNITS:
            # BigQuery cannot add MONTH/QUARTER/YEAR to a TIMESTAMP at all; go via DATE.
            # This drops time-of-day, which is exactly what a month/year truncation wants.
            b = base if base_t == "DATE" else f"DATE({base})"
            fn = "DATE_ADD" if sign == "+" else "DATE_SUB"
            return f"{fn}({b}, INTERVAL {n} {unit})", "DATE"
        raise DialectError(f"BigQuery cannot add INTERVAL {n} {unit} to a {base_t or 'TIMESTAMP'}")


# --------------------------------------------------------------------------------------
def get_dialect(spec=None):
    """'duckdb' (or None) -> DUCKDB; 'bigquery:<project>.<dataset>' -> BigQueryDialect."""
    if spec is None or str(spec).strip().lower() in ("", "duckdb"):
        return DUCKDB
    s = str(spec).strip()
    if s.lower().startswith("bigquery:"):
        target = s.split(":", 1)[1]
        parts = target.split(".")
        if len(parts) != 2:
            raise DialectError("bigquery dialect spec must be 'bigquery:<project>.<dataset>'")
        return BigQueryDialect(parts[0], parts[1])
    raise DialectError(f"unknown dialect spec: {spec!r}")
