# SPDX-License-Identifier: Apache-2.0
"""Reject mismatched selectors and SDK roots using real installed tools."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))
import check_toolchain as toolchain


class ToolchainSelectionTests(unittest.TestCase):
    def check(self, required_tools=None):
        with redirect_stdout(io.StringIO()):
            return toolchain.check(required_tools)

    def fixture(self, temporary):
        root = Path(temporary)
        for name in [".python-version", ".node-version", "global.json", "package.json", "go/go.mod", "go/toolchain.json"]:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        project = root / "eng/Codegen/Codegen.csproj"
        project.parent.mkdir(parents=True)
        project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net11.0</TargetFramework></PropertyGroup></Project>', encoding="utf-8")
        subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
        return root

    def test_actual_tools_match_repository_selectors(self):
        self.assertEqual([], self.check())

    def test_invoking_and_path_python_are_both_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            (root / ".python-version").write_text("0.0.0\n", encoding="utf-8")
            with patch.object(toolchain, "ROOT", root):
                errors = self.check()
            self.assertTrue(any(error.startswith("Invoking Python ") for error in errors))
            self.assertTrue(any(error.startswith("PATH Python ") for error in errors))

    def test_npm_and_its_actual_node_runtime_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            package = json.loads((root / "package.json").read_text(encoding="utf-8"))
            package["packageManager"] = "npm@0.0.0"
            (root / "package.json").write_text(json.dumps(package), encoding="utf-8")
            (root / ".node-version").write_text("0.0.0\n", encoding="utf-8")
            with patch.object(toolchain, "ROOT", root):
                errors = self.check()
            self.assertTrue(any(error.startswith("Selected Node ") for error in errors))
            self.assertTrue(any(error.startswith("Selected npm ") for error in errors))
            self.assertTrue(any(error.startswith("npm uses Node ") for error in errors))

    def test_go_installed_compiler_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            manifest = json.loads((root / "go/toolchain.json").read_text(encoding="utf-8"))
            manifest["goVersion"] = "go0.0.0"
            (root / "go/toolchain.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(toolchain, "ROOT", root):
                errors = self.check()
            self.assertTrue(any(error.startswith("Installed Go ") for error in errors))

    def test_conflicting_msbuild_sdk_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"MSBuildSDKsPath": temporary}):
                self.assertTrue(any("MSBuildSDKsPath" in error for error in self.check()))

    def test_python_only_does_not_execute_dotnet(self):
        # Keep actual Python and Git probes; fail this test if the narrower job
        # invokes any .NET process while recording its own tool identity.
        real_run = subprocess.run
        def observe(arguments, *args, **kwargs):
            self.assertNotIn(Path(arguments[0]).stem.casefold(), {'dotnet'})
            return real_run(arguments, *args, **kwargs)
        with patch.object(toolchain.subprocess, 'run', side_effect=observe):
            self.assertEqual([], self.check(['python']))

    def test_narrow_job_checks_only_its_tools_and_always_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.fixture(temporary)
            (root / ".node-version").write_text("0.0.0\n", encoding="utf-8")
            with patch.object(toolchain, "ROOT", root):
                self.assertEqual([], self.check(["dotnet"]))
                self.assertTrue(any(error.startswith("Selected Node ")
                                    for error in self.check(["node"])))
                (root / ".python-version").write_text("0.0.0\n", encoding="utf-8")
                errors = self.check(["dotnet"])
            self.assertTrue(any(error.startswith("Invoking Python ") for error in errors))
            self.assertTrue(any(error.startswith("PATH Python ") for error in errors))


if __name__ == "__main__":
    unittest.main()
