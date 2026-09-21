# SPDX-License-Identifier: Apache-2.0
"""Publish a verified Maven bundle; keep deployment receipts for safe CI retries."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid
import zipfile

from contracts import ARTIFACTS, ROOT, run, sha256, write_json
from kotlin_tools import MAVEN_MODULES, gradle
from maven_tools import zip_contents
from publish_tools import get

API = "https://central.sonatype.com/api/v1/publisher"
PUBLIC = "https://repo.maven.apache.org/maven2/"


def registry_matches(files: dict[str, bytes]) -> bool:
    present = 0
    for name, data in files.items():
        existing = get(PUBLIC + name)
        if existing is None:
            continue
        if existing != data:
            raise ValueError(f"Existing Maven version has different bytes: {name}")
        present += 1
    if present == len(files):
        return True
    if present:
        raise ValueError("Maven publication is only partly visible; retain the deployment receipt and retry after propagation")
    return False


def request(endpoint: str, credential: str, data: bytes = b"", content_type: str = "application/json") -> bytes:
    with urlopen(Request(API + endpoint, data=data, method="POST", headers={
        "Authorization": "Bearer " + credential,
        "Content-Type": content_type,
        "User-Agent": "ArcForges-Contracts-CI",
    }), timeout=60) as response:
        return response.read()


def recover_receipt(identity: dict) -> dict | None:
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not run_id or not os.environ.get("GH_TOKEN"):
        return None
    records = json.loads(run("gh", "api", f"repos/ArcForges/Contracts/actions/runs/{run_id}/artifacts?per_page=100", capture=True))
    names = sorted(item["name"] for item in records["artifacts"]
                   if item["name"].startswith(f"maven-deployment-{run_id}-") and not item["expired"])
    recovered = []
    with tempfile.TemporaryDirectory(prefix="contracts-receipts-") as temporary:
        for index, name in enumerate(names):
            output = Path(temporary) / str(index)
            run("gh", "run", "download", run_id, "--repo", "ArcForges/Contracts", "--name", name, "--dir", output)
            receipt = json.loads((output / "deployment.json").read_text())
            if all(receipt.get(key) == value for key, value in identity.items()):
                recovered.append(receipt)
    ids = {item["deploymentId"] for item in recovered if item.get("deploymentId")}
    if len(ids) > 1:
        raise ValueError("Conflicting Maven deployment receipts; inspect the Central Portal")
    return next((item for item in recovered if item.get("deploymentId")), recovered[0] if recovered else None)


def signed_bundle(files: dict[str, bytes], directory: Path) -> Path:
    repository = directory / "repository"
    for name, data in files.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    gradle("-p", ROOT / "eng/central-signing", "--offline", "--no-configuration-cache", "signCandidate",
           f"-PcandidateDirectory={repository}", f"-PexpectedFileCount={len(files)}")
    for name, data in files.items():
        path = repository / name
        if path.read_bytes() != data or not path.with_name(path.name + ".asc").is_file():
            raise ValueError("Signing changed a tested file or did not produce its detached signature")
        for algorithm in ("md5", "sha1", "sha256", "sha512"):
            path.with_name(path.name + "." + algorithm).write_text(hashlib.new(algorithm, data).hexdigest(), encoding="ascii")
    bundle = directory / "central-bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(repository.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(repository).as_posix())
    return bundle


def publish(directory: Path, manifest: dict) -> None:
    deadline = time.monotonic() + 540
    entry = next(item for item in manifest["files"] if item["kind"] == "maven")
    unsigned = directory / entry["name"]
    # publish_verified already checks the producer candidate at this trust handoff.
    files = zip_contents(unsigned.read_bytes())
    identity = {"version": manifest["version"], "commit": manifest["commit"], "candidateSha256": sha256(unsigned)}
    receipt = recover_receipt(identity) or dict(identity, deploymentId=None, phase="not-uploaded")
    evidence = ARTIFACTS / "publication/deployment.json"
    write_json(evidence, receipt)
    required = ("MAVEN_CENTRAL_USERNAME", "MAVEN_CENTRAL_TOKEN")
    if any(not os.environ.get(name) for name in required):
        raise ValueError("Configure the Maven Central environment credentials before enabling publication")
    credential = base64.b64encode(":".join(os.environ[name] for name in required).encode()).decode()
    override = os.environ.get("MAVEN_CENTRAL_DEPLOYMENT_ID", "").strip()
    if override:
        # Exceptional recovery only: the administrator obtains the ID from Central.
        # Status identity/coordinates below still reject another deployment.
        receipt["deploymentId"] = str(uuid.UUID(override))
    if not receipt.get("deploymentId"):
        if receipt["phase"] != "not-uploaded":
            raise ValueError("The previous Maven upload has an uncertain outcome. Inspect Central and set MAVEN_CENTRAL_DEPLOYMENT_ID; do not blindly re-upload")
        if not os.environ.get("MAVEN_SIGNING_KEY") or "MAVEN_SIGNING_PASSWORD" not in os.environ:
            raise ValueError("Configure the in-memory Maven PGP signing secrets")
        with tempfile.TemporaryDirectory(prefix="contracts-central-") as temporary:
            bundle = signed_bundle(files, Path(temporary))
            boundary = "arcforges-" + uuid.uuid4().hex
            data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"bundle\"; filename=\"central-bundle.zip\"\r\n"
                    "Content-Type: application/octet-stream\r\n\r\n").encode() + bundle.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
            receipt["phase"] = "upload-started"
            write_json(evidence, receipt)
            # Never automatically retry this POST: a lost response is not failure
            # evidence. The retained receipt records that ambiguity for the retry.
            deployment = request("/upload?" + urlencode({"name": "ArcForges-Contracts-" + manifest["version"],
                                  "publishingType": "AUTOMATIC"}), credential, data, "multipart/form-data; boundary=" + boundary)
            receipt.update(deploymentId=str(uuid.UUID(deployment.decode().strip())), phase="uploaded")
            write_json(evidence, receipt)
    deployment_id = str(uuid.UUID(receipt["deploymentId"]))
    print(f"Maven Central deployment: {deployment_id}", flush=True)
    while time.monotonic() < deadline:
        status = json.loads(request("/status?" + urlencode({"id": deployment_id}), credential))
        if (status.get("deploymentId") != deployment_id
                or status.get("deploymentName") != "ArcForges-Contracts-" + manifest["version"]):
            raise ValueError("Central status identifies another deployment")
        state = status["deploymentState"]
        receipt.update(phase=state, deploymentId=deployment_id)
        write_json(evidence, receipt)
        print(f"Maven Central: {state}", flush=True)
        if state == "PUBLISHED":
            expected = {f"pkg:maven/io.github.arcforges/{module}@{manifest['version']}" for module in MAVEN_MODULES}
            if set(status.get("purls", [])) != expected:
                raise ValueError("Published Central coordinates differ from the candidate")
            print("Maven Central reports PUBLISHED for the expected coordinates.", flush=True)
            return
        if state in {"FAILED", "VALIDATED"}:
            raise ValueError(f"Central requires attention: {state}; deployment {deployment_id}. Inspect the Portal validation details")
        if state not in {"PENDING", "VALIDATING", "PUBLISHING"}:
            raise ValueError(f"Unknown Central deployment state: {state}")
        time.sleep(15)
    else:
        raise ValueError("Central deployment is still processing; re-run failed jobs to resume its retained receipt")
