# SPDX-License-Identifier: Apache-2.0
"""Read committed dependency inputs from explicitly selected sibling Git repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

REPOSITORIES = ("ArcForges", "Cloud", "Web", "DesktopPlatform", "Mobile", "AI",
                "ArcScope", "ArcSlate", "ArcNotes", "Contracts")
INDEPENDENT = {"Mobile", "AI", "ArcScope", "ArcSlate", "ArcNotes"}
IDENTITY = re.compile(r"(?:https://github[.]com/|git@github[.]com:|ssh://git@github[.]com/)ArcForges/([^/]+?)(?:[.]git)?/?\Z", re.I)
PACKAGE = re.compile(r"(?:ArcForges[.][A-Za-z0-9_.-]+|@arcforges/[a-z0-9_-]+|github[.]com/ArcForges/Contracts/go)\Z")
VERSION = re.compile(r"[A-Za-z0-9_.+^~*<>=!|()$@{}\[\], /-]{1,160}\Z")
MAX_INPUT_BYTES = 4 * 1024 * 1024


class Unavailable(Exception):
    """Only fixed diagnostic codes leave the scanner."""


def git(repository: Path, *arguments: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repository), *arguments],
                            capture_output=True, timeout=30)
    if result.returncode:
        raise Unavailable("git_read_failed")
    return result.stdout


def selected_input(path: str) -> bool:
    name = PurePosixPath(path).name
    return (name.endswith((".csproj", ".fsproj", ".vbproj"))
            or name in {"Directory.Build.props", "Directory.Build.targets", "Directory.Packages.props",
                        "package.json", "go.mod"})


def read_repository(workspace: Path, name: str) -> tuple[dict, dict[str, str]]:
    root = workspace / name
    result = {"repository": name, "state": "unknown", "revision": None,
              "dirty": None, "scan_basis": "committed_HEAD", "input_files": [],
              "independent_product": name in INDEPENDENT, "deletion_authorized": False}
    inputs = {}
    try:
        if not root.is_dir():
            raise Unavailable("repository_missing")
        remote = git(root, "remote", "get-url", "origin").decode("utf-8").strip()
        match = IDENTITY.fullmatch(remote)
        if match is None or match[1].casefold() != name.casefold():
            raise Unavailable("origin_identity_mismatch")
        result["origin_identity"] = f"ArcForges/{name}"
        revision = git(root, "rev-parse", "HEAD").decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
            raise Unavailable("revision_invalid")
        result["revision"] = revision
        status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
        result["dirty"] = bool(status)
        paths = git(root, "ls-tree", "-r", "-z", "--name-only", revision).decode("utf-8").split("\0")
        for path in sorted(path for path in paths if selected_input(path)):
            content = git(root, "show", f"{revision}:{path}")
            if len(content) > MAX_INPUT_BYTES:
                raise Unavailable("dependency_input_too_large")
            inputs[path] = content.decode("utf-8-sig")
            result["input_files"].append({"path": path, "sha256": hashlib.sha256(content).hexdigest()})
        if git(root, "rev-parse", "HEAD").decode("ascii").strip() != revision:
            raise Unavailable("revision_changed_during_scan")
        result["state"] = "observed"
    except (Unavailable, OSError, UnicodeError, subprocess.SubprocessError) as error:
        result["diagnostic"] = str(error) if isinstance(error, Unavailable) else "repository_read_failed"
        inputs = {}
    return result, inputs


def xml_rows(text: str):
    root = ET.fromstring(text)
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in {"PackageReference", "PackageVersion", "ProjectReference"}:
            continue
        identity = element.get("Include") or element.get("Update")
        if not identity:
            continue
        version = element.get("VersionOverride") or element.get("Version")
        if version is None:
            version = next((child.text for child in element if child.tag.rsplit("}", 1)[-1] == "Version"), None)
        # Conditions may occur at any ancestor. Report their presence conservatively;
        # this inventory does not evaluate MSBuild and never claims a selected version.
        conditional = any(item.get("Condition") for item in root.iter())
        yield tag, identity, version, conditional


def producer_packages(all_inputs: dict[str, dict[str, str]]) -> dict[str, str]:
    packages = {"github.com/ArcForges/Contracts/go": "Contracts",
                "@arcforges/ai-internal": "Contracts", "@arcforges/proto": "Contracts",
                "@arcforges/api-client": "Contracts", "@arcforges/contract-fixtures": "Contracts",
                "@arcforges/operator-client": "Contracts"}
    for repository in ("Contracts", "DesktopPlatform"):
        for path, content in all_inputs[repository].items():
            if not path.endswith(".csproj"):
                continue
            root = ET.fromstring(content)
            # Explicit IDs override the SDK default (the project filename).
            identity = next((item.text for item in root.iter()
                             if item.tag.rsplit("}", 1)[-1] == "PackageId"), PurePosixPath(path).stem)
            if identity and PACKAGE.fullmatch(identity):
                packages[identity] = repository
    return packages


def parse_inputs(repository: str, inputs: dict[str, str], producers: dict[str, str]) -> tuple[list, list]:
    references, declarations = [], []

    def append(path, kind, identity, version=None, conditional=False):
        target = PurePosixPath(identity.replace("\\", "/")).stem if kind == "ProjectReference" else identity
        producer = producers.get(target)
        if producer is None and (target.startswith("ArcForges.Contracts.") or target == "ArcForges.Sdk.Contracts"):
            producer = "Contracts"
        if producer is None:
            return
        row = {"repository": repository, "input": path, "kind": kind, "dependency": target,
               "producer": producer, "version_expression": version if version and VERSION.fullmatch(version) else None,
               "conditional_input": conditional, "protected_from_deletion": True}
        (declarations if kind == "PackageVersion" else references).append(row)

    for path, content in sorted(inputs.items()):
        name = PurePosixPath(path).name
        if name == "package.json":
            data = json.loads(content)
            for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                for identity, version in data.get(field, {}).items():
                    append(path, f"npm_{field}", identity, version if isinstance(version, str) else None)
        elif name == "go.mod":
            for line in content.splitlines():
                line = line.split("//", 1)[0].strip()
                if line.startswith("require "):
                    line = line[len("require "):].strip()
                tokens = line.split()
                if len(tokens) >= 2:
                    append(path, "go_require", tokens[0], tokens[1])
        else:
            for kind, identity, version, conditional in xml_rows(content):
                append(path, kind, identity, version, conditional)
    return references, declarations


def inventory(workspace: Path) -> dict:
    repositories, all_inputs = [], {}
    for name in REPOSITORIES:
        result, inputs = read_repository(workspace, name)
        repositories.append(result)
        all_inputs[name] = inputs
    report = {"schema": 1, "kind": "arcforges-v2-consumer-inventory",
              "repositories": repositories, "references": [], "version_declarations": [],
              "deletion_authorized": False,
              "protected_shared_surface": "arcforges.local.sandbox.v1 is DesktopPlatform ContentSandbox, not V2 CLI Sandbox",
              "limits": ["Committed authored inputs only; dirty and untracked changes are not consumer evidence.",
                         "References are declared inputs, not evaluated conditional MSBuild resolution or runtime use.",
                         "Missing or mismatched repositories remain unknown; no source/package deletion is authorized."]}
    try:
        producers = producer_packages(all_inputs)
        report["producer_inventory_complete"] = all(next(row for row in repositories if row["repository"] == name)["state"] == "observed"
                                                     for name in ("Contracts", "DesktopPlatform"))
        for row in repositories:
            try:
                refs, declarations = parse_inputs(row["repository"], all_inputs[row["repository"]], producers)
                report["references"].extend(refs)
                report["version_declarations"].extend(declarations)
            except (ET.ParseError, ValueError, TypeError, AttributeError):
                row["state"] = "unknown"
                row["diagnostic"] = "dependency_input_invalid"
    except (ET.ParseError, ValueError, TypeError):
        report["producer_inventory_complete"] = False
        report["diagnostic"] = "producer_input_invalid"
    report["complete"] = report["producer_inventory_complete"] and all(row["state"] == "observed" for row in repositories)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path, help="Explicit directory containing the known Git repositories")
    args = parser.parse_args()
    report = inventory(args.workspace)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
