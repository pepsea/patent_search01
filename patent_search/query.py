"""Safe, parameterised SQL for the Google Patents public BigQuery dataset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

TABLE = "`patents-public-data.patents.publications`"


@dataclass(frozen=True)
class SearchOptions:
    query: str | None = None
    countries: tuple[str, ...] = ()
    cpcs: tuple[str, ...] = ()
    assignee: str | None = None
    inventor: str | None = None
    filed_from: date | None = None
    filed_to: date | None = None
    limit: int = 100


def build_query(options: SearchOptions) -> tuple[str, list[dict[str, Any]]]:
    """Return Standard SQL and named parameter definitions for *options*."""
    if not 1 <= options.limit <= 10_000:
        raise ValueError("limit must be between 1 and 10000")

    where: list[str] = ["publication_number IS NOT NULL"]
    params: list[dict[str, Any]] = [{"name": "limit", "type": "INT64", "value": options.limit}]

    def add(name: str, sql: str, value: Any, type_: str = "STRING") -> None:
        where.append(sql)
        params.append({"name": name, "type": type_, "value": value})

    if options.query:
        add("query", """EXISTS (
  SELECT 1 FROM UNNEST(ARRAY_CONCAT(title_localized, abstract_localized, claims_localized)) AS text
  WHERE text.language = 'en' AND CONTAINS_SUBSTR(LOWER(text.text), LOWER(@query))
)""", options.query)
    if options.countries:
        add("countries", "country_code IN UNNEST(@countries)", list(options.countries), "ARRAY<STRING>")
    if options.cpcs:
        add("cpcs", "EXISTS (SELECT 1 FROM UNNEST(cpc) AS code WHERE EXISTS (SELECT 1 FROM UNNEST(@cpcs) AS prefix WHERE STARTS_WITH(code.code, prefix)))", list(options.cpcs), "ARRAY<STRING>")
    if options.assignee:
        add("assignee", "EXISTS (SELECT 1 FROM UNNEST(assignee_harmonized) AS a WHERE CONTAINS_SUBSTR(LOWER(a.name), LOWER(@assignee)))", options.assignee)
    if options.inventor:
        add("inventor", "EXISTS (SELECT 1 FROM UNNEST(inventor_harmonized) AS i WHERE CONTAINS_SUBSTR(LOWER(i.name), LOWER(@inventor)))", options.inventor)
    if options.filed_from:
        add("filed_from", "filing_date >= @filed_from", options.filed_from.isoformat(), "DATE")
    if options.filed_to:
        add("filed_to", "filing_date <= @filed_to", options.filed_to.isoformat(), "DATE")

    sql = f"""SELECT
  publication_number, country_code, kind_code, family_id, filing_date, priority_date, publication_date, grant_date,
  (SELECT text FROM UNNEST(title_localized) WHERE language = 'en' LIMIT 1) AS title,
  ARRAY(SELECT DISTINCT a.name FROM UNNEST(assignee_harmonized) a WHERE a.name IS NOT NULL) AS assignees,
  ARRAY(SELECT DISTINCT i.name FROM UNNEST(inventor_harmonized) i WHERE i.name IS NOT NULL) AS inventors,
  ARRAY(SELECT DISTINCT code.code FROM UNNEST(cpc) code WHERE code.code IS NOT NULL) AS cpc_codes
FROM {TABLE}
WHERE {' AND '.join(where)}
ORDER BY publication_date DESC
LIMIT @limit"""
    return sql, params
