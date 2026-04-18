from __future__ import annotations

import json
from pathlib import Path

from dbt_artifacts_parser.parser import parse_catalog, parse_manifest


def load_catalog(path: Path | str):
    data = json.loads(Path(path).read_text())
    return parse_catalog(data)


def load_manifest(path: Path | str):
    data = json.loads(Path(path).read_text())
    return parse_manifest(data)
