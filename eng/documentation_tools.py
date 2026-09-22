# SPDX-License-Identifier: Apache-2.0
"""Admit reviewed Dokka resources and verify every documentation archive member."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

from check_provenance import (INVENTORY, STORE, digest, document, fields, package_notice,
                              path as check_path, read, require, verify_package_notice)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "eng/provenance/artifact-profiles/dokka-2-2-0-r5.json"
MODULES = ("contracts-proto", "contracts-connect-client", "contract-fixtures")
THEME_FIX = (b"\n/* SPDX-License-Identifier: Apache-2.0; ArcForges documentation contrast correction. */\n"
             b".theme-dark .main-content a:not([data-name]) { color: var(--default-font-color); }\n")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_components(value: dict, records: dict) -> None:
    components = value["components"]
    require(len({item["record"] for item in components}) == len(components),
            "Documentation components have duplicate provenance IDs")
    require(len({(item["name"], item["version"]) for item in components}) == len(components),
            "Duplicate documentation component identity")
    for component in components:
        require(bool(component["emittedInputs"]), "Documentation component has no emitted inputs")
        names = []
        for member in component["emittedInputs"]:
            fields(member, "path sha256")
            names.append(check_path(member["path"]))
            digest(member["sha256"])
        require(len(set(names)) == len(names), "Duplicate emitted documentation input")
        require(component["record"] in records, "Documentation component has no active legal record")
        record = records[component["record"]]
        require(record["kind"] == "legal-text" and record["notice"]["distribution"] == "documentation" and
                record["sourceRepository"] == component["canonicalRepository"] and
                record["sourceCommit"] == component["gitHead"] and record["licence"]["spdx"] == component["spdx"],
                "Documentation component and legal source identities differ")
        require(any(item["url"] == component["tarball"] and item["sha256"] == component["archiveSha256"]
                    for item in record["verification"]["artifacts"]), "Documentation package archive identity differs")
        require({item["path"] for item in record["targets"]} <= set(record["notice"]["files"]),
                "Documentation component licence is absent from distributed notices")


def profile(root: Path = ROOT) -> dict:
    data = read(root, PROFILE)
    value = document(data)
    fields(value, "schemaVersion generator source inputs fixed excluded modules components fontTransform")
    require(value["schemaVersion"] == 1 and value["generator"] == "org.jetbrains.dokka:2.2.0",
            "Unreviewed documentation producer")
    inv = document(read(root, INVENTORY))
    records = {name: document(read(root, STORE + name + ".json"))
               for name in set(inv["reused"].values()) | set(inv["artifacts"])}
    verify_components(value, records)
    bound = []
    for name in inv["artifacts"]:
        record = document(read(root, STORE + name + ".json"))
        for target in record["artifactTargets"]:
            if target["kind"] == "maven-javadoc":
                require(target["profile"] == PROFILE and target["sha256"] == sha(data.replace(b"\r\n", b"\n")),
                        "Documentation profile differs from reviewed record")
                require(target["project"] in MODULES and target["package"] == "io.github.arcforges:" + target["project"],
                        "Unreviewed documentation package")
                bound.append(target["project"])
    require(sorted(bound) == sorted(MODULES), "Every documentation package requires one registered artifact record")
    for name, expected in value["inputs"].items():
        require(sha(read(root, name).replace(b"\r\n", b"\n")) == expected, "Documentation generation input changed: " + name)
    return value


def normalized_page(data: bytes, release: str) -> bytes:
    # Version display is the sole variable in the golden generated API pages.
    # No dates, arbitrary markup, scripts or source paths are stripped.
    return data.replace(b"\r\n", b"\n").replace(release.encode(), b"{version}")


def admit(raw: dict[str, bytes], module: str, release: str, policy: dict) -> dict[str, bytes]:
    expected = set(policy["fixed"]) | set(policy["excluded"]) | set(policy["modules"][module]["pages"])
    require(set(raw) == expected, "Unclassified or missing generated documentation members: " + module)
    result = {}
    for name, data in raw.items():
        if name in policy["excluded"]:
            require(sha(data) == policy["excluded"][name], "Unreviewed excluded font bytes: " + name)
            continue
        if name in policy["fixed"]:
            require(sha(data) == policy["fixed"][name]["upstreamSha256"], "Changed documentation resource: " + name)
            if name == "ui-kit/ui-kit.min.css":
                transformed, count = re.subn(rb"@font-face\s*\{[^{}]*\}", b"", data)
                require(count == policy["fontTransform"]["declarations"] and b"@font-face" not in transformed,
                        "Unexpected embedded font declarations")
                data = transformed
            if name == "styles/style.css":
                data += THEME_FIX
            require(sha(data) == policy["fixed"][name]["distributedSha256"], "Documentation transformation differs: " + name)
        else:
            require(sha(normalized_page(data, release)) == policy["modules"][module]["pages"][name],
                    "Generated documentation differs from reviewed API oracle: " + name)
        result[name] = data
    return result


def documentation_notice(root: Path = ROOT) -> bytes:
    inv = document(read(root, INVENTORY))
    names = set(inv["reused"].values()) | set(inv["artifacts"])
    legal = set()
    for name in names:
        record = document(read(root, STORE + name + ".json"))
        if record["notice"]["distribution"] == "documentation":
            legal.update(p for p in record["notice"]["files"] if p.startswith("third-party/dokka/"))
    require(bool(legal), "Documentation licence closure is missing")
    parts = [package_notice(root, documentation=True).encode()]
    for name in sorted(legal):
        parts.extend([b"\n--- " + name.encode() + b" ---\n", read(root, name).replace(b"\r\n", b"\n"), b"\n"])
    return b"".join(parts)


def prepare(release: str, root: Path = ROOT) -> None:
    policy = profile(root)
    output = root / "artifacts/documentation"
    require(output.resolve().is_relative_to((root / "artifacts").resolve()), "Documentation output escaped artifacts")
    if output.exists():
        shutil.rmtree(output)
    doc_notice = documentation_notice(root)
    for module in MODULES:
        generated = root / f"src/public/kotlin/{module}/build/dokka/html"
        raw = {p.relative_to(generated).as_posix(): p.read_bytes() for p in generated.rglob("*") if p.is_file()}
        accepted = admit(raw, module, release, policy)
        accepted["NOTICE"] = read(root, f"artifacts/maven-metadata/{module}/NOTICE").replace(b"\r\n", b"\n") + b"\n" + doc_notice
        for name, data in accepted.items():
            target = output / module / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def verify(docs: dict[str, bytes], module: str, manifest: dict, archive: bytes, root: Path = ROOT) -> dict:
    policy = profile(root)
    pages = policy["modules"][module]["pages"]
    expected = set(policy["fixed"]) | set(pages) | {"NOTICE", "META-INF/MANIFEST.MF", "META-INF/LICENSE"}
    require(set(docs) == expected, "Unclassified or missing documentation archive members: " + module)
    require(docs["META-INF/LICENSE"].replace(b"\r\n", b"\n") == read(root, "LICENSE").replace(b"\r\n", b"\n"),
            "Documentation root licence changed")
    require(docs["META-INF/MANIFEST.MF"].replace(b"\r\n", b"\n") == b"Manifest-Version: 1.0\n\n",
            "Unreviewed documentation manifest")
    verify_package_notice(docs["NOTICE"], root)
    require(documentation_notice(root) in docs["NOTICE"].replace(b"\r\n", b"\n"), "Documentation lost full resource notices")
    for name, entry in policy["fixed"].items():
        require(sha(docs[name]) == entry["distributedSha256"], "Changed packaged documentation resource: " + name)
    for name, expected_hash in pages.items():
        require(sha(normalized_page(docs[name], manifest.get("mavenVersion", manifest["version"]))) == expected_hash,
                "Packaged API documentation differs from oracle: " + name)
    for name, markers in policy["modules"][module]["publicApi"].items():
        for marker in markers:
            require(marker.encode() in docs[name], "Public API documentation is incomplete: " + name)
    inv = document(read(root, INVENTORY))
    records = sorted(set(inv["artifacts"]) | {name for name in inv["reused"].values()
                     if document(read(root, STORE + name + ".json"))["notice"]["distribution"] == "documentation"})
    return {"module": module, "kind": "maven-javadoc", "version": manifest["version"],
            "sourceCommit": manifest["commit"], "dirty": manifest["dirty"], "archiveSha256": sha(archive),
            "profileSha256": sha(read(root, PROFILE).replace(b"\r\n", b"\n")), "recordIds": records,
            "members": {name: sha(data) for name, data in sorted(docs.items())},
            "noticeSha256": sha(docs["NOTICE"]), "result": "passed"}
