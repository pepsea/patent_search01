"""Command-line entry point for controlled patent-public-data searches."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .query import SearchOptions, build_query


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("use ISO date YYYY-MM-DD") from error


def arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search Google Patents public data through BigQuery.")
    parser.add_argument("--project", required=True, help="Google Cloud project that runs the query job")
    parser.add_argument("--query", help="English text to find in title, abstract, or claims")
    parser.add_argument("--country", action="append", default=[], help="Publication country code (repeatable, e.g. JP)")
    parser.add_argument("--cpc", action="append", default=[], help="CPC prefix (repeatable; e.g. H01M)")
    parser.add_argument("--assignee")
    parser.add_argument("--inventor")
    parser.add_argument("--from", dest="filed_from", type=parse_date, help="Earliest filing date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="filed_to", type=parse_date, help="Latest filing date (YYYY-MM-DD)")
    parser.add_argument("--max-results", type=int, default=100)
    parser.add_argument("--max-bytes", type=int, default=1_000_000_000, help="Hard BigQuery scan cap; default 1 GB")
    parser.add_argument("--output", type=Path, default=Path("results/patents.csv"))
    parser.add_argument("--execute", action="store_true", help="Run the query; without this flag only dry-run it")
    return parser


def bq_parameters(definitions: list[dict[str, Any]]) -> list[Any]:
    from google.cloud import bigquery

    parameters = []
    for item in definitions:
        if item["type"].startswith("ARRAY<"):
            parameters.append(bigquery.ArrayQueryParameter(item["name"], item["type"][6:-1], item["value"]))
        else:
            parameters.append(bigquery.ScalarQueryParameter(item["name"], item["type"], item["value"]))
    return parameters


def run(args: argparse.Namespace) -> int:
    from google.cloud import bigquery

    options = SearchOptions(args.query, tuple(code.upper() for code in args.country), tuple(args.cpc), args.assignee,
                            args.inventor, args.filed_from, args.filed_to, args.max_results)
    sql, parameter_definitions = build_query(options)
    client = bigquery.Client(project=args.project)
    config = bigquery.QueryJobConfig(query_parameters=bq_parameters(parameter_definitions), maximum_bytes_billed=args.max_bytes)
    dry_config = bigquery.QueryJobConfig(query_parameters=bq_parameters(parameter_definitions), dry_run=True, use_query_cache=False)
    estimate = client.query(sql, job_config=dry_config).total_bytes_processed
    print(f"Estimated bytes processed: {estimate:,}")
    if not args.execute:
        print("Dry run complete. Pass --execute to run and write CSV.")
        return 0
    if estimate > args.max_bytes:
        raise RuntimeError(f"Estimated {estimate:,} bytes exceeds --max-bytes {args.max_bytes:,}; query not run.")
    rows = client.query(sql, job_config=config).result()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["publication_number", "country_code", "kind_code", "family_id", "filing_date", "priority_date", "publication_date", "grant_date", "title", "assignees", "inventors", "cpc_codes", "google_patents_url"]
    with args.output.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            record = dict(row.items())
            record.update({key: "; ".join(value or []) for key, value in record.items() if key in {"assignees", "inventors", "cpc_codes"}})
            record["google_patents_url"] = f"https://patents.google.com/patent/{record['publication_number']}"
            writer.writerow(record)
    metadata = {"created_at": datetime.now(timezone.utc).isoformat(), "project": args.project, "estimated_bytes": estimate, "parameters": parameter_definitions, "sql": sql}
    args.output.with_suffix(args.output.suffix + ".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(arguments().parse_args()))
