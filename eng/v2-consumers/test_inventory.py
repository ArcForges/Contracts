# SPDX-License-Identifier: Apache-2.0
"""Input inventory checks using only temporary, locally owned Git repositories."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("consumer_inventory", Path(__file__).with_name("inventory.py"))
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="afv2-consumers-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, root, *arguments):
        subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)

    def repository(self, name, files=None):
        root = self.root / name
        root.mkdir()
        self.git(root, "init", "--quiet")
        self.git(root, "remote", "add", "origin", f"https://github.com/ArcForges/{name}.git")
        for path, content in (files or {"README.md": "fixture"}).items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self.git(root, "add", ".")
        self.git(root, "-c", "user.name=Consumer inventory fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")
        return root

    def test_complete_scan_binds_commits_and_protects_shared_and_independent_consumers(self):
        for name in inventory.REPOSITORIES:
            if name == "DesktopPlatform":
                files = {"src/ArcForges.Foundation.csproj": "<Project><PropertyGroup><PackageId>ArcForges.Foundation</PackageId></PropertyGroup></Project>"}
            elif name == "Contracts":
                files = {"src/ArcForges.Contracts.LocalRpc.Sandbox.csproj": "<Project />"}
            else:
                files = {"src/Consumer.csproj": '<Project><ItemGroup><PackageReference Include="ArcForges.Contracts.LocalRpc.Sandbox" /><PackageReference Include="ArcForges.Foundation" /></ItemGroup></Project>',
                         "Directory.Packages.props": '<Project><ItemGroup><PackageVersion Include="ArcForges.Foundation" Version="1.2.3" Condition="fixture" /></ItemGroup></Project>'}
            self.repository(name, files)
        report = inventory.inventory(self.root)
        self.assertTrue(report["complete"])
        self.assertFalse(report["deletion_authorized"])
        self.assertEqual(16, len(report["references"]))
        self.assertEqual(8, len(report["version_declarations"]))
        self.assertTrue(all(row["conditional_input"] for row in report["version_declarations"]))
        self.assertTrue(all(row["revision"] and row["dirty"] is False for row in report["repositories"]))
        self.assertEqual(5, sum(row["independent_product"] for row in report["repositories"]))
        self.assertIn("ContentSandbox", report["protected_shared_surface"])

    def test_missing_repository_is_unknown_not_no_consumers(self):
        report = inventory.inventory(self.root)
        self.assertFalse(report["complete"])
        self.assertEqual(10, sum(row["state"] == "unknown" for row in report["repositories"]))
        self.assertEqual("repository_missing", report["repositories"][0]["diagnostic"])

    def test_wrong_origin_and_credential_like_metadata_are_not_exposed(self):
        root = self.repository("Cloud")
        self.git(root, "remote", "set-url", "origin", "https://private-marker@github.com/ArcForges/Cloud.git")
        row, inputs = inventory.read_repository(self.root, "Cloud")
        self.assertEqual("origin_identity_mismatch", row["diagnostic"])
        self.assertEqual({}, inputs)
        self.assertNotIn("private-marker", json.dumps(row))

    def test_only_committed_allowed_inputs_are_read_and_dirty_is_explicit(self):
        root = self.repository("AI", {"package.json": '{"dependencies":{"@arcforges/proto":"1.0.0-ci.287.1"},"scripts":{"fixture":"private-marker"}}',
                                      ".npmrc": "private-marker"})
        (root / "package.json").write_text("uncommitted private-marker", encoding="utf-8")
        (root / "untracked.csproj").write_text("private-marker", encoding="utf-8")
        row, inputs = inventory.read_repository(self.root, "AI")
        self.assertTrue(row["dirty"])
        self.assertEqual(["package.json"], list(inputs))
        references, _ = inventory.parse_inputs("AI", inputs, {"@arcforges/proto": "Contracts"})
        self.assertEqual("1.0.0-ci.287.1", references[0]["version_expression"])
        self.assertNotIn("private-marker", json.dumps([row, references]))

    def test_npm_go_and_project_edges_are_scanned_without_executing_them(self):
        references, declarations = inventory.parse_inputs("Cloud", {
            "package.json": '{"devDependencies":{"@arcforges/ai-internal":"1.2.3"}}',
            "center/go.mod": "module fixture\nrequire (\n github.com/ArcForges/Contracts/go v1.2.3\n)\n",
            "src/Consumer.csproj": '<Project><ItemGroup><ProjectReference Include="../ArcForges.Foundation/ArcForges.Foundation.csproj" /></ItemGroup></Project>'},
            {"@arcforges/ai-internal": "Contracts", "github.com/ArcForges/Contracts/go": "Contracts", "ArcForges.Foundation": "DesktopPlatform"})
        self.assertEqual({"npm_devDependencies", "go_require", "ProjectReference"}, {row["kind"] for row in references})
        self.assertEqual([], declarations)


if __name__ == "__main__":
    unittest.main()
