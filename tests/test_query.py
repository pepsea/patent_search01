from datetime import date
from pathlib import Path
import sys

import pytest


# Support both ``pytest`` and ``python tests/test_query.py``.  Python places
# only the tests directory on sys.path when a test module is run directly.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from patent_search.query import SearchOptions, build_query


def test_build_query_includes_requested_filters_and_parameters():
    sql, parameters = build_query(SearchOptions("battery", ("JP", "US"), ("H01M",), "Acme", "Ada", date(2020, 1, 1), date(2021, 1, 1), 25))

    assert "FROM `patents-public-data.patents.publications`" in sql
    assert "CONTAINS_SUBSTR" in sql
    assert "country_code IN UNNEST(@countries)" in sql
    assert "STARTS_WITH(code.code, prefix)" in sql
    assert "LIMIT @limit" in sql
    assert {item["name"] for item in parameters} == {"query", "countries", "cpcs", "assignee", "inventor", "filed_from", "filed_to", "limit"}


@pytest.mark.parametrize("limit", [0, 10001])
def test_build_query_rejects_unsafe_limits(limit):
    with pytest.raises(ValueError, match="limit"):
        build_query(SearchOptions(limit=limit))
