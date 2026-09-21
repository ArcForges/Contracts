# SPDX-License-Identifier: Apache-2.0
"""Consume archives outside the producer checkout, using empty package caches."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from contracts import ARTIFACTS, NPM, NUGET_ID, ROOT, read_json, run, write_json
from packaging_tools import archive_files, verify_artifacts


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for_host(process: subprocess.Popen, ports: list[int]) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ValueError("The example server exited before becoming ready")
        try:
            for port in ports:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    pass
            return
        except OSError:
            time.sleep(0.2)
    raise ValueError("The example server did not start within 45 seconds")


def consume(directory: Path, aot: bool, update_kotlin_locks: bool = False, snapshot_registry: bool = False) -> None:
    manifest = verify_artifacts(directory)
    repository = None
    def verify_snapshot():
        from snapshot_publish import PUBLIC, inspect
        from maven_tools import verify_bundle
        if manifest.get("mavenVersion") != "1.0.0-SNAPSHOT":
            raise ValueError("Live snapshot consumption requires a snapshot candidate")
        entry = next(item for item in manifest["files"] if item["kind"] == "maven")
        files = verify_bundle(directory / entry["name"], manifest, (directory / "contracts.binpb").read_bytes())
        if not inspect(files, manifest)[0]:
            raise ValueError("Live snapshot differs from the tested candidate")
        return PUBLIC
    if snapshot_registry:
        repository = verify_snapshot()
    release = manifest["version"]
    rid = "win-x64" if os.name == "nt" else "linux-x64"
    evidence_dir = ARTIFACTS / "evidence" / rid
    evidence_dir.mkdir(parents=True, exist_ok=True)
    # TemporaryDirectory owns only the new directory it creates, outside ROOT.
    with tempfile.TemporaryDirectory(prefix="arcforges-contract-consumer-") as temporary:
        consumer = Path(temporary)
        if consumer.resolve().is_relative_to(ROOT):
            raise ValueError("The package consumer must be outside the producer checkout")
        feed = consumer / "feed"
        feed.mkdir()
        for entry in manifest["files"]:
            if entry["kind"] in {"npm", "nuget"}:
                shutil.copyfile(directory / entry["name"], feed / entry["name"])
        for name in ["global.json", "Directory.Build.props", "Directory.Build.targets", "Directory.Packages.props"]:
            shutil.copyfile(ROOT / name, consumer / name)
        pins = ET.parse(consumer / "Directory.Packages.props")
        ET.SubElement(pins.getroot().find("ItemGroup"), "PackageVersion", Include=NUGET_ID, Version=release)
        pins.write(consumer / "Directory.Packages.props", encoding="utf-8", xml_declaration=True)
        consumer.joinpath("NuGet.config").write_text('''<configuration>
  <packageSources>
    <clear />
    <add key="candidate" value="feed" />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
  <packageSourceMapping>
    <clear />
    <packageSource key="candidate"><package pattern="ArcForges.Contracts.*" /></packageSource>
    <packageSource key="nuget.org"><package pattern="*" /></packageSource>
  </packageSourceMapping>
</configuration>
''', encoding="utf-8")
        # These temporary applications are local consumers of the CI producer.
        # Their own compilation must not impersonate its GitHub checkout.
        local_environment = {key: value for key, value in os.environ.items() if not key.startswith("GITHUB_") and key != "CI"}
        write_json(consumer / "expected-build.json", manifest["build"])
        env = dict(local_environment, ARCFORGES_EXPECTED_BUILD=str(consumer / "expected-build.json"),
                   NUGET_PACKAGES=str(consumer / "nuget-cache"),
                   npm_config_cache=str(consumer / "npm-cache"))
        for project_name in ["HelloHost", "HelloClient"]:
            target = consumer / project_name
            target.mkdir()
            original = ROOT / "tests/public" / project_name
            shutil.copyfile(original / "Program.cs", target / "Program.cs")
            project = ET.parse(original / f"{project_name}.csproj")
            references = project.findall(".//ProjectReference")
            if len(references) != 1:
                raise ValueError("Each demo must have exactly one producer reference to replace")
            for item_group in project.findall("ItemGroup"):
                for reference in list(item_group.findall("ProjectReference")):
                    item_group.remove(reference)
                    ET.SubElement(item_group, "PackageReference", Include=NUGET_ID)
            project.write(target / f"{project_name}.csproj", encoding="utf-8", xml_declaration=True)
            run("dotnet", "restore", target, "--force-evaluate", "-p:RestoreLockedMode=false", cwd=consumer, env=env)
            run("dotnet", "restore", target, "--locked-mode", cwd=consumer, env=env)
            run("dotnet", "build", target, "-c", "Release", "--no-restore", cwd=consumer, env=env)

        ts = consumer / "typescript"
        ts.mkdir()
        dependencies = {entry["id"]: "file:../feed/" + entry["name"]
                        for entry in manifest["files"] if entry["kind"] == "npm"}
        api_entry = next(entry for entry in manifest["files"] if entry["id"] == "@arcforges/api-client")
        api_package = json.loads(archive_files(directory / api_entry["name"])["package.json"])
        for dep in ["@bufbuild/protobuf", "@connectrpc/connect"]:
            dependencies[dep] = api_package["dependencies"][dep]
        write_json(ts / "package.json", {
            "name": "contracts-archive-consumer", "private": True, "version": "0.0.0", "type": "module",
            "dependencies": dependencies,
            "devDependencies": {"typescript": read_json(ROOT / "package.json")["devDependencies"]["typescript"]},
        })
        shutil.copyfile(ROOT / ".npmrc", ts / ".npmrc")
        shutil.copyfile(ROOT / "tests/public/package-consumer.ts", ts / "consumer.ts")
        shutil.copyfile(ROOT / "fixtures/public/hello.json", consumer / "hello.json")
        write_json(ts / "tsconfig.json", {
            "compilerOptions": {"target": "ES2022", "module": "NodeNext", "moduleResolution": "NodeNext",
                                "strict": True, "noEmitOnError": True, "outDir": "dist"},
            "include": ["consumer.ts"],
        })
        ts.joinpath("run.mjs").write_text('''import { readFileSync } from "node:fs";
import { verify } from "./dist/consumer.js";
import protoIdentity from "@arcforges/proto/build-identity" with { type: "json" };
import clientIdentity from "@arcforges/api-client/build-identity" with { type: "json" };
import { deepStrictEqual } from "node:assert";
const expectedBuild = JSON.parse(readFileSync(process.env.ARCFORGES_EXPECTED_BUILD));
for (const identity of [protoIdentity, clientIdentity]) {
  deepStrictEqual(identity.build, expectedBuild);
  deepStrictEqual(identity.axes.ContractSet.values.map(value => value.subject + ".v" + value.version), ["arcforges.hello.v1"]);
}
console.log("Both published npm runtime build identities verified.");
const fixture = JSON.parse(readFileSync(new URL("../hello.json", import.meta.url)));
await verify(process.argv[2], fixture.cases);
console.log("TypeScript archive consumer: real gRPC-Web success/error checks passed.");
''', encoding="utf-8")
        run(NPM, "install", "--ignore-scripts", cwd=ts, env=env)
        run(NPM, "ci", "--ignore-scripts", cwd=ts, env=env)
        run("node", ts / "node_modules/typescript/bin/tsc", "-p", ts / "tsconfig.json", cwd=ts, env=env)

        from kotlin_consumer import prepare as prepare_kotlin
        kotlin_client, kotlin_env = prepare_kotlin(consumer, directory, manifest, env, evidence_dir, update_kotlin_locks, repository=repository)
        connect_client, connect_env = prepare_kotlin(consumer, directory, manifest, env, evidence_dir,
                                                     update_kotlin_locks, "KotlinConnectClient", repository=repository)
        native = consumer / "native-client"
        if aot:
            run("dotnet", "restore", consumer / "HelloClient", "-r", rid,
                "-p:PublishAot=true", "-p:RestoreLockedMode=false", "--force-evaluate", cwd=consumer, env=env)
            run("dotnet", "publish", consumer / "HelloClient", "-c", "Release", "-r", rid,
                "-p:PublishAot=true", "--self-contained", "true", "--no-restore", "-o", native,
                cwd=consumer, env=env)

        grpc_port, web_port = free_port(), free_port()
        while web_port == grpc_port:
            web_port = free_port()
        log_path = evidence_dir / "hello-host.log"
        with log_path.open("w", encoding="utf-8") as log:
            host = subprocess.Popen([
                "dotnet", str(consumer / "HelloHost/bin/Release/net10.0/HelloHost.dll"),
                "--grpc-port", str(grpc_port), "--web-port", str(web_port),
            ], cwd=consumer, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                wait_for_host(host, [grpc_port, web_port])
                run("dotnet", consumer / "HelloClient/bin/Release/net10.0/HelloClient.dll",
                    f"http://127.0.0.1:{grpc_port}", consumer / "hello.json", cwd=consumer, env=env)
                run("node", ts / "run.mjs", f"http://127.0.0.1:{web_port}", cwd=ts, env=env)
                run(kotlin_client, grpc_port, cwd=consumer, env=kotlin_env)
                run(connect_client, web_port, grpc_port, cwd=consumer, env=connect_env)
                if aot:
                    run(native / ("HelloClient.exe" if os.name == "nt" else "HelloClient"),
                        f"http://127.0.0.1:{grpc_port}", consumer / "hello.json", cwd=consumer, env=env)
            except Exception:
                log.flush()
                print(log_path.read_text(encoding="utf-8"), flush=True)
                raise
            finally:
                host.terminate()
                try:
                    host.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    host.kill()
                    host.wait(timeout=10)

        for project_name in ["HelloHost", "HelloClient"]:
            shutil.copyfile(consumer / project_name / "packages.lock.json", evidence_dir / f"{project_name}.packages.lock.json")
        shutil.copyfile(ts / "package-lock.json", evidence_dir / "package-lock.json")
        if snapshot_registry:
            verify_snapshot()
        write_json(evidence_dir / "result.json", {
            "version": release, "commit": manifest["commit"], "rid": rid,
            "build": manifest["build"], "runtimeBuildIdentity": {
                "csharp": "passed", "npm": "passed", "jvmAllFourModules": "passed",
                "nativeAot": "passed" if aot else "not-run"},
            "inputs": manifest["files"], "isolatedCaches": True, "sourceReferences": False,
            "csharpGrpc": "passed", "typescriptGrpcWeb": "passed", "kotlinGrpc": "passed",
            "kotlinConnectGrpcWeb": "passed", "kotlinConnectGrpc": "passed",
            "nativeAotGrpc": "passed" if aot else "not-run",
            "browser": "not-run", "androidDevice": "not-run", "registryRestore": "maven-snapshot-passed" if snapshot_registry else "not-run",
            "mavenVersion": manifest.get("mavenVersion", release), "mavenRepository": repository or "isolated-candidate",
        })
    print(f"Independent package consumers passed. Evidence: {evidence_dir}")
