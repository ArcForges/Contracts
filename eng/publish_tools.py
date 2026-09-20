# SPDX-License-Identifier: Apache-2.0
"""Publish only verified main artifacts; never rebuild in a credentialed job."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
from pathlib import Path
import tempfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

from contracts import NPM, run, version
from packaging_tools import archive_files, verify_artifacts


def get(url: str) -> bytes | None:
    try:
        with urlopen(Request(url, headers={"User-Agent": "ArcForges-Contracts-CI"}), timeout=60) as response:
            return response.read()
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def existing_matches(path: Path, entry: dict, release: str) -> bool:
    if entry["kind"] == "npm":
        metadata = get(f"https://registry.npmjs.org/{quote(entry['id'], safe='')}/{release}")
        if metadata is None:
            return False
        actual = json.loads(metadata)["dist"]["integrity"]
        with path.open("rb") as stream:
            expected = "sha512-" + base64.b64encode(hashlib.file_digest(stream, "sha512").digest()).decode()
        if actual != expected:
            raise ValueError(f"Existing npm version has different bytes: {entry['id']}@{release}")
    else:
        package_id = entry["id"].lower()
        archive = get(f"https://api.nuget.org/v3-flatcontainer/{package_id}/{release}/{package_id}.{release}.nupkg")
        if archive is None:
            return False
        # nuget.org adds a repository signature, so compare all original ZIP entries.
        with zipfile.ZipFile(io.BytesIO(archive)) as remote:
            contents = {name: remote.read(name) for name in remote.namelist()
                        if not name.endswith("/") and name != ".signature.p7s"}
        if contents != archive_files(path):
            raise ValueError(f"Existing NuGet version has different contents: {entry['id']} {release}")
    print(f"Already published with matching contents: {entry['id']} {release}")
    return True


def npm_publish_tag(package_id: str, release: str) -> str:
    """Called inside the serialized npm job so an older run cannot rewind latest."""
    metadata = get(f"https://registry.npmjs.org/-/package/{quote(package_id, safe='')}/dist-tags")
    latest = json.loads(metadata).get("latest") if metadata is not None else None
    if latest is None:
        return "latest"
    from release_channels import stable
    version(release)
    version(latest)
    if stable(latest):
        if not stable(release):
            return "ci"
        return "latest" if tuple(map(int, release.split("."))) > tuple(map(int, latest.split("."))) else "release"
    if stable(release):
        return "latest"
    current = tuple(map(int, latest.split(".")[-2:]))
    incoming = tuple(map(int, release.split(".")[-2:]))
    return "latest" if incoming > current else "ci"


def publish_verified(directory: Path, registry: str) -> None:
    if (os.environ.get("GITHUB_REPOSITORY") != "ArcForges/Contracts"
            or not (os.environ.get("GITHUB_REF") == "refs/heads/main"
                    or os.environ.get("GITHUB_REF", "").startswith("refs/tags/v"))
            or os.environ.get("GITHUB_EVENT_NAME") != "push"):
        raise ValueError("Automated publishing is restricted to ArcForges/Contracts main or release-tag push runs")
    expected_commit = os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch("[0-9a-f]{40}", expected_commit):
        raise ValueError("Publishing requires the exact GitHub source commit")
    manifest = verify_artifacts(directory, expected_commit)
    from release_channels import authorize, maven_version
    authorize(manifest["version"])
    if manifest["dirty"]:
        raise ValueError("Never publish a candidate built from a dirty checkout")
    if registry == "maven":
        if manifest.get("mavenVersion") != maven_version(manifest["version"]):
            raise ValueError("Publication requires a channel-aware Maven candidate")
        if manifest["mavenVersion"].endswith("-SNAPSHOT"):
            from snapshot_publish import publish
        else:
            from central_publish import publish
        publish(directory, manifest)
        return
    # Keep manifest order: proto must be accepted before api-client is uploaded.
    entries = [entry for entry in manifest["files"] if entry["kind"] == registry]
    for entry in entries:
        path = directory / entry["name"]
        if existing_matches(path, entry, manifest["version"]):
            continue
        if registry == "nuget":
            if not os.environ.get("NUGET_API_KEY"):
                raise ValueError("NuGet OIDC login did not provide its short-lived credential")
            run("dotnet", "nuget", "push", path, "--source", "https://api.nuget.org/v3/index.json")
        else:
            tag = npm_publish_tag(entry["id"], manifest["version"])
            mode = os.environ.get("NPM_PUBLISH_MODE")
            if mode == "bootstrap":
                token = os.environ.get("NPM_BOOTSTRAP_TOKEN")
                if not token:
                    raise ValueError("Bootstrap mode requires the temporary npm environment secret")
                env = dict(os.environ, NODE_AUTH_TOKEN=token)
                # The first package has no trust relationship yet. Explicitly use
                # the one-time bootstrap credential, without attempting OIDC.
                env.pop("ACTIONS_ID_TOKEN_REQUEST_TOKEN", None)
                env.pop("ACTIONS_ID_TOKEN_REQUEST_URL", None)
                with tempfile.TemporaryDirectory(prefix="contracts-npm-auth-") as temporary:
                    config = Path(temporary) / "npmrc"
                    config.write_text("//registry.npmjs.org/:_authToken=${NODE_AUTH_TOKEN}\n", encoding="utf-8")
                    env["NPM_CONFIG_USERCONFIG"] = str(config)
                    run(NPM, "publish", path, "--access", "public", "--tag", tag, "--ignore-scripts", env=env)
            elif mode == "oidc":
                run(NPM, "publish", path, "--access", "public", "--tag", tag, "--ignore-scripts")
            else:
                raise ValueError("Choose bootstrap or oidc for NPM_PUBLISH_MODE")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"\n{registry}: registry accepted {manifest['version']} (or existing identical archives).\n")
            if registry == "npm":
                stream.write("Stable releases own npm latest after the first stable publication; development builds then use ci.\n")
            stream.write("Registry indexing may follow acceptance. Other registry jobs have separate results.\n")
