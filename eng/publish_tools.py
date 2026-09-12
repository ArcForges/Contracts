# SPDX-License-Identifier: AGPL-3.0-only
"""Publish only verified main artifacts; never rebuild in a credentialed job."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
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
    # This bootstrap only publishes 1.0.0-ci.<run>.<attempt>. Do not guess how a
    # future stable/other release series should be promoted by this workflow.
    try:
        current = tuple(int(part) for part in version(latest).split(".")[-2:])
        incoming = tuple(int(part) for part in version(release).split(".")[-2:])
    except ValueError as error:
        raise ValueError(f"Review the npm release policy before replacing latest={latest}: {package_id}") from error
    if incoming > current:
        return "latest"
    print(f"Preserving npm latest={latest}: {package_id} {release} will use the ci tag")
    return "ci"


def publish_verified(directory: Path, registry: str) -> None:
    if (os.environ.get("GITHUB_REPOSITORY") != "ArcForges/Contracts"
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_EVENT_NAME") != "push"):
        raise ValueError("Automated publishing is restricted to ArcForges/Contracts main push runs")
    manifest = verify_artifacts(directory, os.environ.get("GITHUB_SHA"))
    if manifest["dirty"]:
        raise ValueError("Never publish a candidate built from a dirty checkout")
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
                stream.write("Newer CI versions update npm latest; older runs preserve it using the ci tag.\n")
            stream.write("Registry indexing may follow acceptance. Other registry jobs have separate results.\n")
