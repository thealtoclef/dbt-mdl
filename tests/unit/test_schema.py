"""Tests for the SDL parser (schema.py)."""

from dbt_graphql.formatter.schema import parse_db_graphql


SDL = """\
type customers @database(name: mydb) @schema(name: main) @table(name: customers) {
  customer_id: Integer! @sql(type: "INTEGER") @unique
  first_name: Varchar @sql(type: "VARCHAR")
  last_name: Varchar @sql(type: "VARCHAR")
}

type orders @database(name: mydb) @schema(name: main) @table(name: orders) {
  order_id: Integer! @sql(type: "INTEGER") @id
  customer_id: Integer! @sql(type: "INTEGER") @relation(type: customers, field: customer_id)
  order_date: Date @sql(type: "DATE")
  status: Varchar @sql(type: "VARCHAR")
  tags: [Text] @sql(type: "TEXT[]")
  amount: Varchar @sql(type: "VARCHAR", size: "255")
}

type payments @database(name: mydb) @schema(name: main) @table(name: payments) {
  payment_id: Integer! @sql(type: "INTEGER")
  secret: Text @sql(type: "TEXT")
}
"""


def _parse():
    return parse_db_graphql(SDL)


class TestTableParsing:
    def test_all_tables_present(self):
        info, _ = _parse()
        names = [t.name for t in info.tables]
        assert names == ["customers", "orders", "payments"]

    def test_database_directive(self):
        info, _ = _parse()
        assert info.tables[0].database == "mydb"

    def test_schema_directive(self):
        info, _ = _parse()
        assert info.tables[0].schema == "main"

    def test_table_directive(self):
        info, _ = _parse()
        assert info.tables[0].table == "customers"

    def test_table_defaults_to_name(self):
        """If @table is missing, table name defaults to the type name."""
        sdl = "type foo @database(name: db) @schema(name: public) { id: Integer }"
        info, _ = parse_db_graphql(sdl)
        assert info.tables[0].table == "foo"


class TestColumnParsing:
    def test_not_null(self):
        info, _ = _parse()
        col = next(c for c in info.tables[0].columns if c.name == "customer_id")
        assert col.not_null is True

    def test_nullable(self):
        info, _ = _parse()
        col = next(c for c in info.tables[0].columns if c.name == "first_name")
        assert col.not_null is False

    def test_gql_type(self):
        info, _ = _parse()
        col = next(c for c in info.tables[0].columns if c.name == "customer_id")
        assert col.gql_type == "Integer"

    def test_array_type(self):
        info, _ = _parse()
        col = next(c for c in info.tables[1].columns if c.name == "tags")
        assert col.is_array is True
        assert col.gql_type == "Text"

    def test_sql_type_directive(self):
        info, _ = _parse()
        col = next(c for c in info.tables[1].columns if c.name == "amount")
        assert col.sql_type == "VARCHAR"
        assert col.sql_size == "255"


class TestDirectives:
    def test_id_directive(self):
        info, _ = _parse()
        col = next(c for c in info.tables[1].columns if c.name == "order_id")
        assert col.is_pk is True

    def test_unique_directive(self):
        info, _ = _parse()
        col = next(c for c in info.tables[0].columns if c.name == "customer_id")
        assert col.is_unique is True

    def test_relation_directive(self):
        info, _ = _parse()
        col = next(c for c in info.tables[1].columns if c.name == "customer_id")
        assert col.relation is not None
        assert col.relation.target_model == "customers"
        assert col.relation.target_column == "customer_id"


class TestRegistry:
    def test_get_existing(self):
        _, reg = _parse()
        assert reg.get("customers") is not None
        assert reg["customers"].name == "customers"

    def test_get_missing(self):
        _, reg = _parse()
        assert reg.get("nonexistent") is None

    def test_contains(self):
        _, reg = _parse()
        assert "orders" in reg
        assert "missing" not in reg

    def test_len(self):
        _, reg = _parse()
        assert len(reg) == 3

    def test_iter(self):
        _, reg = _parse()
        names = [t.name for t in reg]
        assert names == ["customers", "orders", "payments"]
