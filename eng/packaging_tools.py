# SPDX-License-Identifier: Apache-2.0
"""Build and inspect a small, explicit set of public distribution archives."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile

from release_channels import maven_version
from package_catalog import packages, ordered, closure
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
    sources = {row["id"]: ROOT / row["sourceRoot"] for row in packages("npm")}

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


def nuget_graph(release: str, row: dict | None = None) -> tuple[list[dict], list[dict]]:
    row = row or next(item for item in packages("nuget") if item["id"] == NUGET_ID)
    assets = read_json(ROOT / row["sourceRoot"] / "obj/project.assets.json")
    target = assets["targets"]["net10.0"]
    resolved = {key.split("/")[0]: key for key in target}
    first_party = {item["id"] for item in packages("nuget")}
    components: dict[str, dict] = {}
    edges: list[dict] = []

    def visit(name: str) -> str:
        if name in components:
            return components[name]["bom-ref"]
        key = resolved[name]
        if name in first_party:
            expression, resolved_version = "Apache-2.0", release
        else:
            package_path = next(Path(folder) / key.lower() for folder in assets["packageFolders"]
                                if (Path(folder) / key.lower()).is_dir())
            licence = ET.parse(next(package_path.glob("*.nuspec"))).find(".//{*}license")
            if licence is None or licence.get("type") != "expression":
                raise ValueError(f"Missing SPDX expression for {key}")
            expression, resolved_version = licence.text or "", key.split("/")[1]
        entry = component(name, resolved_version, expression, "nuget")
        components[name] = entry
        children = [visit(dep) for dep in sorted(target[key].get("dependencies", {}))]
        edges.append({"ref": entry["bom-ref"], "dependsOn": children})
        return entry["bom-ref"]

    dependencies = assets["project"]["frameworks"]["net10.0"].get("dependencies", {})
    direct = {name for name, dep in dependencies.items()
              if not dep.get("autoReferenced") and dep.get("suppressParent") != "All"}
    direct.update(row["dependencies"])
    root = component(row["id"], release, "Apache-2.0", "nuget")
    children = [visit(name) for name in sorted(direct)]
    edges.append({"ref": root["bom-ref"], "dependsOn": children})
    return [root, *components.values()], edges


def package_row(identity: str) -> dict:
    identity = identity.replace("/", ":") if identity.startswith("io.github.arcforges/") else identity
    return next(row for row in packages() if row["id"] == identity)


def schema_sources(row: dict) -> list[str]:
    return sorted({path for item in closure(row["id"])
                   for path in [*item["proto"], *item["jsonSchemas"]]})


def stage_schemas(target: Path, row: dict) -> None:
    shutil.copyfile(ARTIFACTS / row["descriptor"], target / "contracts.binpb")
    for source in schema_sources(row):
        # Preserve the access root to make internal/public ownership explicit.
        destination = target / "schemas" / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, destination)


def stage_tool_licences(target: Path, row: dict) -> None:
    """Retain terms for the framework-dependent tool's embedded managed closure."""
    sbom = read_json(target / "sbom.cdx.json")
    terms = {"Apache-2.0": ROOT / "LICENSE",
             "BSD-3-Clause": ROOT / "third-party/protobuf-generator-LICENSE.txt"}
    destination = target / "third-party"
    destination.mkdir()
    for dependency in sbom["components"]:
        expression = dependency["licenses"][0]["expression"]
        if expression not in terms or (expression == "BSD-3-Clause" and dependency["name"] != "Google.Protobuf"):
            raise ValueError("Review embedded CLI dependency terms: " + dependency["name"])
        shutil.copyfile(terms[expression], destination / (dependency["name"] + "-LICENSE.txt"))
    with (target / "NOTICE").open("a", encoding="utf-8") as stream:
        stream.write("\nEmbedded Google.Protobuf: Copyright 2008 Google Inc. All rights reserved.\n")
        stream.write("Embedded Grpc.Core.Api: Copyright the gRPC authors. Apache-2.0.\n")


def metadata(directory: Path, graph: tuple[list[dict], list[dict]], release: str,
             commit: str, dirty: bool) -> None:
    from check_provenance import package_notice
    components, edges = graph
    root, *dependencies = components
    row = package_row(root["name"])
    descriptor_path = ARTIFACTS / row["descriptor"]
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
    notice.extend(["", ("The CLI tool embeds its resolved managed runtime dependencies; their upstream licence texts accompany this inventory."
                        if row["id"] == "ArcForges.Cli" else
                        "Third-party dependencies are referenced, not vendored into this package. Installed dependencies supply their original licence and notice files."), ""])
    directory.joinpath("NOTICE").write_text("\n".join(notice) + "\n" + package_notice(), encoding="utf-8")
    write_json(directory / "source.json", {
        "repository": "https://github.com/ArcForges/Contracts", "commit": commit,
        "dirty": dirty, "version": release, "contractAccess": row["access"],
        "schemaSources": {path: sha256(ROOT / path) for path in schema_sources(row)},
        "descriptorSha256": sha256(descriptor_path),
        "dependencyLocks": {"package-lock.json": sha256(ROOT / "package-lock.json"),
                            **{item["sourceRoot"] + "/packages.lock.json": sha256(ROOT / item["sourceRoot"] / "packages.lock.json")
                               for item in packages("nuget")},
                            **{str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
                               for path in [ROOT / "gradle.lockfile", *sorted((ROOT / "src/public/kotlin").rglob("gradle.lockfile"))]}},
    })
    from build_identity import build as build_identity, report
    identity = build_identity()
    if identity["sourceCommit"] != commit or identity["dirty"] != dirty:
        raise ValueError("Source changed while packaging")
    write_json(directory / "build-identity.json", report(root, dependencies,
               descriptor_path.read_bytes(), identity))
    if root["purl"].startswith("pkg:maven/"):
        write_json(directory / "META-INF/arcforges" / root["name"].split("/")[-1] / "build-identity.json",
                   read_json(directory / "build-identity.json"))


def pack(release: str) -> None:
    from dependency_admission import audit
    from release_channels import stable
    audit(stable=stable(release))
    check_tools()
    # New tag pushes have no before commit; the canonical/main-ancestry release
    # guard establishes the accepted source tree used for provenance comparison.
    comparison = ["--base", os.environ["GITHUB_SHA"]] if os.environ.get("GITHUB_REF", "").startswith("refs/tags/") else []
    run(sys.executable, ROOT / "eng/check_provenance.py", "--owner", "Contracts", *comparison)
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
        entries = []
        for row in ordered("nuget"):
            nuget_metadata = stage / row["id"]
            metadata(nuget_metadata, nuget_graph(release, row), release, commit, dirty)
            stage_schemas(nuget_metadata, row)
            if row["id"] == "ArcForges.Cli":
                stage_tool_licences(nuget_metadata, row)
            project = ROOT / row["sourceRoot"] / (row["id"] + ".csproj")
            run("dotnet", "pack", project, "-c", "Release", "--no-restore", "-o", output,
                f"-p:PackageVersion={release}", f"-p:Version={release}",
                f"-p:RepositoryCommit={commit}", f"-p:ContractMetadataDir={nuget_metadata}")
            entries.append({"name": f"{row['id']}.{release}.nupkg", "kind": "nuget", "id": row["id"]})
        for row in ordered("npm"):
            project = ROOT / row["sourceRoot"]
            package = read_json(project / "package.json")
            target = stage / package["name"].split("/")[-1]
            target.mkdir()
            shutil.copytree(project / "dist", target / "dist")
            shutil.copyfile(project / "README.md", target / "README.md")
            shutil.copyfile(ROOT / "src/public/LICENSE", target / "LICENSE")
            metadata(target, npm_graph(project, release), release, commit, dirty)
            stage_schemas(target, row)
            package["version"] = release
            package["files"] = sorted(set(package["files"]) | {"build-identity.json", "schemas", "contracts.binpb"})
            package["exports"]["./build-identity"] = "./build-identity.json"
            package.pop("scripts", None)
            for dependency in row["dependencies"]:
                package["dependencies"][dependency] = release
            write_json(target / "package.json", package)
            packed = json.loads(run(NPM, "pack", target, "--ignore-scripts", "--json",
                                    "--pack-destination", output, capture=True))
            entries.append({"name": packed[0]["filename"], "kind": "npm", "id": package["name"]})
        from maven_tools import pack as pack_maven
        entries.append(pack_maven(output, release, commit, dirty))
        for descriptor in sorted({row["descriptor"] for row in packages()}):
            shutil.copyfile(ARTIFACTS / descriptor, output / descriptor)
            entries.append({"name": descriptor, "kind": "descriptor", "id": "descriptor:" + descriptor})
        for entry in entries:
            entry.update(sha256=sha256(output / entry["name"]), size=(output / entry["name"]).stat().st_size)
        from build_identity import build as build_identity
        write_json(output / "manifest.json", {"format": "arcforges.contracts.candidate.v1", "build": build_identity(),
                   "version": release, "mavenVersion": maven_version(release),
                   "commit": commit, "dirty": dirty, "files": entries})
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


def verify_artifacts(directory: Path, commit: str | None = None, *, contents: bool = True) -> dict:
    manifest = read_json(directory / "manifest.json")
    release = version(manifest["version"])
    if manifest["format"] != "arcforges.contracts.candidate.v1":
        raise ValueError("Unknown candidate format")
    if "mavenVersion" in manifest:
        if manifest["mavenVersion"] != maven_version(release):
            raise ValueError("Maven coordinate differs from the build channel")
    if commit and manifest["commit"] != commit:
        raise ValueError("Candidate source commit differs from the expected checkout")
    from build_identity import validate_source, verify_report
    validate_source(manifest["build"])
    if manifest["build"]["sourceCommit"] != manifest["commit"] or manifest["build"]["dirty"] != manifest["dirty"]:
        raise ValueError("Candidate build identity differs from source metadata")
    kinds = {row["id"]: row["kind"] for row in packages() if row["kind"] != "maven"}
    kinds.update({"descriptor:" + row["descriptor"]: "descriptor" for row in packages()})
    kinds["io.github.arcforges"] = "maven"
    if len(manifest["files"]) != len(kinds) or {entry["id"] for entry in manifest["files"]} != set(kinds):
        raise ValueError("Candidate must contain the complete registered package and descriptor inventory")
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
        if entry["kind"] != kinds[entry["id"]]:
            raise ValueError("Candidate package kind differs from its identity")
        if not contents:
            continue  # The producer already checked archive contents; this is a trust handoff.
        if entry["kind"] == "descriptor":
            if entry["id"] != "descriptor:" + name or not path.read_bytes():
                raise ValueError("Missing descriptor")
            continue
        if entry["kind"] == "maven":
            from maven_tools import verify_bundle
            verify_bundle(path, manifest, (directory / "contracts.binpb").read_bytes())
            continue
        row = package_row(entry["id"])
        descriptor = (directory / row["descriptor"]).read_bytes()
        files = archive_files(path)
        for required in ["LICENSE", "NOTICE", "README.md", "sbom.cdx.json", "source.json", "build-identity.json"]:
            if not files.get(required):
                raise ValueError(f"{name} is missing {required}")
        if b"Apache License" not in files["LICENSE"]:
            raise ValueError(f"Incorrect public licence in {name}")
        from check_provenance import verify_package_notice
        verify_package_notice(files["NOTICE"])
        source = json.loads(files["source.json"])
        if source["version"] != release or source["commit"] != manifest["commit"] or source["dirty"] != manifest["dirty"]:
            raise ValueError(f"Source metadata differs in {name}")
        if source.get("contractAccess") != row["access"] or source.get("schemaSources") != {item: sha256(ROOT / item) for item in schema_sources(row)}:
            raise ValueError("Package source ownership or schema inventory differs")
        if source["descriptorSha256"] != hashlib.sha256(descriptor).hexdigest():
            raise ValueError(f"Schema hash differs in {name}")
        sbom = json.loads(files["sbom.cdx.json"])
        verify_report(files["build-identity.json"], sbom, descriptor, manifest)
        if sbom["metadata"]["component"]["name"] != entry["id"]:
            raise ValueError("SBOM identifies another package")
        if entry["kind"] == "nuget":
            nuspec = ET.fromstring(files[f"{entry['id']}.nuspec"])
            if nuspec.findtext(".//{*}id") != entry["id"] or nuspec.findtext(".//{*}version") != release:
                raise ValueError("Unexpected NuGet identity")
            if nuspec.findtext(".//{*}license") != "Apache-2.0":
                raise ValueError("Unexpected NuGet licence")
            assembly = ("tools/net10.0/any/" if entry["id"] == "ArcForges.Cli" else "lib/net10.0/") + entry["id"] + ".dll"
            if assembly not in files:
                raise ValueError("NuGet assembly is missing")
            dependencies = {dep.get("id"): dep.get("version") for dep in nuspec.findall(".//{*}dependency")}
            if entry["id"] == "ArcForges.Cli":
                if "tools/net10.0/any/DotnetToolSettings.xml" not in files:
                    raise ValueError("CLI tool entry point is missing")
            else:
                project = ET.parse(ROOT / row["sourceRoot"] / (row["id"] + ".csproj"))
                expected_dependencies = set(row["dependencies"]) | {
                    item.get("Include") for item in project.findall(".//PackageReference")
                    if item.get("PrivateAssets", "").lower() != "all"}
                if set(dependencies) != expected_dependencies:
                    raise ValueError(f"Unexpected runtime dependency closure: {dependencies}")
                for dependency in row["dependencies"]:
                    if dependencies[dependency].strip("[]() ") != release:
                        raise ValueError("NuGet first-party dependency differs from candidate version")
        elif entry["kind"] == "npm":
            package = json.loads(files["package.json"])
            if package.get("exports", {}).get("./build-identity") != "./build-identity.json":
                raise ValueError("npm runtime build identity export missing")
            if package["name"] != entry["id"] or package["version"] != release or package["license"] != "Apache-2.0":
                raise ValueError("Unexpected npm identity or licence")
            if "scripts" in package or "dist/index.js" not in files or "dist/index.d.ts" not in files:
                raise ValueError("npm package must contain prebuilt JS and declarations without lifecycle scripts")
            for dependency in row["dependencies"]:
                if package.get("dependencies", {}).get(dependency) != release:
                    raise ValueError("The npm package must pin its first-party candidate dependencies")
        else:
            raise ValueError("Unknown candidate entry kind")
        if files.get("contracts.binpb") != descriptor:
            raise ValueError("Package descriptor differs from its selected schema closure")
        for source_path in schema_sources(row):
            if files.get("schemas/" + source_path) != (ROOT / source_path).read_bytes():
                raise ValueError("Authored schema source missing or changed in package")
        if row["access"] == "public" and any(item.startswith("schemas/internal/") for item in files):
            raise ValueError("Internal schema leaked into a public package")
        if any("node_modules/" in item or "/obj/" in item or item.endswith(".csproj") for item in files):
            raise ValueError("Build inputs or installed dependencies leaked into an archive")
    print(f"Verified candidate {'contents' if contents else 'handoff identity/integrity'}: {release}")
    return manifest


def publish(directory: Path, registry: str) -> None:
    from publish_tools import publish_verified
    publish_verified(directory, registry)
