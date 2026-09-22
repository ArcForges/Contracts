# SPDX-License-Identifier: Apache-2.0
"""Enforce the WP03.02 serialization posture over tracked sources, locks and generated outputs.

Generated protobuf/gRPC code is the only business wire implementation. Declared HTTP
exceptions use strict source-generated JSON. Nothing discovers schemas or services at
runtime, and reflection serializers cannot enter any lock. The build and AOT analyzers
enforce the compiled closure; this gate rejects declarations that would bypass them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

# Reflection serializers, runtime schema loaders and discovery services, by ecosystem.
FORBIDDEN_NUGET = {
    "newtonsoft.json": "reflection JSON serializer",
    "refit": "reflection-capable typed HTTP client",
    "refit.httpclientfactory": "reflection-capable typed HTTP client",
    "refit.newtonsoft.json": "reflection-capable typed HTTP client",
    "protobuf-net": "reflection protobuf serializer",
    "protobuf-net.core": "reflection protobuf serializer",
    "protobuf-net.grpc": "code-first reflection gRPC",
    "grpc.reflection": "gRPC server reflection discovery",
    "grpc.aspnetcore.server.reflection": "gRPC server reflection discovery",
    "microsoft.aspnetcore.grpc.jsontranscoding": "JSON transcoding of business services",
    "microsoft.aspnetcore.grpc.swagger": "runtime schema publication",
    "castle.core": "dynamic proxy generation",
    "messagepack": "alternate reflection serializer",
    "utf8json": "alternate reflection serializer",
    "servicestack.text": "alternate reflection serializer",
}
FORBIDDEN_NPM = {
    "protobufjs": "reflection protobuf runtime",
    "google-protobuf": "alternate protobuf runtime",
    "@grpc/proto-loader": "runtime proto schema loading",
    "grpc-web": "alternate gRPC-Web runtime",
    "reflect-metadata": "runtime reflection metadata",
    "class-transformer": "reflection object mapping",
}
FORBIDDEN_MAVEN = {
    "com.google.protobuf:protobuf-java": "full reflective protobuf runtime",
    "com.google.protobuf:protobuf-java-util": "protobuf JSON mapping",
    "io.grpc:grpc-services": "gRPC server reflection discovery",
    "io.grpc:grpc-protobuf": "full reflective protobuf runtime",
}
# Well-known types that defer schema selection to runtime.
FORBIDDEN_IMPORTS = ("google/protobuf/any.proto", "google/protobuf/struct.proto", "google/protobuf/type.proto",
                     "google/protobuf/api.proto", "google/protobuf/descriptor.proto", "google/protobuf/source_context.proto")
FORBIDDEN_PROTO_TYPES = re.compile(r"\bgoogle\.protobuf\.(Any|Struct|Value|ListValue|Type|Api|FileDescriptorSet|DescriptorProto)\b")
CSHARP_APIS = {
    r"\bJsonFormatter\b": "protobuf JSON formatting",
    r"\bJsonParser\b": "protobuf JSON parsing",
    r"\bTypeRegistry\b": "runtime type registry",
    r"\bAny\.(Pack|Unpack|TryUnpack)\b": "Any packing",
    r"\bWithDiscardUnknownFields\b": "unknown-field discard",
    r"\bActivator\.CreateInstance\b": "reflection construction",
    r"\bType\.GetType\s*\(": "runtime type lookup",
    r"\bAssembly\.(Load|LoadFrom|LoadFile|GetTypes|GetExportedTypes)\b": "assembly scanning",
    r"\bMakeGenericType\b": "runtime generic construction",
    r"\bSystem\.Reflection\.Emit\b": "runtime code generation",
    r"\bDynamicMethod\b": "runtime code generation",
    r"\bJsonSerializerIsReflectionEnabledByDefault\b": "reflection JSON switch",
    r"\bDefaultJsonTypeInfoResolver\b": "reflection JSON metadata",
}
TYPESCRIPT_APIS = {
    r"\b(toJson|fromJson|toJsonString|fromJsonString|mergeFromJson)\s*\(": "protobuf JSON mapping",
    r"\bcreate(File)?Registry\s*\(": "runtime schema registry",
    r"\bany(Pack|Unpack|Is)\s*\(": "Any packing",
    r"\breadUnknownFields\s*:\s*false\b": "unknown-field discard",
    r"\buseBinaryFormat\s*:\s*false\b": "JSON business transport",
    r"\bnew\s+Function\s*\(": "runtime code generation",
    r"\beval\s*\(": "runtime code generation",
}
HANDWRITTEN_CSHARP = {
    r"\b(class|struct|record)\s+\w+(<[^>{]*>)?\s*:[^{;]*\b(pb::)?I(Buffer)?Message\b": "handwritten protobuf message",
    r"\bnew\s+(pb::)?MessageParser<": "handwritten protobuf parser",
    r"\bJsonSerializerContext\b": "handwritten JSON metadata context",
    r"\[\s*(global::System\.Text\.Json\.Serialization\.)?JsonPropertyName\b": "handwritten JSON wire record",
}
HANDWRITTEN_TYPESCRIPT = {r"\b(fileDesc|messageDesc|serviceDesc|enumDesc)\s*\(": "handwritten protobuf descriptor"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def tracked(root: Path) -> list[str]:
    output = subprocess.check_output(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"], text=True)
    return sorted(path for path in output.splitlines() if (root / path).is_file())


def generated(path: str) -> bool:
    parts = path.split("/")
    return "Generated" in parts or "gen" in parts or "generated" in parts


def check_locks(root: Path, files: list[str]) -> int:
    count = 0
    for path in files:
        name = path.rsplit("/", 1)[-1]
        if name == "packages.lock.json":
            for graph in json.loads((root / path).read_text(encoding="utf-8"))["dependencies"].values():
                for package in graph:
                    reason = FORBIDDEN_NUGET.get(package.lower())
                    require(reason is None, f"{path}: forbidden NuGet dependency {package} ({reason})")
                    count += 1
        elif name == "package-lock.json":
            for key in json.loads((root / path).read_text(encoding="utf-8"))["packages"]:
                package = key.rsplit("node_modules/", 1)[-1] if "node_modules/" in key else None
                reason = FORBIDDEN_NPM.get(package) if package else None
                require(reason is None, f"{path}: forbidden npm dependency {package} ({reason})")
                count += 1
        elif name.endswith(".lockfile"):
            for line in (root / path).read_text(encoding="utf-8").splitlines():
                if line.startswith("#") or ":" not in line:
                    continue
                coordinate = line.split("=", 1)[0].rsplit(":", 1)[0]
                reason = FORBIDDEN_MAVEN.get(coordinate)
                require(reason is None, f"{path}: forbidden Maven dependency {coordinate} ({reason})")
                count += 1
    return count


def check_protos(root: Path, files: list[str]) -> int:
    protos = [path for path in files if path.endswith(".proto")]
    for path in protos:
        text = (root / path).read_text(encoding="utf-8")
        for name in FORBIDDEN_IMPORTS:
            require(f'"{name}"' not in text, f"{path}: runtime-selected well-known type import {name}")
        match = FORBIDDEN_PROTO_TYPES.search(text)
        require(match is None, f"{path}: runtime-selected well-known type {match.group(0) if match else ''}")
        require("ServerReflection" not in text, f"{path}: gRPC server reflection service")
    return len(protos)


def scan(root: Path, files: list[str], suffix: str, rules: dict[str, str], handwritten: dict[str, str]) -> int:
    count = 0
    for path in files:
        if not path.startswith("src/") or not path.endswith(suffix):
            continue
        is_generated = generated(path)
        if is_generated and ("/Generated/Proto/" in path or "/src/gen/" in path):
            continue  # pinned protoc/plugin output; regeneration and compiler analyzers own it
        text = (root / path).read_text(encoding="utf-8")
        for pattern, reason in rules.items():
            match = re.search(pattern, text)
            require(match is None, f"{path}: forbidden {reason} ({match.group(0) if match else ''})")
        if not is_generated:
            for pattern, reason in handwritten.items():
                match = re.search(pattern, text)
                require(match is None, f"{path}: {reason} outside generated owners ({match.group(0) if match else ''})")
        count += 1
    return count


def msbuild_property(path: Path, name: str) -> list[str]:
    return [element.text or "" for element in ET.parse(path).iter() if element.tag.split("}")[-1] == name]


def check_projects(root: Path, files: list[str]) -> int:
    require(msbuild_property(root / "Directory.Build.props", "JsonSerializerIsReflectionEnabledByDefault") == ["false"],
            "Directory.Build.props must disable reflection-based System.Text.Json")
    projects = [path for path in files if path.endswith(".csproj")]
    packable = 0
    for path in projects:
        require(not msbuild_property(root / path, "JsonSerializerIsReflectionEnabledByDefault"),
                f"{path}: project overrides the reflection-disabled JSON default")
        if path.startswith("src/") and msbuild_property(root / path, "IsPackable") == ["true"]:
            require(msbuild_property(root / path, "IsAotCompatible") == ["true"], f"{path}: packed library is not AOT-compatible")
            packable += 1
    return packable


def check_contexts(root: Path, files: list[str]) -> int:
    sys.path.insert(0, str(root / "eng"))
    from generate_shapes import CS_CONTEXT_OPTIONS
    contexts = 0
    for path in files:
        if not path.endswith(".cs") or "/Generated/Proto/" in path:
            continue
        text = (root / path).read_text(encoding="utf-8")
        for match in re.finditer(r"public partial class (\w+) : global::System\.Text\.Json\.Serialization\.JsonSerializerContext", text):
            require("/Generated/Shapes/" in path, f"{path}: JSON metadata context outside generated shapes")
            require(CS_CONTEXT_OPTIONS in text[:match.start()], f"{path}: {match.group(1)} lacks the strict generation options")
            contexts += 1
    return contexts


def check_services(root: Path) -> int:
    sys.path.insert(0, str(root / "eng"))
    from contracts import proto_services
    from package_catalog import packages
    services = 0
    for row in packages(root=root):
        if row["kind"] == "nuget":
            catalogue = root / row["sourceRoot"] / "Generated/Services/ContractServices.g.cs"
            expected = [f"global::{service['csharp']}.Descriptor," for service in proto_services(row)]
        elif row["kind"] == "npm" and row.get("proto"):
            catalogue = root / row["sourceRoot"] / "src/services/gen/catalog.ts"
            expected = [service["name"] for service in proto_services(row)]
        else:
            continue
        if not expected:
            require(not catalogue.exists(), f"{row['id']}: catalogue lists services absent from its schemas")
            continue
        require(catalogue.is_file(), f"{row['id']}: missing generated service catalogue")
        text = catalogue.read_text(encoding="utf-8")
        for entry in expected:
            require(entry in text, f"{row['id']}: catalogue omits {entry}")
        services += len(expected)
    return services


def audit(root: Path = ROOT) -> dict:
    files = tracked(root)
    return {
        "result": "passed",
        "lockEntries": check_locks(root, files),
        "protoFiles": check_protos(root, files),
        "csharpSources": scan(root, files, ".cs", CSHARP_APIS, HANDWRITTEN_CSHARP),
        "typescriptSources": scan(root, files, ".ts", TYPESCRIPT_APIS, HANDWRITTEN_TYPESCRIPT),
        "packableAotProjects": check_projects(root, files),
        "strictJsonContexts": check_contexts(root, files),
        "catalogueServices": check_services(root),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    options = parser.parse_args()
    try:
        result = audit()
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if options.report:
        options.report.parent.mkdir(parents=True, exist_ok=True)
        options.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
