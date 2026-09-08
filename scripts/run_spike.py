#!/usr/bin/env python3
"""Run scripts/bq_dialect_spike.sql probe-by-probe, without DML.

WHY THIS EXISTS
    bq_dialect_spike.sql is a multi-statement script that accumulates its findings with
    `INSERT INTO spike_results`. That INSERT is DML, and **DML is blocked on a project
    without a billing account** ("DML queries are not allowed in the free tier"), which is
    exactly the situation the spike is meant to be runnable in — it reads no tables and
    scans 0 bytes, so it otherwise costs nothing and needs no billing.

    Feeding the file to `bq query` also fails before it reaches BigQuery: the file's first
    line starts with `--`, which the bq CLI parses as a command-line flag. It has to be fed
    on stdin (`bq query ... < scripts/bq_dialect_spike.sql`), and even then the INSERT is
    what fails.

    So this runner takes the probe SQL straight out of the .sql file — the file stays the
    single source of truth for what each probe says — and submits each probe as its own
    ordinary SELECT, catching rejections client-side instead of in a SQL exception handler.
    Same evidence, no DML, no billing account required.

USAGE
    python scripts/run_spike.py --project $SEMBENCH_BQ_PROJECT
    python scripts/run_spike.py --project $SEMBENCH_BQ_PROJECT --json results.json
    python scripts/run_spike.py --project $SEMBENCH_BQ_PROJECT --markdown   # README table rows

    Add --time-zone America/Toronto to re-run every probe under a non-UTC session
    timezone. That is how the UTC assumption behind probes 2a/2b/3b/4b was measured; see
    README-spike.md, "The UTC assumption".
"""
import argparse
import json
import pathlib
import re
import sys

SPIKE = pathlib.Path(__file__).with_name("bq_dialect_spike.sql")

# Each probe in the .sql has the identical shape:
#     BEGIN
#       EXECUTE IMMEDIATE """<sql>""" INTO r;
#       INSERT INTO spike_results VALUES ('<id>', '<name>', 'RAN', r);
#     EXCEPTION WHEN ERROR THEN ...
# so the probe text and its id/name can be lifted out without parsing SQL.
_PROBE_RE = re.compile(
    r'BEGIN\s*\n\s*EXECUTE IMMEDIATE """(?P<sql>.*?)"""\s*INTO r;\s*\n\s*'
    r"INSERT INTO spike_results VALUES \('(?P<id>[^']+)', '(?P<name>(?:[^']|'')*)', 'RAN', r\);",
    re.S,
)


def extract_probes(path=SPIKE):
    """Return [(probe_id, name, sql)] in file order."""
    src = path.read_text()
    probes = [
        (m.group("id"), m.group("name").replace("''", "'"), m.group("sql").strip())
        for m in _PROBE_RE.finditer(src)
    ]
    if not probes:
        raise SystemExit(f"no probes found in {path} — has its layout changed?")
    return probes


def run(project, time_zone=None, path=SPIKE):
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    prefix = f"SET @@time_zone = '{time_zone}';\n" if time_zone else ""
    results = []
    for probe_id, name, sql in extract_probes(path):
        try:
            rows = list(client.query(prefix + sql).result())
            outcome = "RAN"
            detail = str(rows[0][0]) if rows else "<no rows>"
        except Exception as exc:                       # noqa: BLE001 — rejection IS the result
            outcome = "ERROR"
            # BigQuery messages are multi-line and carry a job id; flatten for one-line output.
            detail = " ".join(str(exc).split())
        results.append(
            {"probe": probe_id, "name": name, "outcome": outcome, "detail": detail}
        )
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", required=True, help="BigQuery project to bill/run against")
    ap.add_argument("--time-zone", default=None,
                    help="run every probe under this session timezone (default: server UTC)")
    ap.add_argument("--json", metavar="PATH", help="also write raw results as JSON")
    ap.add_argument("--markdown", action="store_true",
                    help="emit README-ready table rows instead of plain text")
    args = ap.parse_args(argv)

    results = run(args.project, args.time_zone)

    if args.markdown:
        print("| Probe | Result (`outcome` / `detail`) |")
        print("| --- | --- |")
        for r in results:
            detail = r["detail"].replace("|", "\\|")
            print(f"| {r['probe']} | `{r['outcome']}` — {detail} |")
    else:
        for r in results:
            print(f"{r['probe']:>3} | {r['outcome']:5} | {r['detail']}")

    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(results, indent=1))

    # A [SHIPPED] probe that BigQuery rejects is a hard blocker; make that scriptable.
    blockers = [r for r in results if r["outcome"] == "ERROR" and "[SHIPPED]" in r["name"]]
    if blockers:
        print(f"\nBLOCKER: {len(blockers)} [SHIPPED] probe(s) rejected: "
              f"{', '.join(b['probe'] for b in blockers)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
