"""Tests for GraphJin config generation."""

from pathlib import Path

import yaml

from dbt_mdl import extract_project, format_graphjin


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _make_dbt_project(tmp_path):
    """Create a minimal dbt project layout."""
    import shutil

    (tmp_path / "target").mkdir()
    shutil.copy(FIXTURES_DIR / "catalog.json", tmp_path / "target" / "catalog.json")
    shutil.copy(FIXTURES_DIR / "manifest.json", tmp_path / "target" / "manifest.json")
    shutil.copy(FIXTURES_DIR / "profiles.yml", tmp_path / "profiles.yml")
    return tmp_path


class TestDevYml:
    def test_is_valid_yaml(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        assert isinstance(yaml.safe_load(gj.dev_yml), dict)

    def test_has_database_block(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        data = yaml.safe_load(gj.dev_yml)
        assert "database" in data
        assert data["database"]["type"] in (
            "postgres",
            "mysql",
            "mariadb",
            "sqlite",
            "oracle",
            "snowflake",
            "mssql",
        )

    def test_has_enable_schema(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        data = yaml.safe_load(gj.dev_yml)
        assert data.get("enable_schema") is True

    def test_has_auth_block(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        data = yaml.safe_load(gj.dev_yml)
        assert data.get("auth", {}).get("type") == "none"

    def test_default_block_is_false(self, tmp_path):
        """Without roles, default_block: true would lock out all queries."""
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        data = yaml.safe_load(gj.dev_yml)
        assert data.get("default_block") is False

    def test_tables_only_when_meaningful(self, tmp_path):
        """We don't emit redundant `name: X / table: X` aliases."""
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        data = yaml.safe_load(gj.dev_yml)
        tables = data.get("tables") or []
        for entry in tables:
            assert "columns" in entry or entry.get("table") != entry.get("name")

    def test_relationships_in_tables_columns(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        data = yaml.safe_load(gj.dev_yml)
        tables = {t["name"]: t for t in (data.get("tables") or [])}
        orders = tables.get("orders")
        assert orders is not None
        rel_cols = orders.get("columns") or []
        assert any(
            c["name"] == "customer_id"
            and c.get("related_to", "").startswith("customers.")
            for c in rel_cols
        )


class TestDbGraphQL:
    def test_has_dbinfo_header(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        first_line = gj.db_graphql.splitlines()[0]
        assert first_line.startswith("# dbinfo:")

    def test_has_types(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        assert "type customers" in gj.db_graphql
        assert "type orders" in gj.db_graphql

    def test_has_relation_directive(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        assert "@relation(type: customers, field: customer_id)" in gj.db_graphql

    def test_required_fields_have_bang(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        assert "Integer!" in gj.db_graphql or "BigInt!" in gj.db_graphql

    def test_all_models_present(self, tmp_path):
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        for model in project.models:
            assert f"type {model.name}" in gj.db_graphql

    def test_non_public_schema_directive(self, tmp_path):
        """Fixture uses duckdb 'main' schema — should emit @schema(name: main)."""
        project = extract_project(_make_dbt_project(tmp_path))
        gj = format_graphjin(project)
        if any(m.schema_ and m.schema_ != "public" for m in project.models):
            assert "@schema(name:" in gj.db_graphql

    def test_exclude_patterns(self, tmp_path):
        project = extract_project(
            _make_dbt_project(tmp_path), exclude_patterns=[r"^stg_"]
        )
        gj = format_graphjin(project)
        assert "type stg_orders" not in gj.db_graphql
        assert "type customers" in gj.db_graphql


class TestTypeMapping:
    def test_sql_to_gql_known_types(self):
        from dbt_mdl.graphjin.formatter import _sql_to_gql_type

        assert _sql_to_gql_type("INTEGER") == ("Integer", "")
        assert _sql_to_gql_type("BIGINT") == ("BigInt", "")
        assert _sql_to_gql_type("SMALLINT") == ("SmallInt", "")
        assert _sql_to_gql_type("VARCHAR") == ("Varchar", "")
        assert _sql_to_gql_type("TEXT") == ("Text", "")
        assert _sql_to_gql_type("BOOLEAN") == ("Boolean", "")
        assert _sql_to_gql_type("DATE") == ("Date", "")
        assert _sql_to_gql_type("TIMESTAMP") == ("Timestamp", "")
        assert _sql_to_gql_type("JSONB") == ("Jsonb", "")
        assert _sql_to_gql_type("UUID") == ("Uuid", "")

    def test_size_is_extracted(self):
        from dbt_mdl.graphjin.formatter import _sql_to_gql_type

        assert _sql_to_gql_type("VARCHAR(255)") == ("Varchar", "255")
        assert _sql_to_gql_type("NUMERIC(10,2)") == ("Numeric", "10,2")

    def test_multiword_types(self):
        from dbt_mdl.graphjin.formatter import _sql_to_gql_type

        assert _sql_to_gql_type("TIMESTAMP WITH TIME ZONE") == (
            "TimestampWithTimeZone",
            "",
        )
        assert _sql_to_gql_type("CHARACTER VARYING") == ("CharacterVarying", "")
        assert _sql_to_gql_type("DOUBLE PRECISION") == ("DoublePrecision", "")

    def test_bigquery_aliases(self):
        from dbt_mdl.graphjin.formatter import _sql_to_gql_type

        assert _sql_to_gql_type("INT64") == ("BigInt", "")
        assert _sql_to_gql_type("FLOAT64") == ("DoublePrecision", "")

    def test_array_detection(self):
        from dbt_mdl.graphjin.formatter import _parse_sql_type

        assert _parse_sql_type("INTEGER[]") == ("integer", "", True)
        assert _parse_sql_type("TEXT[]") == ("text", "", True)
        assert _parse_sql_type("ARRAY<STRING>") == ("string", "", True)

    def test_array_renders_as_list(self, tmp_path):
        """Confirm [Type] GraphQL list syntax when a column is an array."""
        from dbt_mdl.graphjin.formatter import _column_line
        from dbt_mdl.domain.models import ColumnInfo, ModelInfo

        m = ModelInfo(name="t", table_name="t", columns=[])
        c = ColumnInfo(name="tags", type="TEXT[]", not_null=False)
        line = _column_line(m, c, rel_map={})
        assert "[Text]" in line


class TestNoRelationships:
    def test_no_relationships_still_works(self, tmp_path):
        import json
        import shutil

        data = json.loads((FIXTURES_DIR / "manifest.json").read_text())
        keys_to_remove = [
            k for k in data["nodes"] if k.startswith("test.") and "relationships" in k
        ]
        for k in keys_to_remove:
            del data["nodes"][k]

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "target").mkdir()
        (project_dir / "target" / "manifest.json").write_text(json.dumps(data))
        shutil.copy(
            FIXTURES_DIR / "catalog.json", project_dir / "target" / "catalog.json"
        )
        shutil.copy(FIXTURES_DIR / "profiles.yml", project_dir / "profiles.yml")

        project = extract_project(project_dir)
        assert len(project.relationships) == 0

        gj = format_graphjin(project)
        assert "@relation" not in gj.db_graphql
        assert isinstance(yaml.safe_load(gj.dev_yml), dict)
