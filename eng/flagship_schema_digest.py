# SPDX-License-Identifier: Apache-2.0
"""Schema digest of the adopted flagship design contracts (AF-CON-01).

For every file listed in eng/flagship-contracts.json, the digest is the SHA-256 of that file's compiled
FileDescriptorProto inside its package descriptor set, compiled exactly as the packages are generated
(pinned protoc, the package's dependency closure, --include_imports; the bytes packed as contracts.binpb).
A FileDescriptorProto carries every declaration, number, type, label, presence, oneof, json_name, option
and import of the file, but no comments, so equal bytes mean an identical schema. The combined digest is
the SHA-256 of the sorted "<file> <sha256>" lines.

With --design PATH (an ArcForges-Design checkout), the specification protos under docs/contracts/proto are
compiled with the same protoc against the design's pinned foundation reference and every adopted file must
produce the same descriptor bytes. Offline; nothing is fetched or installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RECORD = "eng/flagship-contracts.json"
DESIGN_PROTO = "docs/contracts/proto"
DESIGN_FOUNDATION = "docs/contracts/reference/contracts-b774c322"


def protoc() -> Path:
    sys.path.insert(0, str(ROOT / "eng"))
    from contracts import grpc_tools
    key = {"Windows": "windows_x64", "Linux": "linux_x64"}.get(platform.system())
    if key is None or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("The schema digest uses the pinned x64 Windows or Linux protoc")
    return grpc_tools() / "tools" / key / ("protoc.exe" if os.name == "nt" else "protoc")


def file_descriptors(data: bytes) -> dict[str, bytes]:
    """Map each file name in a FileDescriptorSet to its exact FileDescriptorProto bytes."""
    from check_compatibility import fields, text
    result = {}
    for raw in fields(data).get(1, []):
        name = text(fields(raw), 1)
        if name in result:
            raise ValueError("Duplicate descriptor file " + name)
        result[name] = raw
    return result


def compile_set(includes: list[Path], sources: list[Path], output: Path) -> dict[str, bytes]:
    command = [str(protoc()), *(f"-I{path}" for path in includes), "--include_imports",
               f"--descriptor_set_out={output}", *(str(path) for path in sources)]
    subprocess.run(command, check=True, capture_output=True)
    return file_descriptors(output.read_bytes())


def repository_descriptors(root: Path, record: dict, scratch: Path) -> dict[str, bytes]:
    """Compile each owning package's descriptor set as eng/contracts.py generate does."""
    sys.path.insert(0, str(root / "eng"))
    from package_catalog import closure, packages
    rows = {row["id"]: row for row in packages(root=root)}
    result: dict[str, bytes] = {}
    for package in sorted({row["package"] for row in record["files"]}):
        row = rows[package]
        includes = [root / "public/proto"] + ([root / "internal/proto"] if row["access"] == "internal" else [])
        sources = sorted({source for owner in closure(package, root) for source in owner["proto"]})
        compiled = compile_set(includes, [root / source for source in sources], scratch / (package + ".binpb"))
        for file in (item for item in record["files"] if item["package"] == package):
            result[file["design"]] = compiled[file["design"]]
    return result


FOUNDATION = "arcforges/foundation/v1/foundation.proto"


def design_descriptors(design: Path, record: dict, scratch: Path) -> dict[str, bytes]:
    """The adopted files plus the design's pinned foundation reference, compiled together."""
    base = design / DESIGN_PROTO
    sources = sorted(base.rglob("*.proto"))
    compiled = compile_set([base, design / DESIGN_FOUNDATION], sources, scratch / "design.binpb")
    return {name: compiled[name] for name in [*(file["design"] for file in record["files"]), FOUNDATION]}


def digest(descriptors: dict[str, bytes]) -> dict:
    files = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(descriptors.items())}
    lines = "".join(f"{name} {value}\n" for name, value in files.items())
    # A list of {file, sha256} rows keeps each digest off the line that names its file.
    return {"combined": hashlib.sha256(lines.encode("utf-8")).hexdigest(),
            "files": [{"file": name, "sha256": value} for name, value in files.items()]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--design", type=Path, help="ArcForges-Design checkout to compare with")
    args = parser.parse_args()
    record = json.loads((args.root / RECORD).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="flagship-digest-") as directory:
        scratch = Path(directory)
        repository = repository_descriptors(args.root.resolve(), record, scratch)
        report = {"schemaVersion": "flagship-schema-digest.v1", "repository": digest(repository)}
        errors = []
        if record.get("schemaDigest") != report["repository"]:
            errors.append("the repository digest differs from eng/flagship-contracts.json schemaDigest")
        if args.design is not None:
            design = design_descriptors(args.design.resolve(), record, scratch)
            foundation = compile_set([args.root.resolve() / "public/proto"], [args.root.resolve() / "public/proto" / FOUNDATION],
                                     scratch / "foundation.binpb")[FOUNDATION]
            report["foundationIdentical"] = design.pop(FOUNDATION) == foundation
            report["design"] = digest(design)
            if not report["foundationIdentical"]:
                errors.append(FOUNDATION + ": the design's pinned reference differs from the repository's foundation")
            errors.extend(f"{name}: compiled descriptor differs from the design" for name in sorted(repository)
                          if repository[name] != design[name])
    report["errors"] = errors
    print(json.dumps(report, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
