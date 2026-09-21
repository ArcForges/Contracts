# SPDX-License-Identifier: Apache-2.0
"""Portable entry points. Public packages do not import this build tooling."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
DOTNET_PROJECT = ROOT / "src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj"
NPM_PROJECTS = [ROOT / "src/public/ts/proto", ROOT / "src/public/ts/api-client"]
NUGET_ID = "ArcForges.Contracts.PublicApi"
NPM_IDS = ["@arcforges/proto", "@arcforges/api-client"]
NPM = shutil.which("npm.cmd" if os.name == "nt" else "npm") or "npm"


def run(*args: object, cwd: Path = ROOT, capture: bool = False, env: dict | None = None) -> str:
    command = [str(arg) for arg in args]
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(command, cwd=cwd, env=env, check=True, text=True,
                            encoding="utf-8", errors="replace", capture_output=capture)
    return result.stdout if capture else ""


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_commit() -> str:
    return run("git", "rev-parse", "HEAD", capture=True).strip()


def version(value: str) -> str:
    from release_channels import CI, stable
    if not stable(value) and not re.fullmatch(CI, value):
        raise ValueError("Expected X.Y.Z or 1.0.0-ci.<run-number>.<run-attempt> (no leading zeroes)")
    return value


def check_tools() -> None:
    expected_node = ROOT.joinpath(".node-version").read_text().strip()
    if run("node", "--version", capture=True).strip() != "v" + expected_node:
        raise ValueError(f"Select Node {expected_node} from .node-version before continuing")
    if run(NPM, "--version", capture=True).strip() != "11.19.0":
        raise ValueError("Use npm 11.19.0 with the pinned Node distribution")
    if run("dotnet", "--version", capture=True).strip() != "10.0.400":
        raise ValueError("Install the .NET SDK pinned in global.json")


def restore(update_locks: bool = False) -> None:
    check_tools()
    run(NPM, "install" if update_locks else "ci", "--ignore-scripts")
    run("dotnet", "restore", "ArcForges.Contracts.slnx",
        "--force-evaluate" if update_locks else "--locked-mode")
    from kotlin_tools import restore as restore_kotlin
    restore_kotlin(update_locks)


def grpc_tools() -> Path:
    assets = read_json(ROOT / "eng/Codegen/obj/project.assets.json")
    key = next(key for key in assets["libraries"] if key.lower().startswith("grpc.tools/"))
    for folder in assets["packageFolders"]:
        path = Path(folder) / key.lower()
        if path.is_dir():
            return path
    raise FileNotFoundError("Restore the locked Codegen project before generating")


def sync_generated(actual: Path, expected: Path, check: bool) -> None:
    files = {path.relative_to(actual): path.read_bytes() for path in actual.rglob("*") if path.is_file()}
    previous = {path.relative_to(expected): path.read_bytes() for path in expected.rglob("*") if path.is_file()}
    if check:
        changed = sorted(str(path) for path in files.keys() | previous.keys()
                         if files.get(path) != previous.get(path))
        if changed:
            raise ValueError(f"Stale generated files under {expected}: {', '.join(changed)}")
    else:
        expected.mkdir(parents=True, exist_ok=True)
        for path in previous.keys() - files.keys():
            (expected / path).unlink()
        for path, data in files.items():
            (expected / path).parent.mkdir(parents=True, exist_ok=True)
            (expected / path).write_bytes(data)


def generate(check: bool = False) -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    platform_key = {"Windows": "windows_x64", "Linux": "linux_x64", "Darwin": "macosx_x64"}.get(platform.system())
    if platform.machine().lower() not in {"amd64", "x86_64"} or platform_key is None:
        raise ValueError("The bootstrap producer currently supports x64 Windows/Linux/macOS; consumers are managed")
    tool_dir = grpc_tools() / "tools" / platform_key
    suffix = ".exe" if os.name == "nt" else ""
    protoc = tool_dir / ("protoc" + suffix)
    grpc_plugin = tool_dir / ("grpc_csharp_plugin" + suffix)
    es_plugin = ROOT / "node_modules/.bin" / ("protoc-gen-es.cmd" if os.name == "nt" else "protoc-gen-es")
    protos = sorted(str(path.relative_to(ROOT / "public/proto")).replace("\\", "/")
                    for path in (ROOT / "public/proto").rglob("*.proto"))
    with tempfile.TemporaryDirectory(prefix="generate-", dir=ARTIFACTS) as directory:
        stage = Path(directory)
        (stage / "csharp").mkdir()
        (stage / "ts").mkdir()
        common = [protoc, "-I", ROOT / "public/proto", *protos]
        run(*common, f"--csharp_out={stage / 'csharp'}", f"--grpc_out={stage / 'csharp'}",
            f"--plugin=protoc-gen-grpc={grpc_plugin}", "--include_imports",
            f"--descriptor_set_out={stage / 'contracts.binpb'}")
        run(*common, f"--plugin=protoc-gen-es={es_plugin}", f"--es_out={stage / 'ts'}",
            "--es_opt=target=ts")
        from kotlin_tools import generate as generate_kotlin
        generate_kotlin(protoc, protos, stage, check)
        # Canonical LF and one final newline; never alter authored schema contents.
        for generated in [*(stage / "csharp").rglob("*.cs"), *(stage / "ts").rglob("*.ts")]:
            generated.write_bytes(generated.read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n") + b"\n")
        sync_generated(stage / "csharp", DOTNET_PROJECT.parent / "Generated", check)
        sync_generated(stage / "ts", NPM_PROJECTS[0] / "src/gen", check)
        shutil.copyfile(stage / "contracts.binpb", ARTIFACTS / "contracts.binpb")
    print("Generated bindings match the authored proto." if check else "Generated C#, TypeScript, Java/Kotlin and descriptor set.")


def build() -> None:
    run(sys.executable, ROOT / "eng/check_licences.py")
    run("node", ROOT / "eng/check_contract_access.mjs")
    run("dotnet", "build", "ArcForges.Contracts.slnx", "-c", "Release", "--no-restore")
    from build_identity import build as identity
    write_json(ARTIFACTS / "expected-build.json", identity())
    projects = [ROOT / name for name in run("git", "ls-files", "*.csproj", capture=True).splitlines()]
    assemblies = [project.parent / "bin/Release/net10.0" / (project.stem + ".dll") for project in projects]
    run("dotnet", ROOT / "tests/public/HelloClient/bin/Release/net10.0/HelloClient.dll",
        "--inspect-build", ARTIFACTS / "expected-build.json", *assemblies)
    run(NPM, "run", "build")
    run(NPM, "test")
    from kotlin_tools import build as build_kotlin
    build_kotlin()


def verify_local() -> None:
    restore()
    generate(check=True)
    build()
    run(NPM, "run", "format:check")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("restore").add_argument("--update-locks", action="store_true")
    sub.add_parser("generate").add_argument("--check", action="store_true")
    sub.add_parser("build")
    sub.add_parser("verify-local")
    pack_parser = sub.add_parser("pack")
    pack_parser.add_argument("--version", default="1.0.0-ci.0.0", type=version)
    check_parser = sub.add_parser("verify-artifacts")
    check_parser.add_argument("--directory", type=Path, default=ARTIFACTS / "packages")
    check_parser.add_argument("--commit")
    consumer_parser = sub.add_parser("consume")
    consumer_parser.add_argument("--directory", type=Path, default=ARTIFACTS / "packages")
    consumer_parser.add_argument("--aot", action="store_true")
    consumer_parser.add_argument("--snapshot-registry", action="store_true", help="Verify and consume the live Sonatype snapshot")
    consumer_parser.add_argument("--update-kotlin-locks", action="store_true")
    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("registry", choices=["nuget", "npm", "maven"])
    publish_parser.add_argument("--directory", type=Path, default=ARTIFACTS / "packages")
    args = parser.parse_args()
    if args.command == "restore":
        restore(args.update_locks)
    elif args.command == "generate":
        generate(args.check)
    elif args.command == "build":
        build()
    elif args.command == "verify-local":
        verify_local()
    else:
        from packaging_tools import pack, verify_artifacts, publish
        if args.command == "pack":
            pack(args.version)
        elif args.command == "verify-artifacts":
            verify_artifacts(args.directory.resolve(), args.commit)
        elif args.command == "consume":
            from consumer_tools import consume
            consume(args.directory.resolve(), args.aot, args.update_kotlin_locks, args.snapshot_registry)
        elif args.command == "publish":
            publish(args.directory.resolve(), args.registry)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
