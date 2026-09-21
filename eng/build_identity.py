# SPDX-License-Identifier: Apache-2.0
"""Contracts-owned support metadata; compatibility versions never follow releases."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
AXES = ("AppVersion", "ContractSet", "CapabilityVersion", "NativeFormatVersion",
        "StorageSchemaVersion", "NativeAbiVersion", "PolicySchemaVersion",
        "ExtensionProtocolVersion", "PackageVersion")
KINDS = ("release", "contracts", "declarations", "declarations", "migrations",
         "native-abi", "declarations", "declarations", "packages")


def git(*arguments: str, root: Path = ROOT) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root, text=True, encoding="utf-8").strip()


def build(root: Path = ROOT, environment: dict | None = None) -> dict:
    env = os.environ if environment is None else environment
    commit = git("rev-parse", "HEAD", root=root)
    dirty = bool(git("status", "--porcelain", root=root))
    epoch = int(git("show", "-s", "--format=%ct", commit, root=root))
    ci = env.get("GITHUB_ACTIONS") == "true" or env.get("CI", "").lower() == "true"
    result = {"sourceCommit": commit, "dirty": dirty, "kind": "ci" if ci else "local",
              "buildId": "local", "runId": None, "runAttempt": None,
              "pipelineRun": None, "sourceDateEpoch": epoch}
    if ci:
        run, attempt = env.get("GITHUB_RUN_ID", ""), env.get("GITHUB_RUN_ATTEMPT", "")
        if (dirty or env.get("GITHUB_SHA") != commit
                or env.get("GITHUB_REPOSITORY") != "ArcForges/Contracts"
                or not re.fullmatch(r"[1-9][0-9]*", run)
                or not re.fullmatch(r"[1-9][0-9]*", attempt)
                or env.get("GITHUB_SERVER_URL") != "https://github.com"):
            raise ValueError("Incomplete, dirty or mismatched CI build identity")
        result.update(buildId=f"{run}.{attempt}", runId=run, runAttempt=int(attempt),
                      pipelineRun=f"https://github.com/ArcForges/Contracts/actions/runs/{run}")
    validate_build(result)
    return result


def validate_build(value: dict) -> None:
    if (set(value) != {"sourceCommit", "dirty", "kind", "buildId", "runId", "runAttempt", "pipelineRun", "sourceDateEpoch"}
            or not re.fullmatch(r"[0-9a-f]{40}", value["sourceCommit"])
            or type(value["dirty"]) is not bool or type(value["sourceDateEpoch"]) is not int
            or value["sourceDateEpoch"] <= 0):
        raise ValueError("Malformed build identity")
    if value["kind"] == "ci":
        run, attempt = value["runId"], value["runAttempt"]
        if (not isinstance(run, str) or not re.fullmatch(r"[1-9][0-9]*", run)
                or type(attempt) is not int or attempt < 1 or value["dirty"]
                or value["buildId"] != f"{run}.{attempt}"
                or value["pipelineRun"] != f"https://github.com/ArcForges/Contracts/actions/runs/{run}"):
            raise ValueError("Malformed CI build identity")
    elif value["kind"] != "local" or value["buildId"] != "local" or any(value[key] is not None for key in ("runId", "runAttempt", "pipelineRun")):
        raise ValueError("Malformed local build identity")


def validate_source(value: dict, root: Path = ROOT) -> None:
    validate_build(value)
    if value["sourceCommit"] != git("rev-parse", "HEAD", root=root):
        raise ValueError("Build identity source commit differs from checkout")
    if value["sourceDateEpoch"] != int(git("show", "-s", "--format=%ct", value["sourceCommit"], root=root)):
        raise ValueError("Build identity source timestamp differs")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if (value["kind"] != "ci" or value["runId"] != os.environ.get("GITHUB_RUN_ID")
                or value["runAttempt"] > int(os.environ["GITHUB_RUN_ATTEMPT"])):
            raise ValueError("Build identity belongs to another pipeline run")


def source(path: str, root: Path) -> tuple[bytes, dict]:
    if Path(path).is_absolute() or "\\" in path or ":" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError("Version source must be an owner-relative path")
    candidate = root / path
    if not candidate.resolve().is_relative_to(root.resolve()) or candidate.is_symlink():
        raise ValueError("Version source escapes owner")
    content = candidate.read_bytes().replace(b"\r\n", b"\n")
    return content, {"path": path, "sha256": hashlib.sha256(content).hexdigest()}


def axes(package: dict, dependencies: list[dict], descriptor: bytes, root: Path = ROOT,
         catalog: dict | None = None) -> dict:
    if catalog is None:
        catalog = json.loads((root / "eng/version-sources.json").read_text(encoding="utf-8"))
    if set(catalog.get("axes", {})) != set(AXES) or catalog.get("owner") != "Contracts" or catalog.get("schemaVersion") != 1:
        raise ValueError("Version source catalog must define exactly nine axes")
    output = {}
    for name, kind in zip(AXES, KINDS, strict=True):
        spec = catalog["axes"][name]
        if spec.get("kind") != kind:
            raise ValueError(f"Wrong independent source kind for {name}")
        if "absence" in spec:
            allowed = {"kind", "absence", "reason", "producer"}
            if set(spec) - allowed or spec["absence"] not in {"not-applicable", "not-produced"} or not spec.get("reason"):
                raise ValueError("Invalid absent axis")
            if spec["absence"] == "not-produced" and not spec.get("producer"):
                raise ValueError("Absent producer must identify its future owner")
            output[name] = {"status": spec["absence"], "reason": spec["reason"]}
            if "producer" in spec:
                output[name]["producer"] = spec["producer"]
            continue
        if set(spec) - {"kind", "sources"}:
            raise ValueError("Aliases and unknown version source properties are forbidden")
        values = []
        if kind == "packages":
            proof = hashlib.sha256(json.dumps(dependencies, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            values = [{"subject": item["purl"].rsplit("@", 1)[0],
                       "version": item["version"], "source": {"path": "sbom.cdx.json#components", "sha256": proof}}
                      for item in dependencies]
        else:
            for path in spec.get("sources", []):
                content, evidence = source(path, root)
                if kind == "contracts":
                    matches = re.findall(rb"^package\s+([a-zA-Z0-9_.]+)\.v([1-9][0-9]*);", content, re.MULTILINE)
                    if len(matches) != 1 or not descriptor:
                        raise ValueError("Contract source requires its authored namespace and descriptor")
                    subject, major = matches[0]
                    values.append({"subject": subject.decode(), "version": major.decode(), "source": evidence,
                                   "descriptorSha256": hashlib.sha256(descriptor).hexdigest()})
                elif kind == "native-abi":
                    major = re.search(rb"#define\s+ARC_ABI_MAJOR\s+(\d+)", content)
                    minor = re.search(rb"#define\s+ARC_ABI_MINOR\s+(\d+)", content)
                    if not major or not minor:
                        raise ValueError("Native ABI constants missing")
                    values.append({"subject": path, "version": major[1].decode() + "." + minor[1].decode(), "source": evidence})
                else:
                    declared = json.loads(content)
                    entries = declared["migrations"][-1:] if kind == "migrations" else declared["versions"]
                    values.extend({"subject": item["subject"], "version": item["version"], "source": evidence} for item in entries)
        if not values and kind != "packages":
            raise ValueError(f"No implemented source for {name}")
        seen = set()
        for value in values:
            if (not isinstance(value["subject"], str) or not value["subject"] or value["subject"] in seen
                    or not isinstance(value["version"], str) or not re.fullmatch(r"[0-9]+(?:[.][0-9]+)*(?:[-+][A-Za-z0-9.-]+)?", value["version"])):
                raise ValueError("Duplicate subject or malformed independent version")
            seen.add(value["subject"])
        output[name] = {"status": "present", "values": sorted(values, key=lambda item: item["subject"])}
    return copy.deepcopy(output)


def report(package: dict, dependencies: list[dict], descriptor: bytes, identity: dict) -> dict:
    validate_build(identity)
    return {"schema": "arcforges.build-identity.v1", "owner": "Contracts",
            "artifact": {"id": package["name"], "version": package["version"]},
            "build": copy.deepcopy(identity), "axes": axes(package, dependencies, descriptor)}


def verify_report(data: bytes, sbom: dict, descriptor: bytes, manifest: dict) -> None:
    expected = report(sbom["metadata"]["component"], sbom["components"], descriptor, manifest["build"])
    if json.loads(data) != expected:
        raise ValueError("Packaged build identity or independent version axes differ")
