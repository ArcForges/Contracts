# SPDX-License-Identifier: Apache-2.0
"""Kotlin generation uses the same protoc and immutable schema as C# and TS."""

from __future__ import annotations

import os
from pathlib import Path
import platform
import tomllib

from contracts import ARTIFACTS, ROOT, run, sync_generated

MAVEN_GROUP = "io.github.arcforges"
MAVEN_MODULES = ("contracts-proto", "contracts-client", "contract-fixtures")


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
    if not java_plugin.is_file() or not kotlin_plugin.is_file():
        raise ValueError("Run restore to resolve the pinned gRPC Java/Kotlin plugins")
    if os.name != "nt":
        java_plugin.chmod(0o755)
    launcher = stage / ("protoc-gen-grpckt.cmd" if os.name == "nt" else "protoc-gen-grpckt")
    java = Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java")
    if os.name == "nt":
        launcher.write_text(f'@echo off\n"{java}" -jar "{kotlin_plugin}" %*\n')
    else:
        import shlex
        launcher.write_text(f'#!/bin/sh\nexec {shlex.quote(str(java))} -jar {shlex.quote(str(kotlin_plugin))} "$@"\n')
        launcher.chmod(0o755)
    for module in MAVEN_MODULES[:2]:
        for language in ("java", "kotlin"):
            (stage / module / language).mkdir(parents=True)
    messages, client = stage / "contracts-proto", stage / "contracts-client"
    common = [protoc, "-I", ROOT / "public/proto", *protos]
    run(*common, f"--java_out=lite:{messages / 'java'}", f"--kotlin_out=lite:{messages / 'kotlin'}",
        f"--plugin=protoc-gen-grpc-java={java_plugin}",
        f"--grpc-java_out=lite,@generated=omit:{client / 'java'}",
        f"--plugin=protoc-gen-grpckt={launcher}", f"--grpckt_out=lite:{client / 'kotlin'}")
    for module in MAVEN_MODULES[:2]:
        for path in (stage / module).rglob("*"):
            if path.is_file():
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n") + b"\n")
        sync_generated(stage / module, ROOT / f"src/public/kotlin/{module}/generated", check)


def build() -> None:
    gradle("assemble", "check")
