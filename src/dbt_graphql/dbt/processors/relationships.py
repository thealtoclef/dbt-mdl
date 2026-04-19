from __future__ import annotations

from ...ir.models import ProcessorRelationship, JoinType


def _model_name_from_unique_id(unique_id: str) -> str:
    """Extract model name from a unique_id like 'model.project.customers'."""
    parts = unique_id.split(".")
    return parts[-1] if parts else unique_id


def _clean_col(raw: str) -> str:
    """Strip SQL quoting characters from a column name."""
    return raw.strip('"').strip("`")


def build_relationships(manifest) -> list[ProcessorRelationship]:
    """
    Generate Relationship objects from 'relationships' test nodes in the manifest.

    Uses typed manifest — no regex needed:
      node.attached_node → source model unique_id
      node.column_name   → source column
      node.refs[0].name  → target model name
      node.test_metadata.kwargs["field"] → target column
    """
    seen: set[tuple] = set()
    relationships: list[ProcessorRelationship] = []

    for unique_id, node in manifest.nodes.items():
        if not unique_id.startswith("test."):
            continue

        test_metadata = getattr(node, "test_metadata", None)
        if test_metadata is None or test_metadata.name != "relationships":
            continue

        attached_node = getattr(node, "attached_node", None) or ""
        from_model = _model_name_from_unique_id(attached_node)
        from_col = _clean_col(getattr(node, "column_name", None) or "")

        refs = getattr(node, "refs", None) or []
        if not refs:
            continue
        to_model = refs[0].name

        to_col = _clean_col((test_metadata.kwargs or {}).get("field", ""))
        if not to_col or not from_col or not from_model or not to_model:
            continue

        rel_name = f"{from_model}_{from_col}_{to_model}_{to_col}"
        condition = f'"{from_model}"."{from_col}" = "{to_model}"."{to_col}"'

        dedup_key = (rel_name, condition)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        relationships.append(
            ProcessorRelationship(
                name=rel_name,
                models=[from_model, to_model],
                join_type=JoinType.many_to_one,
                condition=condition,
            )
        )

    return relationships
