# SPDX-License-Identifier: Apache-2.0
"""AF-CON-02 (ArcForges-Design conflict C-03): ArcForges.Cli declares only the tool command arcforges-contracts.

The packed-candidate case reads the ArcForges.Cli archive that `python eng/contracts.py pack` wrote to
artifacts/packages (CI packs before it runs these tests). It inspects the archive only; it never installs or
runs the tool.
"""
import json
from pathlib import Path
import re
import subprocess
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ROOT / "artifacts/packages"
PROJECT = ROOT / "src/public/dotnet/ArcForges.Cli/ArcForges.Cli.csproj"
COMMAND = "arcforges-contracts"
PRODUCT_COMMAND = "arcforges"
TOOL_SETTINGS = "tools/net10.0/any/DotnetToolSettings.xml"


def local(element):
    return element.tag.split("}")[-1]


def tool_commands(settings):
    """Every declared (Name, EntryPoint, Runner) in a DotnetToolSettings.xml document."""
    document = ET.fromstring(settings)
    if local(document) != "DotNetCliTool":
        raise ValueError("Not a .NET tool settings document")
    return [(item.get("Name"), item.get("EntryPoint"), item.get("Runner"))
            for item in document.iter() if local(item) == "Command"]


class ProjectDeclaration(unittest.TestCase):
    def test_project_declares_exactly_the_contracts_command(self):
        project = ET.parse(PROJECT).getroot()
        values = {name: [item.text for item in project.iter() if local(item) == name]
                  for name in ("PackAsTool", "ToolCommandName", "PackageId", "OutputType")}
        self.assertEqual(values, {"PackAsTool": ["true"], "ToolCommandName": [COMMAND],
                                  "PackageId": ["ArcForges.Cli"], "OutputType": ["Exe"]})

    def test_no_other_project_or_build_file_declares_a_tool_command(self):
        tracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "*.csproj", "*.props", "*.targets"],
                                          text=True).splitlines()
        declaring = [path for path in tracked
                     if re.search(r"<\s*(ToolCommandName|PackAsTool)\b", (ROOT / path).read_text(encoding="utf-8"))]
        self.assertEqual(declaring, ["src/public/dotnet/ArcForges.Cli/ArcForges.Cli.csproj"])

    def test_usage_message_names_the_contracts_command(self):
        source = (ROOT / "src/public/dotnet/ArcForges.Cli/Program.cs").read_text(encoding="utf-8")
        self.assertIn('"Usage: arcforges-contracts validate-inventory <inventory.json>"', source)
        self.assertNotRegex(source, r"Usage: arcforges(?!-contracts)\b")

    def test_every_documented_invocation_uses_the_contracts_command(self):
        tracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "*.md", "*.cs"], text=True).splitlines()
        invocations = {}
        for path in tracked:
            text = (ROOT / path).read_text(encoding="utf-8")
            found = re.findall(r"\b(arcforges(?:-contracts)?)\s+validate-inventory\b", text)
            if found:
                invocations[path] = found
        self.assertTrue(invocations)
        self.assertEqual({path: names for path, names in invocations.items() if set(names) != {COMMAND}}, {})
        for path in ["src/public/dotnet/ArcForges.Cli/README.md", "docs/consuming.md"]:
            self.assertIn(path, invocations)

    def test_release_note_keeps_earlier_versions_immutable(self):
        for path in ["src/public/dotnet/ArcForges.Cli/README.md", "docs/consuming.md"]:
            text = " ".join((ROOT / path).read_text(encoding="utf-8").split())
            self.assertIn("AF-CON-02", text, path)
            self.assertIn("keep the `arcforges` command", text, path)
            self.assertIn("none is unpublished, deprecated or deleted", text, path)


class PackedCandidate(unittest.TestCase):
    """The packed ArcForges.Cli archive exposes arcforges-contracts and nothing else."""

    @classmethod
    def setUpClass(cls):
        manifest = json.loads((PACKAGES / "manifest.json").read_text(encoding="utf-8"))
        cls.entries = [entry for entry in manifest["files"] if entry["kind"] == "nuget"]
        cls.release = manifest["version"]

    def files(self, entry):
        with zipfile.ZipFile(PACKAGES / entry["name"]) as archive:
            return {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}

    def test_cli_archive_declares_only_the_contracts_command(self):
        entry = next(item for item in self.entries if item["id"] == "ArcForges.Cli")
        self.assertEqual(entry["name"], f"ArcForges.Cli.{self.release}.nupkg")
        files = self.files(entry)
        self.assertEqual(tool_commands(files[TOOL_SETTINGS]), [(COMMAND, "ArcForges.Cli.dll", "dotnet")])
        self.assertIn("tools/net10.0/any/ArcForges.Cli.dll", files)
        nuspec = ET.fromstring(files["ArcForges.Cli.nuspec"])
        self.assertEqual([local(item) for item in nuspec.iter() if local(item) == "packageType"], ["packageType"])
        self.assertEqual([item.get("name") for item in nuspec.iter() if local(item) == "packageType"], ["DotnetTool"])

    def test_no_candidate_archive_declares_the_product_command(self):
        tools = {}
        for entry in self.entries:
            files = self.files(entry)
            for name, content in files.items():
                if name.endswith("DotnetToolSettings.xml"):
                    tools.setdefault(entry["id"], []).extend(command for command, _, _ in tool_commands(content))
        self.assertEqual(tools, {"ArcForges.Cli": [COMMAND]})
        self.assertNotIn(PRODUCT_COMMAND, tools["ArcForges.Cli"])


class ToolSettingsReader(unittest.TestCase):
    def test_reader_refuses_other_documents_and_reports_the_old_command(self):
        with self.assertRaisesRegex(ValueError, "Not a .NET tool settings document"):
            tool_commands(b"<Project />")
        self.assertEqual(tool_commands(
            b'<DotNetCliTool Version="1"><Commands><Command Name="arcforges" EntryPoint="ArcForges.Cli.dll" '
            b'Runner="dotnet" /></Commands></DotNetCliTool>'), [(PRODUCT_COMMAND, "ArcForges.Cli.dll", "dotnet")])


if __name__ == "__main__":
    unittest.main()
