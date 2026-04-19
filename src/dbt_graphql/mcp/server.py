"""MCP server exposing schema discovery and query tools for LLM agents."""

from __future__ import annotations

from typing import Any

from .discovery import SchemaDiscovery


class McpTools:
    """Tool functions exposed to LLM agents via MCP.

    Instantiate directly for testing; wrap with create_mcp_server for serving.
    """

    def __init__(self, project, db=None) -> None:
        self._discovery = SchemaDiscovery(project, db=db)
        self._db = db

    def list_tables(self) -> dict[str, Any]:
        """List all available tables with summary information."""
        tables = self._discovery.list_tables()
        return {
            "tables": [
                {
                    "name": t.name,
                    "description": t.description,
                    "column_count": t.column_count,
                    "relationship_count": t.relationship_count,
                }
                for t in tables
            ],
            "_meta": {
                "next_steps": [
                    "Call describe_table(name) to get full column details for a specific table.",
                    "Call explore_relationships(table_name) to see how tables connect.",
                ]
            },
        }

    def describe_table(self, name: str) -> dict[str, Any]:
        """Get full column details for a table."""
        detail = self._discovery.describe_table(name)
        if detail is None:
            return {"error": f"Table '{name}' not found.", "_meta": {}}
        return {
            "name": detail.name,
            "description": detail.description,
            "columns": [
                {
                    "name": c.name,
                    "sql_type": c.sql_type,
                    "not_null": c.not_null,
                    "is_unique": c.is_unique,
                    "description": c.description,
                    "enum_values": c.enum_values,
                }
                for c in detail.columns
            ],
            "relationships": detail.relationships,
            "_meta": {
                "next_steps": [
                    "Call find_path(from_table, to_table) to discover join paths.",
                    "Call build_query(table, fields) to generate a GraphQL query.",
                ]
            },
        }

    def find_path(self, from_table: str, to_table: str) -> dict[str, Any]:
        """Find the shortest join path between two tables."""
        paths = self._discovery.find_path(from_table, to_table)
        if not paths:
            return {
                "found": False,
                "from_table": from_table,
                "to_table": to_table,
                "_meta": {
                    "next_steps": [
                        "Try explore_relationships to see what each table connects to."
                    ]
                },
            }
        return {
            "found": True,
            "from_table": from_table,
            "to_table": to_table,
            "paths": [
                [
                    {
                        "from_table": s.from_table,
                        "from_column": s.from_column,
                        "to_table": s.to_table,
                        "to_column": s.to_column,
                    }
                    for s in p.steps
                ]
                for p in paths
            ],
            "_meta": {
                "next_steps": [
                    "Use build_query to construct a query using these joins."
                ]
            },
        }

    def explore_relationships(self, table_name: str) -> dict[str, Any]:
        """Get all tables directly related to the given table."""
        related = self._discovery.explore_relationships(table_name)
        return {
            "table": table_name,
            "related_tables": [
                {"name": r.name, "via_column": r.via_column, "direction": r.direction}
                for r in related
            ],
            "_meta": {
                "next_steps": [
                    "Call find_path to discover multi-hop join paths.",
                    "Call describe_table for column details of any related table.",
                ]
            },
        }

    def build_query(self, table: str, fields: list[str]) -> dict[str, Any]:
        """Generate a GraphQL query for a table with the given fields."""
        field_str = "\n    ".join(fields)
        query = f"query {{\n  {table} {{\n    {field_str}\n  }}\n}}"
        return {
            "table": table,
            "fields": fields,
            "query": query,
            "_meta": {
                "next_steps": [
                    "Pass the query to execute_query to run it against the database."
                ]
            },
        }

    async def execute_query(self, sql: str) -> dict[str, Any]:
        """Execute a raw SQL statement against the database."""
        if self._db is None:
            return {"error": "No database connection configured.", "_meta": {}}
        rows = await self._db.execute_text(sql)
        return {
            "row_count": len(rows),
            "rows": rows,
            "_meta": {
                "next_steps": [
                    "Analyze the results or call another tool for further exploration."
                ]
            },
        }


def create_mcp_server(project, db=None):
    """Build and return a fastmcp Server with all tools registered."""
    from fastmcp import FastMCP

    tools = McpTools(project, db=db)
    mcp = FastMCP("dbt-graphql")

    mcp.tool()(tools.list_tables)
    mcp.tool()(tools.describe_table)
    mcp.tool()(tools.find_path)
    mcp.tool()(tools.explore_relationships)
    mcp.tool()(tools.build_query)
    mcp.tool()(tools.execute_query)

    return mcp


def serve_mcp(project, db=None) -> None:
    """Start the MCP server with stdio transport."""
    mcp = create_mcp_server(project, db=db)
    mcp.run(transport="stdio")
