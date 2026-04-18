"""Format dbt project info as GraphQL db schema.

Produces:
- db.graphql: GraphQL SDL schema used by the query compiler.

Column types are emitted as PascalCase GraphQL-compatible names.
The raw SQL type is preserved in an ``@sql(type: "...")`` directive
so the compiler can access the exact type (including size/precision).
"""

from __future__ import annotations

import re
from string import capwords

from pydantic import BaseModel

from ..ir.models import ColumnInfo, ProjectInfo, ModelInfo, RelationshipInfo

# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------


class GraphQLResult(BaseModel):
    """GraphQL schema output."""

    db_graphql: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_graphql(project: ProjectInfo) -> GraphQLResult:
    """Convert domain-neutral ProjectInfo into GraphQL db schema."""
    return GraphQLResult(db_graphql=_build_db_graphql(project))


# ---------------------------------------------------------------------------
# Type parsing
# ---------------------------------------------------------------------------


_SIZE_RE = re.compile(r"^(.*?)\s*\((.+)\)\s*$")


def _parse_sql_type(raw: str) -> tuple[str, str, bool]:
    """Return (base_type, size, is_array) from a raw SQL type.

    >>> _parse_sql_type("VARCHAR(255)")
    ('VARCHAR', '255', False)
    >>> _parse_sql_type("NUMERIC(10,2)")
    ('NUMERIC', '10,2', False)
    >>> _parse_sql_type("INTEGER[]")
    ('INTEGER', '', True)
    >>> _parse_sql_type("ARRAY<STRING>")
    ('STRING', '', True)
    >>> _parse_sql_type("DOUBLE PRECISION")
    ('DOUBLE PRECISION', '', False)
    """
    s = raw.strip()
    is_array = False

    # BigQuery ARRAY<T>
    upper = s.upper()
    if upper.startswith("ARRAY<") and s.endswith(">"):
        s = s[6:-1].strip()
        is_array = True

    # Postgres T[]
    if s.endswith("[]"):
        is_array = True
        s = s[:-2].strip()

    m = _SIZE_RE.match(s)
    if m:
        return m.group(1).strip(), m.group(2).strip(), is_array

    return s.strip(), "", is_array


# ---------------------------------------------------------------------------
# db.graphql builder
# ---------------------------------------------------------------------------


def _build_db_graphql(project: ProjectInfo) -> str:
    """Build a GraphQL SDL schema for all dbt models."""
    rel_map = _build_rel_map(project.relationships)
    blocks: list[str] = []
    for model in project.models:
        blocks.append(_type_block(model, rel_map))
    return "\n".join(blocks).rstrip() + "\n"


def _build_rel_map(
    relationships: list[RelationshipInfo],
) -> dict[tuple[str, str], tuple[str, str]]:
    rel_map: dict[tuple[str, str], tuple[str, str]] = {}
    for rel in relationships:
        if not rel.from_column or not rel.to_column:
            continue
        rel_map[(rel.from_model, rel.from_column)] = (rel.to_model, rel.to_column)
    return rel_map


def _type_block(
    model: ModelInfo,
    rel_map: dict[tuple[str, str], tuple[str, str]],
) -> str:
    """Build a GraphJin SDL type block for a dbt model."""
    type_directives: list[str] = [
        f"@database(name: {model.database})",
        f"@schema(name: {model.schema_})",
        f"@table(name: {model.relation_name})",
    ]

    header = f"type {model.name}"
    if type_directives:
        header += " " + " ".join(type_directives)
    header += " {"

    lines = [header]
    for col in model.columns:
        lines.append("  " + _column_line(model, col, rel_map))
    lines.append("}")
    return "\n".join(lines)


def _column_line(
    model: ModelInfo,
    col: ColumnInfo,
    rel_map: dict[tuple[str, str], tuple[str, str]],
) -> str:
    base, size, is_array = _parse_sql_type(col.type)
    pascal = capwords(base.replace("_", " ")).replace(" ", "")
    gql_type = f"[{pascal}]" if is_array else pascal
    if col.not_null:
        gql_type += "!"

    sql_args = f'type: "{base}"'
    if size:
        sql_args += f', size: "{size}"'
    directives: list[str] = [f"@sql({sql_args})"]
    if col.is_primary_key or col.name == model.primary_key:
        directives.append("@id")
    if col.unique and not (col.is_primary_key or col.name == model.primary_key):
        directives.append("@unique")
    if col.is_hidden:
        directives.append("@blocked")

    rel = rel_map.get((model.name, col.name))
    if rel:
        target_model, target_col = rel
        directives.append(f"@relation(type: {target_model}, field: {target_col})")

    dir_str = " ".join(directives)
    line = f"{col.name}: {gql_type}"
    if dir_str:
        line += f" {dir_str}"
    return line
