from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .graphjin.formatter import format_graphjin
from .wren.formatter import format_mdl
from .pipeline import extract_project


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="dbt-mdl",
        description="Convert a dbt project to model definition formats.",
    )
    parser.add_argument(
        "project_path",
        type=Path,
        help="Path to the dbt project root (must contain profiles.yml).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("."),
        metavar="DIR",
        help="Output directory for generated files (default: current directory).",
    )
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=["wren", "graphjin", "all"],
        default="all",
        help="Output format (default: all).",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to catalog.json (default: <project_path>/target/catalog.json).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to manifest.json (default: <project_path>/target/manifest.json).",
    )
    parser.add_argument(
        "--profile-name",
        default=None,
        metavar="NAME",
        help="dbt profile name to use (default: first profile in profiles.yml).",
    )
    parser.add_argument(
        "--target",
        default=None,
        metavar="TARGET",
        help="dbt target within the profile (default: profile's default target).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="PATTERN",
        help=(
            "Regex pattern matched against model names; matching models are excluded. "
            "May be repeated to add multiple patterns (OR logic). "
            "Example: --exclude '^stg_' --exclude '^int_'"
        ),
    )

    args = parser.parse_args(argv)

    try:
        project = extract_project(
            project_path=args.project_path,
            profile_name=args.profile_name,
            target=args.target,
            exclude_patterns=args.exclude,
            catalog_path=args.catalog,
            manifest_path=args.manifest,
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    fmt = args.fmt

    # --- Domain format ---
    if fmt in ("domain", "all"):
        lineage = project.build_lineage_schema()
        if lineage.table_lineage or lineage.column_lineage:
            lineage_path = output_dir / "lineage.json"
            lineage_path.write_text(lineage.model_dump_json(by_alias=True, indent=2))
            print(f"lineage.json          -> {lineage_path}")

    # --- Wren format ---
    if fmt in ("wren", "all"):
        result = format_mdl(project)

        mdl_path = output_dir / "mdl.json"
        mdl_path.write_text(
            result.manifest.model_dump_json(by_alias=True, exclude_none=True, indent=2)
        )
        print(f"mdl.json              -> {mdl_path}")

        connection_path = output_dir / "connection.json"
        connection_path.write_text(
            json.dumps(
                {
                    "dataSource": result.data_source.value
                    if result.data_source
                    else "",
                    "connection": result.connection_info,
                },
                indent=2,
            )
        )
        print(f"connection.json       -> {connection_path}")

    # --- GraphJin format ---
    if fmt in ("graphjin", "all"):
        gj = format_graphjin(project)

        db_graphql_path = output_dir / "db.graphql"
        db_graphql_path.write_text(gj.db_graphql)
        print(f"db.graphql            -> {db_graphql_path}")

        dev_yml_path = output_dir / "dev.yml"
        dev_yml_path.write_text(gj.dev_yml)
        print(f"dev.yml               -> {dev_yml_path}")
