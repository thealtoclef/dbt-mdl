"""Tests for SchemaDiscovery (no live DB required)."""

from pathlib import Path

from dbt_graphql.pipeline import extract_project
from dbt_graphql.mcp.discovery import SchemaDiscovery


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "dbt-artifacts"
CATALOG = FIXTURES_DIR / "catalog.json"
MANIFEST = FIXTURES_DIR / "manifest.json"


def _make_discovery():
    project = extract_project(CATALOG, MANIFEST)
    return SchemaDiscovery(project)


class TestListTables:
    def test_returns_all_tables(self):
        d = _make_discovery()
        tables = d.list_tables()
        names = {t.name for t in tables}
        assert "customers" in names
        assert "orders" in names

    def test_table_has_column_count(self):
        d = _make_discovery()
        tables = d.list_tables()
        customers = next(t for t in tables if t.name == "customers")
        assert customers.column_count > 0


class TestDescribeTable:
    def test_returns_columns(self):
        d = _make_discovery()
        detail = d.describe_table("customers")
        assert detail is not None
        col_names = {c.name for c in detail.columns}
        assert "customer_id" in col_names

    def test_missing_table_returns_none(self):
        d = _make_discovery()
        assert d.describe_table("nonexistent") is None


class TestFindPath:
    def test_finds_direct_path(self):
        d = _make_discovery()
        paths = d.find_path("orders", "customers")
        assert len(paths) > 0
        assert paths[0].length == 1

    def test_same_table_returns_empty_path(self):
        d = _make_discovery()
        paths = d.find_path("orders", "orders")
        assert len(paths) == 1
        assert paths[0].length == 0

    def test_no_path_returns_empty(self):
        d = _make_discovery()
        paths = d.find_path("customers", "stg_orders")
        assert len(paths) == 0


class TestExploreRelationships:
    def test_orders_has_related_customers(self):
        d = _make_discovery()
        related = d.explore_relationships("orders")
        names = {r.name for r in related}
        assert "customers" in names

    def test_direction_outgoing(self):
        d = _make_discovery()
        related = d.explore_relationships("orders")
        customers_rel = next((r for r in related if r.name == "customers"), None)
        assert customers_rel is not None
        assert customers_rel.direction in ("outgoing", "incoming")
