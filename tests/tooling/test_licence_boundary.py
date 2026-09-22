# SPDX-License-Identifier: Apache-2.0
"""Exercise rejected source and actual MSBuild boundaries in temporary repositories."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eng'))
from check_licences import ROOT, audit, check_package


class LicenceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='contracts-licence-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.write('app.csproj', self.project())
        self.policy = {'schemaVersion': 1, 'repository': 'Contracts', 'spdxLicense': 'Apache-2.0',
                       'licenceBoundary': 'Apache', 'projects': [{'path': 'app.csproj', 'kind': 'msbuild'}]}
        self.save_policy()

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding='utf-8')

    def save_policy(self):
        self.write('eng/policy/licence-boundary.json', json.dumps(self.policy))

    @staticmethod
    def project(boundary='Apache', license='Apache-2.0', reference=None):
        return ('<Project><PropertyGroup><PackageLicenseExpression>' + license + '</PackageLicenseExpression>'
                '<LicenceBoundary>' + boundary + '</LicenceBoundary></PropertyGroup>'
                + (f'<ItemGroup><ProjectReference Include="{reference}" /></ItemGroup>' if reference else '')
                + '<Import Project="Directory.Build.targets" Condition="Exists(\'Directory.Build.targets\')" /></Project>')

    def test_valid_complete_inventory(self):
        self.assertEqual(len(audit(self.root)['projects']), 1)

    def test_new_unregistered_project(self):
        self.write('tools/extra.csproj', self.project())
        with self.assertRaisesRegex(ValueError, 'inventory drift'):
            audit(self.root)

    def test_root_policy_cannot_change_assignment(self):
        self.policy['licenceBoundary'] = 'AGPL'
        self.save_policy()
        with self.assertRaisesRegex(ValueError, 'assignment'):
            audit(self.root)

    def test_missing_or_inconsistent_declaration(self):
        for declaration in [self.project(boundary=''), self.project(license='AGPL-3.0-only')]:
            with self.subTest(declaration=declaration):
                self.write('app.csproj', declaration)
                with self.assertRaisesRegex(ValueError, 'declaration'):
                    audit(self.root)

    def test_imported_property_override(self):
        self.write('Directory.Build.props', '<Project><PropertyGroup><LicenceBoundary>AGPL</LicenceBoundary></PropertyGroup></Project>')
        with self.assertRaisesRegex(ValueError, 'override'):
            audit(self.root)

    def test_reference_escape_or_unregistered_target(self):
        for target, expected in [('../external.csproj', 'escapes'), ('missing.csproj', 'Unregistered')]:
            with self.subTest(target=target):
                self.write('app.csproj', self.project(reference=target))
                with self.assertRaisesRegex(ValueError, expected):
                    audit(self.root)

    def test_transitive_agpl_and_unknown_packages(self):
        for name in ['ArcForges.Native.Media', 'ArcForges.Unknown']:
            with self.subTest(name=name):
                self.write('packages.lock.json', json.dumps({'dependencies': {'net10.0': {name: {'type': 'Transitive'}}}}))
                with self.assertRaisesRegex(ValueError, 'Non-Apache or unknown'):
                    audit(self.root)

    def test_npm_alias_cannot_hide_boundary(self):
        self.policy['projects'].append({'path': 'package.json', 'kind': 'npm'})
        self.save_policy()
        for alias in ['npm:@arcforges/web-ui@1.0.0', 'npm:@arcforges/web-ui', 'npm:@arcforges/unknown']:
            with self.subTest(alias=alias):
                self.write('package.json', json.dumps({'name': '@arcforges/tools', 'license': 'Apache-2.0',
                           'arcforges': {'licenceBoundary': 'Apache'}, 'dependencies': {'alias': alias}}))
                with self.assertRaisesRegex(ValueError, 'Non-Apache or unknown'):
                    audit(self.root)

    def test_closed_first_party_names(self):
        for valid in ['ArcForges.Contracts.PublicApi', '@arcforges/api-client', 'io.github.arcforges:contracts-connect-client']:
            check_package(valid)
        for invalid in ['@arcforges/unknown', 'io.github.arcforges:unknown']:
            with self.assertRaisesRegex(ValueError, 'unknown'):
                check_package(invalid)

    def msbuild(self, *args):
        shutil.copyfile(ROOT / 'Directory.Build.targets', self.root / 'Directory.Build.targets')
        return subprocess.run(['dotnet', 'msbuild', 'app.csproj', '-nologo', '-verbosity:quiet',
                               '-t:ArcForgesVerifyLicenceBoundary', *args], cwd=self.root,
                              text=True, encoding='utf-8', capture_output=True, timeout=60)

    def test_actual_msbuild_rejects_global_override(self):
        self.assertEqual(self.msbuild().returncode, 0)
        result = self.msbuild('-p:LicenceBoundary=AGPL')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AFL001', result.stdout)

    def test_actual_msbuild_rejects_agpl_reference(self):
        self.write('app.csproj', self.project(reference='library.csproj'))
        self.write('library.csproj', self.project(boundary='AGPL', license='AGPL-3.0-only'))
        result = self.msbuild()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AFL003', result.stdout)

    def test_actual_msbuild_rejects_reference_escape(self):
        self.write('app.csproj', self.project(reference='../external.csproj'))
        result = self.msbuild()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AFL002', result.stdout)

    def test_actual_gradle_rejects_evaluated_override(self):
        init = self.root / 'override.gradle'
        init.write_text('gradle.afterProject { p -> if (p.path == ":contracts-connect-client") p.ext.licenceBoundary = "AGPL" }\n', encoding='utf-8')
        wrapper = ROOT / ('gradlew.bat' if os.name == 'nt' else 'gradlew')
        result = subprocess.run([str(wrapper), '--no-daemon', '--console=plain', '-I', str(init), 'help'],
                                cwd=ROOT, text=True, encoding='utf-8', capture_output=True, timeout=180)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AFL001', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
