# SPDX-License-Identifier: Apache-2.0
"""Build and validate the unsigned repository consumed and later signed by CI."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import xml.etree.ElementTree as ET
import zipfile

from contracts import ARTIFACTS, ROOT, read_json
from kotlin_tools import MAVEN_GROUP, MAVEN_MODULES, gradle

BUNDLE_ID = "io.github.arcforges"
SUFFIXES = (".jar", "-sources.jar", "-javadoc.jar", ".pom", ".module")


def runtime_graph(module: str, release: str):
    from packaging_tools import component
    graph = read_json(ARTIFACTS / f"maven-graphs/{module}.json")
    # Reviewed upstream runtime licences. Unknown dependencies stop publication
    # instead of guessing a licence from a parent POM or a repository-wide label.
    licences = {
        "io.github.arcforges": "Apache-2.0", "io.grpc": "Apache-2.0",
        "org.jetbrains.kotlin": "Apache-2.0", "org.jetbrains.kotlinx": "Apache-2.0",
        "org.jetbrains": "Apache-2.0", "com.google.protobuf": "BSD-3-Clause",
        "com.google.guava": "Apache-2.0", "com.google.errorprone": "Apache-2.0",
        "com.google.code.findbugs": "Apache-2.0", "io.perfmark": "Apache-2.0",
        "org.checkerframework": "MIT", "com.google.j2objc": "Apache-2.0",
        "org.jspecify": "Apache-2.0",
        "javax.annotation": "CDDL-1.1", "org.codehaus.mojo": "MIT",
        "com.connectrpc": "Apache-2.0", "io.ktor": "Apache-2.0",
        "com.squareup.okio": "Apache-2.0", "com.squareup.moshi": "Apache-2.0",
        "org.slf4j": "MIT",
    }
    components = {}
    root = f"{MAVEN_GROUP}:{module}:{release}"
    for identity in [root, *sorted(set(graph) - {root})]:
        group, name, resolved = identity.split(":")
        if group not in licences:
            raise ValueError(f"Review new Maven runtime licence: {identity}")
        components[identity] = component(f"{group}/{name}", resolved, licences[group], "maven")
    edges = [{"ref": components[key]["bom-ref"], "dependsOn": [components[child]["bom-ref"] for child in children]}
             for key, children in graph.items()]
    return list(components.values()), edges


def clean_output(path: Path) -> None:
    resolved = path.resolve()
    if not resolved.is_relative_to(ARTIFACTS.resolve()) or resolved == ARTIFACTS.resolve():
        raise ValueError("Maven build output must stay below repository artifacts")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


def pack(output: Path, release: str, commit: str, dirty: bool) -> dict:
    from packaging_tools import metadata
    from release_channels import maven_version
    build_version = release
    release = maven_version(release)
    gradle("runtimeInventory", f"-PreleaseVersion={release}")
    clean_output(ARTIFACTS / "maven-metadata")
    clean_output(ARTIFACTS / "maven-repository")
    for module in MAVEN_MODULES:
        target = ARTIFACTS / f"maven-metadata/{module}"
        metadata(target, runtime_graph(module, release), build_version, commit, dirty)
        shutil.copyfile(ROOT / f"src/public/kotlin/{module}/README.md", target / "README.md")
    from documentation_tools import prepare
    gradle("dokkaGeneratePublicationHtml", f"-PreleaseVersion={release}")
    prepare(release)
    gradle("publishToMavenLocal", f"-Dmaven.repo.local={ARTIFACTS / 'maven-repository'}",
           f"-PreleaseVersion={release}", f"-PsourceCommit={commit}")
    bundle = output / f"arcforges-maven-{release}.zip"
    repository = ARTIFACTS / "maven-repository"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in expected_paths(release):
            path = repository / name
            if not path.is_file():
                raise ValueError(f"Missing Maven publication file: {name}")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return {"name": bundle.name, "kind": "maven", "id": BUNDLE_ID}


def expected_paths(release: str) -> list[str]:
    return [f"io/github/arcforges/{module}/{release}/{module}-{release}{suffix}"
            for module in MAVEN_MODULES for suffix in SUFFIXES]


def zip_contents(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate ZIP entries are forbidden")
        if any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name for name in names):
            raise ValueError("Unsafe ZIP entry")
        return {name: archive.read(name) for name in names}


def verify_bundle(path: Path, manifest: dict, descriptor: bytes) -> dict[str, bytes]:
    from check_provenance import verify_package_notice
    release = manifest.get("mavenVersion", manifest["version"])
    files = zip_contents(path.read_bytes())
    if set(files) != set(expected_paths(release)):
        raise ValueError("Maven bundle must contain all complete publications and no extra files")
    documentation_receipts = []
    for module in MAVEN_MODULES:
        prefix = f"io/github/arcforges/{module}/{release}/{module}-{release}"
        pom = ET.fromstring(files[prefix + ".pom"])
        if (pom.findtext("{*}groupId"), pom.findtext("{*}artifactId"), pom.findtext("{*}version")) != (MAVEN_GROUP, module, release):
            raise ValueError("Maven POM identity differs from the candidate")
        for field in ("name", "description", "url", "licenses/license/name", "developers/developer/id", "scm/connection"):
            if not pom.findtext("/".join("{*}" + part for part in field.split("/"))):
                raise ValueError(f"Missing Central POM requirement: {module} {field}")
        if pom.findtext("{*}licenses/{*}license/{*}name") != "Apache-2.0":
            raise ValueError("Unexpected Maven licence")
        dependencies = {dep.findtext("{*}groupId") + ":" + dep.findtext("{*}artifactId"): dep.findtext("{*}version")
                        for dep in pom.findall("{*}dependencies/{*}dependency")}
        for dep, resolved in dependencies.items():
            if not resolved or any(marker in resolved for marker in ("+", "[", "]", "(", ")")):
                raise ValueError("Maven dependencies must use exact versions")
            if "SNAPSHOT" in resolved and not dep.startswith(MAVEN_GROUP + ":"):
                raise ValueError("Third-party dependencies cannot use SNAPSHOT")
            if dep.startswith(MAVEN_GROUP + ":") and resolved != release:
                raise ValueError("Maven client must pin this candidate's proto version")
        if module == "contracts-connect-client" and f"{MAVEN_GROUP}:contracts-proto" not in dependencies:
            raise ValueError("Maven client lost its proto dependency")
        if any(dep.endswith(":protobuf-java") or dep.endswith(":grpc-protobuf") for dep in dependencies):
            raise ValueError("Android artifacts must use protobuf lite")
        module_metadata = json.loads(files[prefix + ".module"])
        identity = module_metadata["component"]
        if (identity["group"], identity["module"], identity["version"]) != (MAVEN_GROUP, module, release):
            raise ValueError("Gradle metadata identity differs")
        for variant in module_metadata["variants"]:
            for item in variant.get("files", []):
                artifact = str(PurePosixPath(prefix).parent / item["url"])
                if artifact not in files or hashlib.sha512(files[artifact]).hexdigest() != item["sha512"]:
                    raise ValueError("Gradle metadata contains a wrong artifact hash")
        jar = zip_contents(files[prefix + ".jar"])
        for required in ("META-INF/LICENSE", "NOTICE", "README.md", "source.json", "sbom.cdx.json"):
            if not jar.get(required):
                raise ValueError(f"Maven JAR is missing {required}")
        if b"Apache License" not in jar["META-INF/LICENSE"]:
            raise ValueError("Maven JAR licence is incorrect")
        verify_package_notice(jar["NOTICE"])
        source = json.loads(jar["source.json"])
        if any(source[field] != manifest[field] for field in ("version", "commit", "dirty")):
            raise ValueError("Maven source metadata differs from candidate")
        if source["descriptorSha256"] != hashlib.sha256(descriptor).hexdigest():
            raise ValueError("Maven schema identity differs")
        sbom = json.loads(jar["sbom.cdx.json"])
        from build_identity import verify_report
        resource = f"META-INF/arcforges/{module}/build-identity.json"
        if not jar.get(resource) or jar.get("build-identity.json") != jar[resource]:
            raise ValueError("Maven module-specific build identity resource missing")
        verify_report(jar[resource], sbom, descriptor, manifest)
        if sbom["metadata"]["component"]["name"] != f"{MAVEN_GROUP}/{module}":
            raise ValueError("Maven SBOM identifies another module")
        classes = {"contracts-proto": "io/github/arcforges/contracts/hello/v1/SayHelloRequest.class",
                   "contracts-connect-client": "io/github/arcforges/contracts/hello/v1/HelloServiceClient.class",
                   "contract-fixtures": "io/github/arcforges/contracts/fixtures/ContractFixtures.class"}
        if classes[module] not in jar:
            raise ValueError(f"Maven JAR is missing its public API: {module}")
        if any(name.startswith(("com/google/", "io/grpc/", "kotlin/", "kotlinx/", "com/connectrpc/", "okhttp3/", "okio/", "io/ktor/")) for name in jar):
            raise ValueError("Runtime dependencies must not be shaded into Maven JARs")
        if module == "contracts-connect-client":
            if dependencies.get("com.connectrpc:connect-kotlin") is None or "io/github/arcforges/contracts/hello/v1/HelloServiceClientInterface.class" not in jar:
                raise ValueError("Connect client is missing its interface or runtime dependency")
            if "io/github/arcforges/contracts/hello/v1/SayHelloRequest.class" in jar:
                raise ValueError("Connect client must reuse the proto package's messages")
        if module == "contracts-proto" and (jar.get("contracts.binpb") != descriptor or "proto/arcforges/hello/v1/hello.proto" not in jar):
            raise ValueError("Maven proto or descriptor is missing")
        if module == "contract-fixtures" and not jar.get("arcforges/fixtures/hello.json"):
            raise ValueError("Maven fixture resource is missing")
        sources = zip_contents(files[prefix + "-sources.jar"])
        docs = zip_contents(files[prefix + "-javadoc.jar"])
        for companion in (sources, docs):
            if b"Apache License" not in companion.get("META-INF/LICENSE", b""):
                raise ValueError("Maven companion licence is missing")
            verify_package_notice(companion.get("NOTICE", b""))
        if not any(name.endswith((".java", ".kt")) for name in sources) or not any(name.endswith("index.html") for name in docs):
            raise ValueError("Maven sources or API documentation are missing")
        from documentation_tools import verify as verify_documentation
        documentation_receipts.append(verify_documentation(docs, module, dict(manifest, version=release), files[prefix + "-javadoc.jar"]))
    from contracts import write_json
    write_json(ARTIFACTS / "evidence/documentation-provenance.json", {
        "result": "passed", "sourceCommit": manifest["commit"], "version": release,
        "bundleSha256": hashlib.sha256(path.read_bytes()).hexdigest(), "archives": documentation_receipts})
    return files
