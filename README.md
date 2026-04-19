# dbt-graphql

Turn a dbt project into a typed GraphQL schema, a SQL-backed GraphQL API, and an MCP surface for LLM agents.

dbt-graphql reads `catalog.json` and `manifest.json`, projects them into a GraphQL SDL enriched with custom directives (database/schema/table, SQL types, primary keys, unique constraints, foreign-key relationships), and provides a compiler that turns GraphQL queries into warehouse SQL. It also exposes an MCP server so AI agents can discover the schema, find join paths, build queries, and execute them — grounded in the same dbt artifacts your analytics team already maintains.

## Features

- **Generate** `db.graphql` + `lineage.json` from dbt artifacts
- **Serve** a read-only GraphQL API over your warehouse (FastAPI + Ariadne + SQLAlchemy)
- **MCP server** for LLM agents with schema discovery, join-path search, query build, and execution tools
- **Multi-warehouse**: DuckDB, PostgreSQL, MySQL/MariaDB, SQLite (anything with an async SQLAlchemy driver)
- **Lineage-aware**: table and column lineage surfaced alongside the schema

## Installation

```bash
pip install dbt-graphql                 # generate only
pip install dbt-graphql[api]            # + GraphQL API server
pip install dbt-graphql[mcp]            # + MCP server
pip install dbt-graphql[duckdb]         # warehouse drivers
pip install dbt-graphql[postgres]
pip install dbt-graphql[mysql]
pip install dbt-graphql[sqlite]
```

## Quick start

### 1. Generate schema

```bash
dbt-graphql generate \
  --format graphql \
  --catalog target/catalog.json \
  --manifest target/manifest.json \
  --output output/
```

Produces `output/db.graphql` and `output/lineage.json`.

### 2. Serve GraphQL API

```bash
dbt-graphql serve \
  --db-graphql output/db.graphql \
  --db-url duckdb+duckdb:///jaffle_shop.duckdb
```

Playground at `http://localhost:8080/graphql`.

### 3. Start the MCP server

```bash
dbt-graphql mcp \
  --catalog target/catalog.json \
  --manifest target/manifest.json \
  --db-url duckdb+duckdb:///jaffle_shop.duckdb
```

Starts an MCP stdio server for Claude Desktop, Cline, and other MCP clients.

## Commands

### `generate`

```
dbt-graphql generate --format graphql --catalog PATH --manifest PATH [--output DIR] [--exclude PATTERN]
```

| Flag         | Description                                                                 |
|--------------|-----------------------------------------------------------------------------|
| `--format`   | Output format (`graphql`)                                                   |
| `--catalog`  | Path to `catalog.json` (from `dbt docs generate`)                           |
| `--manifest` | Path to `manifest.json` (from `dbt compile` or `dbt run`)                   |
| `--output`   | Output directory (default: current directory)                               |
| `--exclude`  | Regex pattern to exclude models; may be repeated                            |

### `serve`

```
dbt-graphql serve --db-graphql PATH --db-url URL [--host HOST] [--port PORT]
```

| Flag           | Description                                                       |
|----------------|-------------------------------------------------------------------|
| `--db-graphql` | Path to `db.graphql` SDL file                                     |
| `--db-url`     | SQLAlchemy async URL (e.g. `postgresql+asyncpg://user:pw@host/db`) |
| `--db-config`  | Path to `db.yml` config (alternative to `--db-url`)                |
| `--host`       | Bind host (default: `0.0.0.0`)                                     |
| `--port`       | Bind port (default: `8080`)                                        |

### `mcp`

```
dbt-graphql mcp --catalog PATH --manifest PATH [--db-url URL] [--exclude PATTERN]
```

| Flag         | Description                                                    |
|--------------|----------------------------------------------------------------|
| `--catalog`  | Path to `catalog.json`                                         |
| `--manifest` | Path to `manifest.json`                                        |
| `--db-url`   | SQLAlchemy async URL for live execution (optional)             |
| `--exclude`  | Regex pattern to exclude models                                |

## A taste of the generated schema

```graphql
type orders @database(name: mydb) @schema(name: public) @table(name: orders) {
  order_id: Integer! @sql(type: "INTEGER") @id
  customer_id: Integer! @sql(type: "INTEGER") @relation(type: customers, field: customer_id)
  status: Varchar @sql(type: "VARCHAR")
  amount: Numeric @sql(type: "NUMERIC", size: "10,2")
}
```

Column types render as PascalCase GraphQL names (`INTEGER` → `Integer`, `TIMESTAMP WITH TIME ZONE` → `TimestampWithTimeZone`), with the exact SQL type preserved in an `@sql` directive so the compiler can emit warehouse-correct SQL.

## Documentation

- [**Architecture & Design**](docs/architecture.md) — pipeline flow, component-by-component deep dive, and the design rationale behind them.
- [**Landscape & Comparison**](docs/comparison.md) — how dbt-graphql relates to Cube, Wren, Malloy, Hasura, PostGraphile, pg_graphql, and agent-side text-to-SQL; an honest strengths/gaps assessment.
- [**Roadmap**](ROADMAP.md) — planned features (dbt selector support, source node inclusion, …).

## Development

```bash
uv sync --all-extras --all-groups           # install
uv run pytest tests/ -v                     # tests
uv run ruff check --fix && uv run ruff format
```

## License

MIT.
