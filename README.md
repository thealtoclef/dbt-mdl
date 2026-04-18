# dbt-graphql

Convert dbt artifacts into a GraphQL schema, serve a SQL-backed GraphQL API, and expose MCP tools for LLM agents.

## Overview

**dbt-graphql** reads your dbt `catalog.json` and `manifest.json` and produces:

- `db.graphql` — a GraphQL SDL schema describing your warehouse tables, columns, types, and relationships
- `lineage.json` — table and column-level lineage extracted from your dbt project
- A live **GraphQL API** (FastAPI + Ariadne) that compiles GraphQL queries into SQL and executes them
- An **MCP server** for LLM agents to discover your schema, find join paths, build queries, and execute them

## Installation

```bash
# Core (generate only)
pip install dbt-graphql

# With GraphQL API server
pip install dbt-graphql[api]

# With MCP server for LLM agents
pip install dbt-graphql[mcp]

# Database drivers
pip install dbt-graphql[duckdb]
pip install dbt-graphql[postgres]
pip install dbt-graphql[mysql]
pip install dbt-graphql[sqlite]
```

## Quick Start

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

GraphQL playground available at `http://localhost:8080/graphql`.

### 3. Start MCP server

```bash
dbt-graphql mcp \
  --catalog target/catalog.json \
  --manifest target/manifest.json \
  --db-url duckdb+duckdb:///jaffle_shop.duckdb
```

Starts an MCP stdio server for LLM agent integration.

## Commands

### `generate`

```
dbt-graphql generate --format graphql --catalog PATH --manifest PATH [--output DIR] [--exclude PATTERN]
```

| Flag | Description |
|------|-------------|
| `--format` | Output format (`graphql`) |
| `--catalog` | Path to `catalog.json` (from `dbt docs generate`) |
| `--manifest` | Path to `manifest.json` (from `dbt compile` or `dbt run`) |
| `--output` | Output directory (default: current directory) |
| `--exclude` | Regex pattern to exclude models; may be repeated |

### `serve`

```
dbt-graphql serve --db-graphql PATH --db-url URL [--host HOST] [--port PORT]
```

| Flag | Description |
|------|-------------|
| `--db-graphql` | Path to `db.graphql` SDL file |
| `--db-url` | SQLAlchemy async URL (e.g. `postgresql+asyncpg://user:pass@host/db`) |
| `--db-config` | Path to `db.yml` config file (alternative to `--db-url`) |
| `--host` | Bind host (default: `0.0.0.0`) |
| `--port` | Bind port (default: `8080`) |

### `mcp`

```
dbt-graphql mcp --catalog PATH --manifest PATH [--db-url URL] [--exclude PATTERN]
```

| Flag | Description |
|------|-------------|
| `--catalog` | Path to `catalog.json` |
| `--manifest` | Path to `manifest.json` |
| `--db-url` | SQLAlchemy async URL for live enrichment (optional) |
| `--exclude` | Regex pattern to exclude models |

## Architecture

```
dbt artifacts (catalog.json + manifest.json)
    │
    ▼
extract_project()           ← dbt/processors/
    │
    ▼
ProjectInfo IR              ← ir/models.py
    │
    ├──▶ formatter/         → db.graphql SDL
    │       graphql.py      ← type/column/directive formatting
    │       schema.py       ← SDL → TableRegistry parser
    │
    ├──▶ compiler/          → SQL queries
    │       query.py        ← GraphQL selection → SQLAlchemy SELECT
    │       connection.py   ← async engine + URL builder
    │
    ├──▶ serve/             → GraphQL API (Ariadne + FastAPI)
    │       app.py          ← FastAPI factory + granian runner
    │       resolvers.py    ← per-table Ariadne resolvers
    │
    └──▶ mcp/               → MCP tools for LLM agents
            discovery.py    ← SchemaDiscovery (list/describe/path/explore)
            server.py       ← fastmcp tool registration
```

## GraphQL Schema Format

Generated `db.graphql` uses type-level and field-level directives:

```graphql
type orders @database(name: mydb) @schema(name: public) @table(name: orders) {
  order_id: Integer! @sql(type: "INTEGER") @id
  customer_id: Integer! @sql(type: "INTEGER") @relation(type: customers, field: customer_id)
  status: Varchar @sql(type: "VARCHAR")
  amount: Numeric @sql(type: "NUMERIC", size: "10,2")
}
```

| Directive | Meaning |
|-----------|---------|
| `@database(name: ...)` | Warehouse database name |
| `@schema(name: ...)` | Warehouse schema name |
| `@table(name: ...)` | Physical table name (may differ from type name) |
| `@sql(type: "...", size: "...")` | Raw SQL type + size/precision |
| `@id` | Primary key column |
| `@unique` | Unique constraint |
| `@blocked` | Hidden from queries |
| `@relation(type: Model, field: col)` | Foreign key to another type |

Column types are emitted as PascalCase GraphQL-compatible names (`INTEGER` → `Integer`, `VARCHAR(255)` → `Varchar`, `TIMESTAMP WITH TIME ZONE` → `TimestampWithTimeZone`).

## MCP Tools

The MCP server exposes these tools to LLM agents:

| Tool | Description |
|------|-------------|
| `list_tables` | All tables with name, description, column count, relationship count |
| `describe_table(name)` | Full column details + relationships for one table |
| `find_path(from_table, to_table)` | Shortest join path(s) between two tables via BFS |
| `explore_relationships(table_name)` | All directly related tables with direction |
| `build_query(table, fields)` | Generate a GraphQL query for a table |
| `execute_query(sql)` | Run SQL against the database (requires `--db-url`) |

Each response includes a `_meta.next_steps` field guiding the agent's next action.

## Development

```bash
# Install with all extras
uv sync --all-extras --all-groups

# Run tests
uv run pytest tests/ -v

# Lint and format
uv run ruff check --fix && uv run ruff format
```
