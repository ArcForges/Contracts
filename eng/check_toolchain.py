# SPDX-License-Identifier: Apache-2.0
"""Check the actual local/CI tools against repository selectors before restoration."""
from __future__ import annotations

import hashlib
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def check(required_tools: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    required = set(required_tools if required_tools is not None else ["python", "dotnet", "node", "npm", "go"])
    required.add("python")
    expected = {
        "python": (ROOT / ".python-version").read_text(encoding="utf-8").strip(),
        "dotnet": json.loads((ROOT / "global.json").read_text(encoding="utf-8"))["sdk"]["version"],
        "node": (ROOT / ".node-version").read_text(encoding="utf-8").strip(),
        "npm": json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["packageManager"].removeprefix("npm@"),
        "go": json.loads((ROOT / "go/toolchain.json").read_text(encoding="utf-8"))["goVersion"],
    }
    evidence: dict = {"expected": expected, "required_tools": sorted(required), "invoking_python": {
        "version": platform.python_version(), "executable": sys.executable}, "tools": {}}
    if platform.python_version() != expected["python"]:
        errors.append(f"Invoking Python {platform.python_version()} does not match {expected['python']}")

    def probe(tool: str, arguments: list[str], *, cwd: Path = ROOT, env: dict | None = None) -> str | None:
        if tool not in required:
            return None
        path = shutil.which("npm.cmd" if tool == "npm" and os.name == "nt" else tool)
        if path is None:
            errors.append(f"{tool} is missing from PATH")
            return None
        try:
            process = subprocess.run([path, *arguments], cwd=cwd, env=env, capture_output=True,
                                     text=True, encoding="utf-8", timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            errors.append(f"{tool} probe failed: {error}")
            return None
        evidence["tools"].setdefault(tool, {"path": path})
        if process.returncode:
            errors.append(f"{tool} probe exited {process.returncode}: {process.stderr.strip()}")
            return None
        return process.stdout.strip()

    python = probe("python", ["--version"])
    if python is not None:
        evidence["tools"]["python"]["version"] = python
        if python != "Python " + expected["python"]:
            errors.append(f"PATH Python {python} does not match {expected['python']}")

    sdk = probe("dotnet", ["--version"])
    if sdk is not None:
        evidence["tools"]["dotnet"]["version"] = sdk
        if sdk != expected["dotnet"]:
            errors.append(f"Selected .NET SDK {sdk} does not match {expected['dotnet']}")
        override = os.environ.get("MSBuildSDKsPath")
        if override:
            installed = probe("dotnet", ["--list-sdks"]) or ""
            paths = [Path(line.split("[", 1)[1].rstrip("]")) / expected["dotnet"] / "Sdks"
                     for line in installed.splitlines() if line.startswith(expected["dotnet"] + " [")]
            if not any(Path(override).resolve() == path.resolve() for path in paths):
                errors.append("MSBuildSDKsPath conflicts with the selected pinned SDK")

    node = probe("node", ["--eval", "console.log(JSON.stringify({version:process.versions.node,executable:process.execPath}))"])
    if node is not None:
        try:
            actual = json.loads(node)
            evidence["tools"]["node"].update(actual)
            if actual["version"] != expected["node"]:
                errors.append(f"Selected Node {actual['version']} does not match {expected['node']}")
        except (ValueError, KeyError, TypeError):
            errors.append("Node returned an invalid version identity")

    npm = probe("npm", ["version", "--json"])
    if npm is not None:
        try:
            actual = json.loads(npm)
            evidence["tools"]["npm"].update(version=actual["npm"], node=actual["node"])
            if actual["npm"] != expected["npm"]:
                errors.append(f"Selected npm {actual['npm']} does not match {expected['npm']}")
            if actual["node"] != expected["node"]:
                errors.append(f"npm uses Node {actual['node']} instead of {expected['node']}")
        except (ValueError, KeyError, TypeError):
            errors.append("npm returned an invalid npm/Node version identity")

    # Preflight checks the installed compiler; it must not download a replacement to pass.
    go = probe("go", ["env", "-json", "GOVERSION", "GOROOT", "GOTOOLCHAIN"], cwd=ROOT / "go",
               env={**os.environ, "GOTOOLCHAIN": "local"})
    if go is not None:
        try:
            actual = json.loads(go)
            evidence["tools"]["go"].update(actual)
            if actual["GOVERSION"] != expected["go"]:
                errors.append(f"Installed Go {actual['GOVERSION']} does not match {expected['go']}")
        except (ValueError, KeyError, TypeError):
            errors.append("Go returned an invalid compiler identity")

    tracked = subprocess.run(["git", "ls-files", "--", "*packages.lock.json", "*package-lock.json", "*go.sum"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    if tracked.returncode:
        errors.append("Cannot enumerate tracked dependency locks")
    else:
        evidence["lock_sha256_lf"] = {path: hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                                     for path in sorted(tracked.stdout.splitlines())}
    print(json.dumps(evidence, ensure_ascii=True, sort_keys=True))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", nargs="+", choices=["python", "dotnet", "node", "npm", "go"],
                        help="Applicable tools for a narrower CI job; Python is always checked. Default: all.")
    errors = check(parser.parse_args().tools)
    for error in errors:
        print("toolchain mismatch: " + error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
