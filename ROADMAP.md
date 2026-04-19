# Roadmap

Planned features and improvements, roughly ordered by priority.

---

## dbt Selector Support (`--select` / `--exclude`)

**Motivation:** Large dbt projects use schema-per-team layouts, exposures tied to specific dashboards, or node graph traversal (`+orders`, `tag:finance`) to define meaningful subsets of the model graph. A simple regex on model names can't express these patterns, and implementing the full dbt node selection graph ourselves is unnecessary complexity.

**Approach:** Shell out to `dbt ls` with the user-provided selector string and let dbt resolve the node set. Feed the resulting model names as an allowlist into `extract_project`.

```bash
# User experience
dbt-graphql generate \
  --format graphql \
  --catalog target/catalog.json \
  --manifest target/manifest.json \
  --select "tag:finance,+orders"   # any dbt selector syntax
  --project-dir .                  # needed for dbt ls
```

**Implementation sketch:**
1. Add `--select` / `--project-dir` CLI flags (alongside existing `--exclude`).
2. When `--select` is provided, run `dbt ls --select <selector> --output json --profiles-dir <dir>`.
3. Parse the JSON output to get the set of selected node unique IDs.
4. In `extract_project`, skip catalog nodes not in that set.

**References:**
- dbt node selection: https://docs.getdbt.com/reference/node-selection/syntax
- YAML selectors: https://docs.getdbt.com/reference/node-selection/yaml-selectors

---

## Source Node Inclusion

**Motivation:** dbt projects commonly reference raw source tables (defined via `sources:` in YAML) as FK targets in relationship tests. Currently, these source nodes are silently ignored because `extract_project` only iterates `catalog.nodes` (which contains model, test, and seed nodes) and skips `catalog.sources`. This means FK relationships pointing to a source table are dropped from the GraphQL schema.

**Approach:** Iterate `catalog.sources` in addition to `catalog.nodes`. Create `ModelInfo` entries for source tables that are either directly selected or are FK targets of selected models. Mark them as read-only (no write resolvers) in the GraphQL schema.

**Scope:**
- Extend `extract_project` to iterate `catalog.sources`.
- Extend `build_relationships` to resolve source nodes (their unique IDs start with `source.` rather than `model.`).
- The GraphQL SDL and SQL compiler already work generically via table names, so formatter changes should be minimal.
