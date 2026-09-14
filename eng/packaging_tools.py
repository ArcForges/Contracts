# SPDX-License-Identifier: Apache-2.0
"""Build and inspect a small, explicit set of public distribution archives."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile

from contracts import (ARTIFACTS, DOTNET_PROJECT, NPM, NPM_IDS, NPM_PROJECTS, NUGET_ID,
                       ROOT, build, check_tools, generate, read_json, run, sha256,
                       source_commit, version, write_json)


def component(name: str, release: str, license_expression: str, ecosystem: str) -> dict:
    if not license_expression or "GPL" in license_expression:
        raise ValueError(f"Review public dependency licence before packaging: {name}: {license_expression}")
    purl = f"pkg:{ecosystem}/{quote(name, safe='/')}@{release}"
    return {"type": "library", "bom-ref": purl, "name": name, "version": release,
            "purl": purl, "licenses": [{"expression": license_expression}]}


def npm_graph(project: Path, release: str) -> tuple[list[dict], list[dict]]:
    components: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    sources = {name: path for name, path in zip(NPM_IDS, NPM_PROJECTS, strict=True)}

    def visit(path: Path) -> str:
        package = read_json(path / "package.json")
        name = package["name"]
        if name in components:
            return components[name]["bom-ref"]
        entry = component(name, release if name in sources else package["version"], package["license"], "npm")
        components[name] = entry
        dependencies = set(package.get("dependencies", {})) | set(package.get("peerDependencies", {}))
        children = [visit(sources.get(dep, ROOT / "node_modules" / dep)) for dep in sorted(dependencies)]
        edges[name] = {"ref": entry["bom-ref"], "dependsOn": children}
        return entry["bom-ref"]

    visit(project)
    return list(components.values()), list(edges.values())


def nuget_graph(release: str) -> tuple[list[dict], list[dict]]:
    assets = read_json(DOTNET_PROJECT.parent / "obj/project.assets.json")
    target = assets["targets"]["net10.0"]
    resolved = {key.split("/")[0]: key for key in target}
    components: dict[str, dict] = {}
    edges: list[dict] = []

    def visit(name: str) -> str:
        if name in components:
            return components[name]["bom-ref"]
        key = resolved[name]
        package_path = next(Path(folder) / key.lower() for folder in assets["packageFolders"]
                            if (Path(folder) / key.lower()).is_dir())
        metadata = ET.parse(next(package_path.glob("*.nuspec")))
        licence = metadata.find(".//{*}license")
        if licence is None or licence.get("type") != "expression":
            raise ValueError(f"Missing SPDX expression for {key}")
        entry = component(name, key.split("/")[1], licence.text or "", "nuget")
        components[name] = entry
        children = [visit(dep) for dep in sorted(target[key].get("dependencies", {}))]
        edges.append({"ref": entry["bom-ref"], "dependsOn": children})
        return entry["bom-ref"]

    dependencies = assets["project"]["frameworks"]["net10.0"]["dependencies"]
    root = component(NUGET_ID, release, "Apache-2.0", "nuget")
    children = [visit(name) for name, dep in dependencies.items()
                if not dep.get("autoReferenced") and dep.get("suppressParent") != "All"]
    edges.append({"ref": root["bom-ref"], "dependsOn": children})
    return [root, *components.values()], edges


def metadata(directory: Path, graph: tuple[list[dict], list[dict]], release: str,
             commit: str, dirty: bool) -> None:
    components, edges = graph
    root, *dependencies = components
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "sbom.cdx.json", {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {"component": root}, "components": dependencies, "dependencies": edges,
    })
    notice = ["ArcForges Contracts", "Copyright 2026 ArcForges contributors", "",
              f"{root['name']} {release} (Apache-2.0)", "",
              "Resolved runtime dependency inventory (dependencies retain their own licences):"]
    notice.extend(f"- {dep['name']} {dep['version']}: {dep['licenses'][0]['expression']} ({dep['purl']})"
                  for dep in dependencies)
    notice.extend(["", "Third-party dependencies are referenced, not vendored into this package.",
                   "The installed dependency packages supply their original licence and notice files.", ""])
    directory.joinpath("NOTICE").write_text("\n".join(notice), encoding="utf-8")
    write_json(directory / "source.json", {
        "repository": "https://github.com/ArcForges/Contracts", "commit": commit,
        "dirty": dirty, "version": release, "schema": "arcforges.hello.v1",
        "descriptorSha256": sha256(ARTIFACTS / "contracts.binpb"),
        "dependencyLocks": {"package-lock.json": sha256(ROOT / "package-lock.json"),
                            "PublicApi/packages.lock.json": sha256(DOTNET_PROJECT.parent / "packages.lock.json"),
                            **{str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
                               for path in [ROOT / "gradle.lockfile", *sorted((ROOT / "src/public/kotlin").rglob("gradle.lockfile"))]}},
    })


def pack(release: str) -> None:
    check_tools()
    generate(check=True)
    build()
    commit = source_commit()
    dirty = bool(run("git", "status", "--porcelain", capture=True).strip())
    output = (ARTIFACTS / "packages").resolve()
    if not output.is_relative_to(ARTIFACTS.resolve()) or output == ARTIFACTS.resolve():
        raise ValueError("Package output must stay below repository artifacts")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="pack-", dir=ARTIFACTS) as temporary:
        stage = Path(temporary)
        nuget_metadata = stage / "nuget-metadata"
        metadata(nuget_metadata, nuget_graph(release), release, commit, dirty)
        shutil.copyfile(ARTIFACTS / "contracts.binpb", nuget_metadata / "contracts.binpb")
        run("dotnet", "pack", DOTNET_PROJECT, "-c", "Release", "--no-restore", "-o", output,
            f"-p:PackageVersion={release}", f"-p:Version={release}",
            f"-p:RepositoryCommit={commit}", f"-p:ContractMetadataDir={nuget_metadata}")
        entries = [{"name": next(output.glob("*.nupkg")).name, "kind": "nuget", "id": NUGET_ID}]
        for project in NPM_PROJECTS:
            package = read_json(project / "package.json")
            target = stage / package["name"].split("/")[-1]
            target.mkdir()
            shutil.copytree(project / "dist", target / "dist")
            for name in ["README.md"]:
                shutil.copyfile(project / name, target / name)
            shutil.copyfile(ROOT / "src/public/LICENSE", target / "LICENSE")
            metadata(target, npm_graph(project, release), release, commit, dirty)
            package["version"] = release
            package.pop("scripts", None)
            for dependency in NPM_IDS:
                if dependency in package["dependencies"]:
                    package["dependencies"][dependency] = release
            if package["name"] == "@arcforges/proto":
                shutil.copytree(ROOT / "public/proto", target / "proto")
                shutil.copyfile(ARTIFACTS / "contracts.binpb", target / "contracts.binpb")
            write_json(target / "package.json", package)
            packed = json.loads(run(NPM, "pack", target, "--ignore-scripts", "--json",
                                    "--pack-destination", output, capture=True))
            entries.append({"name": packed[0]["filename"], "kind": "npm", "id": package["name"]})
        from maven_tools import pack as pack_maven
        entries.append(pack_maven(output, release, commit, dirty))
        shutil.copyfile(ARTIFACTS / "contracts.binpb", output / "contracts.binpb")
        entries.append({"name": "contracts.binpb", "kind": "descriptor", "id": "arcforges.hello.v1"})
        for entry in entries:
            entry.update(sha256=sha256(output / entry["name"]), size=(output / entry["name"]).stat().st_size)
        write_json(output / "manifest.json", {"format": "arcforges.contracts.candidate.v1",
                   "version": release, "commit": commit, "dirty": dirty, "files": entries})
    verify_artifacts(output, commit)
    print(f"Candidate archives are ready in {output}. Publication has not occurred.")


def archive_files(path: Path) -> dict[str, bytes]:
    if path.suffix == ".nupkg":
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    with tarfile.open(path, "r:gz") as archive:
        result = {}
        for member in archive.getmembers():
            if not member.isfile() or not member.name.startswith("package/"):
                raise ValueError("npm archives must contain regular package files only")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Unreadable npm archive member")
            result[member.name.removeprefix("package/")] = stream.read()
        return result


def verify_artifacts(directory: Path, commit: str | None = None) -> dict:
    manifest = read_json(directory / "manifest.json")
    release = version(manifest["version"])
    if manifest["format"] != "arcforges.contracts.candidate.v1":
        raise ValueError("Unknown candidate format")
    if commit and manifest["commit"] != commit:
        raise ValueError("Candidate source commit differs from the expected checkout")
    expected = {NUGET_ID, *NPM_IDS, "arcforges.hello.v1", "io.github.arcforges"}
    if len(manifest["files"]) != 5 or {entry["id"] for entry in manifest["files"]} != expected:
        raise ValueError("Candidate must contain one NuGet, two npm packages, three Maven modules and a descriptor")
    names = {entry["name"] for entry in manifest["files"]}
    if {path.name for path in directory.iterdir()} != names | {"manifest.json"}:
        raise ValueError("Unexpected or missing candidate files")
    descriptor = (directory / "contracts.binpb").read_bytes()
    for entry in manifest["files"]:
        name = entry["name"]
        if Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("Candidate filenames must be flat")
        path = directory / name
        if sha256(path) != entry["sha256"] or path.stat().st_size != entry["size"]:
            raise ValueError(f"Candidate hash or size mismatch: {name}")
        if entry["kind"] == "descriptor":
            if name != "contracts.binpb" or not descriptor:
                raise ValueError("Missing descriptor")
            continue
        if entry["kind"] == "maven":
            from maven_tools import verify_bundle
            verify_bundle(path, manifest, descriptor)
            continue
        files = archive_files(path)
        for required in ["LICENSE", "NOTICE", "README.md", "sbom.cdx.json", "source.json"]:
            if not files.get(required):
                raise ValueError(f"{name} is missing {required}")
        if b"Apache License" not in files["LICENSE"]:
            raise ValueError(f"Incorrect public licence in {name}")
        source = json.loads(files["source.json"])
        if source["version"] != release or source["commit"] != manifest["commit"] or source["dirty"] != manifest["dirty"]:
            raise ValueError(f"Source metadata differs in {name}")
        if source["descriptorSha256"] != hashlib.sha256(descriptor).hexdigest():
            raise ValueError(f"Schema hash differs in {name}")
        sbom = json.loads(files["sbom.cdx.json"])
        if sbom["metadata"]["component"]["name"] != entry["id"]:
            raise ValueError("SBOM identifies another package")
        if entry["kind"] == "nuget":
            nuspec = ET.fromstring(files[f"{NUGET_ID}.nuspec"])
            if nuspec.findtext(".//{*}id") != NUGET_ID or nuspec.findtext(".//{*}version") != release:
                raise ValueError("Unexpected NuGet identity")
            if nuspec.findtext(".//{*}license") != "Apache-2.0":
                raise ValueError("Unexpected NuGet licence")
            if f"lib/net10.0/{NUGET_ID}.dll" not in files:
                raise ValueError("NuGet assembly is missing")
            dependencies = {dep.get("id") for dep in nuspec.findall(".//{*}dependency")}
            if dependencies != {"Google.Protobuf", "Grpc.Core.Api"}:
                raise ValueError(f"Unexpected runtime dependency closure: {dependencies}")
        elif entry["kind"] == "npm":
            package = json.loads(files["package.json"])
            if package["name"] != entry["id"] or package["version"] != release or package["license"] != "Apache-2.0":
                raise ValueError("Unexpected npm identity or licence")
            if "scripts" in package or "dist/index.js" not in files or "dist/index.d.ts" not in files:
                raise ValueError("npm package must contain prebuilt JS and declarations without lifecycle scripts")
            if entry["id"] == "@arcforges/api-client" and package["dependencies"]["@arcforges/proto"] != release:
                raise ValueError("The API client must pin this candidate's proto version")
        else:
            raise ValueError("Unknown candidate entry kind")
        if entry["id"] in {NUGET_ID, "@arcforges/proto"}:
            if files.get("contracts.binpb") != descriptor or "proto/arcforges/hello/v1/hello.proto" not in files:
                raise ValueError("Proto or descriptor set is missing from schema package")
        if any("node_modules/" in item or "/obj/" in item or item.endswith(".csproj") for item in files):
            raise ValueError("Build inputs or installed dependencies leaked into an archive")
    print(f"Verified all candidate identities, metadata and hashes: {release}")
    return manifest


def publish(directory: Path, registry: str) -> None:
    from publish_tools import publish_verified
    publish_verified(directory, registry)
