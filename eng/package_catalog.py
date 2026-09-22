# SPDX-License-Identifier: Apache-2.0
"""The complete Contracts producer inventory shared by build and publication."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def packages(kind: str | None = None, root: Path = ROOT) -> list[dict]:
    catalog = json.loads((root / "eng/contract-packages.json").read_text(encoding="utf-8"))
    if catalog.get("schemaVersion") != 1:
        raise ValueError("Unsupported contract package catalog")
    rows = catalog["packages"]
    ids = {row["id"] for row in rows}
    if len(ids) != len(rows):
        raise ValueError("Duplicate contract package identity")
    for row in rows:
        if row["kind"] not in {"nuget", "npm", "maven"} or row["access"] not in {"public", "internal"}:
            raise ValueError("Unknown package kind/access")
        for path in [row["sourceRoot"], *row["proto"], *row["jsonSchemas"]]:
            if not path or ":" in path or "\\" in path or any(p in {"", ".", ".."} for p in path.split("/")):
                raise ValueError("Unsafe package source path")
        if not row["sourceRoot"].startswith("src/" + row["access"] + "/"):
            raise ValueError("Package access/source mismatch")
        if any(dep not in ids for dep in row["dependencies"]):
            raise ValueError("Unknown first-party package dependency")
        if Path(row["descriptor"]).name != row["descriptor"] or "\\" in row["descriptor"]:
            raise ValueError("Descriptor filename must be flat")
    return [row for row in rows if kind is None or row["kind"] == kind]


def closure(package_id: str, root: Path = ROOT) -> list[dict]:
    rows = {row["id"]: row for row in packages(root=root)}
    ordered: list[dict] = []
    active: set[str] = set()
    seen: set[str] = set()

    def visit(identity: str) -> None:
        if identity in active:
            raise ValueError("Contract package dependency cycle")
        if identity in seen:
            return
        row = rows[identity]
        active.add(identity)
        for dependency in row["dependencies"]:
            target = rows[dependency]
            if target["kind"] != row["kind"] or (row["access"] == "public" and target["access"] != "public"):
                raise ValueError("Forbidden contract package dependency")
            visit(dependency)
        active.remove(identity)
        seen.add(identity)
        ordered.append(row)

    visit(package_id)
    return ordered


def ordered(kind: str, root: Path = ROOT) -> list[dict]:
    output: dict[str, dict] = {}
    for row in packages(kind, root):
        for dependency in closure(row["id"], root):
            output[dependency["id"]] = dependency
    return list(output.values())
