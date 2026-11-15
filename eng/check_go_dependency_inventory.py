# SPDX-License-Identifier: Apache-2.0
"""Measure selected Go modules and actual tool/owned-test dependencies without changing source or locks.

This is evidence for one native host/configuration, not latest-version admission or aggregate qualification.
The explicit output must be outside the checkout or below its ignored artifacts/ directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import go_bindings

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "arcforges.contracts.go-dependency-inventory.v1"
# Design AD-0023 amendment, merged 2296e2fe37ad9ad1f7b65be871fea1f0b39ce7ad.
# These are candidates only; membership never overrides measured use.
METADATA_CANDIDATES = frozenset({
    "golang.org/x/tools/go/expect", "golang.org/x/tools/go/packages/packagestest",
    "github.com/google/go-cmdtest", "github.com/google/go-cmp", "github.com/google/renameio",
    "github.com/yuin/goldmark", "golang.org/x/net", "golang.org/x/exp", "github.com/golang/protobuf",
})
INPUTS = ("go/go.mod", "go/go.sum", "go/tools/go.mod", "go/tools/go.sum", "go/toolchain.json")
NUMBER = r"(?:0|[1-9][0-9]*)"
PRERELEASE = r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
VERSION = re.compile(r"v" + NUMBER + r"\." + NUMBER + r"\." + NUMBER
                     + r"(?:-" + PRERELEASE + r"(?:\." + PRERELEASE + r")*)?"
                     + r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
APPLIED_ENVIRONMENT = {"GOTOOLCHAIN": "local", "GOWORK": "off", "GOFLAGS": "-mod=readonly", "GOTELEMETRY": "off"}
GO_ENV = ("GOVERSION", "GOROOT", "GOOS", "GOARCH", "GOHOSTOS", "GOHOSTARCH", "CGO_ENABLED",
          "GOAMD64", "GOEXPERIMENT", "GOFLAGS", "GOWORK", "GOTOOLCHAIN", "GOTELEMETRY", "GOMOD", "CC", "CXX")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON object key: " + key)
        result[key] = value
    return result


def json_stream(text: str) -> list[dict]:
    def invalid_constant(value):
        raise ValueError("Nonfinite JSON constant: " + value)

    decoder = json.JSONDecoder(object_pairs_hook=unique_object, parse_constant=invalid_constant)
    result, offset = [], 0
    while offset < len(text):
        if text[offset].isspace():
            offset += 1
            continue
        value, offset = decoder.raw_decode(text, offset)
        require(isinstance(value, dict), "Expected Go JSON object stream")
        result.append(value)
    require(bool(result), "Empty Go JSON output")
    return result


def module_graph(records: list[dict], main_path: str) -> dict[str, dict]:
    result = {}
    for value in records:
        path = value.get("Path")
        require(isinstance(path, str) and bool(path), "Module has no path")
        require(path not in result, "Duplicate module path: " + path)
        require(not value.get("Error") and not value.get("Replace"), "Module error/replacement: " + path)
        if value.get("Main") is True:
            require(path == main_path and not value.get("Version"), "Unexpected main module: " + path)
        else:
            require(isinstance(value.get("Version"), str) and VERSION.fullmatch(value["Version"]) is not None,
                    "Missing/noncanonical selected module version: " + path)
        result[path] = value
    require(sum(value.get("Main") is True for value in result.values()) == 1, "Expected one main module")
    return dict(sorted(result.items()))


def package_closure(records: list[dict], graph: dict[str, dict]) -> list[dict]:
    result = {}
    for value in records:
        path = value.get("ImportPath")
        require(isinstance(path, str) and bool(path), "Package has no import path")
        require(path not in result, "Duplicate package identity: " + path)
        require(not any(value.get(key) for key in ("Error", "DepsErrors", "Incomplete")),
                "Incomplete/error package: " + path)
        package = {"importPath": path, "standard": value.get("Standard") is True}
        module = value.get("Module")
        if module is not None:
            require(isinstance(module, dict) and not module.get("Replace") and not module.get("Error"),
                    "Invalid/replaced package module: " + path)
            selected = graph.get(module.get("Path"))
            require(selected is not None and module.get("Version", "") == selected.get("Version", ""),
                    "Package module is absent from or disagrees with selected graph: " + path)
            require(not package["standard"], "Standard package unexpectedly has a module: " + path)
            package.update(modulePath=module["Path"], moduleVersion=module.get("Version", ""))
        else:
            require(package["standard"], "Unclassified nonstandard package: " + path)
        for source, target in (("Imports", "imports"), ("ForTest", "forTest")):
            if source in value:
                valid = (isinstance(value[source], list) and all(isinstance(item, str) for item in value[source])
                         if source == "Imports" else isinstance(value[source], str))
                require(valid, "Invalid package " + source)
                package[target] = sorted(value[source]) if source == "Imports" else value[source]
        result[path] = package
    require(bool(result), "Empty package closure")
    return [result[path] for path in sorted(result)]


def classification(graphs: dict[str, dict], closures: dict[str, list[dict]]) -> dict:
    selected, actual = {}, {}
    for name, graph in graphs.items():
        for path, module in graph.items():
            if module.get("Main") is not True:
                selected.setdefault((path, module["Version"]), []).append(name)
    for name, packages in closures.items():
        for package in packages:
            if package.get("moduleVersion"):
                actual.setdefault((package["modulePath"], package["moduleVersion"]), set()).add(name)
    require(set(actual) <= set(selected), "Actual closure contains a module outside both selected graphs")
    used_paths = {path for path, _ in actual}

    def row(identity):
        path, version = identity
        return {"path": path, "version": version, "selectedIn": sorted(selected[identity]),
                "usedIn": sorted(actual.get(identity, ()))}

    metadata = []
    for identity in sorted(set(selected) - set(actual)):
        item = row(identity)
        item["namedCandidate"] = identity[0] in METADATA_CANDIDATES
        item["eligibleForThisHostConfiguration"] = item["namedCandidate"] and identity[0] not in used_paths
        metadata.append(item)
    candidates = []
    for path in sorted(METADATA_CANDIDATES):
        versions = [row(identity) for identity in sorted(selected) if identity[0] == path]
        used = sorted({name for identity, names in actual.items() if identity[0] == path for name in names})
        candidates.append({"path": path, "selected": versions, "usedIn": used,
                           "eligibleForThisHostConfiguration": bool(versions) and not used,
                           "reason": "actual-dependency" if used else "metadata-only" if versions else "not-selected"})
    return {"actualDependencies": [row(identity) for identity in sorted(actual)],
            "metadataOnly": metadata, "namedCandidates": candidates}


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
    require(result.returncode == 0, "Git query failed: " + " ".join(args))
    return result.stdout


def tree_snapshot(root: Path) -> dict:
    files = {}
    names = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").decode("utf-8").split("\0")
    for name in sorted(set(names) - {""}):
        path = root / name
        try:
            before = path.lstat()
        except FileNotFoundError:
            files[name] = None  # An already deleted path is still part of the starting tree identity.
            continue
        if stat.S_ISLNK(before.st_mode):
            digest = sha(os.readlink(path).encode("utf-8"))
        else:
            require(stat.S_ISREG(before.st_mode), "Non-file source tree entry: " + name)
            digest = sha(path.read_bytes())
        after = path.lstat()
        require((before.st_mode, before.st_size, before.st_mtime_ns) ==
                (after.st_mode, after.st_size, after.st_mtime_ns), "Source changed while hashing: " + name)
        files[name] = [before.st_mode, before.st_size, before.st_mtime_ns, digest]
    return {"head": git(root, "rev-parse", "HEAD").decode().strip(),
            "statusSha256": sha(git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")),
            "dirty": bool(git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")),
            "indexSha256": sha(git(root, "ls-files", "--stage", "-z")), "files": files}


def unchanged(before: dict, after: dict) -> None:
    require(before == after, "Source tree, index, HEAD or lock bytes drifted during Go inventory measurement")


class GoQueries:
    def __init__(self):
        path = shutil.which("go")
        require(path is not None, "Go is missing from PATH")
        self.path = str(Path(path).resolve())
        self.environment = go_bindings.environment()
        require(all(self.environment.get(key) == value for key, value in APPLIED_ENVIRONMENT.items()),
                "go_bindings environment no longer selects the reviewed query configuration")
        self.commands: list[dict] = []

    def run(self, arguments: list[str], cwd: Path) -> str:
        command = [self.path, *arguments]
        result = subprocess.run(command, cwd=cwd, env=self.environment, capture_output=True,
                                text=True, encoding="utf-8", errors="strict", timeout=120)
        self.commands.append({"argv": command, "cwd": str(cwd), "exitCode": result.returncode,
                              "stdoutSha256": sha(result.stdout.encode()), "stderrSha256": sha(result.stderr.encode())})
        require(result.returncode == 0, "Go query failed with exit " + str(result.returncode) + ": " + " ".join(arguments))
        return result.stdout


def measure(root: Path, report: dict) -> None:
    before = tree_snapshot(root)
    report["source"] = {key: value for key, value in before.items() if key != "files"}
    report["source"].update(fileCount=len(before["files"]),
                            treeSha256=sha(json.dumps(before, sort_keys=True).encode()))
    try:
        report["inputs"] = {}
        for name in INPUTS:
            path = root / name
            require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root),
                    "Dependency input must be a regular file inside the checkout: " + name)
            data = path.read_bytes()
            report["inputs"][name] = {"sha256": sha(data), "sha256Lf": sha(data.replace(b"\r\n", b"\n"))}
        queries = GoQueries()
        report["commands"] = queries.commands
        version = queries.run(["version"], root / "go").strip()
        config_records = json_stream(queries.run(["env", "-json", *GO_ENV], root / "go"))
        require(len(config_records) == 1, "Expected one Go configuration object")
        config = config_records[0]
        expected = json_stream((root / "go/toolchain.json").read_text(encoding="utf-8"))[0]["goVersion"]
        host_os = {"Windows": "windows", "Linux": "linux"}.get(platform.system())
        require(host_os is not None and config.get("GOHOSTOS") == config.get("GOOS") == host_os
                and config.get("GOHOSTARCH") == config.get("GOARCH") == "amd64", "Expected native Windows/Linux amd64 Go")
        require(config.get("GOVERSION") == expected and version == f"go version {expected} {host_os}/amd64",
                "Installed Go does not match go/toolchain.json")
        for key, value in APPLIED_ENVIRONMENT.items():
            # go env GOTELEMETRY reports the user's mode file, independently of the inherited
            # variable. Record both facts; never change that host setting to satisfy this tool.
            if key != "GOTELEMETRY":
                require(config.get(key) == value, "Unexpected effective Go setting: " + key)
        require(Path(config.get("GOMOD", "")).resolve() == (root / "go/go.mod").resolve(), "Wrong effective main go.mod")
        report["host"] = {"system": platform.system(), "machine": platform.machine(), "goVersion": version,
                          "goExecutable": queries.path, "appliedEnvironment": dict(APPLIED_ENVIRONMENT),
                          "configuration": config}
        modules = {"main": (root / "go", go_bindings.GO_MODULE),
                   "tools": (root / "go/tools", go_bindings.TOOLS_MODULE)}
        graphs = {name: module_graph(json_stream(queries.run(["list", "-mod=readonly", "-m", "-json", "all"], cwd)), identity)
                  for name, (cwd, identity) in modules.items()}
        # Preserve upstream requirement edges, including versions displaced by MVS.
        # They explain selected metadata; they never establish actual package use.
        requirements = {}
        for name, (cwd, _) in modules.items():
            edges = [line.split() for line in queries.run(["mod", "graph"], cwd).splitlines()]
            require(edges and all(len(edge) == 2 for edge in edges), "Invalid module requirement graph: " + name)
            requirements[name] = sorted(edges)
        closures = {}
        for name, package in go_bindings.TOOL_PACKAGES.items():
            closures["tool:" + name] = package_closure(json_stream(queries.run(
                ["list", "-mod=readonly", "-deps", "-json", package], root / "go/tools")), graphs["tools"])
            require(any(item["importPath"] == package for item in closures["tool:" + name]),
                    "Declared tool is missing from its measured closure: " + name)
        closures["owned-packages-and-tests"] = package_closure(json_stream(queries.run(
            ["list", "-mod=readonly", "-deps", "-test", "-json", "./..."], root / "go")), graphs["main"])
        require(any(item.get("modulePath") == go_bindings.GO_MODULE
                    for item in closures["owned-packages-and-tests"]), "Owned module is missing from its closure")
        if go_bindings.race_supported():
            closures["owned-packages-and-tests:race"] = package_closure(json_stream(queries.run(
                ["list", "-mod=readonly", "-race", "-deps", "-test", "-json", "./..."], root / "go")), graphs["main"])
        report.update(toolPackages=dict(go_bindings.TOOL_PACKAGES), selectedGraphs=graphs,
                      moduleRequirements=requirements, packageClosures=closures,
                      classification=classification(graphs, closures))
    finally:
        unchanged(before, tree_snapshot(root))
    report["unchangedSourceAndLocks"] = True


def output_path(value: Path, root: Path) -> Path:
    target = value.resolve()
    if target.is_relative_to(root):
        require(target.is_relative_to(root / "artifacts"), "Output inside the checkout must be below ignored artifacts/")
        require(not git(root, "ls-files", "--", target.relative_to(root).as_posix()).strip(), "Output must not overwrite a tracked file")
    return target


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        target = output_path(args.output, ROOT)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    report = {"schema": SCHEMA, "measuredAtUtc": datetime.now(timezone.utc).isoformat(), "result": "failed",
              "scope": "This native host/default build configuration only; no aggregate qualification or latest-version admission",
              "policy": {"designCommit": "2296e2fe37ad9ad1f7b65be871fea1f0b39ce7ad",
                         "crossHostQualification": "not-established"}}
    try:
        measure(ROOT, report)
        report["result"] = "passed"
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
    write_report(target, report)  # A failure replaces stale success evidence at the explicit output path.
    print(f"Go dependency inventory {report['result']}: {target}")
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
