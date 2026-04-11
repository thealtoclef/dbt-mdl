# Plan: Rewrite dbt-to-Wren Converter in Python

## Context

The Go codebase at `/home/blue/repos/WrenAI/wren-launcher/commands/dbt/` converts dbt artifacts (catalog.json, manifest.json, profiles.yml) into Wren MDL. We're rewriting this in Python, leveraging `dbt-artifacts-parser` for typed artifact access and integrating directly with `wren-engine` so the converter returns a ready-to-use `WrenEngine` instance.

**Scope exclusion**: No dbt metrics or semantic layer support.

**Key difference from Go**: The Go code works with untyped `map[string]interface{}` and uses regex for ref parsing. In Python, `dbt-artifacts-parser` gives us typed Pydantic models — `test_node.refs[0].name` replaces regex, `catalog.nodes[id].columns[name].type` replaces manual map traversal.

## Integration with wren-engine

`WrenEngine` needs:
```python
WrenEngine(
    manifest_str=manifest_str,       # base64-encoded camelCase MDL JSON
    data_source=DataSource.postgres,  # wren DataSource StrEnum
    connection_info=conn_dict,        # dict matching ConnectionInfo schema
)
```

## Dependencies

- **Python 3.14**, **uv** package manager, **uv** build backend
- `wren-engine` — `WrenEngine`, `DataSource`, `ConnectionInfo` models
- `pydantic` (v2) — data models (also transitive from wren-engine)
- `dbt-artifacts-parser` — typed manifest/catalog parsing
- `dbt-core` — dbt utilities if needed (ref resolution, etc.)
- `pyyaml` — profiles.yml parsing
- `pytest` — dev dependency

## Public API

```python
from wren_dbt_converter import from_dbt_project, build_manifest

# Get a WrenEngine directly
engine = from_dbt_project("/path/to/dbt/project")
with engine:
    result = engine.query("SELECT * FROM customers LIMIT 10")

# Lower-level: get pieces without constructing engine
result = build_manifest("/path/to/dbt/project", profile_name="default", target="dev")
# result.manifest       -> WrenMDLManifest Pydantic model
# result.manifest_str   -> base64-encoded JSON
# result.data_source    -> wren DataSource enum
# result.connection_info -> dict for wren-engine
```

## Package Structure

```
wren-dbt-converter/
├── pyproject.toml
├── src/
│   └── wren_dbt_converter/
│       ├── __init__.py              # Public API: from_dbt_project(), build_manifest()
│       ├── converter.py             # Main orchestration
│       ├── engine_builder.py        # WrenEngine construction
│       ├── models/
│       │   ├── __init__.py
│       │   ├── wren_mdl.py          # MDL Pydantic models (camelCase serialization)
│       │   ├── data_source.py       # dbt→wren DataSource mapping + connection_info builder
│       │   └── profiles.py          # DbtProfiles, DbtProfile, DbtConnection
│       ├── parsers/
│       │   ├── __init__.py
│       │   ├── profiles_parser.py   # profiles.yml YAML parsing
│       │   └── artifacts.py         # Thin wrappers around dbt-artifacts-parser
│       ├── processors/
│       │   ├── __init__.py
│       │   ├── tests_preprocessor.py  # Extract enums, not-null from typed manifest tests
│       │   ├── relationships.py       # Generate relationships from typed test nodes
│       │   └── columns.py            # Column conversion using typed catalog/manifest
│       └── utils.py
└── tests/
    ├── conftest.py
    ├── test_data_source.py
    ├── test_profiles_parser.py
    ├── test_converter.py
    ├── test_relationships.py
    ├── test_columns.py
    ├── test_tests_preprocessor.py
    └── fixtures/
        ├── catalog.json
        ├── manifest.json
        ├── profiles.yml
        └── dbt_project.yml
```

## Implementation Steps

### Step 1: Project scaffolding
- `pyproject.toml` with uv build backend, deps: `wren-engine`, `dbt-artifacts-parser`, `dbt-core`, `pydantic`, `pyyaml`; dev: `pytest`
- `src/wren_dbt_converter/__init__.py`
- `uv sync`

### Step 2: MDL output models (`models/wren_mdl.py`)
Pydantic models matching wren-engine's camelCase MDL JSON schema (`wren-mdl/mdl.schema.json`):
- `EnumDefinition(name, values: list[EnumValue])`
- `TableReference(catalog, schema, table)`
- `WrenColumn(name, type, displayName, isCalculated, notNull, expression, relationship, properties)`
- `WrenModel(name, tableReference, columns, primaryKey, cached, refreshTime, properties)`
- `Relationship(name, models: list[str], joinType, condition, properties)`
- `WrenMDLManifest(catalog, schema, dataSource, models, relationships, enumDefinitions, views)`
- `to_manifest_str()` → base64-encoded camelCase JSON

### Step 3: Profiles input models (`models/profiles.py`)
- `DbtConnection` with `ConfigDict(extra="allow")` for unknown fields
- `DbtProfile(target, outputs: dict[str, DbtConnection])`
- `DbtProfiles(profiles: dict[str, DbtProfile])`

### Step 4: Data source mapping (`models/data_source.py`)
Bridge dbt profiles to wren-engine types:
- `map_dbt_type_to_wren(dbt_type: str) -> WrenDataSource` — `"postgres"→postgres`, `"duckdb"→duckdb`, `"sqlserver"→mssql`, `"bigquery"→bigquery`, `"mysql"→mysql`, `"snowflake"→snowflake`
- `build_connection_info(conn: DbtConnection, dbt_home: Path) -> dict` — builds dict matching wren-engine ConnectionInfo for each type. BigQuery: 3 auth methods preserved (service-account-json, service-account keyfile, oauth)
- `get_active_connection(profiles, profile_name, target, dbt_home) -> tuple[WrenDataSource, dict]`
- `map_column_type(data_source: WrenDataSource, source_type: str) -> str` — database-specific type mapping (BigQuery INT64→integer, etc.)

### Step 5: Data source tests (`tests/test_data_source.py`)
Port all 14 Go tests adapted for the mapping approach:
- Postgres/MySQL/MSSQL/BigQuery/DuckDB connection building
- BigQuery credential handling (3 auth methods, tmp_path for keyfiles)
- Active connection selection (default/explicit target, missing profiles)
- Type mapping across data sources
- Validation via wren-engine's `DataSource.get_connection_info()`

### Step 6: Profiles parser (`parsers/profiles_parser.py`)
- `analyze_dbt_profiles(path) -> DbtProfiles` — YAML → typed models
- `find_profiles_file(project_path) -> Path | None` — 3-location search
- `get_default_profiles_path() -> Path`

### Step 7: Profiles parser tests (`tests/test_profiles_parser.py`)
- Multi-profile parsing, missing file, 3-location search, flexible types

### Step 8: Artifact parsers (`parsers/artifacts.py`)
- `load_catalog(path)` — `dbt_artifacts_parser.parser.parse_catalog`
- `load_manifest(path)` — `dbt_artifacts_parser.parser.parse_manifest`

### Step 9: Tests preprocessor (`processors/tests_preprocessor.py`)
Uses typed manifest — iterate `manifest.nodes` where `unique_id.startswith("test.")`:
- **not_null tests**: `node.test_metadata.name == "not_null"` → `column_to_not_null_map[f"{node.attached_node}.{node.column_name}"] = True`
- **accepted_values tests**: `node.test_metadata.name == "accepted_values"` → extract `node.test_metadata.kwargs["values"]` → deduplicate enums by sorted value set → build `column_to_enum_name_map`
- Enum name sanitization (remove non-alphanumeric, prefix `_` if starts with digit)
- Returns: `(enum_definitions, column_to_enum_name_map, column_to_not_null_map)`

### Step 10: Relationships processor (`processors/relationships.py`)
Uses typed manifest — iterate test nodes where `node.test_metadata.name == "relationships"`:
- **Source model**: `node.attached_node` → extract model name from unique_id
- **Source column**: `node.column_name`
- **Target model**: `node.refs[0].name` (typed RefArgs — NO regex needed)
- **Target column**: `node.test_metadata.kwargs["field"]`
- Build `Relationship(name=f"{from_model}_{from_col}_{to_model}_{to_col}", models=[from_model, to_model], joinType="MANY_TO_ONE", condition=f'"{from_model}"."{from_col}" = "{to_model}"."{to_col}"')`
- Deduplicate by (name, joinType, condition)

### Step 11: Columns processor (`processors/columns.py`)
Uses typed catalog + manifest:
- `convert_columns(catalog_node, manifest_node, data_source, enum_map, not_null_map) -> list[WrenColumn]`
- For each `catalog_node.columns[col_name]`:
  - `name` = `col.name`
  - `type` = `map_column_type(data_source, col.type)`
  - `notNull` = lookup in `not_null_map`
  - `properties.description` = `manifest_node.columns[col_name].description` if available
  - `properties.comment` = `col.comment` if available
  - `properties.enumDefinition` = lookup in `enum_map`
- Sort by `col.index` then `col.name`

### Step 12: Processor tests (`tests/test_*.py`)
- `test_tests_preprocessor.py` — enum extraction, not-null, deduplication
- `test_relationships.py` — typed test node → Relationship, dedup, missing refs
- `test_columns.py` — sort order, type mapping, enum linking, not-null

### Step 13: Engine builder (`engine_builder.py`)
```python
def build_engine(manifest: WrenMDLManifest, data_source: WrenDataSource, connection_info: dict) -> WrenEngine:
    return WrenEngine(
        manifest_str=manifest.to_manifest_str(),
        data_source=data_source,
        connection_info=connection_info,
    )
```

### Step 14: Main converter (`converter.py`)
Orchestration:
1. Validate dbt project (`dbt_project.yml` exists)
2. Find/parse profiles.yml → `get_active_connection()` → `(WrenDataSource, connection_info)`
3. Load catalog via `parse_catalog()`, manifest via `parse_manifest()`
4. Preprocess: tests → `(enums, enum_map, not_null_map)`
5. For each `catalog.nodes[key]` where `key.startswith("model.")`:
   - Skip staging if configured (`stg_` / `staging_` prefix)
   - Convert to `WrenModel` using typed catalog columns + manifest descriptions
6. Generate relationships from typed test nodes
7. Assemble `WrenMDLManifest`
8. Return `ConvertResult`

Public functions:
```python
def build_manifest(project_path, ...) -> ConvertResult:
def from_dbt_project(project_path, ...) -> WrenEngine:
```

### Step 15: Integration test (`tests/test_converter.py`)
- Fixture files (catalog.json, manifest.json, profiles.yml, dbt_project.yml)
- `build_manifest()` → verify manifest structure
- `from_dbt_project()` → WrenEngine that can `.dry_plan()`
- Error cases: missing project, missing catalog, missing profiles

### Step 16: Package API + cleanup
- Exports from `__init__.py`
- `uv build` → wheel
- `uv run pytest` → all pass

## Key Files to Reference

| Python module | Go source | Typed library reference |
|---|---|---|
| `models/wren_mdl.py` | `wren_mdl.go` | `wren-mdl/mdl.schema.json` |
| `models/data_source.py` | `data_source.go` | `wren.model.data_source.DataSource`, `wren.model.ConnectionInfo` |
| `processors/relationships.py` | `converter.go` (regex+map) | `dbt_artifacts_parser` `GenericTestNode.refs[].name`, `.test_metadata`, `.attached_node` |
| `processors/tests_preprocessor.py` | `converter.go` (map traversal) | `dbt_artifacts_parser` `GenericTestNode.test_metadata.kwargs["values"]` |
| `processors/columns.py` | `converter.go` (map traversal) | `dbt_artifacts_parser` `CatalogV1.nodes[].columns[].type/index/comment` |
| `engine_builder.py` | — | `wren.engine.WrenEngine` |

## Verification

1. `uv sync` — dependencies resolve
2. `uv run pytest` — all tests pass
3. `from_dbt_project()` on fixtures → `WrenEngine.dry_plan()` works
4. `uv build` → `.whl` and `.tar.gz`
