"""Schema discovery for MCP tools.

Provides static discovery (from ProjectInfo) and optional live enrichment
(from a live database connection).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ColumnDetail:
    name: str
    sql_type: str
    not_null: bool = False
    is_primary_key: bool = False
    is_unique: bool = False
    description: str = ""
    enum_values: list[str] | None = None


@dataclass
class TableSummary:
    name: str
    description: str = ""
    column_count: int = 0
    relationship_count: int = 0


@dataclass
class TableDetail:
    name: str
    description: str = ""
    columns: list[ColumnDetail] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)


@dataclass
class JoinStep:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass
class JoinPath:
    steps: list[JoinStep] = field(default_factory=list)

    @property
    def length(self) -> int:
        return len(self.steps)


@dataclass
class RelatedTable:
    name: str
    via_column: str
    direction: str  # "outgoing" | "incoming"


class SchemaDiscovery:
    """Discover schema structure from a ProjectInfo IR."""

    def __init__(self, project, db=None) -> None:
        self._project = project
        self._db = db
        # Build adjacency for BFS path-finding
        self._adj: dict[
            str, list[tuple[str, str, str]]
        ] = {}  # table → [(via_col, to_table, to_col)]
        for rel in project.relationships:
            self._adj.setdefault(rel.from_model, []).append(
                (rel.from_column, rel.to_model, rel.to_column)
            )
            self._adj.setdefault(rel.to_model, []).append(
                (rel.to_column, rel.from_model, rel.from_column)
            )

    def list_tables(self) -> list[TableSummary]:
        return [
            TableSummary(
                name=m.name,
                description=m.description,
                column_count=len(m.columns),
                relationship_count=len(m.relationships),
            )
            for m in self._project.models
        ]

    def describe_table(self, name: str) -> TableDetail | None:
        model = next((m for m in self._project.models if m.name == name), None)
        if model is None:
            return None
        columns = [
            ColumnDetail(
                name=c.name,
                sql_type=c.type,
                not_null=c.not_null,
                is_primary_key=c.is_primary_key,
                is_unique=c.unique,
                description=c.description,
                enum_values=c.enum_values,
            )
            for c in model.columns
        ]
        relationships = [
            f"{rel.from_model}.{rel.from_column} → {rel.to_model}.{rel.to_column}"
            for rel in model.relationships
        ]
        return TableDetail(
            name=name,
            description=model.description,
            columns=columns,
            relationships=relationships,
        )

    def find_path(self, from_table: str, to_table: str) -> list[JoinPath]:
        """BFS to find all shortest join paths between two tables."""
        if from_table == to_table:
            return [JoinPath()]

        queue: list[tuple[str, list[JoinStep]]] = [(from_table, [])]
        visited: set[str] = {from_table}
        shortest: list[JoinPath] = []
        shortest_len: int | None = None

        while queue:
            current, path = queue.pop(0)
            if shortest_len is not None and len(path) >= shortest_len:
                break

            for via_col, neighbor, neighbor_col in self._adj.get(current, []):
                step = JoinStep(
                    from_table=current,
                    from_column=via_col,
                    to_table=neighbor,
                    to_column=neighbor_col,
                )
                new_path = path + [step]
                if neighbor == to_table:
                    shortest_len = len(new_path)
                    shortest.append(JoinPath(steps=new_path))
                elif neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, new_path))

        return shortest

    def explore_relationships(self, table_name: str) -> list[RelatedTable]:
        """Return all tables directly related to the given table."""
        result: list[RelatedTable] = []
        for rel in self._project.relationships:
            if rel.from_model == table_name:
                result.append(
                    RelatedTable(
                        name=rel.to_model,
                        via_column=rel.from_column,
                        direction="outgoing",
                    )
                )
            elif rel.to_model == table_name:
                result.append(
                    RelatedTable(
                        name=rel.from_model,
                        via_column=rel.to_column,
                        direction="incoming",
                    )
                )
        return result

    # ---- Live enrichment (requires db connection) ----

    async def get_row_count(self, table: str) -> int | None:
        if self._db is None:
            return None
        rows = await self._db.execute_text(f"SELECT COUNT(*) AS cnt FROM {table}")
        return rows[0]["cnt"] if rows else None

    async def get_distinct_values(
        self, table: str, column: str, limit: int = 50
    ) -> list:
        if self._db is None:
            return []
        rows = await self._db.execute_text(
            f"SELECT DISTINCT {column} FROM {table} LIMIT {limit}"
        )
        return [r[column] for r in rows]

    async def get_date_range(
        self, table: str, column: str
    ) -> tuple[str | None, str | None]:
        if self._db is None:
            return None, None
        rows = await self._db.execute_text(
            f"SELECT MIN({column}) AS mn, MAX({column}) AS mx FROM {table}"
        )
        if not rows:
            return None, None
        return str(rows[0]["mn"]), str(rows[0]["mx"])

    async def get_sample_rows(self, table: str, limit: int = 5) -> list[dict]:
        if self._db is None:
            return []
        return await self._db.execute_text(f"SELECT * FROM {table} LIMIT {limit}")
