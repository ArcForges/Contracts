# SPDX-License-Identifier: Apache-2.0
"""Independent source mutations and sealed candidate tamper rejection."""
import copy
import json
from pathlib import Path
import shutil
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
import build_identity as identity
from contracts import ARTIFACTS, ROOT, sha256, write_json


class BuildIdentityTests(unittest.TestCase):
    def test_compiled_metadata_rejects_wrong_expected_commit(self):
        executable = ROOT / "tests/public/HelloClient/bin/Release/net10.0/HelloClient.dll"
        assembly = ROOT / "eng/Codegen/bin/Release/net10.0/Codegen.dll"
        expected = identity.build(environment={})
        expected["sourceCommit"] = "0" * 40
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "expected.json"
            write_json(path, expected)
            process = subprocess.run(["dotnet", str(executable), "--inspect-build", str(path), str(assembly)],
                                     cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Compiled assembly build identity mismatch: SourceCommit", process.stderr)

    def test_msbuild_rejects_incomplete_ci_metadata(self):
        env = dict(os.environ, GITHUB_ACTIONS="true", GITHUB_SHA="0" * 40,
                   GITHUB_RUN_ID="", GITHUB_RUN_ATTEMPT="1", GITHUB_REPOSITORY="ArcForges/Contracts",
                   GITHUB_SERVER_URL="https://github.com")
        process = subprocess.run(["dotnet", "msbuild", "eng/Codegen/Codegen.csproj", "-t:ContractsBuildIdentity"],
                                 cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("AFB001", process.stdout + process.stderr)

    def test_nine_real_source_kinds_mutate_independently(self):
        # Mechanism fixture; these declarations do not claim production support.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            catalog = {"schemaVersion": 1, "owner": "Contracts", "axes": {}}
            for axis, kind in zip(identity.AXES, identity.KINDS, strict=True):
                path = axis + ".txt"
                catalog["axes"][axis] = {"kind": kind, "sources": [path]} if kind != "packages" else {"kind": kind}
                content = ('package example.v1;\n' if kind == "contracts" else
                           '#define ARC_ABI_MAJOR 1\n#define ARC_ABI_MINOR 0\n' if kind == "native-abi" else
                           json.dumps({"migrations" if kind == "migrations" else "versions": [{"subject": axis, "version": "1"}]}))
                (root / path).write_text(content, encoding="utf-8")
            dependencies = [{"purl": "pkg:nuget/Dependency@1.0.0", "version": "1.0.0"}]
            before = identity.axes({}, dependencies, b"descriptor", root, catalog)
            for axis in identity.AXES:
                if axis == "PackageVersion":
                    changed = identity.axes({}, [{"purl": "pkg:nuget/Dependency@2.0.0", "version": "2.0.0"}], b"descriptor", root, catalog)
                else:
                    path = root / (axis + ".txt")
                    original = path.read_text(encoding="utf-8")
                    path.write_text(original.replace("1", "2"), encoding="utf-8")
                    changed = identity.axes({}, dependencies, b"descriptor", root, catalog)
                    path.write_text(original, encoding="utf-8")
                self.assertEqual([key for key in identity.AXES if before[key] != changed[key]], [axis])
            self.assertEqual(before, identity.axes({}, dependencies, b"descriptor", root, catalog))
            dependencies[0]["version"] = "9"
            self.assertEqual(before["PackageVersion"]["values"][0]["version"], "1.0.0")

    def test_catalog_rejects_missing_unknown_alias_and_unowned_absence(self):
        with self.assertRaises(ValueError):
            identity.axes({}, [], b"descriptor", catalog={})
        original = json.loads((ROOT / "eng/version-sources.json").read_text(encoding="utf-8"))
        for mutation in (lambda axes: axes.pop("ContractSet"), lambda axes: axes.update(Unknown={}),
                         lambda axes: axes["PackageVersion"].update(alias="AppVersion"),
                         lambda axes: axes["CapabilityVersion"].pop("producer")):
            catalog = copy.deepcopy(original)
            mutation(catalog["axes"])
            with self.assertRaises(ValueError):
                identity.axes({}, [], b"descriptor", catalog=catalog)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "duplicate.json", {"versions": [{"subject": "same", "version": "1"}] * 2})
            for entries in ([{"subject": "same", "version": "1"}] * 2,
                            [{"subject": "x", "version": "${AppVersion}"}]):
                write_json(root / "duplicate.json", {"versions": entries})
                catalog = copy.deepcopy(original)
                catalog["axes"]["AppVersion"] = {"kind": "release", "sources": ["duplicate.json"]}
                with self.assertRaisesRegex(ValueError, "Duplicate subject or malformed"):
                    identity.axes({}, [], b"descriptor", root, catalog)

    def test_ci_requires_real_clean_source_run_and_timestamp(self):
        local = identity.build(environment={})
        self.assertEqual(local["kind"], "local")
        clean = {"GITHUB_ACTIONS": "true", "GITHUB_SHA": local["sourceCommit"], "GITHUB_RUN_ID": "123",
                 "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REPOSITORY": "ArcForges/Contracts", "GITHUB_SERVER_URL": "https://github.com"}
        original_git = identity.git
        def clean_git(*args, **kwargs):
            return "" if args[0] == "status" else original_git(*args, **kwargs)
        with patch.object(identity, "git", side_effect=clean_git):
            ci = identity.build(environment=clean)
            self.assertEqual(ci["buildId"], "123.1")
            for field in clean:
                environment = dict(clean, **{field: "invalid"})
                if field == "GITHUB_ACTIONS":
                    environment["CI"] = "true"
                    # The other CI signal still requires all run identity fields.
                    environment["GITHUB_RUN_ID"] = ""
                with self.assertRaises(ValueError):
                    identity.build(environment=environment)
        with patch.object(identity, "git", side_effect=lambda *args, **kwargs: " M changed" if args[0] == "status" else original_git(*args, **kwargs)):
            with self.assertRaises(ValueError):
                identity.build(environment=clean)
        for field, value in [("sourceCommit", "0" * 40), ("sourceDateEpoch", 1), ("kind", "ci")]:
            with self.assertRaises(ValueError):
                identity.validate_source(dict(local, **{field: value}))

    def test_rehashed_package_cannot_forge_build_or_axis(self):
        from packaging_tools import verify_artifacts
        for field in ("build", "axes"):
            with tempfile.TemporaryDirectory() as folder:
                candidate = Path(folder) / "candidate"
                shutil.copytree(ARTIFACTS / "packages", candidate)
                package = next(candidate.glob("*.nupkg"))
                with zipfile.ZipFile(package) as archive:
                    files = {name: archive.read(name) for name in archive.namelist()}
                report = json.loads(files["build-identity.json"])
                if field == "build":
                    report["build"]["sourceCommit"] = "0" * 40
                else:
                    report["axes"]["ContractSet"]["values"][0]["version"] = "999"
                files["build-identity.json"] = json.dumps(report).encode()
                with zipfile.ZipFile(package, "w") as archive:
                    for name, content in files.items():
                        archive.writestr(name, content)
                manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
                entry = next(item for item in manifest["files"] if item["kind"] == "nuget")
                entry.update(sha256=sha256(package), size=package.stat().st_size)
                write_json(candidate / "manifest.json", manifest)
                with self.assertRaisesRegex(ValueError, "build identity or independent version axes"):
                    verify_artifacts(candidate)


if __name__ == "__main__":
    unittest.main()
