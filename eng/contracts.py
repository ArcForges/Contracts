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
    locked = read_json(ROOT / "eng/Codegen/packages.lock.json")["dependencies"]["net10.0"]["Grpc.Tools"]
    key = "grpc.tools/" + locked["resolved"]
    assets_path = ROOT / "eng/Codegen/obj/project.assets.json"
    folders = []
    if assets_path.is_file():
        assets = read_json(assets_path)
        if key not in {name.lower() for name in assets["libraries"]}:
            raise ValueError("Codegen assets differ from locked Grpc.Tools")
        folders.extend(assets["packageFolders"])
    folders.append(os.environ.get("NUGET_PACKAGES", str(Path.home() / ".nuget/packages")))
    for folder in folders:
        path = Path(folder) / key
        if path.is_dir():
            # NuGet's restore content hash is recorded in .nupkg.metadata;
            # the archive SHA512 can differ for a repository-signed package.
            metadata = path / ".nupkg.metadata"
            if not metadata.is_file() or read_json(metadata).get("contentHash") != locked["contentHash"]:
                raise ValueError("Cached Grpc.Tools package differs from the lock integrity")
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


def generation_packages() -> list[dict]:
    from package_catalog import packages as catalog_packages
    packages = catalog_packages(root=ROOT)
    for row in packages:
        for source in row.get("proto", []):
            if not source.startswith(("public/proto/", "internal/proto/")) or ".." in Path(source).parts:
                raise ValueError("Invalid schema input: " + source)
            if row["access"] == "public" and source.startswith("internal/"):
                raise ValueError("Public generator cannot own private schemas")
    return packages


def normalize_generated(path: Path) -> None:
    lines = path.read_bytes().replace(b"\r\n", b"\n").split(b"\n")
    content = b"\n".join(line.rstrip(b" \t") for line in lines).rstrip(b"\n") + b"\n"
    prefix = b"// SPDX-License-Identifier: Apache-2.0\n// Generated by ArcForges Contracts; do not edit.\n"
    path.write_bytes(prefix + content if not content.startswith(prefix) else content)


SERVICE_HEADER = "// SPDX-License-Identifier: Apache-2.0\n// <auto-generated />\n// Generated by eng/contracts.py; do not edit.\n"


def proto_services(row: dict) -> list[dict]:
    """Return the authored services of a package's own schemas in source order."""
    services = []
    for source in row.get("proto", []):
        text = (ROOT / source).read_text(encoding="utf-8")
        package = re.search(r"^package ([a-z0-9_.]+);", text, re.M)
        namespace = re.search(r'^option csharp_namespace = "([A-Za-z0-9_.]+)";', text, re.M)
        for match in re.finditer(r"^service ([A-Za-z][A-Za-z0-9]*) \{(.*?)^\}", text, re.M | re.S):
            if package is None or namespace is None:
                raise ValueError("Service schema lacks package or C# namespace: " + source)
            methods = re.findall(r"^  rpc ([A-Za-z][A-Za-z0-9]*)\(", match.group(2), re.M)
            services.append({"name": match.group(1), "fullName": package.group(1) + "." + match.group(1),
                             "csharp": namespace.group(1) + "." + match.group(1), "methods": methods,
                             "module": source.split("/proto/", 1)[1][:-len(".proto")] + "_pb.js"})
    return services


def generate_service_catalogues(packages: list[dict], check: bool) -> None:
    """Emit explicit per-package catalogues of generated services; nothing is discovered at runtime."""
    def emit(path: Path, content: str) -> None:
        data = content.encode("utf-8")
        if check:
            if not path.is_file() or path.read_bytes() != data:
                raise ValueError("Stale generated service catalogue: " + str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    for row in packages:
        if row["kind"] == "nuget":
            target = ROOT / row["sourceRoot"] / "Generated/Services/ContractServices.g.cs"
        elif row["kind"] == "npm" and row.get("proto"):
            target = ROOT / row["sourceRoot"] / "src/services/gen/catalog.ts"
        else:
            continue
        services = proto_services(row)
        if not services:
            if target.exists():
                raise ValueError("Package without services has a stale catalogue: " + row["id"])
            continue
        if row["kind"] == "nuget":
            entries = "".join(f"        global::{service['csharp']}.Descriptor,\n" for service in services)
            emit(target, SERVICE_HEADER + f"namespace {row['id']};\n\n"
                 "/// <summary>Generated services owned by this package. Hosts bind each one explicitly\n"
                 "/// through its generated <c>BindService</c> method; nothing is discovered at runtime.</summary>\n"
                 "public static class ContractServices\n{\n"
                 "    /// <summary>The package's authored service descriptors in schema order.</summary>\n"
                 "    public static global::System.Collections.Generic.IReadOnlyList<global::Google.Protobuf.Reflection.ServiceDescriptor> All { get; } =\n"
                 f"    [\n{entries}    ];\n}}\n")
        else:
            imports = "".join(f'import {{ {service["name"]} }} from "../../gen/{service["module"]}";\n' for service in services)
            emit(target, SERVICE_HEADER + imports
                 + "\n/** Generated services owned by this package, in schema order; nothing is discovered at runtime. */\n"
                 + "export const contractServices = Object.freeze([" + ", ".join(s["name"] for s in services) + "] as const);\n")


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
    packages = generation_packages()
    public = next(row for row in packages if row["id"] == "@arcforges/proto")
    def common(row: dict) -> list:
        includes = [ROOT / "public/proto"]
        if row["access"] == "internal":
            includes.append(ROOT / "internal/proto")
        return [protoc, *(arg for include in includes for arg in ("-I", include)),
                *(ROOT / source for source in row["proto"])]
    with tempfile.TemporaryDirectory(prefix="generate-", dir=ARTIFACTS) as directory:
        stage = Path(directory)
        for index, row in enumerate(packages):
            if row["kind"] == "nuget" or (row["kind"] == "npm" and row["access"] == "internal" and row["proto"]):
                from package_catalog import closure
                descriptor_sources = sorted({source for owner in closure(row["id"])
                                             for source in owner["proto"]})
                if descriptor_sources:
                    descriptor_row = {**row, "proto": descriptor_sources}
                    run(*common(descriptor_row), "--include_imports",
                        f"--descriptor_set_out={ARTIFACTS / row['descriptor']}")
            if not row.get("proto") or row["kind"] not in {"nuget", "npm"}:
                continue
            output = stage / str(index)
            output.mkdir()
            if row["kind"] == "nuget":
                descriptor = row["descriptor"]
                if Path(descriptor).name != descriptor:
                    raise ValueError("Descriptor filename must be flat")
                run(*common(row), f"--csharp_out={output}", f"--grpc_out={output}",
                    f"--plugin=protoc-gen-grpc={grpc_plugin}")
                target = ROOT / row["sourceRoot"] / "Generated/Proto"
            else:
                run(*common(row), f"--plugin=protoc-gen-es={es_plugin}", f"--es_out={output}",
                    "--es_opt=target=ts,import_extension=js")
                target = ROOT / row["sourceRoot"] / "src/gen"
                if row["access"] == "internal":
                    # Imported public definitions keep their single generated owner.
                    for file in output.rglob("*.ts"):
                        value = file.read_text(encoding="utf-8")
                        value = re.sub(r'from "(?:\.\./)+(?:foundation|events|hello)/v1/[^"/]+_pb\.js"',
                                       'from "@arcforges/proto"', value)
                        file.write_text(value, encoding="utf-8")
            for file in output.rglob("*"):
                if file.is_file():
                    normalize_generated(file)
            sync_generated(output, target, check)
            if row["kind"] == "npm":
                barrel = "// SPDX-License-Identifier: Apache-2.0\n// Generated by ArcForges Contracts; do not edit.\n"
                barrel += "".join(f'export * from "./gen/{file.relative_to(output).as_posix()[:-3]}.js";\n'
                                  for file in sorted(output.rglob("*.ts")))
                barrel += 'export * from "./shapes/gen/proto.js";\n'
                if row['id'] == '@arcforges/proto':
                    barrel += 'export * from "./values.js";\n'
                    barrel += 'export * from "./wire.js";\n'
                if proto_services(row):
                    barrel += 'export * from "./services/gen/catalog.js";\n'
                index_file = ROOT / row["sourceRoot"] / "src/index.ts"
                if check:
                    if not index_file.is_file() or index_file.read_text(encoding="utf-8") != barrel:
                        raise ValueError("Stale generated export barrel: " + str(index_file))
                else:
                    index_file.write_text(barrel, encoding="utf-8")
        run(*common(public), "--include_imports", f"--descriptor_set_out={ARTIFACTS / 'contracts.binpb'}")
        from kotlin_tools import generate as generate_kotlin
        maven = next(row for row in packages if row["id"] == "io.github.arcforges:contracts-proto")
        generate_kotlin(protoc, [str(ROOT / source) for source in maven["proto"]], stage, check)
        generate_service_catalogues(packages, check)
        from generate_shapes import generate as generate_shapes
        generate_shapes(check)
        from generate_fixtures import generate as generate_fixtures
        generate_fixtures(check)
        from generate_values import generate as generate_values
        generate_values(check)
    print("Generated bindings match the authored proto." if check else "Generated C#, TypeScript, Java/Kotlin and descriptor set.")


def build() -> None:
    run(sys.executable, ROOT / "eng/check_licences.py")
    run("node", ROOT / "eng/check_contract_access.mjs")
    run(sys.executable, ROOT / "eng/check_foundation.py", "--generated", "--self-test")
    run(sys.executable, ROOT / "eng/check_serialization.py", "--report", ARTIFACTS / "evidence/serialization-policy.json")
    run("dotnet", "build", "ArcForges.Contracts.slnx", "-c", "Release", "--no-restore")
    from build_identity import build as identity
    write_json(ARTIFACTS / "expected-build.json", identity())
    projects = [ROOT / name for name in run("git", "ls-files", "*.csproj", capture=True).splitlines()]
    assemblies = [project.parent / "bin/Release/net10.0" / (project.stem + ".dll") for project in projects]
    run("dotnet", ROOT / "tests/public/HelloClient/bin/Release/net10.0/HelloClient.dll",
        "--inspect-build", ARTIFACTS / "expected-build.json", *assemblies)
    structure_tests = ROOT / "tests/StructureTests/bin/Release/net10.0/StructureTests.dll"
    run("dotnet", structure_tests, ROOT, "--foundation-exchange")
    run(NPM, "run", "build")
    run(NPM, "test")
    run("node", ROOT / "tests/public/foundation.test.mjs", "--exchange")
    run("dotnet", structure_tests, ROOT, "--verify-foundation-exchange")
    serialization_probe()
    from kotlin_tools import build as build_kotlin
    build_kotlin()


def serialization_probe() -> None:
    """Publish the WP03.02 probe with Native AOT for this host and run the independent vectors once."""
    rid = {"Windows": "win-x64", "Linux": "linux-x64"}.get(platform.system())
    if rid is None or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("The Native AOT serialization probe is selected for x64 Windows and Linux only")
    output = ARTIFACTS / "serialization-probe" / rid
    # AOT and trim diagnostics are errors; every contract library is rooted for complete analysis.
    # The project selects the host RID itself; -r would also flow into every referenced library restore.
    run("dotnet", "publish", ROOT / "tests/public/SerializationProbe/SerializationProbe.csproj", "-c", "Release",
        "-o", output)
    probe = output / ("SerializationProbe.exe" if rid == "win-x64" else "SerializationProbe")
    run(probe, ROOT, "--report", ARTIFACTS / f"evidence/serialization-probe-{rid}.json")


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
