# SPDX-License-Identifier: Apache-2.0
"""Kotlin generation uses the same protoc and immutable schema as C# and TS."""

from __future__ import annotations

import os
from pathlib import Path
import platform
import tomllib

from contracts import ARTIFACTS, ROOT, run, sync_generated

MAVEN_GROUP = "io.github.arcforges"
GENERATED_MODULES = ("contracts-proto", "contracts-client", "contracts-connect-client")
MAVEN_MODULES = (*GENERATED_MODULES, "contract-fixtures")


def gradle(*args: object, cwd: Path = ROOT, env: dict | None = None) -> str:
    wrapper = cwd / ("gradlew.bat" if os.name == "nt" else "gradlew")
    # shell=True is unnecessary even for the Windows wrapper; arguments contain no secrets.
    return run(wrapper, "--no-daemon", "--console=plain", *args, cwd=cwd, env=env)


def restore(update_locks: bool = False) -> None:
    args = ["resolveLockedDependencies", "resolveCodegenTools"]
    if update_locks:
        args += ["--write-locks", "--write-verification-metadata", "sha256"]
    gradle(*args)


def generate(protoc: Path, protos: list[str], stage: Path, check: bool) -> None:
    versions = tomllib.loads((ROOT / "gradle/libs.versions.toml").read_text())["versions"]
    classifier = {"Windows": "windows-x86_64", "Linux": "linux-x86_64", "Darwin": "osx-x86_64"}[platform.system()]
    java_plugin = ARTIFACTS / "kotlin-codegen" / f"protoc-gen-grpc-java-{versions['grpc']}-{classifier}.exe"
    kotlin_plugin = ARTIFACTS / "kotlin-codegen" / f"protoc-gen-grpc-kotlin-{versions['grpc-kotlin']}-jdk8.jar"
    connect_plugin = ARTIFACTS / "kotlin-codegen" / f"protoc-gen-connect-kotlin-{versions['connect']}.jar"
    if any(not plugin.is_file() for plugin in (java_plugin, kotlin_plugin, connect_plugin)):
        raise ValueError("Run restore to resolve the pinned gRPC and Connect-Kotlin plugins")
    if os.name != "nt":
        java_plugin.chmod(0o755)
    launcher = jar_launcher(stage, "grpckt", kotlin_plugin)
    connect_launcher = jar_launcher(stage, "connect-kotlin", connect_plugin)
    for module in GENERATED_MODULES:
        for language in ("java", "kotlin"):
            (stage / module / language).mkdir(parents=True)
    messages, client = stage / "contracts-proto", stage / "contracts-client"
    common = [protoc, "-I", ROOT / "public/proto", *protos]
    run(*common, f"--java_out=lite:{messages / 'java'}", f"--kotlin_out=lite:{messages / 'kotlin'}",
        f"--plugin=protoc-gen-grpc-java={java_plugin}",
        f"--grpc-java_out=lite,@generated=omit:{client / 'java'}",
        f"--plugin=protoc-gen-grpckt={launcher}", f"--grpckt_out=lite:{client / 'kotlin'}",
        f"--plugin=protoc-gen-connect-kotlin={connect_launcher}",
        "--connect-kotlin_opt=generateCallbackMethods=false,generateCoroutineMethods=true,generateBlockingUnaryMethods=false",
        f"--connect-kotlin_out={stage / 'contracts-connect-client/kotlin'}")
    for module in GENERATED_MODULES:
        for path in (stage / module).rglob("*"):
            if path.is_file():
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n") + b"\n")
        sync_generated(stage / module, ROOT / f"src/public/kotlin/{module}/generated", check)


def jar_launcher(stage: Path, name: str, plugin: Path) -> Path:
    launcher = stage / (f"protoc-gen-{name}.cmd" if os.name == "nt" else f"protoc-gen-{name}")
    java = Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java")
    if os.name == "nt":
        launcher.write_text(f'@echo off\n"{java}" -jar "{plugin}" %*\n')
    else:
        import shlex
        launcher.write_text(f'#!/bin/sh\nexec {shlex.quote(str(java))} -jar {shlex.quote(str(plugin))} "$@"\n')
        launcher.chmod(0o755)
    return launcher


def build() -> None:
    gradle("assemble", "check")
