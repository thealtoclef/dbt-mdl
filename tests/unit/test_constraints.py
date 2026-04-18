"""Tests for dbt constraint extraction (primary keys, foreign keys)."""

from dbt_graphql.dbt.processors.constraints import (
    _parse_fk_expression,
    extract_constraints,
)
from dbt_graphql.ir.models import JoinType, ProcessorRelationship


# ---------------------------------------------------------------------------
# _parse_fk_expression
# ---------------------------------------------------------------------------


class TestParseFkExpression:
    def test_simple_table_column(self):
        result = _parse_fk_expression("customers(customer_id)")
        assert result == ("customers", "customer_id")

    def test_schema_qualified(self):
        result = _parse_fk_expression("public.customers(customer_id)")
        assert result == ("customers", "customer_id")

    def test_catalog_schema_qualified(self):
        result = _parse_fk_expression("mydb.public.customers(customer_id)")
        assert result == ("customers", "customer_id")

    def test_strips_double_quotes(self):
        result = _parse_fk_expression('"customers"("customer_id")')
        assert result == ("customers", "customer_id")

    def test_strips_backtick_quotes(self):
        result = _parse_fk_expression("`customers`(`customer_id`)")
        assert result == ("customers", "customer_id")

    def test_whitespace_trimmed(self):
        result = _parse_fk_expression("  customers( customer_id )  ")
        assert result == ("customers", "customer_id")

    def test_invalid_no_parens_returns_none(self):
        assert _parse_fk_expression("customers") is None

    def test_invalid_empty_returns_none(self):
        assert _parse_fk_expression("") is None

    def test_invalid_only_parens_returns_none(self):
        assert _parse_fk_expression("()") is None


# ---------------------------------------------------------------------------
# extract_constraints — helpers
# ---------------------------------------------------------------------------


class _FakeNode:
    def __init__(self, constraints=None, columns=None):
        self.constraints = constraints or []
        self.columns = columns or {}


class _FakeManifest:
    def __init__(self, nodes):
        self.nodes = nodes


def _manifest_with(**nodes):
    return _FakeManifest(nodes)


# ---------------------------------------------------------------------------
# extract_constraints
# ---------------------------------------------------------------------------


class TestExtractConstraints:
    def test_empty_manifest_returns_empty(self):
        manifest = _manifest_with()
        result = extract_constraints(manifest)
        assert result.primary_keys == {}
        assert result.foreign_key_relationships == []

    def test_non_model_nodes_ignored(self):
        manifest = _manifest_with(
            **{
                "test.project.some_test": _FakeNode(
                    constraints=[{"type": "primary_key", "columns": ["id"]}]
                )
            }
        )
        result = extract_constraints(manifest)
        assert result.primary_keys == {}

    def test_model_level_primary_key(self):
        uid = "model.project.orders"
        manifest = _manifest_with(
            **{
                uid: _FakeNode(
                    constraints=[{"type": "primary_key", "columns": ["order_id"]}]
                )
            }
        )
        result = extract_constraints(manifest)
        assert result.primary_keys[uid] == "order_id"

    def test_column_level_primary_key(self):
        uid = "model.project.orders"
        manifest = _manifest_with(
            **{
                uid: _FakeNode(
                    columns={
                        "order_id": {
                            "constraints": [{"type": "primary_key"}]
                        }
                    }
                )
            }
        )
        result = extract_constraints(manifest)
        assert result.primary_keys[uid] == "order_id"

    def test_model_level_pk_takes_precedence_over_column_level(self):
        uid = "model.project.orders"
        manifest = _manifest_with(
            **{
                uid: _FakeNode(
                    constraints=[{"type": "primary_key", "columns": ["order_id"]}],
                    columns={
                        "another_id": {"constraints": [{"type": "primary_key"}]}
                    },
                )
            }
        )
        result = extract_constraints(manifest)
        assert result.primary_keys[uid] == "order_id"

    def test_model_level_foreign_key(self):
        uid = "model.project.orders"
        manifest = _manifest_with(
            **{
                uid: _FakeNode(
                    constraints=[
                        {
                            "type": "foreign_key",
                            "columns": ["customer_id"],
                            "expression": "customers(customer_id)",
                        }
                    ]
                )
            }
        )
        result = extract_constraints(manifest)
        assert len(result.foreign_key_relationships) == 1
        rel = result.foreign_key_relationships[0]
        assert isinstance(rel, ProcessorRelationship)
        assert rel.models == ["orders", "customers"]
        assert rel.join_type == JoinType.many_to_one
        assert '"orders"."customer_id" = "customers"."customer_id"' in rel.condition

    def test_column_level_foreign_key(self):
        uid = "model.project.orders"
        manifest = _manifest_with(
            **{
                uid: _FakeNode(
                    columns={
                        "customer_id": {
                            "constraints": [
                                {
                                    "type": "foreign_key",
                                    "expression": "customers(id)",
                                }
                            ]
                        }
                    }
                )
            }
        )
        result = extract_constraints(manifest)
        assert len(result.foreign_key_relationships) == 1
        rel = result.foreign_key_relationships[0]
        assert rel.models == ["orders", "customers"]
        assert '"orders"."customer_id" = "customers"."id"' in rel.condition

    def test_duplicate_fk_deduplicated(self):
        uid = "model.project.orders"
        manifest = _manifest_with(
            **{
                uid: _FakeNode(
                    constraints=[
                        {
                            "type": "foreign_key",
                            "columns": ["customer_id"],
                            "expression": "customers(customer_id)",
                        },
                        {
                            "type": "foreign_key",
                            "columns": ["customer_id"],
                            "expression": "customers(customer_id)",
                        },
                    ]
                )
            }
        )
        result = extract_constraints(manifest)
        assert len(result.foreign_key_relationships) == 1

    def test_invalid_fk_expression_skipped(self):
        uid = "model.project.orders"
        manifest = _manifest_with(
            **{
                uid: _FakeNode(
                    constraints=[
                        {
                            "type": "foreign_key",
                            "columns": ["customer_id"],
                            "expression": "not_valid_expression",
                        }
                    ]
                )
            }
        )
        result = extract_constraints(manifest)
        assert len(result.foreign_key_relationships) == 0

    def test_rel_name_built_from_parts(self):
        uid = "model.project.orders"
        manifest = _manifest_with(
            **{
                uid: _FakeNode(
                    constraints=[
                        {
                            "type": "foreign_key",
                            "columns": ["customer_id"],
                            "expression": "customers(customer_id)",
                        }
                    ]
                )
            }
        )
        result = extract_constraints(manifest)
        rel = result.foreign_key_relationships[0]
        assert rel.name == "orders_customer_id_customers_customer_id"
