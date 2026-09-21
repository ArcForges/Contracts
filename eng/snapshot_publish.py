# SPDX-License-Identifier: Apache-2.0
"""Publish the retained latest-main SNAPSHOT; remote-byte inspection is opt-in."""

import hashlib
import json
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

from contracts import ARTIFACTS, ROOT, run, write_json
from kotlin_tools import MAVEN_MODULES, gradle
from maven_tools import SUFFIXES, zip_contents
from publish_tools import get

PUBLIC = "https://central.sonatype.com/repository/maven-snapshots/"


def resolve(module: str, version: str, repository: str = PUBLIC) -> dict[str, str]:
    prefix = f"io/github/arcforges/{module}/{version}/"
    metadata = get(repository + prefix + "maven-metadata.xml")
    if metadata is None:
        return {}
    root = ET.fromstring(metadata)
    if tuple(root.findtext(field) for field in ("groupId", "artifactId", "version")) != (
            "io.github.arcforges", module, version):
        raise ValueError("Snapshot metadata identifies another module")
    result = {}
    for item in root.findall("versioning/snapshotVersions/snapshotVersion"):
        extension = item.findtext("extension")
        classifier = item.findtext("classifier", "")
        suffix = ("-" + classifier if classifier else "") + "." + str(extension)
        if suffix not in SUFFIXES:
            continue
        value = item.findtext("value", "")
        if not re.fullmatch(re.escape(version.removesuffix("SNAPSHOT")) + r"\d{8}\.\d{6}-[1-9][0-9]*", value):
            raise ValueError("Invalid timestamped snapshot identity")
        if suffix in result:
            raise ValueError("Duplicate snapshot artifact metadata")
        result[suffix] = prefix + module + "-" + value + suffix
    return result


def inspect(files: dict[str, bytes], manifest: dict, repository: str = PUBLIC) -> tuple[bool, list]:
    version = manifest["mavenVersion"]
    incoming = tuple(map(int, manifest["version"].split(".")[-2:]))
    records = []
    complete = True
    for module in MAVEN_MODULES:
        resolved = resolve(module, version, repository)
        if set(resolved) != set(SUFFIXES):
            complete = False
        timestamps = set()
        for suffix, remote in resolved.items():
            data = get(repository + remote)
            candidate = f"io/github/arcforges/{module}/{version}/{module}-{version}{suffix}"
            if data is None:
                complete = False
                continue
            if suffix == ".jar":
                source = json.loads(zip_contents(data)["source.json"])
                build = source["version"]
                if not re.fullmatch(r"1\.0\.0-ci\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", build):
                    raise ValueError("Snapshot contains an unknown build identity")
                if tuple(map(int, build.split(".")[-2:])) > incoming:
                    raise ValueError("A newer snapshot is published; refusing to rewind it")
                if build == manifest["version"] and data != files[candidate]:
                    raise ValueError("Existing snapshot build has different bytes")
            if data != files[candidate]:
                complete = False
            timestamps.add(remote.removeprefix(f"io/github/arcforges/{module}/{version}/{module}-").removesuffix(suffix))
            records.append({"candidate": candidate, "remote": remote,
                            "sha256": hashlib.sha256(data).hexdigest(), "matches": data == files[candidate]})
        if len(timestamps) != 1:
            complete = False
    return complete, records


def transport(files: dict[str, bytes], version: str, repository: str = PUBLIC) -> None:
    with tempfile.TemporaryDirectory(prefix="contracts-snapshot-") as temporary:
        stage = Path(temporary)
        for name, data in files.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        gradle("-p", ROOT / "eng/central-signing", "--no-configuration-cache",
               "publishAllPublicationsToSnapshotsRepository", f"-PcandidateDirectory={stage}",
               f"-PexpectedFileCount={len(files)}", f"-PsnapshotVersion={version}",
               f"-PsnapshotRepository={repository}")
        if any((stage / name).read_bytes() != data for name, data in files.items()):
            raise ValueError("Snapshot transport modified tested candidate files")


def publish(directory: Path, manifest: dict) -> None:
    entry = next(item for item in manifest["files"] if item["kind"] == "maven")
    receipt = {"channel": "snapshot", "version": manifest["version"], "mavenVersion": manifest["mavenVersion"],
               "commit": manifest["commit"], "candidateSha256": entry["sha256"], "phase": "checking-main"}
    evidence = ARTIFACTS / "publication/deployment.json"
    write_json(evidence, receipt)
    # The serialized publication job checks one small GitHub ref response, not public JARs.
    current = json.loads(run("gh", "api", "repos/ArcForges/Contracts/git/ref/heads/main", capture=True))
    if (current.get("ref") != "refs/heads/main" or current.get("object", {}).get("type") != "commit"
            or not re.fullmatch(r"[0-9a-f]{40}", current.get("object", {}).get("sha", ""))):
        raise ValueError("GitHub returned an invalid main branch identity")
    if current["object"]["sha"] != manifest["commit"]:
        receipt["phase"] = "superseded"
        write_json(evidence, receipt)
        print("Snapshot upload skipped: a newer main commit owns the development channel.", flush=True)
        return
    # publish_verified already validates the retained bundle's identity and digest.
    files = zip_contents((directory / entry["name"]).read_bytes())
    receipt["phase"] = "upload-started"
    write_json(evidence, receipt)
    transport(files, manifest["mavenVersion"])
    receipt["phase"] = "upload-completed"
    write_json(evidence, receipt)
    print("Sonatype snapshot upload completed; no public-byte polling was performed.", flush=True)
