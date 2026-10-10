# SPDX-License-Identifier: Apache-2.0
"""Exercise rejected source and actual MSBuild boundaries in temporary repositories."""

import json
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

    @staticmethod
    def architecture_project(private_assets='all', generate_path='true'):
        return ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework>'
                '<OutputType>Exe</OutputType><IsPackable>false</IsPackable><IsTestProject>true</IsTestProject>'
                '<PackageLicenseExpression>Apache-2.0</PackageLicenseExpression><LicenceBoundary>Apache</LicenceBoundary>'
                '</PropertyGroup><ItemGroup><PackageReference Include="ArcForges.Build.Policy" '
                f'PrivateAssets="{private_assets}" GeneratePathProperty="{generate_path}" /></ItemGroup>'
                '<Import Project="$(PkgArcForges_Build_Policy)/tools/architecture/ArchitecturePolicy.props" />'
                '</Project>')

    def add_architecture_policy_admission(self, *, path='tests/ArchitectureTests/ArcForges.Contracts.ArchitectureTests.csproj',
                                          version='1.0.0-ci.94.1', private_assets='all', generate_path='true',
                                          lock_type='Direct', lock_path='tests/ArchitectureTests/packages.lock.json'):
        if not any(entry['path'] == path for entry in self.policy['projects']):
            self.policy['projects'].append({'path': path, 'kind': 'msbuild'})
        self.save_policy()
        self.write(path, self.architecture_project(private_assets, generate_path))
        self.write('Directory.Packages.props',
                   '<Project><ItemGroup><PackageVersion Include="ArcForges.Build.Policy" Version="' + version + '" />'
                   '</ItemGroup></Project>')
        self.write(lock_path, json.dumps({'version': 1, 'dependencies': {'net10.0': {
            'ArcForges.Build.Policy': {'type': lock_type, 'resolved': version,
                                       'contentHash': 'c2lnbmF0dXJlZA=='}}}}))

    def test_exact_architecture_only_agpl_build_policy_admission(self):
        self.add_architecture_policy_admission()
        self.assertEqual({'app.csproj', 'tests/ArchitectureTests/ArcForges.Contracts.ArchitectureTests.csproj'},
                         {entry['path'] for entry in audit(self.root)['projects']})

    def test_build_policy_cannot_be_admitted_by_generic_first_party_allowlist(self):
        with self.assertRaisesRegex(ValueError, 'unknown'):
            check_package('ArcForges.Build.Policy')

    def test_build_policy_requires_exact_version_and_private_test_reference(self):
        for version, private_assets, generate_path in [
                ('1.0.0-ci.94.2', 'all', 'true'), ('1.0.0-ci.94.1', 'none', 'true'),
                ('1.0.0-ci.94.1', 'all', 'false')]:
            with self.subTest(version=version, private_assets=private_assets, generate_path=generate_path):
                self.add_architecture_policy_admission(version=version, private_assets=private_assets,
                                                       generate_path=generate_path)
                with self.assertRaisesRegex(ValueError, 'Build.Policy'):
                    audit(self.root)

    def test_build_policy_cannot_enter_another_project_or_lock_closure(self):
        self.add_architecture_policy_admission()
        other = 'src/public/dotnet/ArcForges.Contracts.Foundation/ArcForges.Contracts.Foundation.csproj'
        self.write(other, self.project().replace('</Project>', '<ItemGroup><PackageReference Include="ArcForges.Build.Policy" PrivateAssets="all" GeneratePathProperty="true" /></ItemGroup></Project>'))
        self.policy['projects'].append({'path': other, 'kind': 'msbuild'})
        self.save_policy()
        with self.assertRaisesRegex(ValueError, 'only as the exact private'):
            audit(self.root)

    def test_build_policy_transitive_or_duplicate_lock_is_rejected(self):
        for lock_type, lock_path in [
                ('Transitive', 'tests/ArchitectureTests/packages.lock.json'),
                ('Direct', 'src/public/dotnet/packages.lock.json')]:
            with self.subTest(lock_type=lock_type, lock_path=lock_path):
                self.add_architecture_policy_admission(lock_type=lock_type, lock_path=lock_path)
                with self.assertRaisesRegex(ValueError, 'Build.Policy'):
                    audit(self.root)

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

    def test_gradle_build_is_retired(self):
        # CON.40 retired the Kotlin/Maven channel, so the evaluated Gradle override check has no build left to run:
        # the owner has no Gradle wrapper or Gradle project, and a Gradle project that reappears without a
        # reviewed registration is inventory drift.
        for name in ('gradlew', 'gradlew.bat', 'build.gradle.kts', 'settings.gradle.kts', 'gradle'):
            with self.subTest(name=name):
                self.assertFalse((ROOT / name).exists())
        self.assertNotIn('gradle', {project['kind'] for project in audit(ROOT)['projects']})
        self.assertNotIn('gradle', {entry['kind'] for entry in json.loads(
            (ROOT / 'eng/policy/licence-boundary.json').read_text(encoding='utf-8'))['projects']})
        self.write('build.gradle.kts', 'extra["spdxLicense"] = "Apache-2.0"\nextra["licenceBoundary"] = "Apache"\n')
        with self.assertRaisesRegex(ValueError, 'inventory drift'):
            audit(self.root)

    def test_retired_npm_workspaces_are_gone(self):
        # CON.40 retired @arcforges/proto, @arcforges/api-client, @arcforges/contract-fixtures and
        # @arcforges/operator-client: the only npm projects left are the root workspace and @arcforges/ai-internal,
        # and a retired workspace that reappears without a reviewed registration is inventory drift.
        retired = ['src/public/ts/proto', 'src/public/ts/api-client', 'src/public/ts/contract-fixtures',
                   'src/internal/ts/operator-client']
        for name in retired:
            with self.subTest(name=name):
                self.assertFalse((ROOT / name).exists())
        npm = ['package.json', 'src/internal/ts/ai-internal/package.json']
        self.assertEqual(sorted(project['path'] for project in audit(ROOT)['projects'] if project['kind'] == 'npm'), npm)
        self.assertEqual(sorted(entry['path'] for entry in json.loads(
            (ROOT / 'eng/policy/licence-boundary.json').read_text(encoding='utf-8'))['projects'] if entry['kind'] == 'npm'), npm)
        self.write('src/public/ts/proto/package.json', json.dumps({'name': '@arcforges/proto', 'license': 'Apache-2.0',
                                                                   'arcforges': {'licenceBoundary': 'Apache'}}))
        with self.assertRaisesRegex(ValueError, 'inventory drift'):
            audit(self.root)


if __name__ == '__main__':
    unittest.main()
