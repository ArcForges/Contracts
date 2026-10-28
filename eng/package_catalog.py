# SPDX-License-Identifier: Apache-2.0
"""The complete Contracts producer inventory shared by build and publication.

A row marked "retired" stays in the catalog as the record of a published identity whose
publication stopped (CON.40). No new version of it is generated, built, packed or published:
packages() and ordered() return active rows only, while closure() still resolves a retired
identity so its historical schema closure remains reportable.

AF-CTR-01 adds the one "go" row: the Go module github.com/ArcForges/Contracts/go in go/, published by an
immutable go/v<version> tag of the publishing commit (channel "go-module") at the cohort version of the NuGet
packages. Its generated sources live in go/, not under src/<access>/, so its row is validated separately: it owns
no JSON schema and no first-party dependency, and every proto package it generates is mapped to exactly one Go
package (goPackages).
"""

from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


KINDS = {"nuget", "npm", "maven", "go"}
GO_MODULE = "github.com/ArcForges/Contracts/go"
GO_PACKAGE_FIELDS = {"protoPackage", "importPath", "name", "contractAccess"}


def retired(row: dict) -> bool:
    return "retired" in row


def go_row(row: dict) -> None:
    """The Go module row (AF-CTR-01): one module in go/, internal contract access, proto-owned packages only."""
    if (row["id"] != GO_MODULE or row.get("channel") != "go-module" or row["sourceRoot"] != "go"
            or row["access"] != "internal" or row["dependencies"] or row["jsonSchemas"] or "retired" in row):
        raise ValueError("The Go module row must be " + GO_MODULE + " in go/ with internal access and no other owner")
    if not row["proto"] or len(set(row["proto"])) != len(row["proto"]):
        raise ValueError("The Go module row must list each generated proto file once")
    mapping = row.get("goPackages")
    if not isinstance(mapping, list) or not mapping:
        raise ValueError("The Go module row must map its proto packages to Go packages")
    seen = set()
    for item in mapping:
        if not isinstance(item, dict) or set(item) != GO_PACKAGE_FIELDS:
            raise ValueError("Invalid Go package mapping")
        match = re.fullmatch(r"arcforges\.([a-z]+)\.(v[1-9][0-9]*)", item["protoPackage"])
        if (match is None or item["name"] != match[1] + match[2]
                or item["importPath"] != f"{GO_MODULE}/arcforges/{match[1]}/{match[2]}"
                or item["contractAccess"] not in {"public", "internal"} or item["protoPackage"] in seen):
            raise ValueError("Go package mapping differs from its proto package: " + str(item.get("protoPackage")))
        seen.add(item["protoPackage"])
    by_directory = {item["importPath"].removeprefix(GO_MODULE + "/"): item for item in mapping}
    used = set()
    for source in row["proto"]:
        access, _, virtual = source.partition("/proto/")
        item = by_directory.get(virtual.rsplit("/", 1)[0])
        if access not in {"public", "internal"} or item is None or item["contractAccess"] != access:
            raise ValueError("Generated proto file has no Go package of its access: " + source)
        used.add(item["protoPackage"])
    if used != seen:
        raise ValueError("A Go package mapping has no generated proto file")


def packages(kind: str | None = None, root: Path = ROOT, *, include_retired: bool = False) -> list[dict]:
    catalog = json.loads((root / "eng/contract-packages.json").read_text(encoding="utf-8"))
    if catalog.get("schemaVersion") != 1:
        raise ValueError("Unsupported contract package catalog")
    rows = catalog["packages"]
    ids = {row["id"] for row in rows}
    if len(ids) != len(rows):
        raise ValueError("Duplicate contract package identity")
    for row in rows:
        if row["kind"] not in KINDS or row["access"] not in {"public", "internal"}:
            raise ValueError("Unknown package kind/access")
        for path in [row["sourceRoot"], *row["proto"], *row["jsonSchemas"]]:
            if not path or ":" in path or "\\" in path or any(p in {"", ".", ".."} for p in path.split("/")):
                raise ValueError("Unsafe package source path")
        if row["kind"] == "go":
            go_row(row)
        elif "channel" in row or "goPackages" in row:
            raise ValueError("Only the Go module row names a Go channel or Go packages: " + row["id"])
        elif not row["sourceRoot"].startswith("src/" + row["access"] + "/"):
            raise ValueError("Package access/source mismatch")
        if any(dep not in ids for dep in row["dependencies"]):
            raise ValueError("Unknown first-party package dependency")
        if Path(row["descriptor"]).name != row["descriptor"] or "\\" in row["descriptor"]:
            raise ValueError("Descriptor filename must be flat")
        if retired(row):
            marker = row["retired"]
            if (not isinstance(marker, dict) or set(marker) != {"task", "reason"}
                    or not isinstance(marker["task"], str) or not re.fullmatch(r"[A-Z]+\.[0-9]+", marker["task"])
                    or not isinstance(marker["reason"], str) or not marker["reason"].strip()):
                raise ValueError("Retired package marker must name its task and reason: " + row["id"])
            if (root / row["sourceRoot"]).exists():
                raise ValueError("Retired package still has producer sources: " + row["id"])
    by_id = {row["id"]: row for row in rows}
    for row in rows:
        if not retired(row) and any(retired(by_id[dep]) for dep in row["dependencies"]):
            raise ValueError("Active package depends on a retired package: " + row["id"])
    return [row for row in rows if (kind is None or row["kind"] == kind) and (include_retired or not retired(row))]


def closure(package_id: str, root: Path = ROOT) -> list[dict]:
    rows = {row["id"]: row for row in packages(root=root, include_retired=True)}
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
