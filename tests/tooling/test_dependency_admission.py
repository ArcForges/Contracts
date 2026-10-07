# SPDX-License-Identifier: Apache-2.0
"""Admission rejection tests use committed inputs and synthetic mutations only."""
import copy
import gzip
import json
import hashlib
import subprocess
import tempfile
from pathlib import Path
import sys
import re
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eng'))
from dependency_admission import (ROOT, POLICY, ARCHITECTURE_TEST_LOCK, ARCHITECTURE_TEST_PROJECT,
    BUILD_POLICY_KEY, BUILD_POLICY_SCOPE, audit, inventory, immutable_coordinates, major_upgrade, pinned,
    stable_dependency, validate, validate_architecture_policy_boundary)


# The CON.21 and CON.22 allowlist tests re-verify what the Security runs observed at three task-branch
# commits. CON.21 and CON.22 were squash-merged and their branches deleted, so those commits are not in a
# fresh clone. Each historical file is therefore pinned by its exact git blob id and read from either a
# commit that is reachable from main and holds the identical blob, or a byte-exact frozen copy in
# tests/tooling/history. Every read re-verifies the blob id, so the bytes are exactly the observed ones.
HISTORY_DIR = ROOT / 'tests/tooling/history'
HISTORICAL_BLOBS = {
    ('a0c945131855601b2ef229f3ac0661f00d96526d', 'eng/policy/dependency-policy.json'):
        ('0ec34ba1dc7468bb09b894d0ab9c27700fe42da4', None),
    ('a0c945131855601b2ef229f3ac0661f00d96526d', 'eng/policy/contract-access.json'):
        ('407e5e494c57f85e519b818101e0bdce8bb985ac', None),
    ('a0c945131855601b2ef229f3ac0661f00d96526d', 'eng/policy/dependency-reviews/con-21-r1.json'):
        ('37bc2c44ea6b9d9b61a292c602c7f4c78504b0f0', None),
    ('a0c945131855601b2ef229f3ac0661f00d96526d', 'eng/provenance/artifact-profiles/dokka-2-2-0-r17.json'):
        ('fc084f0cbe245cda07677bb1bbfea1b832a4a31a', '1d17838dd6bb30f89ffbfb9a26ce311f6c742d34'),
    ('a0c945131855601b2ef229f3ac0661f00d96526d', 'eng/provenance/records/dokka-combokeys-licence-r1.json'):
        ('e98b2da5810522ea871b6d3af8884684eea705e4', 'f302a2097f5b466ad1b1d00d9c21484e294060f7'),
    ('a0c945131855601b2ef229f3ac0661f00d96526d', 'eng/provenance/records/dokka-object-keys-licence-r1.json'):
        ('cd7d108312cae98587ea6b77781f5ec2e04096a6', 'f302a2097f5b466ad1b1d00d9c21484e294060f7'),
    ('a0c945131855601b2ef229f3ac0661f00d96526d', 'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj'):
        ('acee6d6c012fa3f65b53081771d43a627e8c4fd7', 'f9dc23fea7ae1dae3805404bb800583aea4e13e0'),
    ('cf532b47c482d6444ae9f18a0edb3924c9bbbf79', 'eng/policy/dependency-policy.json'):
        ('d919849472aa8e295a1a827484ce734b58d70eae', '1d17838dd6bb30f89ffbfb9a26ce311f6c742d34'),
    ('cf532b47c482d6444ae9f18a0edb3924c9bbbf79', 'eng/policy/contract-access.json'):
        ('b3718dea2c52bb56225a74f60f7ede1e41584477', '1d17838dd6bb30f89ffbfb9a26ce311f6c742d34'),
    ('cf532b47c482d6444ae9f18a0edb3924c9bbbf79', 'eng/policy/dependency-reviews/con-21-r1.json'):
        ('aa3c4a7479ccffeac457612cda8fcc89739eae0e', '1d17838dd6bb30f89ffbfb9a26ce311f6c742d34'),
    ('cf532b47c482d6444ae9f18a0edb3924c9bbbf79', 'eng/provenance/artifact-profiles/dokka-2-2-0-r17.json'):
        ('fc084f0cbe245cda07677bb1bbfea1b832a4a31a', '1d17838dd6bb30f89ffbfb9a26ce311f6c742d34'),
    ('cf532b47c482d6444ae9f18a0edb3924c9bbbf79', 'eng/provenance/records/dokka-combokeys-licence-r1.json'):
        ('e98b2da5810522ea871b6d3af8884684eea705e4', 'f302a2097f5b466ad1b1d00d9c21484e294060f7'),
    ('cf532b47c482d6444ae9f18a0edb3924c9bbbf79', 'eng/provenance/records/dokka-object-keys-licence-r1.json'):
        ('cd7d108312cae98587ea6b77781f5ec2e04096a6', 'f302a2097f5b466ad1b1d00d9c21484e294060f7'),
    ('cf532b47c482d6444ae9f18a0edb3924c9bbbf79', 'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj'):
        ('acee6d6c012fa3f65b53081771d43a627e8c4fd7', 'f9dc23fea7ae1dae3805404bb800583aea4e13e0'),
    ('727f9957773c3ae01ab849ebdeaae3f3ef174b09', 'eng/policy/dependency-policy.json'):
        ('f6c808b6fc6ccc2d64085e25887bb13364377fba', None),
    ('727f9957773c3ae01ab849ebdeaae3f3ef174b09', 'eng/policy/contract-access.json'):
        ('65ee5833f249bfaf137b8a917081ef5fe86feaf6', None),
    ('727f9957773c3ae01ab849ebdeaae3f3ef174b09', 'eng/policy/dependency-reviews/con-22-r1.json'):
        ('53ee346163b79d51efbcd34c880334657127e717', None),
    ('727f9957773c3ae01ab849ebdeaae3f3ef174b09', 'eng/provenance/artifact-profiles/dokka-2-2-0-r16.json'):
        ('c1142d009c5d0bda6eb195b7f1f2121e55897a2c', '9577ab67fb631a37a73b1b7e8d087714f6292e8a'),
}


def frozen_git_blob(commit, path):
    """Return the exact bytes of path at an observed task-branch commit without needing that commit."""
    blob_id, reachable_commit = HISTORICAL_BLOBS[(commit, path)]
    if reachable_commit is None:
        data = gzip.decompress((HISTORY_DIR / (blob_id + '.gz')).read_bytes())
    else:
        data = subprocess.check_output(['git', 'show', f'{reachable_commit}:{path}'], cwd=ROOT)
    assert hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest() == blob_id, (commit, path)
    return data


def committed_with(receipt_path, key):
    """Bytes of an input as committed with an immutable receipt: the access digest moves with later central pins."""
    scan_head = subprocess.check_output(['git', 'log', '--diff-filter=A', '--format=%H', '--', receipt_path],
                                        cwd=ROOT, text=True).split()[-1]
    return subprocess.check_output(['git', 'show', f'{scan_head}:{key}'], cwd=ROOT)


class DependencyAdmission(unittest.TestCase):
    def architecture_boundary_fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix='contracts-policy-admission-')
        root = Path(temporary.name)
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        project = root / ARCHITECTURE_TEST_PROJECT
        project.parent.mkdir(parents=True)
        project.write_text('''<Project Sdk="Microsoft.NET.Sdk">
    <PropertyGroup><TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType><IsTestProject>true</IsTestProject><IsPackable>false</IsPackable><PackageLicenseExpression>Apache-2.0</PackageLicenseExpression><LicenceBoundary>Apache</LicenceBoundary></PropertyGroup>
  <ItemGroup><PackageReference Include="ArcForges.Build.Policy" PrivateAssets="all" GeneratePathProperty="true" /></ItemGroup>
  <Import Project="$(PkgArcForges_Build_Policy)/tools/architecture/ArchitecturePolicy.props" />
</Project>''', encoding='utf-8')
        (root / 'Directory.Packages.props').write_text(
            '<Project><ItemGroup><PackageVersion Include="ArcForges.Build.Policy" Version="1.0.0-ci.124.1" /></ItemGroup></Project>',
            encoding='utf-8')
        digest = 'c2lnbmF0dXJlZA=='
        lock = root / ARCHITECTURE_TEST_LOCK
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(json.dumps({'version': 1, 'dependencies': {'net10.0': {
            'ArcForges.Build.Policy': {'type': 'Direct', 'resolved': '1.0.0-ci.124.1', 'contentHash': digest}}}}),
            encoding='utf-8')
        catalog = root / 'eng/contract-packages.json'
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({'packages': []}), encoding='utf-8')
        return temporary, root, digest

    def test_build_policy_agpl_exception_is_exact_and_test_only(self):
        policy = copy.deepcopy(json.loads((ROOT / POLICY).read_text()))
        row = {'integrity': 'c2lnbmF0dXJlZA==', 'licence': 'AGPL-3.0-only',
               'evidence': [{'source': 'https://api.nuget.org/v3-flatcontainer/arcforges.build.policy/1.0.0-ci.124.1/arcforges.build.policy.nuspec',
                            'sha256': 'a' * 64}], 'scope': BUILD_POLICY_SCOPE}
        policy['closure'] = {BUILD_POLICY_KEY: row}
        validate(policy, {BUILD_POLICY_KEY: row['integrity']})
        for bad_key, bad_row in [
                (BUILD_POLICY_KEY, {**row, 'licence': 'AGPL-3.0-only', 'scope': 'build dependency'}),
                (BUILD_POLICY_KEY, {**row, 'licence': 'Apache-2.0'}),
                ('nuget:arcforges.build.policy@1.0.0-ci.94.2', row),
                ('nuget:arcforges.unknown@1.0.0-ci.124.1', row),
        ]:
            with self.subTest(key=bad_key, scope=bad_row.get('scope'), licence=bad_row.get('licence')):
                policy['closure'] = {bad_key: bad_row}
                with self.assertRaisesRegex(ValueError, 'Forbidden|Build.Policy|exact'):
                    validate(policy, {bad_key: row['integrity']})
        self.assertTrue(stable_dependency(BUILD_POLICY_KEY))
        self.assertFalse(stable_dependency('nuget:arcforges.build.policy@1.0.0-ci.94.2'))

    def test_build_policy_exception_requires_exact_reference_and_locked_closure(self):
        temporary, root, digest = self.architecture_boundary_fixture()
        self.addCleanup(temporary.cleanup)
        validate_architecture_policy_boundary(root, {BUILD_POLICY_KEY: digest})

        host = root / ARCHITECTURE_TEST_PROJECT
        original_project = host.read_text(encoding='utf-8')
        lock = root / ARCHITECTURE_TEST_LOCK
        original_lock = json.loads(lock.read_text(encoding='utf-8'))
        for bad_project, bad_lock in [
                (original_project.replace('PrivateAssets="all"', 'PrivateAssets="none"'), original_lock),
                (original_project.replace('<IsPackable>false</IsPackable>', '<IsPackable>true</IsPackable>'), original_lock),
                (original_project, {'version': 1, 'dependencies': {'net10.0': {
                    'ArcForges.Build.Policy': {'type': 'Direct', 'resolved': '1.0.0-ci.124.1', 'contentHash': 'mutated'}}}}),
                (original_project, {'version': 1, 'dependencies': {'net10.0': {
                    'ArcForges.Build.Policy': {'type': 'Transitive', 'resolved': '1.0.0-ci.124.1', 'contentHash': digest}}}}),
                (original_project, {'version': 1, 'dependencies': {'net10.0': {
                    'ArcForges.Build.Policy': {'type': 'Direct', 'resolved': '1.0.0-ci.94.2', 'contentHash': digest}}}}),
        ]:
            with self.subTest(project=bad_project != original_project, lock=bad_lock):
                host.write_text(bad_project, encoding='utf-8')
                lock.write_text(json.dumps(bad_lock), encoding='utf-8')
                with self.assertRaises(ValueError):
                    validate_architecture_policy_boundary(root, {BUILD_POLICY_KEY: digest})
        host.write_text(original_project, encoding='utf-8')
        lock.write_text(json.dumps(original_lock), encoding='utf-8')
        other_lock = root / 'src/other/packages.lock.json'
        other_lock.parent.mkdir(parents=True)
        other_lock.write_text(json.dumps(original_lock), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'only the exact direct'):
            validate_architecture_policy_boundary(root, {BUILD_POLICY_KEY: digest})

    def test_con02_exceptions_bind_only_observed_public_digest_rows(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        rows = [row for row in config['allowlists'] if row['description'].startswith('CON.02 exact')]
        expected = {
            'eng/policy/dependency-policy.json': 3,
            'eng/policy/dependency-reviews/con-02-descriptors-r1.json': 7,
            'eng/provenance/artifact-profiles/dokka-2-2-0-r9.json': 164,
        }
        self.assertEqual(len(rows), len(expected))
        for row, (path, count) in zip(rows, sorted(expected.items()), strict=True):
            self.assertEqual(row['targetRules'], ['generic-api-key'])
            self.assertEqual(row['condition'], 'AND')
            self.assertEqual(row['regexTarget'], 'line')
            self.assertEqual(row['paths'], ['^' + re.escape(path) + '$'])
            self.assertEqual(len(row['regexes']), count)
            for wrong in [path + '.backup', 'src/secrets.json', path.replace('r1.json', 'r2.json') + '.other']:
                self.assertIsNone(re.fullmatch(row['paths'][0], wrong))
            lines = (ROOT / path).read_text().splitlines()
            # These exact retained task commits produced the two CI observations;
            # accepted historical receipts are never rewritten to hide findings.
            for commit in ['77e0965e7f257c5cd4d6a95c2bf9b58167e62fcc',
                           '55ad3b4a1e60e6f0285fea37cbf71489f7cfabc5',
                           '4dfaebd33118f5405e1bbbcc5ef92ae21177f650',
                           'dbfb192751a3745626e89c7907ace188e01b41d7']:
                lines.extend(subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT,
                                                      text=True).splitlines())
            for pattern in row['regexes']:
                matched = sorted(set(line for line in lines if re.fullmatch(pattern, line)))
                self.assertTrue(matched, pattern)
                for line in matched:
                    key, digest = next(iter(json.loads('{' + line.strip().rstrip(',') + '}').items()))
                    self.assertRegex(digest, '^[0-9a-f]{64}$')
                    for invalid in [f'"{key}": "' + '0' * 64 + '"',
                                    f'"unrelated-key": "{digest}"',
                                    f'"{key}": "ghp_actual_credential"',
                                    f'"{key}": "{digest}", "token": "extra"']:
                        self.assertIsNone(re.fullmatch(pattern, invalid))


    def test_shard_receipt_exceptions_are_exact_public_rows(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        rows = [row for row in config['allowlists'] if row['description'].startswith('CON.01 exact')]
        self.assertEqual(len(rows), 2)
        receipt_path = 'eng/policy/dependency-reviews/con-01-shards-r1.json'
        receipt = json.loads((ROOT / receipt_path).read_text())['review']['inputHashes']
        sources = ['eng/policy/contract-access.json', 'eng/provenance/records/dokka-combokeys-licence-r1.json',
                   'eng/provenance/records/dokka-object-keys-licence-r1.json',
                   'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        for row, filename, keys in zip(rows, ['eng/policy/dependency-policy.json', receipt_path],
                                       [sources[:1], sources], strict=True):
            self.assertEqual(row['targetRules'], ['generic-api-key'])
            self.assertEqual(row['condition'], 'AND')
            self.assertEqual(row['regexTarget'], 'line')
            self.assertEqual(row['paths'], ['^' + re.escape(filename) + '$'])
            self.assertIsNone(re.fullmatch(row['paths'][0], filename + '.backup'))
            self.assertEqual(len(row['regexes']), len(keys))
            for pattern, key in zip(row['regexes'], keys, strict=True):
                digest = receipt[key]
                # Access policy evolved after the reviewed pre-rebase snapshot;
                # its exact historical digest remains in the retained r1 receipt.
                if key != 'eng/policy/contract-access.json':
                    actual = hashlib.sha256((ROOT / key).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                    self.assertEqual(actual, digest)
                self.assertIsNotNone(re.fullmatch(pattern, f' "{key}": "{digest}",'))
                self.assertIsNone(re.fullmatch(pattern, f' "{key}": "' + '0' * 64 + '",'))
                self.assertIsNone(re.fullmatch(pattern, f' "unrelated-key": "{digest}",'))

    def test_shard_successor_exceptions_match_reviewed_sources(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        rows = [row for row in config['allowlists'] if row['description'].startswith('CON.01 r2')]
        self.assertEqual(len(rows), 2)
        receipt_path = 'eng/policy/dependency-reviews/con-01-shards-r2.json'
        inputs = json.loads((ROOT / receipt_path).read_text())['review']['inputHashes']
        sources = ['eng/policy/contract-access.json', 'eng/provenance/records/dokka-combokeys-licence-r1.json',
                   'eng/provenance/records/dokka-object-keys-licence-r1.json',
                   'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        for row, filename, keys in zip(rows, ['eng/policy/dependency-policy.json', receipt_path],
                                       [sources[:1], sources], strict=True):
            self.assertEqual(row['targetRules'], ['generic-api-key'])
            self.assertEqual(row['condition'], 'AND')
            self.assertEqual(row['regexTarget'], 'line')
            self.assertEqual(row['paths'], ['^' + re.escape(filename) + '$'])
            self.assertIsNone(re.fullmatch(row['paths'][0], filename + '.backup'))
            self.assertEqual(len(row['regexes']), len(keys))
            for pattern, key in zip(row['regexes'], keys, strict=True):
                digest = inputs[key]
                # CON.01 immutable exception binds its accepted source, which may evolve later.
                source = subprocess.check_output(['git', 'show',
                    'f5ae65c9bfafb46a36941cd4391ba274fddb5d9e:' + key], cwd=ROOT)
                self.assertEqual(hashlib.sha256(source.replace(b'\r\n', b'\n')).hexdigest(), digest)
                self.assertIsNotNone(re.fullmatch(pattern, f' "{key}": "{digest}",'))
                for bad in [f' "{key}": "' + '0' * 64 + '",', f' "unrelated-key": "{digest}",',
                            f' "{key}": "ghp_actual_credential",', f' "{key}": "{digest}", "token": "extra"']:
                    self.assertIsNone(re.fullmatch(pattern, bad))

    def test_retirement_hash_exceptions_match_only_observed_exact_rows(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        expected = ['eng/policy/dependency-policy.json',
                    'eng/policy/dependency-reviews/con-23-retirement-r1.json',
                    'eng/provenance/artifact-profiles/dokka-2-2-0-r8.json']
        for allow, name in zip(config['allowlists'][13:16], expected, strict=True):
            self.assertEqual(allow['targetRules'], ['generic-api-key'])
            self.assertEqual(allow['condition'], 'AND')
            self.assertEqual(allow['regexTarget'], 'line')
            paths = ['^' + re.escape(name) + '$']
            if name == expected[1]:
                paths.append('^' + re.escape(name.replace('-r1.json', '-r2.json')) + '$')
            self.assertEqual(allow['paths'], paths)
            self.assertIsNone(re.fullmatch(allow['paths'][0], name + '.backup'))
            # The current-policy rows also remain in the immutable r1 receipt.
            source = ROOT / (expected[1] if name == expected[0] else name)
            lines = source.read_text().splitlines()
            for pattern in allow['regexes']:
                matched = [line for line in lines if re.fullmatch(pattern, line)]
                self.assertTrue(matched)
                for line in matched:
                    value = json.loads('{' + line.strip().rstrip(',') + '}')
                    self.assertRegex(next(iter(value.values())), '^[0-9a-f]{64}$')
                    changed = re.sub('[0-9a-f]{64}', '0' * 64, line)
                    self.assertIsNone(re.fullmatch(pattern, changed))

    def test_con17_secret_exceptions_reject_other_paths_keys_digests_and_tokens(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        paths = ['eng/policy/dependency-reviews/con17-previous-client-113-1.json',
                 'eng/policy/dependency-policy.json']
        # Historical SHA verified from pre-rebase 8050e7f4c87eb40803c36cbc66979069246ed3dc;
        # subsequent actual source snapshots are a1d2f4b and beb433af (CI findings).
        digests = ['622d53ff60931677847ab90c550721b7630c13e167133bd13688215e46f5ae1e',
                   '9de84aa03629c593bad2d795db15f7edb83c5f01cb37b2cb1aca012c67660cbf',
                   '145298928cd567802b7e8504f75b765270f95539fe9f12d2d65405b4d6c8dc92']
        source = 'eng/policy/contract-access.json'
        historical = json.loads((ROOT / paths[0]).read_text())['review']['inputHashes'][source]
        self.assertEqual(historical, digests[-1])
        for allow, path, expected in zip(config['allowlists'][17:19], paths, [digests, digests[1:]], strict=True):
            self.assertEqual(allow['targetRules'], ['generic-api-key'])
            self.assertEqual(allow['condition'], 'AND')
            self.assertEqual(allow['regexTarget'], 'line')
            self.assertEqual(allow['paths'], ['^' + re.escape(path) + '$'])
            for other in [path + '.backup', 'src/secrets.json', 'eng/policy/dependency-reviews/other.json']:
                self.assertIsNone(re.fullmatch(allow['paths'][0], other))
            for pattern, digest in zip(allow['regexes'], expected, strict=True):
                self.assertIsNotNone(re.fullmatch(pattern, f'  "{source}": "{digest}",'))
                for line in [f'"{source}": "' + '0' * 64 + '"',
                             f'"secret_key": "{digest}"', f'"{source}": "ghp_actual_credential"',
                             f'"{source}": "{digest}", "token": "extra"']:
                    self.assertIsNone(re.fullmatch(pattern, line))

    def test_con12_observed_hash_exceptions_remain_exact(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        rows = [row for row in config['allowlists'] if row['description'].startswith('CON12 observed')]
        # CI36345963386 observed these exact public input identities. Source hashes
        # were independently rehashed at 76d36b1 and pre-rebase 3870157, not secrets.
        access = 'eng/policy/contract-access.json'
        current = 'cfe372f32129aa483b7d8e2ba147ee8b973808449843758f48e52ef0bfbeef39'
        latest = 'f91320260c81e4d6bac5abcf1b479cafa5b51bdbaa2e12a6b3e7978e588f2511'  # CI36348431152 observed source31f9a14, rehashed
        previous = '7bfbf2a7a7ec9b6e8086261baa6509a57de5de592cc674b5df9d07e67eca1a78'
        prior_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/con-16-signed-formats-r1.json').read_text())['review']['inputHashes']
        expected = [
            ('eng/policy/dependency-policy.json', [(access, current), (access, latest)]),
            ('eng/policy/dependency-reviews/con-12-profiles-r1.json', [
                (access, current), (access, latest), (access, previous),
                ('eng/provenance/records/dokka-combokeys-licence-r1.json', prior_receipt['eng/provenance/records/dokka-combokeys-licence-r1.json']),
                ('eng/provenance/records/dokka-object-keys-licence-r1.json', prior_receipt['eng/provenance/records/dokka-object-keys-licence-r1.json']),
                ('src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj', prior_receipt['src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj'])])]
        self.assertEqual(len(rows), len(expected))
        for allow, (path, pairs) in zip(rows, expected, strict=True):
            self.assertEqual(allow['targetRules'], ['generic-api-key'])
            self.assertEqual(allow['condition'], 'AND')
            self.assertEqual(allow['regexTarget'], 'line')
            self.assertEqual(allow['paths'], ['^' + re.escape(path) + '$'])
            for other in [path + '.backup', 'secrets.json', 'eng/policy/dependency-reviews/other.json']:
                self.assertIsNone(re.fullmatch(allow['paths'][0], other))
            self.assertEqual(len(allow['regexes']), len(pairs))
            for pattern, (key, digest) in zip(allow['regexes'], pairs, strict=True):
                line = '  "' + key + '": "' + digest + '",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for wrong in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                              line.replace(key, key + '.other'), line + ' "token": "extra"',
                              '"api_key": "synthetic-secret" ' + line]:
                    self.assertIsNone(re.fullmatch(pattern, wrong))

    def test_con16_hash_exceptions_are_exact_observed_source_rows(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        receipt = 'eng/policy/dependency-reviews/con-16-signed-formats-r1.json'
        keys = ['eng/policy/contract-access.json',
                'eng/provenance/records/dokka-combokeys-licence-r1.json',
                'eng/provenance/records/dokka-object-keys-licence-r1.json',
                'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        values = json.loads((ROOT / receipt).read_text())['review']['inputHashes']
        for allow, path, selected in zip(config['allowlists'][23:25],
                ['eng/policy/dependency-policy.json', receipt], [keys[:1], keys], strict=True):
            self.assertEqual(allow['targetRules'], ['generic-api-key'])
            self.assertEqual(allow['condition'], 'AND')
            self.assertEqual(allow['regexTarget'], 'line')
            self.assertEqual(allow['paths'], ['^' + re.escape(path) + '$'])
            self.assertEqual(len(allow['regexes']), len(selected))
            for wrong_path in [path + '.backup', path.replace('-r1.', '-r2.'), 'secrets.json']:
                if wrong_path != path:
                    self.assertIsNone(re.fullmatch(allow['paths'][0], wrong_path))
            for pattern, key in zip(allow['regexes'], selected, strict=True):
                source = subprocess.check_output(['git', 'show',
                    '7eeaa3b407ca1d99f1320ecf9d1fb752c9c9ba21:' + key], cwd=ROOT)
                digest = hashlib.sha256(source.replace(b'\r\n', b'\n')).hexdigest()
                self.assertEqual(values[key], digest)
                line = '  "' + key + '": "' + digest + '",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for altered in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                                line.replace(key, key + '.other'), line + ' "api_key": "synthetic-secret"',
                                '"api_key": "synthetic-secret" ' + line]:
                    self.assertIsNone(re.fullmatch(pattern, altered))

    def test_con05_observed_hash_exceptions_remain_exact(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        allowances = [item for item in config['allowlists'] if item['description'].startswith('CON05 observed')]
        self.assertEqual(len(allowances), 2)
        access = 'eng/policy/contract-access.json'
        receipt = 'eng/policy/dependency-reviews/con-05-local-contracts-r1.json'
        old = '563a8d6f0688ae136be9021dbe3c900c2118abe5a65e796fc69be9fa809a60f2'
        middle = 'a022f6b9e927489be7154a3ff57bc4494ffdfd5f8bb0d535b599a52eff3e9781'
        current = 'eb06d2aaa28fe2df9b67638826c1f79fc7c9186be605160c2c8b48cfec9cd914'
        latest = '044f72f24c1e3def8f062b13f1cb4623c81d04f4dfaeab0936d8e15c2f8729ad'
        merged = 'ef5c0d7def7947ad7c7467eb15da29d4358cfff641659dbd571ba9b8f99aa8d7'
        formatted = 'a620fa8949c0792ec676ae3556b5c276e0c1f8b1aac846aa3b5ac4b09e339802'
        finalbase = '490eb4cfcb1ec489a3b6145c87e8e4bc1cdd91ca594b132797ee1701b0b51835'
        historic = json.loads(subprocess.check_output(['git', 'show', '970cf59fa53fb3d398d617555a832db8edef5146:' + receipt], cwd=ROOT))
        # The retained intermediate receipt refers to pre-rebase 1691927; its public
        # access blob was independently byte-verified in Design87/Plan55 review.
        self.assertEqual(historic['review']['inputHashes'][access], old)
        for revision, expected in [('b6a000496703829801fcff0b269cfe59200c408a', middle),
                                   ('a222f72df9221f0f92279b702a7132c905b23949', current),
                                   ('b771db98b4ae518f96161f8fba81f191276692f0', latest),
                                   ('509cf357551a3bec377aea0f1f165c444e6b3c65', merged),
                                   ('f2ec7aa84b03827f2986fdcccf213fbd076a256f', formatted),
                                   ('ed76affa36e19c3a3ecba20ae73175976348837c', finalbase)]:
            source = subprocess.check_output(['git', 'show', revision + ':' + access], cwd=ROOT)
            self.assertEqual(hashlib.sha256(source.replace(b'\r\n', b'\n')).hexdigest(), expected)
        other_keys = ['eng/provenance/records/dokka-combokeys-licence-r1.json',
                      'eng/provenance/records/dokka-object-keys-licence-r1.json',
                      'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        other = []
        for key in other_keys:
            source = subprocess.check_output(['git', 'show', 'a222f72df9221f0f92279b702a7132c905b23949:' + key], cwd=ROOT)
            digest = hashlib.sha256(source.replace(b'\r\n', b'\n')).hexdigest()
            self.assertEqual(historic['review']['inputHashes'][key], digest)
            other.append((key, digest))
        expected_rows = [[(access, middle), (access, current), (access, latest), (access, merged), (access, formatted), (access, finalbase)],
                         [(access, old), (access, middle), (access, current), (access, latest), (access, merged), (access, formatted), (access, finalbase), *other]]
        for allow, target, rows in zip(allowances, ['eng/policy/dependency-policy.json', receipt], expected_rows, strict=True):
            self.assertEqual(allow['targetRules'], ['generic-api-key'])
            self.assertEqual(allow['condition'], 'AND')
            self.assertEqual(allow['regexTarget'], 'line')
            self.assertEqual(allow['paths'], ['^' + re.escape(target) + '$'])
            self.assertEqual(len(allow['regexes']), len(rows))
            for wrong in [target + '.backup', 'secrets.json', 'eng/policy/dependency-reviews/con-05-local-contracts-r2.json']:
                self.assertIsNone(re.fullmatch(allow['paths'][0], wrong))
            for pattern, (key, digest) in zip(allow['regexes'], rows, strict=True):
                line = '  "' + key + '": "' + digest + '",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for changed in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                                line.replace(key, key + '.other'), line + ' "api_key": "synthetic-secret"',
                                '"api_key": "synthetic-secret" ' + line]:
                    self.assertIsNone(re.fullmatch(pattern, changed))

    def test_con04_observed_hash_exceptions_are_narrow(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        groups = [row for row in config['allowlists'] if row['description'].startswith('CON04 observed')]
        self.assertEqual(len(groups), 2)
        access = 'eng/policy/contract-access.json'
        receipt = 'eng/policy/dependency-reviews/con-04-r1.json'
        historical = 'f80d54b5a5572909211b19090936e6869505fd52b68fe1d91e9284a030d2dfad'
        sources = [('c28876c909144f67de6529033e225badd7cbb05e', 'ebe08d8b390df96270eb539a1cb236732dbe3efc9d8f2338daeca6add4d3bed6'),
                   ('7d0a8630f950734404da81c21714c59a76bf1bd8', '2e7115ac2dec1721a7b1e0a83bf214235230f168e37083e09e77807e17ca9e58'),
                   ('7f5321e0695d2b7780c381d63cfdf4a70922cd84', 'd2e977d7b4300d320207d4ea0b44be5faf09ef04dc233faebc4222d949771eec'),
                   ('a353a1f24d1b04e5e7e44edec3b10ac23ca10e19', 'e5f4c02d5ace66df561da638a6c99cc96cfcce42ec59fd6c3e22db653c6998f0')]
        for commit, digest in sources:
            value = subprocess.check_output(['git', 'show', commit + ':' + access], cwd=ROOT)
            self.assertEqual(hashlib.sha256(value.replace(b'\r\n', b'\n')).hexdigest(), digest)
        # Pre-rebase source 1012a58 was independently rehashed in Design87 comment5859309280;
        # the scanned historical receipt remains in the task ancestry after rebase.
        old = json.loads(subprocess.check_output(['git', 'show', 'edbcf96c6684e31b9eceb880576813286fc0a01d:' + receipt], cwd=ROOT))
        self.assertEqual(old['review']['inputHashes'][access], historical)
        hashes = json.loads(subprocess.check_output(['git', 'show', 'a353a1f24d1b04e5e7e44edec3b10ac23ca10e19:' + receipt], cwd=ROOT))['review']['inputHashes']
        other = ['eng/provenance/records/dokka-combokeys-licence-r1.json',
                 'eng/provenance/records/dokka-object-keys-licence-r1.json',
                 'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        rows = [[(access, digest) for _, digest in sources],
                [(access, digest) for _, digest in sources[:2]] + [(access, historical)] + [(access, digest) for _, digest in sources[2:]] + [(key, hashes[key]) for key in other]]
        for key in other:
            source = subprocess.check_output(['git', 'show', 'a353a1f24d1b04e5e7e44edec3b10ac23ca10e19:' + key], cwd=ROOT)
            self.assertEqual(hashlib.sha256(source.replace(b'\r\n', b'\n')).hexdigest(), hashes[key])
        for group, path, expected in zip(groups, ['eng/policy/dependency-policy.json', receipt], rows, strict=True):
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], ['^' + re.escape(path) + '$'])
            self.assertEqual(len(group['regexes']), len(expected))
            for wrong in [path + '.backup', 'secrets.json', 'eng/policy/dependency-reviews/other.json']:
                self.assertIsNone(re.fullmatch(group['paths'][0], wrong))
            for pattern, (key, digest) in zip(group['regexes'], expected, strict=True):
                line = f'  "{key}": "{digest}",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for bad in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                            line + ' "token": "synthetic-secret"', '"token": "synthetic-secret" ' + line,
                            line.replace(digest, 'ghp_synthetic_credential')]:
                    self.assertIsNone(re.fullmatch(pattern, bad))


    def test_con13_observed_hash_exceptions_are_narrow(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        groups = [row for row in config['allowlists'] if row['description'].startswith('CON13 observed public input')]
        self.assertEqual(len(groups), 2)
        keys = ['eng/policy/contract-access.json', 'eng/provenance/records/dokka-combokeys-licence-r1.json', 'eng/provenance/records/dokka-object-keys-licence-r1.json', 'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        digests = ['35563026049706b6a119191ce3679a7ebb918a228aee5267b0fdf84c6764d996', '75219d61672002f0bb242fed0fd93a0886f07d944e0b9e1b1f72132f59df1b41', '55621ecc7032745ca46e56d13133dc22a3bd808d80966d737427b5d6fc5bd096', '986b7a97734cd5d0630e548da897869de322a112c087c2d0df6a0bfc98b8784c']
        rows = list(zip(keys, digests, strict=True))
        for key, expected in rows:
            source = subprocess.check_output(['git', 'show', '1acce905a742a92598180916a86dbdbc9354214e:' + key], cwd=ROOT)
            self.assertEqual(hashlib.sha256(source.replace(b'\r\n', b'\n')).hexdigest(), expected)
        targets = ['eng/policy/dependency-policy.json', 'eng/policy/dependency-reviews/con-13-r1.json']
        for group, path, bindings in zip(groups, targets, [rows[:1], rows], strict=True):
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], ['^' + re.escape(path) + '$'])
            self.assertEqual(len(group['regexes']), len(bindings))
            for wrong in [path + '.backup', 'secrets.json', 'eng/policy/dependency-reviews/other.json']:
                self.assertIsNone(re.fullmatch(group['paths'][0], wrong))
            for pattern, (key, digest) in zip(group['regexes'], bindings, strict=True):
                line = f'  "{key}": "{digest}",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for wrong in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                              line + ' "token": "synthetic-secret"', '"token": "synthetic-secret" ' + line,
                              line.replace(digest, 'ghp_synthetic_credential')]:
                    self.assertIsNone(re.fullmatch(pattern, wrong))

    def test_con13_r10_observed_hash_exceptions_preserve_exact_r9_bindings(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        group = next(row for row in config['allowlists'] if row['description'].startswith('CON13 observed unchanged'))
        commit = 'dd8d18f43fbbbed7c6ea9af1d5bad923cd46bb97'
        prior = tomllib.loads(subprocess.check_output(['git', 'show', commit + ':.gitleaks.toml'], cwd=ROOT).decode())
        previous = next(row for row in prior['allowlists'] if row['description'].startswith('CON.02 exact observed') and any('r9' in path for path in row['paths']))
        self.assertEqual(group['regexes'], previous['regexes'])
        self.assertEqual(len(group['regexes']), 164)
        path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r10.json'
        self.assertEqual(group['paths'], ['^' + re.escape(path) + '$'])
        self.assertEqual(group['targetRules'], ['generic-api-key'])
        self.assertEqual(group['condition'], 'AND')
        self.assertEqual(group['regexTarget'], 'line')
        old = json.loads(subprocess.check_output(['git', 'show', commit + ':' + path.replace('r10.json', 'r9.json')], cwd=ROOT))
        new = json.loads(subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT))
        old_pages = {key: value for module in old['modules'].values() for key, value in module['pages'].items()}
        new_pages = {key: value for module in new['modules'].values() for key, value in module['pages'].items()}
        by_hash = {}
        for key, value in old_pages.items():
            by_hash.setdefault(value, []).append(key)
        for pattern in group['regexes']:
            digest = re.search(r'[0-9a-f]{64}', pattern).group()
            keys = [key for key in by_hash[digest] if re.fullmatch(pattern, f'  "{key}": "{digest}",')]
            self.assertEqual(len(keys), 1)
            key = keys[0]
            self.assertEqual(new_pages[key], digest)
            line = f'  "{key}": "{digest}",'
            for bad in [line.replace(key, 'api_key'), line.replace(digest, '0' * 64),
                        line + ' "token": "synthetic-secret"', '"token": "synthetic-secret" ' + line]:
                self.assertIsNone(re.fullmatch(pattern, bad))
        for wrong in [path + '.backup', path.replace('r10.json', 'r11.json'), 'secrets.json']:
            self.assertIsNone(re.fullmatch(group['paths'][0], wrong))

    def test_con06_observed_public_hashes_are_exact_and_immutable(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        groups = [row for row in config['allowlists'] if row['description'].startswith('CON06 exact observed')]
        self.assertEqual(len(groups), 3)
        commit = '0b86db7e5375d60530404d87fcca4088bc9beba6'
        targets = ['eng/policy/dependency-policy.json', 'eng/policy/dependency-reviews/con-06-r1.json',
                   'eng/provenance/artifact-profiles/dokka-2-2-0-r11.json']
        frozen = lambda path: subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT).replace(b'\r\n', b'\n')
        prior = json.loads(frozen(targets[2].replace('r11.json', 'r10.json')))
        prior_pages = {key: value for module in prior['modules'].values() for key, value in module['pages'].items()}
        permissions, occurrences = set(), 0
        for group, path, count in zip(groups, targets, [1, 4, 164], strict=True):
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], ['^' + re.escape(path) + '$'])
            self.assertEqual(len(group['regexes']), count)
            lines = frozen(path).decode().splitlines()
            for pattern in group['regexes']:
                matching = [line for line in lines if re.fullmatch(pattern, line)]
                self.assertTrue(matching)
                occurrences += len(matching)
                pairs = {tuple(json.loads('{' + line.strip().rstrip(',') + '}').items())[0] for line in matching}
                self.assertEqual(len(pairs), 1)
                key, digest = pairs.pop()
                expected = r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                self.assertEqual(pattern, expected)
                permissions.add((path, key, digest))
                if path == targets[2]:
                    self.assertEqual(prior_pages[key], digest)
                else:
                    self.assertEqual(hashlib.sha256(frozen(key)).hexdigest(), digest)
                line = matching[0]
                for wrong in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                              line + ' "token": "synthetic-secret"', '"token": "synthetic-secret" ' + line,
                              line.replace(digest, 'ghp_synthetic_credential')]:
                    self.assertIsNone(re.fullmatch(pattern, wrong))
            for wrong in [path + '.backup', 'secrets.json', path.replace('r11.json', 'r12.json') if path == targets[2] else 'eng/policy/other.json']:
                self.assertIsNone(re.fullmatch(group['paths'][0], wrong))
        self.assertEqual(occurrences, 170)
        self.assertEqual(len(permissions), 169)
        canonical = ''.join('\t'.join(row) + '\n' for row in sorted(permissions)).encode()
        expected_digest = '9c1a63824bc8b29c9fb89a8b508c4b32b443167aa1b45b74ff551b4ec2a5857f'
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), expected_digest)

    def test_con03_secret_scan_exceptions_bind_only_reviewed_history_rows(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        groups = [row for row in config['allowlists'] if row['description'].startswith('CON03 exact')]
        self.assertEqual(len(groups), 3)
        by_path = {row['paths'][0]: row for row in groups}
        commits = ['0152f214ed79340bbdd0419f52542d1cf3448117',
                   '963eeb3473b36718c4979fddcc1672d9e04e69e5',
                   '9b9a38a36757e6081905bd22f59a9a99757e26a6',
                   '6bc02659e56802daecbc351325132e3642e13fb2']
        frozen = lambda commit, path: subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT).replace(b'\r\n', b'\n')
        pair = lambda line: tuple(json.loads('{' + line.strip().rstrip(',') + '}').items())[0]
        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-03-r1.json'
        policy_rows, receipt_rows = [], []
        for commit in commits:
            policy_lines = frozen(commit, policy_path).decode().splitlines()
            rows = [pair(line) for line in policy_lines
                    if line.strip().startswith('"eng/policy/contract-access.json":')]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], rows[1])
            access = hashlib.sha256(frozen(commit, 'eng/policy/contract-access.json')).hexdigest()
            self.assertEqual(rows[0], ('eng/policy/contract-access.json', access))
            policy_rows.extend(rows)

            receipt_lines = frozen(commit, receipt_path).decode().splitlines()
            rows = [pair(line) for line in receipt_lines
                    if line.strip().startswith('"eng/policy/contract-access.json":')]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][1], access)
            receipt_rows.extend(rows)

        initial_receipt = frozen(commits[0], receipt_path).decode().splitlines()
        supporting_rows = [pair(initial_receipt[index - 1]) for index in (60, 120, 176)]
        self.assertEqual([key for key, _ in supporting_rows], [
            'eng/provenance/records/dokka-combokeys-licence-r1.json',
            'eng/provenance/records/dokka-object-keys-licence-r1.json',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj'])
        receipt_rows.extend(supporting_rows)
        self.assertEqual(len(policy_rows), 8)
        self.assertEqual(len(set(policy_rows)), 4)
        self.assertEqual(len(receipt_rows), 7)
        self.assertEqual(len(set(receipt_rows)), 7)

        def assert_group(path, rows, occurrences):
            group = by_path['^' + re.escape(path) + '$']
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            expected = [r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                        for key, digest in sorted(set(rows))]
            self.assertEqual(group['regexes'], expected)
            self.assertEqual(len(rows), occurrences)
            self.assertIsNotNone(re.fullmatch(group['paths'][0], path))
            for wrong in [path + '.backup', 'src/secrets.json', path.replace('.json', '.txt')]:
                self.assertIsNone(re.fullmatch(group['paths'][0], wrong))
            for key, digest in set(rows):
                line = f'  "{key}": "{digest}",'
                pattern = expected[sorted(set(rows)).index((key, digest))]
                self.assertIsNotNone(re.fullmatch(pattern, line))
                self.assertEqual(sum(re.fullmatch(candidate, line) is not None for candidate in expected), 1)
                for bad in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                            line + ' "credential": "synthetic-secret"']:
                    self.assertIsNone(re.fullmatch(pattern, bad))

        assert_group(policy_path, policy_rows, 8)
        assert_group(receipt_path, receipt_rows, 7)

        dokka_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r12.json'
        dokka_group = by_path['^' + re.escape(dokka_path) + '$']
        self.assertEqual(dokka_group['targetRules'], ['generic-api-key'])
        self.assertEqual(dokka_group['condition'], 'AND')
        self.assertEqual(dokka_group['regexTarget'], 'line')
        self.assertEqual(dokka_group['paths'], ['^' + re.escape(dokka_path) + '$'])
        baseline = '0b86db7e5375d60530404d87fcca4088bc9beba6'
        r11_group = next(row for row in config['allowlists']
                         if row['description'].startswith('CON06 exact observed') and 'r11' in row['paths'][0])
        self.assertEqual(len(dokka_group['regexes']), 164)
        self.assertEqual(dokka_group['regexes'], r11_group['regexes'])
        prior_profile = json.loads(subprocess.check_output(
            ['git', 'show', baseline + ':eng/provenance/artifact-profiles/dokka-2-2-0-r11.json'], cwd=ROOT))
        current_profile = json.loads((ROOT / dokka_path).read_bytes())
        prior_pages = prior_profile['modules']['contracts-proto']['pages']
        current_pages = current_profile['modules']['contracts-proto']['pages']
        dokka_pairs = set()
        for pattern in dokka_group['regexes']:
            prior = [(key, digest) for key, digest in prior_pages.items()
                     if re.fullmatch(pattern, f'  "{key}": "{digest}",')]
            current = [(key, digest) for key, digest in current_pages.items()
                       if re.fullmatch(pattern, f'  "{key}": "{digest}",')]
            self.assertEqual(len(prior), 1)
            self.assertEqual(current, prior)
            key, digest = current[0]
            dokka_pairs.add((key, digest))
            for bad in [f'  "{key}": "' + '0' * 64 + '",',
                        f'  "api_key": "{digest}",',
                        f'  "{key}": "{digest}", "credential": "synthetic-secret"']:
                self.assertIsNone(re.fullmatch(pattern, bad))
        canonical = ''.join('\t'.join(row) + '\n' for row in sorted(dokka_pairs)).encode()
        self.assertEqual(len(dokka_pairs), 164)
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         '439cb05e61abb110888dd125c36e8d499ae5937be12ad2eaf3cc115dbc22c8e7')
        unique_bindings = ({(policy_path, key, digest) for key, digest in set(policy_rows)} |
                           {(receipt_path, key, digest) for key, digest in set(receipt_rows)} |
                           {(dokka_path, key, digest) for key, digest in dokka_pairs})
        self.assertEqual(8 + 7 + 164, 179)
        self.assertEqual(len(unique_bindings), 175)

    def setUp(self):
        self.policy = json.loads((ROOT / POLICY).read_text())
        self.graph = inventory(ROOT)

    def test_current_closure(self):
        self.assertEqual(audit()['result'], 'passed')
        with self.assertRaisesRegex(ValueError, 'Stable closure contains prerelease: nuget:arcforges.contracts.'):
            audit(stable=True)

    def test_forbidden_licence(self):
        next(iter(self.policy['closure'].values()))['licence'] = 'AGPL-3.0-only'
        with self.assertRaisesRegex(ValueError, 'Forbidden'):
            validate(self.policy, self.graph)

    def test_new_dependency(self):
        self.graph['npm:unadmitted@1.0.0'] = 'hash'
        with self.assertRaisesRegex(ValueError, 'Unadmitted'):
            validate(self.policy, self.graph)

    def test_mutable_version(self):
        self.graph[next(iter(self.graph))] = 'changed-archive'
        with self.assertRaisesRegex(ValueError, 'Mutable'):
            validate(self.policy, self.graph)

    def test_review_cannot_mutate_previously_admitted_artifact(self):
        for kind in ['nuget:', 'npm:', 'maven:']:
            old = copy.deepcopy(self.policy)
            changed = copy.deepcopy(self.policy)
            row = next(value for key, value in changed['closure'].items() if key.startswith(kind))
            if isinstance(row['integrity'], dict):
                row['integrity'][next(iter(row['integrity']))] = ['0' * 64]
            else:
                row['integrity'] = 'new-reviewed-content'
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'Historical immutable'):
                immutable_coordinates(changed, [old])

    def test_floating_tag_or_selector(self):
        for value in ['latest', 'ci', 'main', '^1.0.0', '1.+', '1.0-SNAPSHOT', 'git+https://example.test/source#v1']:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Floating'):
                pinned(value)
        self.policy['review']['baselineCommit'] = 'v1.0.0'
        with self.assertRaisesRegex(ValueError, 'Floating source'):
            validate(self.policy, self.graph)

    def test_wrong_publisher_and_feed(self):
        for field, value in [('repository', 'fork/Contracts'), ('workflow', 'untrusted.yml')]:
            policy = copy.deepcopy(self.policy)
            policy['publisher'][field] = value
            with self.assertRaisesRegex(ValueError, 'Wrong publisher'):
                validate(policy, self.graph)

    def test_major_framework_change_requires_runtime_review(self):
        before = {'frameworkVersions': {'kotlin': '2.4.20'}}
        after = {'frameworkVersions': {'kotlin': '3.0.0'}}
        with self.assertRaisesRegex(ValueError, 'framework major'):
            major_upgrade(before, after)
        after['frameworkMajorReview'] = {'changed': ['kotlin'], 'owner': 'Architecture owner',
            'nativeAotTrim': 'fixture', 'androidKotlinArtR8': 'fixture', 'transport': 'fixture', 'localCoverage': 'not run: fixture'}
        major_upgrade(before, after)

    def test_upgrade_review_required(self):
        for field in ['inputHashes', 'checks']:
            policy = copy.deepcopy(self.policy)
            policy['review'][field] = {}
            with self.assertRaisesRegex(ValueError, 'Upgrade|upgrade'):
                validate(policy, self.graph)

    def test_stable_rejects_transitive_prerelease(self):
        entry = copy.deepcopy(next(iter(self.policy['closure'].values())))
        key = 'nuget:preview.transitive@1.0.0-rc.1'
        self.policy['closure'][key] = entry
        self.graph[key] = entry['integrity']
        with self.assertRaisesRegex(ValueError, 'Stable closure'):
            validate(self.policy, self.graph, stable=True)

    def test_nonstandard_preview_is_not_stable(self):
        for key in ['nuget:test@1.0.0-dev.1', 'npm:test@1.0.0-eap', 'maven:example:library:1.0.0-dev']:
            with self.subTest(key=key):
                self.assertFalse(stable_dependency(key))
        for version in ['1.0.0-jre', '1.0.0-android', '1.0.0.GA', '1.0.0.Final']:
            self.assertTrue(stable_dependency('maven:example:library:' + version))

    def test_public_internal_guard_required(self):
        self.policy['publicInternalGate'] = ''
        with self.assertRaisesRegex(ValueError, 'Public/internal'):
            validate(self.policy, self.graph)

    def test_secret_scan_exceptions_are_exact_public_source_rows(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        self.assertEqual(config['extend'], {'useDefault': True})
        self.assertEqual(len(config['allowlists']), 100)
        allow = config['allowlists'][0]
        self.assertEqual(allow['targetRules'], ['generic-api-key'])
        self.assertEqual(allow['condition'], 'AND')
        self.assertEqual(allow['regexTarget'], 'line')
        self.assertEqual(len(allow['paths']), 1)
        self.assertIsNone(re.fullmatch(allow['paths'][0], 'src/secret.json'))
        self.assertEqual(len(allow['regexes']), 4)
        sources = ['eng/policy/contract-access.json', 'eng/provenance/records/dokka-combokeys-licence-r1.json',
                   'eng/provenance/records/dokka-object-keys-licence-r1.json',
                   'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        for source, pattern in zip(sources, allow['regexes']):
            receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/wp02-05-r1.json').read_text(encoding='utf-8'))
            digest = receipt['review']['inputHashes'][source]
            self.assertIsNotNone(re.fullmatch(pattern, f'  "{source}": "{digest}",'))
            self.assertIsNone(re.fullmatch(pattern, f'  "{source}": "' + '0' * 64 + '",'))


        gov05_allowlists = [row for row in config['allowlists']
                            if row.get('description') == 'GOV.05 exact dependency receipt source digests']
        self.assertEqual(len(gov05_allowlists), 1)
        gov05_allow = gov05_allowlists[0]
        self.assertEqual(gov05_allow['targetRules'], ['generic-api-key'])
        self.assertEqual(gov05_allow['condition'], 'AND')
        self.assertEqual(gov05_allow['regexTarget'], 'line')
        self.assertEqual(gov05_allow['paths'], [r'^eng/policy/dependency-reviews/gov-05-r1\.json$'])
        self.assertEqual(len(gov05_allow['regexes']), 4)
        self.assertIsNone(re.fullmatch(gov05_allow['paths'][0], 'eng/policy/dependency-reviews/con-06-r1.json'))
        gov05_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/gov-05-r1.json').read_text(encoding='utf-8'))
        gov05_sources = ['eng/policy/contract-access.json',
                         'eng/provenance/records/dokka-combokeys-licence-r1.json',
                         'eng/provenance/records/dokka-object-keys-licence-r1.json',
                         'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        for source, pattern in zip(gov05_sources, gov05_allow['regexes']):
            digest = gov05_receipt['review']['inputHashes'][source]
            self.assertIsNotNone(re.fullmatch(pattern, f'  "{source}": "{digest}",'))
            self.assertIsNone(re.fullmatch(pattern, f'  "{source}": "' + '0' * 64 + '",'))

        gov05_policy_allowlists = [row for row in config['allowlists']
                                   if row.get('description') == 'GOV.05 exact dependency-policy contract-access input digest']
        self.assertEqual(len(gov05_policy_allowlists), 1)
        gov05_policy_allow = gov05_policy_allowlists[0]
        self.assertEqual(gov05_policy_allow['targetRules'], ['generic-api-key'])
        self.assertEqual(gov05_policy_allow['condition'], 'AND')
        self.assertEqual(gov05_policy_allow['regexTarget'], 'line')
        self.assertEqual(gov05_policy_allow['paths'], [r'^eng/policy/dependency\-policy\.json$'])
        self.assertEqual(len(gov05_policy_allow['regexes']), 1)
        expected_contract_access_digest = (
            '75cd9803c8c2b3a6d88dee89f11641b1'
            '838fa954adeddc8ccc31b9f39ec05621'
        )
        previous_contract_access_digest = (
            '99e2e46d33a86a1486ecdc71d314f553'
            'a224433259cbf9c93e93417d635a9188'
        )
        # The live policy advances with later tasks; the GOV.05 digest is bound in its immutable receipt.
        self.assertEqual(gov05_receipt['review']['inputHashes']['eng/policy/contract-access.json'],
                         expected_contract_access_digest)
        self.assertIsNotNone(re.fullmatch(
            gov05_policy_allow['regexes'][0],
            f'  "eng/policy/contract-access.json": "{expected_contract_access_digest}",'))
        self.assertIsNone(re.fullmatch(
            gov05_policy_allow['regexes'][0],
            f'  "eng/policy/contract-access.json": "{previous_contract_access_digest}",'))
        self.assertIsNone(re.fullmatch(
            gov05_policy_allow['regexes'][0],
            f'  "eng/policy/other.json": "{expected_contract_access_digest}",'))


        receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/wp03-00-r1.json').read_text())
        pages = json.loads((ROOT / 'eng/provenance/artifact-profiles/dokka-2-2-0-r4.json').read_text())['modules']['contracts-proto']['pages']
        current_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/wp03-01-r1.json').read_text())
        current_pages = json.loads((ROOT / 'eng/provenance/artifact-profiles/dokka-2-2-0-r5.json').read_text())['modules']['contracts-proto']['pages']
        latest_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/wp03-01-r2.json').read_text())
        serialization_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/wp03-02-r1.json').read_text())
        prettier_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/dependabot-2026-09-26-prettier-3-9-8.json').read_text())
        grpc_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/dependabot-2026-09-26-grpc-2-84-0.json').read_text())
        protobuf_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/dependabot-2026-09-26-protobuf-4-36-2.json').read_text())
        latest_pages = json.loads((ROOT / 'eng/provenance/artifact-profiles/dokka-2-2-0-r6.json').read_text())['modules']['contracts-proto']['pages']
        r7_pages = json.loads((ROOT / 'eng/provenance/artifact-profiles/dokka-2-2-0-r7.json').read_text())['modules']['contracts-proto']['pages']
        # Exact public API rows reported by CI at source f9dc23fea7ae1dae3805404bb800583aea4e13e0.
        reviewed_public_pages = [
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block-kt/-dsl/clear-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block-kt/-dsl/has-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block-kt/-dsl/order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block-or-builder/get-order-key-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block-or-builder/get-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block-or-builder/has-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block/-builder/clear-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block/-builder/get-order-key-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block/-builder/get-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block/-builder/has-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block/-builder/set-order-key-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block/-builder/set-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block/get-order-key-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block/get-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-block/has-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view-kt/-dsl/clear-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view-kt/-dsl/has-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view-kt/-dsl/order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view-or-builder/get-order-key-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view-or-builder/get-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view-or-builder/has-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view/-builder/clear-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view/-builder/get-order-key-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view/-builder/get-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view/-builder/has-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view/-builder/set-order-key-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view/-builder/set-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view/get-order-key-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view/get-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-folder-view/has-order-key.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query-kt/-dsl/clear-dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query-kt/-dsl/dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query-kt/-dsl/has-dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query-or-builder/get-dataset-token-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query-or-builder/get-dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query-or-builder/has-dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query/-builder/clear-dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query/-builder/get-dataset-token-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query/-builder/get-dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query/-builder/has-dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query/-builder/set-dataset-token-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query/-builder/set-dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query/get-dataset-token-bytes.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query/get-dataset-token.html',
            'contracts-proto/io.github.arcforges.contracts.publicapi.v1/-notes-query/has-dataset-token.html',
        ]
        new_sources = [
            {key: receipt['review']['inputHashes'][key] for key in [
                'eng/policy/contract-access.json',
                'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']},
            {key: value for key, value in pages.items() if 'message-key' in key},
            {key: current_receipt['review']['inputHashes'][key] for key in sources},
            {key: value for key, value in current_pages.items() if 'message-key' in key},
            {key: current_pages[key] for key in reviewed_public_pages},
            {key: latest_pages[key] for key in reviewed_public_pages + [key for key in current_pages if 'message-key' in key]},
            {key: latest_receipt['review']['inputHashes'][key] for key in sources},
            {key: serialization_receipt['review']['inputHashes'][key] for key in sources},
            {key: prettier_receipt['review']['inputHashes'][key] for key in sources},
            {key: grpc_receipt['review']['inputHashes'][key] for key in sources},
            {key: protobuf_receipt['review']['inputHashes'][key] for key in sources},
            {key: r7_pages[key] for key in reviewed_public_pages + [key for key in current_pages if 'message-key' in key]},
        ]
        for allow, source_rows, permitted, excluded in zip(config['allowlists'][1:13], new_sources,
                ['eng/policy/dependency-reviews/wp03-00-r1.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r4.json',
                 'eng/policy/dependency-reviews/wp03-01-r1.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r5.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r5.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r6.json',
                 'eng/policy/dependency-reviews/wp03-01-r2.json',
                 'eng/policy/dependency-reviews/wp03-02-r1.json',
                 'eng/policy/dependency-reviews/dependabot-2026-09-26-prettier-3-9-8.json',
                 'eng/policy/dependency-reviews/dependabot-2026-09-26-grpc-2-84-0.json',
                 'eng/policy/dependency-reviews/dependabot-2026-09-26-protobuf-4-36-2.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r7.json'],
                ['eng/provenance/artifact-profiles/dokka-2-2-0-r4.json',
                 'eng/policy/dependency-policy.json',
                 'eng/policy/dependency-reviews/wp03-00-r1.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r4.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r4.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r5.json',
                 'eng/policy/dependency-reviews/wp03-01-r1.json',
                 'eng/policy/dependency-reviews/wp03-01-r2.json',
                 'eng/policy/dependency-reviews/wp03-02-r1.json',
                 'eng/policy/dependency-reviews/dependabot-2026-09-26-prettier-3-9-8.json',
                 'eng/policy/dependency-reviews/dependabot-2026-09-26-grpc-2-84-0.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r6.json'], strict=True):
            self.assertEqual(allow['targetRules'], ['generic-api-key'])
            self.assertEqual(allow['condition'], 'AND')
            self.assertEqual(allow['regexTarget'], 'line')
            self.assertEqual(len(allow['paths']), 1)
            self.assertIsNotNone(re.fullmatch(allow['paths'][0], permitted))
            for wrong_path in [excluded, 'src/secret.json', permitted + '.backup']:
                self.assertIsNone(re.fullmatch(allow['paths'][0], wrong_path))
            self.assertEqual(len(allow['regexes']), len(source_rows))
            for (source, digest), pattern in zip(sorted(source_rows.items()), allow['regexes'], strict=True):
                self.assertEqual(pattern, rf'(?s)^\s*"{re.escape(source)}":\s*"{digest}",?\s*$')
                self.assertIsNotNone(re.fullmatch(pattern, f'  "{source}": "{digest}",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "{source}": "' + '0' * 64 + '",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "credential": "{digest}",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "{source}": "{digest}", "credential": "other"'))
        self.assertIsNotNone(re.fullmatch(config['allowlists'][3]['paths'][0], 'eng/policy/dependency-policy.json'))
        self.assertIsNone(re.fullmatch(config['allowlists'][3]['paths'][0], 'eng/policy/dependency-reviews/wp03-01-r2.json'))
        self.assertEqual(config['allowlists'][6]['paths'], [r'^eng/provenance/artifact-profiles/dokka-2-2-0-r6\.json$'])
        self.assertEqual(config['allowlists'][7]['paths'], [r'^eng/policy/(dependency-policy\.json|dependency-reviews/wp03-01-r2\.json)$'])
        self.assertIsNotNone(re.fullmatch(config['allowlists'][7]['paths'][0], 'eng/policy/dependency-policy.json'))
        self.assertIsNone(re.fullmatch(config['allowlists'][7]['paths'][0], 'eng/policy/dependency-reviews/wp03-01-r3.json'))
        self.assertEqual(config['allowlists'][8]['paths'], [r'^eng/policy/(dependency-policy\.json|dependency-reviews/wp03-02-r1\.json)$'])
        self.assertIsNone(re.fullmatch(config['allowlists'][8]['paths'][0], 'eng/policy/dependency-reviews/wp03-02-r2.json'))
        self.assertEqual(config['allowlists'][9]['paths'], [r'^eng/policy/(dependency-policy\.json|dependency-reviews/dependabot\-2026\-09\-26\-prettier\-3\-9\-8\.json)$'])
        self.assertIsNone(re.fullmatch(config['allowlists'][9]['paths'][0], 'eng/policy/dependency-reviews/dependabot-2026-09-26-prettier-3-9-9.json'))
        self.assertEqual(config['allowlists'][10]['paths'], [r'^eng/policy/(dependency-policy\.json|dependency-reviews/dependabot\-2026\-09\-26\-grpc\-2\-84\-0\.json)$'])
        self.assertIsNone(re.fullmatch(config['allowlists'][10]['paths'][0], 'eng/policy/dependency-reviews/dependabot-2026-09-26-grpc-2-84-1.json'))
        self.assertEqual(config['allowlists'][11]['paths'], [r'^eng/policy/(dependency-policy\.json|dependency-reviews/dependabot\-2026\-09\-26\-protobuf\-4\-36\-2\.json)$'])
        self.assertIsNone(re.fullmatch(config['allowlists'][11]['paths'][0], 'eng/policy/dependency-reviews/dependabot-2026-09-26-protobuf-4-36-3.json'))
        self.assertEqual(config['allowlists'][12]['paths'], [r'^eng/provenance/artifact-profiles/dokka-2-2-0-r7\.json$'])
        self.assertIsNone(re.fullmatch(config['allowlists'][12]['paths'][0], 'eng/provenance/artifact-profiles/dokka-2-2-0-r8.json'))
        for source in sources:
            self.assertEqual(hashlib.sha256((ROOT / source).read_bytes().replace(b'\r\n', b'\n')).hexdigest(), self.policy['inputHashes'][source])
        self.assertEqual([len(item['regexes']) for item in config['allowlists']], [4, 2, 15, 4, 15, 45, 60, 4, 4, 4, 4, 4, 60, 2, 4, 15, 4, 3, 2, 1, 4, 1, 4, 1, 4, 3, 7, 164, 4, 7, 164, 2, 6, 4, 8, 6, 10, 1, 4, 164, 1, 4, 164, 2, 5, 197, 1, 4, 208, 5, 1, 1, 273, 4, 1, 4, 1, 4, 2, 5, 315, 2, 5, 315, 1, 4, 315, 1, 4, 360, 1, 4, 1, 4, 1, 4, 776, 4, 1, 4, 1, 4, 806, 1, 3, 3, 4, 4, 4, 1, 4, 4, 1, 1, 1, 3, 4, 1, 3, 1])

        ext02_groups = [row for row in config['allowlists']
                        if row['description'] == 'Reviewed EXT.02 exact public dependency-input hashes']
        self.assertEqual(len(ext02_groups), 2)
        ext02_policy_path = r'^eng/policy/dependency-policy\.json$'
        ext02_receipt_path = r'^eng/policy/dependency-reviews/ext-02-r1\.json$'
        ext02_by_path = {row['paths'][0]: row for row in ext02_groups}
        self.assertEqual(set(ext02_by_path), {ext02_policy_path, ext02_receipt_path})
        ext02_policy_group = ext02_by_path[ext02_policy_path]
        ext02_receipt_group = ext02_by_path[ext02_receipt_path]
        ext02_base = 'affeeae06e563340354698dd5e32d74891c96e78'
        policy_path = 'eng/policy/dependency-policy.json'
        ext02_policy = json.loads(subprocess.check_output(
            ['git', 'show', ext02_base + ':' + policy_path], cwd=ROOT, text=True))
        current_policy = json.loads((ROOT / policy_path).read_text(encoding='utf-8'))
        ext02_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/ext-02-r1.json').read_text(encoding='utf-8'))
        self.assertEqual(ext02_policy['inputHashes']['eng/policy/contract-access.json'],
                         ext02_receipt['review']['inputHashes']['eng/policy/contract-access.json'])
        self.assertNotEqual(current_policy['inputHashes']['eng/policy/contract-access.json'],
                            ext02_receipt['review']['inputHashes']['eng/policy/contract-access.json'])
        ext02_policy_rows = [
            ('eng/policy/contract-access.json', ext02_policy['inputHashes']['eng/policy/contract-access.json']),
        ]
        ext02_receipt_rows = [
            ('eng/policy/contract-access.json', ext02_receipt['review']['inputHashes']['eng/policy/contract-access.json']),
            ('eng/provenance/records/dokka-combokeys-licence-r1.json',
             ext02_receipt['review']['inputHashes']['eng/provenance/records/dokka-combokeys-licence-r1.json']),
            ('eng/provenance/records/dokka-object-keys-licence-r1.json',
             ext02_receipt['review']['inputHashes']['eng/provenance/records/dokka-object-keys-licence-r1.json']),
            ('src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
             ext02_receipt['review']['inputHashes']['src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']),
        ]
        for group, path_pattern, rows in [
            (ext02_policy_group, ext02_policy_path, ext02_policy_rows),
            (ext02_receipt_group, ext02_receipt_path, ext02_receipt_rows),
        ]:
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path_pattern])
            self.assertEqual(group['regexes'], [
                rf'(?s)^\s*"{re.escape(source)}":\s*"{digest}",?\s*$'
                for source, digest in rows
            ])
            for (source, digest), pattern in zip(rows, group['regexes'], strict=True):
                line = f'  "{source}": "{digest}",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for bad in [line.replace(digest, '0' * 64),
                            line.replace('"' + source + '"', '"credential"'),
                            line + ' "credential": "synthetic-secret"']:
                    self.assertIsNone(re.fullmatch(pattern, bad))

        self.assertEqual(ext02_policy_path, r'^eng/policy/dependency-policy\.json$')
        self.assertEqual(ext02_receipt_path, r'^eng/policy/dependency-reviews/ext-02-r1\.json$')
        self.assertIsNotNone(re.fullmatch(ext02_policy_path, 'eng/policy/dependency-policy.json'))
        self.assertIsNotNone(re.fullmatch(ext02_receipt_path, 'eng/policy/dependency-reviews/ext-02-r1.json'))
        for path_pattern, wrong_path in [
            (ext02_policy_path, 'eng/policy/dependency-reviews/ext-02-r1.json'),
            (ext02_receipt_path, 'eng/policy/dependency-policy.json'),
            (ext02_policy_path, 'eng/policy/dependency-reviews/con-08-r1.json'),
            (ext02_receipt_path, 'eng/policy/dependency-reviews/ext-02-r2.json'),
            (ext02_policy_path, 'src/secret.json'),
            (ext02_receipt_path, 'src/secret.json'),
        ]:
            self.assertIsNone(re.fullmatch(path_pattern, wrong_path))

        for path, group, expected_count, source_lines in [
            (policy_path, ext02_policy_group, 2,
             subprocess.check_output(['git', 'show', ext02_base + ':' + policy_path], cwd=ROOT, text=True).splitlines()),
            ('eng/policy/dependency-reviews/ext-02-r1.json', ext02_receipt_group, 4,
             (ROOT / 'eng/policy/dependency-reviews/ext-02-r1.json').read_text(encoding='utf-8').splitlines()),
        ]:
            matched_lines = [line for line in source_lines
                             if any(re.fullmatch(pattern, line) for pattern in group['regexes'])]
            self.assertEqual(len(matched_lines), expected_count)

    def test_con08_secret_scan_allowlists_bind_only_observed_public_digest_lines(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text())
        groups = [row for row in config['allowlists'] if row['description'].startswith('CON08 exact observed')]
        self.assertEqual(len(groups), 3)
        by_path = {row['paths'][0]: row for row in groups}

        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-08-r1.json'
        dokka_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r13.json'
        policy = json.loads((ROOT / policy_path).read_text())
        receipt = json.loads((ROOT / receipt_path).read_text())
        profile = json.loads((ROOT / dokka_path).read_text())
        access_key = 'eng/policy/contract-access.json'
        self.assertEqual(policy['review']['inputHashes'], policy['inputHashes'])
        self.assertEqual(sum(line.strip().startswith('"' + access_key + '":')
                             for line in (ROOT / policy_path).read_text().splitlines()), 2)

        predecessor = '23f6b7496ef9fa6398c05ebadedf5301c675683e'
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        self.assertEqual(subprocess.run(['git', 'merge-base', '--is-ancestor', predecessor, head],
                                        cwd=ROOT, check=False).returncode, 0)
        historical_policy = json.loads(subprocess.check_output(
            ['git', 'show', predecessor + ':' + policy_path], cwd=ROOT, text=True))
        historical_receipt = json.loads(subprocess.check_output(
            ['git', 'show', predecessor + ':' + receipt_path], cwd=ROOT, text=True))
        committed_receipt = json.loads(subprocess.check_output(
            ['git', 'show', head + ':' + receipt_path], cwd=ROOT, text=True))
        # The policy is intentionally a mutable active pointer. Later CON.09/10
        # successors must not make this historical CON.08 fixture compare the
        # whole current policy object with its predecessor snapshot.
        self.assertEqual(committed_receipt, receipt)
        old_access_digest = historical_policy['inputHashes'][access_key]
        current_access_digest = policy['inputHashes'][access_key]
        con08_access_digest = receipt['review']['inputHashes'][access_key]
        con10_r1_receipt = json.loads(
            (ROOT / 'eng/policy/dependency-reviews/con-10-r1.json').read_text(encoding='utf-8'))
        con10_r1_access_digest = con10_r1_receipt['review']['inputHashes'][access_key]
        self.assertEqual(old_access_digest, historical_policy['review']['inputHashes'][access_key])
        self.assertEqual(old_access_digest, historical_receipt['review']['inputHashes'][access_key])
        self.assertNotEqual(old_access_digest, con08_access_digest)
        self.assertNotEqual(con08_access_digest, current_access_digest)

        ext02_group = next(row for row in config['allowlists']
                           if row['description'] == 'Reviewed EXT.02 exact public dependency-input hashes' and
                           row['paths'] == [r'^eng/policy/dependency-policy\.json$'])
        con09_policy_group = next(row for row in config['allowlists']
                                  if row['description'].startswith('CON09 exact observed active dependency-policy') and
                                  row['paths'] == [r'^eng/policy/dependency\-policy\.json$'])
        con10_policy_group = next(row for row in config['allowlists']
                                  if row['description'].startswith('CON10 exact observed active dependency-policy') and
                                  row['paths'] == [r'^eng/policy/dependency\-policy\.json$'])
        active_access_line = f'  "{access_key}": "{current_access_digest}",'
        historical_con10_line = f'  "{access_key}": "{con10_r1_access_digest}",'
        self.assertFalse(any(re.fullmatch(pattern, active_access_line) for pattern in ext02_group['regexes']))
        self.assertFalse(any(re.fullmatch(pattern, active_access_line) for pattern in con09_policy_group['regexes']))
        self.assertTrue(any(re.fullmatch(pattern, historical_con10_line)
                            for pattern in con10_policy_group['regexes']))
        self.assertFalse(any(re.fullmatch(pattern, active_access_line)
                             for pattern in con10_policy_group['regexes']))
        self.assertFalse(any(re.fullmatch(pattern, active_access_line)
                             for pattern in by_path['^' + re.escape(policy_path) + '$']['regexes']))

        receipt_keys = [
            'eng/policy/contract-access.json',
            'eng/provenance/records/dokka-combokeys-licence-r1.json',
            'eng/provenance/records/dokka-object-keys-licence-r1.json',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
        ]
        r13_pages = profile['modules']['contracts-proto']['pages']
        omitted_page = 'contracts-proto/io.github.arcforges.contracts.foundation.v1/-action-descriptor/-builder/get-description-key.html'
        dokka_rows = [(key, value) for key, value in sorted(r13_pages.items())
                      if re.search(r'(key|token)', key, re.IGNORECASE) and key != omitted_page]
        self.assertEqual(len(dokka_rows), 197)

        expected_rows = {
            policy_path: [(access_key, old_access_digest), (access_key, con08_access_digest)],
            receipt_path: [(access_key, old_access_digest),
                           (access_key, con08_access_digest)] +
                          [(key, receipt['review']['inputHashes'][key])
                           for key in receipt_keys[1:]],
            dokka_path: dokka_rows,
        }
        self.assertEqual(set(by_path), {'^' + re.escape(path) + '$' for path in expected_rows})
        for path, rows in expected_rows.items():
            group = by_path['^' + re.escape(path) + '$']
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], ['^' + re.escape(path) + '$'])
            unique_rows = sorted(set(rows))
            expected = [r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                        for key, digest in unique_rows]
            self.assertEqual(group['regexes'], expected)
            for (key, digest), pattern in zip(unique_rows, group['regexes'], strict=True):
                line = f'  "{key}": "{digest}",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for bad in [line.replace(digest, '0' * 64),
                            line.replace('"' + key + '"', '"api_key"'),
                            line.replace('"' + key + '"', '"api_token"'),
                            line + ' "credential": "synthetic-secret"']:
                    self.assertIsNone(re.fullmatch(pattern, bad))
            for wrong_path in [path + '.backup', 'src/secrets.json']:
                self.assertIsNone(re.fullmatch(group['paths'][0], wrong_path))

        omitted_line = f'  "{omitted_page}": "{r13_pages[omitted_page]}",'
        self.assertFalse(any(re.fullmatch(pattern, omitted_line)
                             for pattern in by_path['^' + re.escape(dokka_path) + '$']['regexes']))

    def test_con09_secret_scan_allowlists_bind_only_observed_public_digest_lines(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        groups = [row for row in config['allowlists']
                  if row['description'].startswith('CON09 exact observed')]
        self.assertEqual(len(groups), 3)
        by_path = {row['paths'][0]: row for row in groups}

        docs_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r14.json'
        receipt_path = 'eng/policy/dependency-reviews/con-09-r1.json'
        policy_path = 'eng/policy/dependency-policy.json'
        path_patterns = {path: '^' + re.escape(path) + '$'
                         for path in [docs_path, receipt_path, policy_path]}
        self.assertEqual(set(by_path), set(path_patterns.values()))

        observed_intro = '14aa5d0a24e9fd5e622f2104599e9f70dd3e9b96'
        observed_head = '48455ec708f66846581102395502b2425edd32ed'
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        for ancestor in [observed_intro, observed_head]:
            self.assertEqual(subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, head],
                                            cwd=ROOT, check=False).returncode, 0)

        def committed_json(commit, path):
            return json.loads(subprocess.check_output(['git', 'show', commit + ':' + path],
                                                      cwd=ROOT, text=True))

        initial_profile = committed_json(observed_intro, docs_path)
        current_profile = committed_json(head, docs_path)
        pages = initial_profile['modules']['contracts-proto']['pages']
        current_pages = current_profile['modules']['contracts-proto']['pages']
        omitted_page = ('contracts-proto/io.github.arcforges.contracts.foundation.v1/'
                        '-action-descriptor/-builder/get-description-key.html')
        docs_rows = {(key, digest) for key, digest in pages.items()
                     if re.search(r'(key|token)', key, re.IGNORECASE) and key != omitted_page}
        current_docs_rows = {(key, digest) for key, digest in current_pages.items()
                             if re.search(r'(key|token)', key, re.IGNORECASE) and key != omitted_page}
        digest_set_hash = lambda rows: hashlib.sha256(
            ''.join(key + '\t' + value + '\n' for key, value in sorted(rows)).encode()).hexdigest()
        self.assertEqual(len(docs_rows), 208)
        self.assertEqual(current_docs_rows, docs_rows)
        self.assertEqual(digest_set_hash(docs_rows),
                         'd6c8ba4e9904aee40edbcaf5cc388ee6cfc1a19a65477ba68f5fa72295f72b4e')

        receipt_keys = [
            'eng/policy/contract-access.json',
            'eng/provenance/records/dokka-combokeys-licence-r1.json',
            'eng/provenance/records/dokka-object-keys-licence-r1.json',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
        ]
        initial_receipt = committed_json(observed_intro, receipt_path)['review']['inputHashes']
        observed_receipt = committed_json(observed_head, receipt_path)['review']['inputHashes']
        current_receipt = committed_json(head, receipt_path)['review']['inputHashes']
        self.assertEqual(committed_json(head, receipt_path), committed_json(observed_head, receipt_path))
        receipt_rows = {(key, initial_receipt[key]) for key in receipt_keys}
        receipt_rows |= {(key, observed_receipt[key]) for key in receipt_keys}
        self.assertEqual(len(receipt_rows), 5)
        self.assertEqual(digest_set_hash(receipt_rows),
                         '91299dfa0022fe0e7a57f19bc6d879bccfc0ae54293cc8ca69588a6664d44660')
        self.assertEqual(current_receipt, observed_receipt)

        access_key = 'eng/policy/contract-access.json'
        base_policy = committed_json('affeeae06e563340354698dd5e32d74891c96e78', policy_path)
        con09_policy = committed_json(observed_head, policy_path)
        current_policy = committed_json(head, policy_path)
        ext02_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/ext-02-r1.json')
                                   .read_text(encoding='utf-8'))
        old_access_digest = base_policy['inputHashes'][access_key]
        con09_access_digest = con09_policy['inputHashes'][access_key]
        current_access_digest = current_policy['inputHashes'][access_key]
        current_access_bytes = subprocess.check_output(
            ['git', 'show', head + ':' + access_key], cwd=ROOT)
        actual_current_access_digest = hashlib.sha256(current_access_bytes).hexdigest()
        self.assertEqual(old_access_digest,
                         ext02_receipt['review']['inputHashes'][access_key])
        self.assertEqual(con09_access_digest,
                         '86d2b588471d30595c5b1eeb8ea99e180f7cd42b52fb2452a5b6b476e529a533')
        self.assertEqual(current_access_digest, actual_current_access_digest)
        self.assertNotEqual(con09_access_digest, old_access_digest)
        self.assertNotEqual(current_access_digest, con09_access_digest)
        policy_rows = {(access_key, con09_access_digest)}
        self.assertEqual(digest_set_hash(policy_rows),
                         '9376bfc063d6056b2715a6da75899e4ef098f3e7ca916bc89b1c79a892a62e3a')
        expected_rows = {
            docs_path: docs_rows,
            receipt_path: receipt_rows,
            policy_path: policy_rows,
        }

        for path, rows in expected_rows.items():
            group = by_path[path_patterns[path]]
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path_patterns[path]])
            expected_patterns = [
                r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + value + r'",?\s*$'
                for key, value in sorted(rows)
            ]
            self.assertEqual(group['regexes'], expected_patterns)
            for (key, value), pattern in zip(sorted(rows), group['regexes'], strict=True):
                line = f'  "{key}": "{value}",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                wrong_digest = '0' * 64 if value != '0' * 64 else '1' * 64
                self.assertIsNone(re.fullmatch(pattern, line.replace(value, wrong_digest)))
                self.assertIsNone(re.fullmatch(pattern, line.replace('"' + key + '"', '"credential"')))
                self.assertIsNone(re.fullmatch(pattern, line + ' "credential": "synthetic-secret"'))
            for wrong_path in [path + '.backup', 'src/secrets.json']:
                self.assertIsNone(re.fullmatch(group['paths'][0], wrong_path))

        def matching_lines(text, group):
            return [line for line in text.splitlines()
                    if any(re.fullmatch(pattern, line) for pattern in group['regexes'])]

        docs_group = by_path[path_patterns[docs_path]]
        receipt_group = by_path[path_patterns[receipt_path]]
        policy_group = by_path[path_patterns[policy_path]]
        self.assertEqual(len(matching_lines(subprocess.check_output(
            ['git', 'show', observed_intro + ':' + docs_path], cwd=ROOT, text=True), docs_group)), 208)
        self.assertEqual(len(matching_lines(subprocess.check_output(
            ['git', 'show', head + ':' + docs_path], cwd=ROOT, text=True), docs_group)), 208)
        self.assertEqual(len(matching_lines(subprocess.check_output(
            ['git', 'show', observed_intro + ':' + receipt_path], cwd=ROOT, text=True), receipt_group)), 4)
        self.assertEqual(len(matching_lines(subprocess.check_output(
            ['git', 'show', head + ':' + receipt_path], cwd=ROOT, text=True), receipt_group)), 4)
        historical_policy_text = subprocess.check_output(
            ['git', 'show', 'affeeae06e563340354698dd5e32d74891c96e78:' + policy_path], cwd=ROOT, text=True)
        con09_policy_text = subprocess.check_output(
            ['git', 'show', observed_head + ':' + policy_path], cwd=ROOT, text=True)
        current_policy_text = subprocess.check_output(
            ['git', 'show', head + ':' + policy_path], cwd=ROOT, text=True)
        self.assertEqual(len(matching_lines(historical_policy_text, policy_group)), 0)
        self.assertEqual(len(matching_lines(con09_policy_text, policy_group)), 2)
        self.assertEqual(len(matching_lines(current_policy_text, policy_group)), 0)

        ext02_policy_group = next(row for row in config['allowlists']
                                  if row['description'] == 'Reviewed EXT.02 exact public dependency-input hashes' and
                                  row['paths'] == [r'^eng/policy/dependency-policy\.json$'])
        con08_policy_group = next(row for row in config['allowlists']
                                  if row['description'].startswith('CON08 exact observed') and
                                  row['paths'] == [path_patterns[policy_path]])
        con09_policy_group = next(row for row in config['allowlists']
                                  if row['description'].startswith('CON09 exact observed active dependency-policy') and
                                  row['paths'] == [path_patterns[policy_path]])
        old_line = f'  "{access_key}": "{old_access_digest}",'
        con09_line = f'  "{access_key}": "{con09_access_digest}",'
        current_line = f'  "{access_key}": "{current_access_digest}",'
        self.assertTrue(any(re.fullmatch(pattern, old_line) for pattern in ext02_policy_group['regexes']))
        self.assertFalse(any(re.fullmatch(pattern, current_line) for pattern in ext02_policy_group['regexes']))
        self.assertFalse(any(re.fullmatch(pattern, con09_line) for pattern in con08_policy_group['regexes']))
        self.assertTrue(any(re.fullmatch(pattern, con09_line) for pattern in con09_policy_group['regexes']))
        self.assertFalse(any(re.fullmatch(pattern, current_line) for pattern in con09_policy_group['regexes']))
        self.assertEqual(sum(len(rows) for rows in expected_rows.values()), 214)
        self.assertEqual(208 + 5 + 2, 215)

    def test_con10_secret_scan_allowlist_binds_r1_history_not_current_policy(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        policy_path = 'eng/policy/dependency-policy.json'
        access_key = 'eng/policy/contract-access.json'
        path_pattern = r'^eng/policy/dependency\-policy\.json$'
        r1_digest = '466e30f0c4f4e5cb426b9cd63c8c00a46b084d0f885ec54af774da3cd66c0615'
        con09_digest = '86d2b588471d30595c5b1eeb8ea99e180f7cd42b52fb2452a5b6b476e529a533'

        con09_group = next(row for row in config['allowlists']
                           if row['description'].startswith('CON09 exact observed active dependency-policy') and
                           row['paths'] == [path_pattern])
        con10_groups = [row for row in config['allowlists']
                        if row['description'] == 'CON10 exact observed active dependency-policy digest row']
        self.assertEqual(len(con10_groups), 1)
        con10_group = con10_groups[0]
        for group in [con09_group, con10_group]:
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path_pattern])
        old_pattern = r'(?s)^\s*"' + re.escape(access_key) + r'":\s*"' + con09_digest + r'",?\s*$'
        r1_pattern = r'(?s)^\s*"' + re.escape(access_key) + r'":\s*"' + r1_digest + r'",?\s*$'
        self.assertEqual(con09_group['regexes'], [old_pattern])
        self.assertEqual(con10_group['regexes'], [r1_pattern])

        predecessor = 'bf42fef5e4fd28792004c8a16623465784e2bfb7'
        previous_policy = json.loads(subprocess.check_output(
            ['git', 'show', predecessor + ':' + policy_path], cwd=ROOT, text=True))
        current_policy = json.loads((ROOT / policy_path).read_text(encoding='utf-8'))
        r1_source = 'b6f0bad2b2876544eda836741f574a61e8c44ea0'
        r1_policy_text = subprocess.check_output(
            ['git', 'show', r1_source + ':' + policy_path], cwd=ROOT, text=True)
        r1_policy = json.loads(r1_policy_text)
        r1_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/con-10-r1.json')
                                     .read_text(encoding='utf-8'))
        current_receipt = json.loads((ROOT / current_policy['reviewReceipt'])
                                     .read_text(encoding='utf-8'))
        current_digest = current_policy['inputHashes'][access_key]
        self.assertEqual(previous_policy['inputHashes'][access_key], con09_digest)
        self.assertEqual(previous_policy['review']['inputHashes'][access_key], con09_digest)
        self.assertEqual(current_policy['inputHashes'][access_key], current_digest)
        self.assertEqual(current_policy['review']['inputHashes'][access_key], current_digest)
        self.assertEqual(current_receipt['review']['inputHashes'][access_key], current_digest)
        self.assertEqual(r1_policy['inputHashes'][access_key], r1_digest)
        self.assertEqual(r1_policy['review']['inputHashes'][access_key], r1_digest)
        self.assertEqual(r1_receipt['review']['inputHashes'][access_key], r1_digest)
        self.assertEqual(hashlib.sha256((ROOT / access_key).read_bytes()).hexdigest(), current_digest)

        old_line = f'  "{access_key}": "{con09_digest}",'
        r1_line = f'  "{access_key}": "{r1_digest}",'
        current_line = f'  "{access_key}": "{current_digest}",'
        self.assertIsNotNone(re.fullmatch(old_pattern, old_line))
        self.assertIsNotNone(re.fullmatch(r1_pattern, r1_line))
        for group, pattern, allowed, rejected in [
            (con09_group, old_pattern, old_line, r1_line),
            (con10_group, r1_pattern, r1_line, old_line),
        ]:
            allowed_digest = con09_digest if group is con09_group else r1_digest
            self.assertTrue(any(re.fullmatch(candidate, allowed) for candidate in group['regexes']))
            self.assertFalse(any(re.fullmatch(candidate, rejected) for candidate in group['regexes']))
            for bad_line in [
                allowed.replace(allowed_digest, '0' * 64 if allowed_digest != '0' * 64 else '1' * 64),
                allowed.replace('"' + access_key + '"', '"credential"'),
                allowed + ' "credential": "synthetic-secret"',
            ]:
                self.assertFalse(any(re.fullmatch(candidate, bad_line) for candidate in group['regexes']))
            self.assertFalse(re.fullmatch(group['paths'][0], policy_path + '.backup'))
            self.assertFalse(re.fullmatch(group['paths'][0], 'src/secrets.json'))

        current_policy_text = (ROOT / policy_path).read_text(encoding='utf-8')
        current_matches = [line for line in current_policy_text.splitlines()
                           if any(re.fullmatch(pattern, line) for pattern in con10_group['regexes'])]
        self.assertEqual(len(current_matches), 0)
        r1_matches = [line for line in r1_policy_text.splitlines()
                      if any(re.fullmatch(pattern, line) for pattern in con10_group['regexes'])]
        self.assertEqual(len(r1_matches), 2)
        self.assertFalse(any(re.fullmatch(pattern, current_line) for pattern in con10_group['regexes']))

    def test_con10_secret_scan_allowlists_bind_exact_hosted_fingerprint_sets(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        docs_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r15.json'
        receipt_path = 'eng/policy/dependency-reviews/con-10-r1.json'
        docs_commit = '3be95f260dbee990c1e35a94c99122bfa96c539e'
        receipt_commit = '300105355db421cb74c186f72d2bcba97b03d896'
        docs_file_sha = '31c4b9a5d5fd2185680258ea649d03137d3d8cf48982d13737b72d8b6e29eeb8'
        receipt_file_sha = '638410d18b0dfe3a6f5c1eed0d125333ec6d5ea41112d16b1a2068507483b89b'
        docs_fingerprint_sha = 'a308bfa4defb2c696b800e3d4c9c0e5b5150e98ea3321065ca1717cfdd4dc68b'
        receipt_fingerprint_sha = '9270f889d976afc16b5727700cb376c142cd248e6abf15192cb23e47608dcca4'
        descriptions = [
            'CON10 exact observed r15 Dokka findings (Security run 36572854175)',
            'CON10 exact observed dependency-review findings (Security run 36572854175)',
        ]
        groups = [row for row in config['allowlists'] if row['description'] in descriptions]
        self.assertEqual(len(groups), 2)
        by_description = {row['description']: row for row in groups}
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()

        docs_excluded_candidates = {
            ('contracts-proto/io.github.arcforges.contracts.foundation.v1/'
             '-action-descriptor/-builder/get-description-key.html'),
            ('contracts-proto/io.github.arcforges.contracts.publicapi.v1/'
             '-automation-service-resolve-missed-request-kt/-dsl/-occurrence-keys-proxy/index.html'),
            ('contracts-proto/io.github.arcforges.contracts.publicapi.v1/'
             '-general-search-query/get-dataset-token-bytes.html'),
        }
        receipt_keys = {
            'eng/policy/contract-access.json',
            'eng/provenance/records/dokka-combokeys-licence-r1.json',
            'eng/provenance/records/dokka-object-keys-licence-r1.json',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
        }
        cases = [
            {
                'description': descriptions[0],
                'path': docs_path,
                'commit': docs_commit,
                'file_sha': docs_file_sha,
                'fingerprint_sha': docs_fingerprint_sha,
                'count': 273,
            },
            {
                'description': descriptions[1],
                'path': receipt_path,
                'commit': receipt_commit,
                'file_sha': receipt_file_sha,
                'fingerprint_sha': receipt_fingerprint_sha,
                'count': 4,
            },
        ]

        for case in cases:
            with self.subTest(path=case['path']):
                group = by_description[case['description']]
                path = case['path']
                source_commit = case['commit']
                path_pattern = '^' + re.escape(path) + '$'
                self.assertEqual(group['targetRules'], ['generic-api-key'])
                self.assertEqual(group['condition'], 'AND')
                self.assertEqual(group['regexTarget'], 'line')
                self.assertEqual(group['paths'], [path_pattern])
                self.assertEqual(
                    subprocess.run(['git', 'merge-base', '--is-ancestor', source_commit, head],
                                   cwd=ROOT, check=False).returncode,
                    0,
                )

                source_blob = subprocess.check_output(
                    ['git', 'show', source_commit + ':' + path], cwd=ROOT)
                self.assertEqual(hashlib.sha256(source_blob).hexdigest(), case['file_sha'])
                self.assertEqual((ROOT / path).read_bytes(), source_blob)
                source_text = source_blob.decode('utf-8')
                source_json = json.loads(source_text)
                if path == docs_path:
                    source_rows = source_json['modules']['contracts-proto']['pages']
                    candidates = {
                        (key, digest) for key, digest in source_rows.items()
                        if re.search(r'(key|token)', key, re.IGNORECASE)
                    }
                    self.assertEqual(len(candidates), 276)
                    self.assertEqual(
                        {key for key, _ in candidates} & docs_excluded_candidates,
                        docs_excluded_candidates,
                    )
                    expected_rows = {
                        (key, digest) for key, digest in candidates
                        if key not in docs_excluded_candidates
                    }
                else:
                    source_rows = source_json['review']['inputHashes']
                    self.assertTrue(receipt_keys.issubset(source_rows))
                    expected_rows = {(key, source_rows[key]) for key in receipt_keys}

                self.assertEqual(len(expected_rows), case['count'])
                ordered_rows = sorted(expected_rows)
                expected_patterns = [
                    r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                    for key, digest in ordered_rows
                ]
                self.assertEqual(group['regexes'], expected_patterns)

                matched_rows = []
                fingerprints = []
                for line_number, line in enumerate(source_text.splitlines(), start=1):
                    matches = [pattern for pattern in group['regexes'] if re.fullmatch(pattern, line)]
                    self.assertLessEqual(len(matches), 1)
                    if matches:
                        row = re.fullmatch(r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})"\s*,?\s*', line)
                        self.assertIsNotNone(row)
                        matched_rows.append((row.group(1), row.group(2)))
                        fingerprints.append(
                            f"{source_commit}:{path}:generic-api-key:{line_number}"
                        )
                self.assertEqual(set(matched_rows), expected_rows)
                self.assertEqual(len(matched_rows), case['count'])
                self.assertEqual(len(set(fingerprints)), case['count'])
                canonical_fingerprints = '\n'.join(sorted(set(fingerprints))) + '\n'
                self.assertEqual(
                    hashlib.sha256(canonical_fingerprints.encode('utf-8')).hexdigest(),
                    case['fingerprint_sha'],
                )

                for (key, digest), pattern in zip(ordered_rows, group['regexes'], strict=True):
                    line = f'  "{key}": "{digest}",'
                    self.assertIsNotNone(re.fullmatch(pattern, line))
                    wrong_digest = '0' * 64 if digest != '0' * 64 else '1' * 64
                    for rejected_line in [
                        line.replace(digest, wrong_digest),
                        line.replace('"' + key + '"', '"credential"'),
                        line + ' "credential": "synthetic-secret"',
                    ]:
                        self.assertIsNone(re.fullmatch(pattern, rejected_line))
                self.assertIsNone(re.fullmatch(group['paths'][0], path + '.backup'))
                self.assertIsNone(re.fullmatch(group['paths'][0], 'src/secrets.json'))

    def test_con10_r2_allowlists_bind_exact_observed_historical_fingerprints(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        source_commit = '27ae79d9d8536b0467092ba9213d8cff596c62ad'
        cases = [
            {
                'description': 'CON10 exact observed r2 dependency-policy findings (Security run 36593612384)',
                'path': 'eng/policy/dependency-policy.json',
                'file_sha': 'fd00ef19559e9cf7d0471b0b155ab80a729dba6407b1f43e81c4b289211c41f0',
                'fingerprint_sha': 'bc30c71e0ccc4eeef7bc5e6dee0dd9c3c447bf9d8e4233cd1321a21c9f0190e6',
                'count': 2,
                'rows': {
                    'eng/policy/contract-access.json':
                        '06f5b1673ad4663796667bc198ce9336b71b11b0d50553f32ff29614f010cd17',
                },
            },
            {
                'description': 'CON10 exact observed r2 dependency-review findings (Security run 36593612384)',
                'path': 'eng/policy/dependency-reviews/con-10-r2.json',
                'file_sha': '32bbf7edec831f06e8d645f8c05dd9f7429f03ca23fa9637dee208bf3478e993',
                'fingerprint_sha': '1cd604920361e339d85318d0dfa22028b9339840a4a1f83124a16883a5dd0822',
                'count': 4,
                'rows': {
                    'eng/policy/contract-access.json':
                        '06f5b1673ad4663796667bc198ce9336b71b11b0d50553f32ff29614f010cd17',
                    'eng/provenance/records/dokka-combokeys-licence-r1.json':
                        '75219d61672002f0bb242fed0fd93a0886f07d944e0b9e1b1f72132f59df1b41',
                    'eng/provenance/records/dokka-object-keys-licence-r1.json':
                        '55621ecc7032745ca46e56d13133dc22a3bd808d80966d737427b5d6fc5bd096',
                    'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj':
                        '986b7a97734cd5d0630e548da897869de322a112c087c2d0df6a0bfc98b8784c',
                },
            },
        ]
        rows = [row for row in config['allowlists']
                if row['description'].startswith('CON10 exact observed r2 ')]
        self.assertEqual(len(rows), 2)
        by_description = {row['description']: row for row in rows}
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        self.assertEqual(
            subprocess.run(['git', 'merge-base', '--is-ancestor', source_commit, head],
                           cwd=ROOT, check=False).returncode,
            0,
        )

        for case in cases:
            with self.subTest(path=case['path']):
                group = by_description[case['description']]
                path = case['path']
                self.assertEqual(group['targetRules'], ['generic-api-key'])
                self.assertEqual(group['condition'], 'AND')
                self.assertEqual(group['regexTarget'], 'line')
                self.assertEqual(group['paths'], ['^' + re.escape(path) + '$'])

                source_blob = subprocess.check_output(
                    ['git', 'show', source_commit + ':' + path], cwd=ROOT)
                self.assertEqual(hashlib.sha256(source_blob).hexdigest(), case['file_sha'])
                source_text = source_blob.decode('utf-8')
                expected_rows = set(case['rows'].items())
                expected_patterns = [
                    r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                    for key, digest in sorted(expected_rows)
                ]
                self.assertEqual(group['regexes'], expected_patterns)

                matched_rows = []
                fingerprints = []
                for line_number, line in enumerate(source_text.splitlines(), start=1):
                    matches = [pattern for pattern in group['regexes'] if re.fullmatch(pattern, line)]
                    self.assertLessEqual(len(matches), 1)
                    if matches:
                        row = re.fullmatch(r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})"\s*,?\s*', line)
                        self.assertIsNotNone(row)
                        matched_rows.append((row.group(1), row.group(2)))
                        fingerprints.append(
                            f'{source_commit}:{path}:generic-api-key:{line_number}')
                self.assertEqual(set(matched_rows), expected_rows)
                self.assertEqual(len(matched_rows), case['count'])
                canonical = '\n'.join(sorted(set(fingerprints))) + '\n'
                self.assertEqual(
                    hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
                    case['fingerprint_sha'],
                )

                for (key, digest), pattern in zip(sorted(expected_rows), group['regexes'], strict=True):
                    line = f'  "{key}": "{digest}",'
                    self.assertIsNotNone(re.fullmatch(pattern, line))
                    wrong_digest = '0' * 64 if digest != '0' * 64 else '1' * 64
                    for rejected_line in [
                        line.replace(digest, wrong_digest),
                        line.replace('"' + key + '"', '"unrelated-key"'),
                        line + ' "synthetic-secret": "redacted"',
                    ]:
                        self.assertIsNone(re.fullmatch(pattern, rejected_line))
                self.assertIsNone(re.fullmatch(group['paths'][0], path + '.backup'))
                self.assertIsNone(re.fullmatch(group['paths'][0], 'src/secrets.json'))

    def test_con10_r3_allowlists_bind_exact_observed_historical_fingerprints(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        source_commit = 'd849aedf31cd1cf6a23f8421634e9ce52d35471a'
        cases = [
            {
                'description': 'CON10 exact observed r3 dependency-policy findings (Security run 36604131513)',
                'path': 'eng/policy/dependency-policy.json',
                'file_sha': '1ae59af258c6362ed809a6cd8479f878d7169b013870b316ee2cd93f839be296',
                'fingerprint_sha': '1f0e3209bdb0598591ac6777d9b644464f2d1ae40cacbc6dfa4043e4f7a39e85',
                'count': 2,
                'rows': {
                    'eng/policy/contract-access.json':
                        '02cee466238c9827849dc43788ccbb93736ec1268003936154939399eac4e127',
                },
            },
            {
                'description': 'CON10 exact observed r3 dependency-review findings (Security run 36604131513)',
                'path': 'eng/policy/dependency-reviews/con-10-r3.json',
                'file_sha': '890fefb85962202b2abc476d7b458c768ee88ec7cd4a48c6fb9d35d6b52b8267',
                'fingerprint_sha': 'a6025c646a5fca7910b4d4f980c13492938ddd1202609200ec38414863c6c3e7',
                'count': 4,
                'rows': {
                    'eng/policy/contract-access.json':
                        '02cee466238c9827849dc43788ccbb93736ec1268003936154939399eac4e127',
                    'eng/provenance/records/dokka-combokeys-licence-r1.json':
                        '75219d61672002f0bb242fed0fd93a0886f07d944e0b9e1b1f72132f59df1b41',
                    'eng/provenance/records/dokka-object-keys-licence-r1.json':
                        '55621ecc7032745ca46e56d13133dc22a3bd808d80966d737427b5d6fc5bd096',
                    'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj':
                        '986b7a97734cd5d0630e548da897869de322a112c087c2d0df6a0bfc98b8784c',
                },
            },
        ]
        rows = [row for row in config['allowlists']
                if row['description'].startswith('CON10 exact observed r3 ')]
        self.assertEqual(len(rows), 2)
        by_description = {row['description']: row for row in rows}
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        self.assertEqual(
            subprocess.run(['git', 'merge-base', '--is-ancestor', source_commit, head],
                           cwd=ROOT, check=False).returncode,
            0,
        )

        for case in cases:
            with self.subTest(path=case['path']):
                group = by_description[case['description']]
                path = case['path']
                self.assertEqual(group['targetRules'], ['generic-api-key'])
                self.assertEqual(group['condition'], 'AND')
                self.assertEqual(group['regexTarget'], 'line')
                self.assertEqual(group['paths'], ['^' + re.escape(path) + '$'])

                source_blob = subprocess.check_output(
                    ['git', 'show', source_commit + ':' + path], cwd=ROOT)
                self.assertEqual(hashlib.sha256(source_blob).hexdigest(), case['file_sha'])
                source_text = source_blob.decode('utf-8')
                expected_rows = set(case['rows'].items())
                expected_patterns = [
                    r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                    for key, digest in sorted(expected_rows)
                ]
                self.assertEqual(group['regexes'], expected_patterns)

                matched_rows = []
                fingerprints = []
                for line_number, line in enumerate(source_text.splitlines(), start=1):
                    matches = [pattern for pattern in group['regexes'] if re.fullmatch(pattern, line)]
                    self.assertLessEqual(len(matches), 1)
                    if matches:
                        row = re.fullmatch(r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})"\s*,?\s*', line)
                        self.assertIsNotNone(row)
                        matched_rows.append((row.group(1), row.group(2)))
                        fingerprints.append(
                            f'{source_commit}:{path}:generic-api-key:{line_number}')
                self.assertEqual(set(matched_rows), expected_rows)
                self.assertEqual(len(matched_rows), case['count'])
                canonical = '\n'.join(sorted(set(fingerprints))) + '\n'
                self.assertEqual(
                    hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
                    case['fingerprint_sha'],
                )

                for (key, digest), pattern in zip(sorted(expected_rows), group['regexes'], strict=True):
                    line = f'  "{key}": "{digest}",'
                    self.assertIsNotNone(re.fullmatch(pattern, line))
                    wrong_digest = '0' * 64 if digest != '0' * 64 else '1' * 64
                    for rejected_line in [
                        line.replace(digest, wrong_digest),
                        line.replace('"' + key + '"', '"unrelated-key"'),
                        line + ' "synthetic-secret": "redacted"',
                    ]:
                        self.assertIsNone(re.fullmatch(pattern, rejected_line))
                self.assertIsNone(re.fullmatch(group['paths'][0], path + '.backup'))
                self.assertIsNone(re.fullmatch(group['paths'][0], 'src/secrets.json'))

    def test_con22_allowlists_bind_only_observed_public_digest_lines(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        descriptions = {
            'CON22 exact observed dependency-policy findings (Security run 36667240142)',
            'CON22 exact observed dependency-review findings (Security run 36667240142)',
            'CON22 exact observed r16 documentation findings (Security run 36667240142)',
        }
        groups = [row for row in config['allowlists']
                  if row['description'].startswith('CON22 exact observed')]
        self.assertEqual({row['description'] for row in groups}, descriptions)
        self.assertEqual(len(groups), 3)
        by_description = {row['description']: row for row in groups}

        historical_commit = '727f9957773c3ae01ab849ebdeaae3f3ef174b09'
        accepted_con22_commit = '9577ab67fb631a37a73b1b7e8d087714f6292e8a'
        con21_snapshot_commit = '1d17838dd6bb30f89ffbfb9a26ce311f6c742d34'
        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-22-r1.json'
        current_con21_receipt_path = 'eng/policy/dependency-reviews/con-21-r1.json'
        profile_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r16.json'
        access_key = 'eng/policy/contract-access.json'

        def git_blob(commit, path):
            if (commit, path) in HISTORICAL_BLOBS:
                return frozen_git_blob(commit, path)
            return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)

        old_policy = json.loads(git_blob(historical_commit, policy_path))
        accepted_con22_policy = json.loads(git_blob(accepted_con22_commit, policy_path))
        con21_snapshot_policy_bytes = git_blob(con21_snapshot_commit, policy_path)
        con21_snapshot_policy = json.loads(con21_snapshot_policy_bytes)
        con21_snapshot_receipt_bytes = git_blob(con21_snapshot_commit, current_con21_receipt_path)
        con21_snapshot_receipt = json.loads(con21_snapshot_receipt_bytes)
        old_access = old_policy['inputHashes'][access_key]
        accepted_con22_access = accepted_con22_policy['inputHashes'][access_key]
        old_access_bytes = git_blob(historical_commit, access_key)
        accepted_con22_access_bytes = git_blob(accepted_con22_commit, access_key)
        con21_snapshot_access_bytes = git_blob(con21_snapshot_commit, access_key)
        current_con21_access = hashlib.sha256(con21_snapshot_access_bytes).hexdigest()
        self.assertEqual(old_access, hashlib.sha256(old_access_bytes).hexdigest())
        self.assertEqual(accepted_con22_access, hashlib.sha256(accepted_con22_access_bytes).hexdigest())
        accepted_con22_receipt = json.loads(git_blob(accepted_con22_commit, receipt_path))
        self.assertEqual(
            accepted_con22_receipt['review']['inputHashes'][access_key], accepted_con22_access)
        self.assertEqual(con21_snapshot_policy['inputHashes'][access_key], current_con21_access)
        self.assertEqual(
            con21_snapshot_policy['review']['inputHashes'][access_key], current_con21_access)
        self.assertEqual(
            con21_snapshot_receipt['review']['inputHashes'][access_key], current_con21_access)
        self.assertEqual(subprocess.run(
            ['git', 'merge-base', '--is-ancestor', con21_snapshot_commit,
             subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()],
            cwd=ROOT, check=False).returncode, 0)
        self.assertNotIn(current_con21_access, {old_access, accepted_con22_access})
        fixed_receipt_rows = {
            ('eng/provenance/records/dokka-combokeys-licence-r1.json',
             '75219d61672002f0bb242fed0fd93a0886f07d944e0b9e1b1f72132f59df1b41'),
            ('eng/provenance/records/dokka-object-keys-licence-r1.json',
             '55621ecc7032745ca46e56d13133dc22a3bd808d80966d737427b5d6fc5bd096'),
            ('src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
             '986b7a97734cd5d0630e548da897869de322a112c087c2d0df6a0bfc98b8784c'),
        }

        expected_rows = {
            'CON22 exact observed dependency-policy findings (Security run 36667240142)':
                [(('eng/policy/contract-access.json', old_access)),
                 (('eng/policy/contract-access.json', accepted_con22_access))],
            'CON22 exact observed dependency-review findings (Security run 36667240142)':
                [(('eng/policy/contract-access.json', old_access)),
                 (('eng/policy/contract-access.json', accepted_con22_access)),
                 *sorted(fixed_receipt_rows)],
        }

        for description, rows in expected_rows.items():
            with self.subTest(description=description):
                group = by_description[description]
                path = policy_path if 'dependency-policy' in description else receipt_path
                self.assertEqual(group['targetRules'], ['generic-api-key'])
                self.assertEqual(group['condition'], 'AND')
                self.assertEqual(group['regexTarget'], 'line')
                self.assertEqual(group['paths'], ['^' + re.escape(path) + '$'])
                expected_patterns = [
                    r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                    for key, digest in rows
                ]
                self.assertEqual(group['regexes'], expected_patterns)
                self.assertEqual(len(group['regexes']), len(set(group['regexes'])))
                for (key, digest), pattern in zip(rows, group['regexes'], strict=True):
                    line = f'  "{key}": "{digest}",'
                    self.assertIsNotNone(re.fullmatch(pattern, line))
                    wrong_digest = '0' * 64 if digest != '0' * 64 else '1' * 64
                    for rejected_line in [
                        line.replace(digest, wrong_digest),
                        line.replace('"' + key + '"', '"unrelated-key"'),
                        line + ' "synthetic-secret": "redacted"',
                    ]:
                        self.assertIsNone(re.fullmatch(pattern, rejected_line))
                self.assertIsNone(re.fullmatch(group['paths'][0], path + '.backup'))
                self.assertIsNone(re.fullmatch(group['paths'][0], 'src/secrets.json'))

        def matched_rows(blob, patterns):
            result = []
            for line_number, line in enumerate(blob.decode('utf-8').splitlines(), start=1):
                matches = [pattern for pattern in patterns if re.fullmatch(pattern, line)]
                self.assertLessEqual(len(matches), 1)
                if matches:
                    parsed = re.fullmatch(r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})",?\s*', line)
                    self.assertIsNotNone(parsed)
                    result.append((line_number, parsed.group(1), parsed.group(2)))
            return result

        policy_group = by_description[
            'CON22 exact observed dependency-policy findings (Security run 36667240142)']
        receipt_group = by_description[
            'CON22 exact observed dependency-review findings (Security run 36667240142)']
        old_policy = git_blob(historical_commit, policy_path)
        accepted_con22_policy = git_blob(accepted_con22_commit, policy_path)
        current_con21_policy = con21_snapshot_policy_bytes
        old_receipt = git_blob(historical_commit, receipt_path)
        accepted_con22_receipt = git_blob(accepted_con22_commit, receipt_path)
        current_con21_receipt = con21_snapshot_receipt_bytes
        old_policy_hits = matched_rows(old_policy, policy_group['regexes'])
        accepted_con22_policy_hits = matched_rows(accepted_con22_policy, policy_group['regexes'])
        current_con21_policy_hits = matched_rows(current_con21_policy, policy_group['regexes'])
        old_receipt_hits = matched_rows(old_receipt, receipt_group['regexes'])
        accepted_con22_receipt_hits = matched_rows(accepted_con22_receipt, receipt_group['regexes'])
        current_con21_receipt_hits = matched_rows(current_con21_receipt, receipt_group['regexes'])
        self.assertEqual(len(old_policy_hits), 2)
        self.assertEqual({row[2] for row in old_policy_hits}, {old_access})
        self.assertEqual(len(accepted_con22_policy_hits), 2)
        self.assertEqual({row[2] for row in accepted_con22_policy_hits}, {accepted_con22_access})
        self.assertEqual(current_con21_policy_hits, [])
        current_con21_receipt_access_lines = [
            line for line in current_con21_receipt.decode('utf-8').splitlines()
            if re.fullmatch(r'\s*"' + re.escape(access_key) + r'"\s*:\s*"[0-9a-f]{64}",?\s*', line)
        ]
        self.assertEqual(len(current_con21_receipt_access_lines), 1)
        self.assertIn(current_con21_access, current_con21_receipt_access_lines[0])
        self.assertTrue(all(re.fullmatch(pattern, current_con21_receipt_access_lines[0]) is None
                            for pattern in receipt_group['regexes']))
        self.assertIsNone(re.fullmatch(receipt_group['paths'][0], current_con21_receipt_path))
        current_con21_receipt_pairs = {(row[1], row[2]) for row in current_con21_receipt_hits}
        self.assertTrue(current_con21_receipt_pairs <= fixed_receipt_rows)
        old_policy_pairs = {(row[1], row[2]) for row in old_policy_hits}
        accepted_con22_policy_pairs = {(row[1], row[2]) for row in accepted_con22_policy_hits}
        self.assertEqual(old_policy_pairs - accepted_con22_policy_pairs,
                         {('eng/policy/contract-access.json', old_access)})
        self.assertEqual(accepted_con22_policy_pairs - old_policy_pairs,
                         {('eng/policy/contract-access.json', accepted_con22_access)})
        self.assertEqual(len(old_receipt_hits), 4)
        self.assertEqual({(row[1], row[2]) for row in old_receipt_hits},
                         {('eng/policy/contract-access.json', old_access), *fixed_receipt_rows})
        self.assertEqual(len(accepted_con22_receipt_hits), 4)
        self.assertEqual({(row[1], row[2]) for row in accepted_con22_receipt_hits},
                         {('eng/policy/contract-access.json', accepted_con22_access), *fixed_receipt_rows})
        old_receipt_pairs = {(row[1], row[2]) for row in old_receipt_hits}
        accepted_con22_receipt_pairs = {(row[1], row[2]) for row in accepted_con22_receipt_hits}
        self.assertEqual(old_receipt_pairs - accepted_con22_receipt_pairs,
                         {('eng/policy/contract-access.json', old_access)})
        self.assertEqual(accepted_con22_receipt_pairs - old_receipt_pairs,
                         {('eng/policy/contract-access.json', accepted_con22_access)})
        self.assertEqual(len(set(policy_group['regexes'])), 2)
        self.assertEqual(len(set(receipt_group['regexes'])), 5)

        profile_group = by_description[
            'CON22 exact observed r16 documentation findings (Security run 36667240142)']
        self.assertEqual(profile_group['targetRules'], ['generic-api-key'])
        self.assertEqual(profile_group['condition'], 'AND')
        self.assertEqual(profile_group['regexTarget'], 'line')
        self.assertEqual(profile_group['paths'], ['^' + re.escape(profile_path) + '$'])
        self.assertEqual(len(profile_group['regexes']), 315)
        self.assertEqual(len(set(profile_group['regexes'])), 315)
        old_profile = git_blob(historical_commit, profile_path)
        current_profile = (ROOT / profile_path).read_bytes()
        self.assertEqual(old_profile, current_profile)
        self.assertEqual(
            HISTORICAL_BLOBS[(historical_commit, profile_path)][0],
            'c1142d009c5d0bda6eb195b7f1f2121e55897a2c',
        )
        self.assertEqual(
            subprocess.check_output(['git', 'rev-parse', f'HEAD:{profile_path}'],
                                    cwd=ROOT, text=True).strip(),
            'c1142d009c5d0bda6eb195b7f1f2121e55897a2c',
        )
        profile_hits = matched_rows(old_profile, profile_group['regexes'])
        self.assertEqual(len(profile_hits), 315)
        self.assertEqual(sum(key.endswith('.html') for _, key, _ in profile_hits), 308)
        self.assertEqual(sum(key.endswith(('.java', '.kt')) for _, key, _ in profile_hits), 7)
        for _, key, digest in profile_hits:
            line = f'  "{key}": "{digest}",'
            pattern = next(pattern for pattern in profile_group['regexes']
                           if re.fullmatch(pattern, line))
            self.assertIsNotNone(re.fullmatch(pattern, line))
            wrong_digest = '0' * 64 if digest != '0' * 64 else '1' * 64
            for rejected_line in [
                line.replace(digest, wrong_digest),
                line.replace('"' + key + '"', '"unrelated-key"'),
                line + ' "synthetic-secret": "redacted"',
            ]:
                self.assertIsNone(re.fullmatch(pattern, rejected_line))
        self.assertIsNone(re.fullmatch(profile_group['paths'][0], profile_path + '.backup'))
        self.assertIsNone(re.fullmatch(profile_group['paths'][0], 'eng/secrets.json'))
        profile_fingerprints = [
            f'{historical_commit}:{profile_path}:generic-api-key:{line_number}'
            for line_number, _, _ in profile_hits
        ]
        canonical = '\n'.join(sorted(set(profile_fingerprints))) + '\n'
        self.assertEqual(
            hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
            'ffd73090672c7f27600ac8e3385629b165c8c62fec7f498db61791c78dc0efd6',
        )
        self.assertEqual(2 + 4 + 315, 321)
        self.assertEqual(2 + 1, 3)
        self.assertEqual(321 + 3, 324)

    def test_con21_secret_scan_allowlists_bind_only_observed_public_digest_tuples(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        expected_descriptions = {
            'Observed CON.21 dependency-policy exact tuples',
            'Observed CON.21 con-21-r1 receipt exact tuples',
            'Observed CON.21 Dokka r17 profile exact tuples',
        }
        groups = [row for row in config['allowlists']
                  if row['description'] in expected_descriptions]
        self.assertEqual({row['description'] for row in groups}, expected_descriptions)
        self.assertEqual(len(groups), 3)
        by_description = {row['description']: row for row in groups}

        historical_commit = 'a0c945131855601b2ef229f3ac0661f00d96526d'
        diagnostic_commit = 'cf532b47c482d6444ae9f18a0edb3924c9bbbf79'
        observed_commits = [historical_commit, diagnostic_commit]
        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-21-r1.json'
        profile_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r17.json'
        access_key = 'eng/policy/contract-access.json'
        receipt_keys = {
            access_key,
            'eng/provenance/records/dokka-combokeys-licence-r1.json',
            'eng/provenance/records/dokka-object-keys-licence-r1.json',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
        }

        def git_blob(commit, path):
            if (commit, path) in HISTORICAL_BLOBS:
                return frozen_git_blob(commit, path)
            return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)

        policy_rows = set()
        receipt_rows = set()
        for commit in observed_commits:
            policy = json.loads(git_blob(commit, policy_path))
            access_digest = policy['inputHashes'][access_key]
            self.assertEqual(access_digest,
                             hashlib.sha256(git_blob(commit, access_key)).hexdigest())
            policy_rows.add((access_key, access_digest))

            receipt = json.loads(git_blob(commit, receipt_path))
            receipt_hashes = receipt['review']['inputHashes']
            for key in receipt_keys:
                digest = receipt_hashes[key]
                self.assertEqual(digest, hashlib.sha256(git_blob(commit, key)).hexdigest())
                receipt_rows.add((key, digest))
            self.assertEqual(receipt_hashes[access_key], access_digest)

        self.assertEqual(len(policy_rows), 2)
        self.assertEqual(len(receipt_rows), 5)

        profile_blob = git_blob(historical_commit, profile_path)
        self.assertEqual(profile_blob, git_blob(diagnostic_commit, profile_path))
        profile_document = json.loads(profile_blob)
        profile_maps = [module['pages'] for module in profile_document['modules'].values()]
        profile_maps.append(profile_document['inputs'])
        reported_line_ranges = '''
            982,984,986-987,1650-1652,3724-3726,3728,3730-3732,3734,3737,
            3749-3754,3756-3758,3771-3773,3784,3786-3789,3791-3793,3799-3804,
            3820-3825,3827-3829,4008,4022,4025,4037-4038,4045,4053,4063-4064,
            4071,4085-4086,4104-4105,4112,4496,4525,4537,4575-4576,4611,4645,
            4676-4677,4712,4744-4745,4804-4805,4840,5223,5225,5228,5231-5232,
            5235,5238,5240-5241,5244,5247-5248,5254-5255,5258,5333,5342,5347,
            5356-5357,5363,5371,5379-5380,5386,5397-5398,5412-5413,5419,
            10156,10164-10167,10173-10175,10179,10184-10187,10198,10207-10210,
            11415,11425,11432-11433,11443,11449-11450,11463-11464,11475-11476,
            18782,18786,18790,18794,18796,18801,18804-18805,18811-18812,18814,
            18818,18821,18825,18827-18828,18834-18835,18837,18841,18846-18847,
            18853-18854,18863-18864,18870-18871,18873,18877,18975,18978,18982,
            18985,18987,18992,19000-19001,19004-19005,19007,19010,19018,19021,
            19028-19029,19032-19033,19035,19038,19043-19044,19047-19048,
            19061-19062,19065-19066,19068,19071,22398,22403,22406,22423-22424,
            22442,22457,22466-22467,22485,22497-22498,22518,22541,24090-24092,
            24094,24096-24097,24099,24102,24105,24108-24109,24111,24114-24115,
            24117,24120-24121,24123,24125-24126,24128,24131-24132,24134,
            24138-24139,24141,24149,24151,24153,24156-24157,24159,24174,24176,
            24179,24181,24183,24187,24197,24200,24204,24206,24215,24217,24224,
            24227,24231,24233,24239,24242,24255,24259,24263,24265,24572,24576,
            24583,24589-24590,24594,24599,24604-24605,24609,24617-24618,
            24628-24629,24633,24862,24872,24878,24890-24891,24899,24907,24916-24917,
            24925,24938-24939,24957-24958,24966,27176,27182,27188,27198,27205,
            27213,27220,27227,27235,27249,27257,38279-38281,48746,48752
        '''
        reported_line_numbers = set()
        profile_lines = profile_blob.decode('utf-8').splitlines()
        for item in reported_line_ranges.split(','):
            bounds = [int(value) for value in item.strip().split('-')]
            self.assertIn(len(bounds), [1, 2])
            first = bounds[0]
            last = bounds[-1]
            self.assertLessEqual(first, last)
            selected = set(range(first, last + 1))
            self.assertFalse(reported_line_numbers & selected)
            reported_line_numbers.update(selected)
        self.assertEqual(len(reported_line_numbers), 315)

        profile_rows = set()
        for line_number in sorted(reported_line_numbers):
            line = profile_lines[line_number - 1]
            parsed = re.fullmatch(r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})",?\s*', line)
            self.assertIsNotNone(parsed)
            key, digest = parsed.groups()
            profile_values = [mapping[key] for mapping in profile_maps if key in mapping]
            self.assertEqual(profile_values, [digest])
            profile_rows.add((key, digest))
        self.assertEqual(len(profile_rows), 315)
        self.assertEqual(sum(key.endswith('.html') for key, _ in profile_rows), 308)
        self.assertEqual(sum(key.endswith(('.java', '.kt')) for key, _ in profile_rows), 7)

        expected_rows = {
            'Observed CON.21 dependency-policy exact tuples':
                (policy_path, policy_rows),
            'Observed CON.21 con-21-r1 receipt exact tuples':
                (receipt_path, receipt_rows),
            'Observed CON.21 Dokka r17 profile exact tuples':
                (profile_path, profile_rows),
        }
        self.assertEqual(len(policy_rows) + len(receipt_rows) + len(profile_rows), 322)
        for description, (outer_path, rows) in expected_rows.items():
            with self.subTest(description=description):
                group = by_description[description]
                path_pattern = '^' + re.escape(outer_path).replace(r'\-', '-') + '$'
                self.assertEqual(group['targetRules'], ['generic-api-key'])
                self.assertEqual(group['condition'], 'AND')
                self.assertEqual(group['regexTarget'], 'line')
                self.assertEqual(group['paths'], [path_pattern])
                ordered_rows = sorted(rows)
                expected_patterns = [
                    r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                    for key, digest in ordered_rows
                ]
                self.assertEqual(group['regexes'], expected_patterns)
                self.assertEqual(len(group['regexes']), len(set(group['regexes'])))
                for (key, digest), pattern in zip(ordered_rows, group['regexes'], strict=True):
                    line = f'  "{key}": "{digest}",'
                    self.assertIsNotNone(re.fullmatch(pattern, line))
                    wrong_digest = '0' * 64 if digest != '0' * 64 else '1' * 64
                    for rejected_line in [
                        line.replace(digest, wrong_digest),
                        line.replace('"' + key + '"', '"unrelated-key"'),
                        line + ' "credential": "synthetic-secret"',
                    ]:
                        self.assertIsNone(re.fullmatch(pattern, rejected_line))
                self.assertIsNone(re.fullmatch(path_pattern, outer_path + '.backup'))
                self.assertIsNone(re.fullmatch(path_pattern, 'src/secrets.json'))

        def matched_rows(blob, patterns):
            matches = []
            for line_number, line in enumerate(blob.decode('utf-8').splitlines(), start=1):
                matching_patterns = [pattern for pattern in patterns if re.fullmatch(pattern, line)]
                self.assertLessEqual(len(matching_patterns), 1)
                if matching_patterns:
                    parsed = re.fullmatch(r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})",?\s*', line)
                    self.assertIsNotNone(parsed)
                    key, digest = parsed.groups()
                    matches.append((line_number, key, digest))
            return matches

        policy_group = by_description['Observed CON.21 dependency-policy exact tuples']
        receipt_group = by_description['Observed CON.21 con-21-r1 receipt exact tuples']
        profile_group = by_description['Observed CON.21 Dokka r17 profile exact tuples']
        old_policy_hits = matched_rows(git_blob(historical_commit, policy_path),
                                       policy_group['regexes'])
        new_policy_hits = matched_rows(git_blob(diagnostic_commit, policy_path),
                                       policy_group['regexes'])
        old_receipt_hits = matched_rows(git_blob(historical_commit, receipt_path),
                                        receipt_group['regexes'])
        new_receipt_hits = matched_rows(git_blob(diagnostic_commit, receipt_path),
                                        receipt_group['regexes'])
        old_profile_hits = matched_rows(profile_blob, profile_group['regexes'])
        self.assertEqual(len(old_policy_hits), 2)
        self.assertEqual({row[2] for row in old_policy_hits}, {digest for _, digest in policy_rows} -
                         {json.loads(git_blob(diagnostic_commit, policy_path))['inputHashes'][access_key]})
        self.assertEqual(len(new_policy_hits), 2)
        self.assertEqual(len(old_receipt_hits), 4)
        self.assertEqual(len(new_receipt_hits), 4)
        old_receipt_pairs = {(key, digest) for _, key, digest in old_receipt_hits}
        new_receipt_pairs = {(key, digest) for _, key, digest in new_receipt_hits}
        self.assertEqual(len(old_receipt_pairs | new_receipt_pairs), 5)
        self.assertEqual(len(old_profile_hits), 315)
        self.assertEqual({(key, digest) for _, key, digest in old_profile_hits}, profile_rows)


    def test_con24_secret_scan_allowlists_bind_only_observed_public_digest_tuples(self):
        # Frozen Security run 36751795694/job 110012013584 at e04. The external
        # candidate artifact 11116170091 independently verified the 308 HTML rows
        # with the existing normalized_page rule; these are public content hashes.
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        frozen_head = 'e04d5a3026a827196b7b62eac6fc5180391c2c00'
        policy_history_head = 'e88cd0f94f01985a166a18d2f43526486b2b5761'
        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-24-r1.json'
        profile_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r18.json'
        access_key = 'eng/policy/contract-access.json'
        expected_descriptions = {
            'Observed CON.24 dependency-policy exact public digest tuples',
            'Observed CON.24 con-24-r1 receipt exact public digest tuples',
            'Observed CON.24 Dokka r18 profile exact public digest tuples',
        }

        def git_blob(commit, path):
            return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)

        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                       text=True).strip()
        for earlier, later in [(frozen_head, policy_history_head),
                               (policy_history_head, head)]:
            self.assertEqual(subprocess.run(
                ['git', 'merge-base', '--is-ancestor', earlier, later],
                cwd=ROOT, check=False).returncode, 0)

        frozen_allowlists = tomllib.loads(
            git_blob(policy_history_head, '.gitleaks.toml').decode('utf-8'))['allowlists']
        self.assertEqual(len(frozen_allowlists), 67)
        self.assertEqual(config['allowlists'][:67], frozen_allowlists)
        groups = config['allowlists'][64:67]
        self.assertEqual({row['description'] for row in groups}, expected_descriptions)
        self.assertEqual(len(groups), 3)
        by_description = {row['description']: row for row in groups}

        frozen_policy_blob = git_blob(policy_history_head, policy_path)
        self.assertEqual(git_blob(frozen_head, policy_path), frozen_policy_blob)
        frozen_blobs = {
            policy_path: frozen_policy_blob,
            receipt_path: git_blob(frozen_head, receipt_path),
            profile_path: git_blob(frozen_head, profile_path),
        }
        for path in (receipt_path, profile_path):
            self.assertEqual(frozen_blobs[path], git_blob(head, path))

        def parse_json_line(blob, line_number):
            lines = blob.decode('utf-8').splitlines()
            self.assertLessEqual(line_number, len(lines))
            match = re.fullmatch(
                r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})",?\s*',
                lines[line_number - 1])
            self.assertIsNotNone(match)
            return match.group(1), match.group(2)

        policy_blob = frozen_blobs[policy_path]
        policy_document = json.loads(policy_blob)
        policy_occurrences = [
            (line_number, *parse_json_line(policy_blob, line_number))
            for line_number in (19, 2489)
        ]
        self.assertEqual([row[0] for row in policy_occurrences], [19, 2489])
        self.assertEqual(len({(key, digest) for _, key, digest in policy_occurrences}), 1)
        for _, key, digest in policy_occurrences:
            self.assertEqual(key, access_key)
            self.assertEqual(policy_document['inputHashes'][key], digest)
            self.assertEqual(digest, hashlib.sha256(git_blob(frozen_head, key)).hexdigest())

        receipt_blob = frozen_blobs[receipt_path]
        receipt_document = json.loads(receipt_blob)
        receipt_hashes = receipt_document['review']['inputHashes']
        receipt_occurrences = [
            (line_number, *parse_json_line(receipt_blob, line_number))
            for line_number in (22, 75, 141, 197)
        ]
        self.assertEqual(
            [row[0] for row in receipt_occurrences], [22, 75, 141, 197])
        self.assertEqual(len({(key, digest) for _, key, digest in receipt_occurrences}), 4)
        for _, key, digest in receipt_occurrences:
            self.assertEqual(receipt_hashes[key], digest)
            self.assertEqual(digest, hashlib.sha256(git_blob(frozen_head, key)).hexdigest())

        profile_blob = frozen_blobs[profile_path]
        profile_lines = profile_blob.decode('utf-8').splitlines()
        profile_document = json.loads(profile_blob)
        profile_maps = [module['pages'] for module in profile_document['modules'].values()]
        profile_maps.append(profile_document['inputs'])
        reported_line_ranges = '''
            984,986,988-989,1664-1666,3738-3740,3742,3744-3746,3748,3751,
            3763-3768,3770-3772,3785-3787,3798,3800-3803,3805-3807,3813-3818,
            3834-3839,3841-3843,4022,4036,4039,4051-4052,4059,4067,4077-4078,
            4085,4099-4100,4118-4119,4126,4510,4539,4551,4589-4590,4625,4659,
            4690-4691,4726,4758-4759,4818-4819,4854,5237,5239,5242,5245-5246,
            5249,5252,5254-5255,5258,5261-5262,5268-5269,5272,5347,5356,5361,
            5370-5371,5377,5385,5393-5394,5400,5411-5412,5426-5427,5433,
            10170,10178-10181,10187-10189,10193,10198-10201,10212,10221-10224,
            11429,11439,11446-11447,11457,11463-11464,11477-11478,11489-11490,
            18796,18800,18804,18808,18810,18815,18818-18819,18825-18826,18828,
            18832,18835,18839,18841-18842,18848-18849,18851,18855,18860-18861,
            18867-18868,18877-18878,18884-18885,18887,18891,18989,18992,18996,
            18999,19001,19006,19014-19015,19018-19019,19021,19024,19032,19035,
            19042-19043,19046-19047,19049,19052,19057-19058,19061-19062,
            19075-19076,19079-19080,19082,19085,22412,22417,22420,22437-22438,
            22456,22471,22480-22481,22499,22511-22512,22532,22555,
            24104-24106,24108,24110-24111,24113,24116,24119,24122-24123,24125,
            24128-24129,24131,24134-24135,24137,24139-24140,24142,24145-24146,
            24148,24152-24153,24155,24163,24165,24167,24170-24171,24173,24188,
            24190,24193,24195,24197,24201,24211,24214,24218,24220,24229,24231,
            24238,24241,24245,24247,24253,24256,24269,24273,24277,24279,
            24586,24590,24597,24603-24604,24608,24613,24618-24619,24623,
            24631-24632,24642-24643,24647,24876,24886,24892,24904-24905,24913,
            24921,24930-24931,24939,24952-24953,24971-24972,24980,27190,27196,
            27202,27212,27219,27227,27234,27241,27249,27263,27271,39053-39055,
            49679,49685
        '''
        reported_line_numbers = set()
        for item in reported_line_ranges.split(','):
            bounds = [int(value) for value in item.strip().split('-')]
            self.assertIn(len(bounds), [1, 2])
            first = bounds[0]
            last = bounds[-1]
            self.assertLessEqual(first, last)
            selected = set(range(first, last + 1))
            self.assertFalse(reported_line_numbers & selected)
            reported_line_numbers.update(selected)
        self.assertEqual(len(reported_line_numbers), 315)

        profile_occurrences = []
        for line_number in sorted(reported_line_numbers):
            line = profile_lines[line_number - 1]
            key, digest = parse_json_line(profile_blob, line_number)
            profile_values = [mapping[key] for mapping in profile_maps if key in mapping]
            self.assertEqual(profile_values, [digest])
            profile_occurrences.append((line_number, key, digest))
        profile_rows = {(key, digest) for _, key, digest in profile_occurrences}
        self.assertEqual(len(profile_rows), 315)
        html_rows = {key for key, _ in profile_rows if key.endswith('.html')}
        source_rows = {(key, digest) for key, digest in profile_rows
                       if key.endswith(('.java', '.kt'))}
        self.assertEqual(len(html_rows), 308)
        self.assertEqual(sum(key.startswith('contracts-proto/') for key in html_rows), 306)
        self.assertEqual(sum(key.startswith('contracts-connect-client/') for key in html_rows), 2)
        self.assertEqual(len(source_rows), 7)
        for key, digest in source_rows:
            self.assertEqual(digest, hashlib.sha256(git_blob(frozen_head, key)).hexdigest())

        observations = {
            'policy': (policy_path, policy_occurrences),
            'receipt': (receipt_path, receipt_occurrences),
            'profile': (profile_path, profile_occurrences),
        }
        component_hashes = {
            'policy': '5daeaf83d1c4b0d7ab311bb148e2abb5970a660bcf152e2581e1538c82cdd879',
            'receipt': '407ff41253183e7ecda39c751c6a86d4861143a8cc0072afae6cc4bc9793b80e',
            'profile': 'db4e07d22e3e85637512312f6503f13a0bffb0cd08770f06f08aceac4989430d',
        }
        tuple_sets = {}
        occurrence_count = 0
        digest_values = set()
        for name, (outer_path, occurrences) in observations.items():
            occurrence_count += len(occurrences)
            rows = {(outer_path, digest) for _, _, digest in occurrences}
            tuple_sets[name] = rows
            digest_values.update(digest for _, _, digest in occurrences)
            canonical = ''.join(
                f'generic-api-key\t{path}\t{digest}\n'
                for path, digest in sorted(rows)
            ).encode('utf-8')
            self.assertEqual(hashlib.sha256(canonical).hexdigest(), component_hashes[name])

        all_tuples = set().union(*tuple_sets.values())
        self.assertEqual(occurrence_count, 321)
        self.assertEqual(len(tuple_sets['policy']), 1)
        self.assertEqual(len(tuple_sets['receipt']), 4)
        self.assertEqual(len(tuple_sets['profile']), 315)
        self.assertEqual(len(all_tuples), 320)
        self.assertEqual(len(digest_values), 319)
        canonical_all = ''.join(
            f'generic-api-key\t{path}\t{digest}\n'
            for path, digest in sorted(all_tuples)
        ).encode('utf-8')
        self.assertEqual(
            hashlib.sha256(canonical_all).hexdigest(),
            'baafcbb6ecce96024b40203d864789a716c7aafcc22111dff71d89aa33eb5571')

        expected_rows = {
            'Observed CON.24 dependency-policy exact public digest tuples':
                (policy_path, {(key, digest) for _, key, digest in policy_occurrences}),
            'Observed CON.24 con-24-r1 receipt exact public digest tuples':
                (receipt_path, {(key, digest) for _, key, digest in receipt_occurrences}),
            'Observed CON.24 Dokka r18 profile exact public digest tuples':
                (profile_path, profile_rows),
        }
        for description, (outer_path, rows) in expected_rows.items():
            with self.subTest(description=description):
                group = by_description[description]
                path_pattern = '^' + re.escape(outer_path).replace(r'\-', '-') + '$'
                self.assertEqual(group['targetRules'], ['generic-api-key'])
                self.assertEqual(group['condition'], 'AND')
                self.assertEqual(group['regexTarget'], 'line')
                self.assertEqual(group['paths'], [path_pattern])
                ordered_rows = sorted(rows)
                expected_patterns = [
                    r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                    for key, digest in ordered_rows
                ]
                self.assertEqual(group['regexes'], expected_patterns)
                self.assertEqual(len(group['regexes']), len(set(group['regexes'])))
                occurrence_rows = observations[
                    'policy' if outer_path == policy_path else
                    'receipt' if outer_path == receipt_path else 'profile'
                ][1]
                blob = frozen_blobs[outer_path]
                source_lines = blob.decode('utf-8').splitlines()
                for line_number, key, digest in occurrence_rows:
                    line = source_lines[line_number - 1]
                    self.assertEqual(parse_json_line(blob, line_number), (key, digest))
                    matching = [pattern for pattern in group['regexes']
                                if re.fullmatch(pattern, line)]
                    self.assertEqual(len(matching), 1)
                expected_pairs = rows
                actual_matches = []
                for line_number, line in enumerate(source_lines, start=1):
                    parsed = re.fullmatch(
                        r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})",?\s*', line)
                    if parsed and (parsed.group(1), parsed.group(2)) in expected_pairs:
                        self.assertEqual(
                            sum(re.fullmatch(pattern, line) is not None
                                for pattern in group['regexes']), 1)
                        actual_matches.append((line_number, parsed.group(1), parsed.group(2)))
                self.assertEqual(actual_matches, occurrence_rows)
                for (key, digest), pattern in zip(
                        ordered_rows, group['regexes'], strict=True):
                    line = f'  "{key}": "{digest}",'
                    self.assertIsNotNone(re.fullmatch(pattern, line))
                    wrong_digest = '0' * 64 if digest != '0' * 64 else '1' * 64
                    unrelated_digest = 'a' * 64 if digest != 'a' * 64 else 'b' * 64
                    for rejected_line in [
                        line.replace(digest, wrong_digest),
                        line.replace('"' + key + '"', '"unrelated-key"'),
                        f'  "unrelated-key": "{unrelated_digest}",',
                        line + ' "credential": "synthetic-secret"',
                    ]:
                        self.assertIsNone(re.fullmatch(pattern, rejected_line))
                self.assertIsNone(re.fullmatch(path_pattern, outer_path + '.backup'))
                self.assertIsNone(re.fullmatch(path_pattern, 'src/secrets.json'))


    def test_con11_secret_scan_allowlists_bind_only_observed_public_digest_tuples(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        self.assertEqual(len(config['allowlists']), 100)
        groups = config['allowlists'][67:70]
        expected_descriptions = {
            'CON.11 reviewed dependency policy public input digest',
            'CON.11 reviewed immutable dependency receipt public input digests',
            'CON.11 reviewed Dokka r19 public profile exact source digest rows',
        }
        self.assertEqual(len(groups), 3)
        self.assertEqual({row['description'] for row in groups}, expected_descriptions)
        by_description = {row['description']: row for row in groups}

        scan_head = '1ea545850b73705a5c37ab9d69184ed2c7df013c'
        profile_head = 'f248b048bbe1582c82158c0b52897b39737f7e89'
        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-11-r1.json'
        profile_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r19.json'

        def git_blob(commit, path):
            return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)

        head = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        for earlier in (scan_head, profile_head):
            self.assertEqual(subprocess.run(
                ['git', 'merge-base', '--is-ancestor', earlier, head],
                cwd=ROOT, check=False).returncode, 0)

        def parse_json_line(blob, line_number):
            lines = blob.decode('utf-8').splitlines()
            self.assertLessEqual(line_number, len(lines))
            match = re.fullmatch(
                r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})",?\s*',
                lines[line_number - 1])
            self.assertIsNotNone(match)
            return match.group(1), match.group(2)

        policy_blob = git_blob(scan_head, policy_path)
        policy_document = json.loads(policy_blob)
        policy_occurrences = [
            (line_number, *parse_json_line(policy_blob, line_number))
            for line_number in (19, 2490)
        ]
        self.assertEqual(
            policy_occurrences,
            [
                (19, 'eng/policy/contract-access.json',
                 '99e2e46d33a86a1486ecdc71d314f553a224433259cbf9c93e93417d635a9188'),
                (2490, 'eng/policy/contract-access.json',
                 '99e2e46d33a86a1486ecdc71d314f553a224433259cbf9c93e93417d635a9188'),
            ])
        self.assertEqual(len({(key, digest) for _, key, digest in policy_occurrences}), 1)
        for _, key, digest in policy_occurrences:
            self.assertEqual(policy_document['inputHashes'][key], digest)
            self.assertEqual(
                digest, hashlib.sha256(git_blob(scan_head, key)).hexdigest())

        receipt_blob = git_blob(scan_head, receipt_path)
        receipt_document = json.loads(receipt_blob)
        receipt_hashes = receipt_document['review']['inputHashes']
        receipt_occurrences = [
            (line_number, *parse_json_line(receipt_blob, line_number))
            for line_number in (22, 76, 142, 198)
        ]
        self.assertEqual(
            [row[0] for row in receipt_occurrences], [22, 76, 142, 198])
        self.assertEqual(
            [digest for _, key, digest in receipt_occurrences],
            [receipt_hashes[key] for _, key, _ in receipt_occurrences])
        for _, key, digest in receipt_occurrences:
            self.assertEqual(
                digest, hashlib.sha256(git_blob(scan_head, key)).hexdigest())

        profile_blob = git_blob(profile_head, profile_path)
        self.assertEqual(profile_blob, git_blob(head, profile_path))
        profile_lines = profile_blob.decode('utf-8').splitlines()
        profile_document = json.loads(profile_blob)
        profile_maps = [module['pages'] for module in profile_document['modules'].values()]
        profile_maps.append(profile_document['inputs'])
        reported_line_numbers = [
            1133, 1135, 1137, 1138, 1891, 1892, 1893, 4213, 4239, 4256, 4281, 4282,
            4304, 4316, 4321, 4326, 4332, 4333, 4337, 4342, 4347, 4348, 4352, 4359,
            4360, 4370, 4371, 4375, 4529, 4535, 4541, 4550, 4551, 4554, 4562, 4570,
            4571, 4574, 4581, 4582, 4595, 4596, 4599, 4625, 4648, 4649, 4671, 4714,
            4715, 4780, 4781, 4803, 6853, 6854, 6855, 6857, 6859, 6860, 6861, 6863,
            6866, 6878, 6879, 6880, 6881, 6882, 6883, 6885, 6886, 6887, 6900, 6901,
            6902, 6913, 6915, 6916, 6917, 6918, 6920, 6921, 6922, 6928, 6929, 6930,
            6931, 6932, 6933, 6949, 6950, 6951, 6952, 6953, 6954, 6956, 6957, 6958,
            7137, 7151, 7154, 7166, 7167, 7174, 7182, 7192, 7193, 7200, 7214, 7215,
            7233, 7234, 7241, 7625, 7654, 7666, 7704, 7705, 7740, 7774, 7805, 7806,
            7841, 7873, 7874, 7933, 7934, 7969, 8352, 8354, 8357, 8360, 8361, 8364,
            8367, 8369, 8370, 8373, 8376, 8377, 8383, 8384, 8387, 8462, 8471, 8476,
            8485, 8486, 8492, 8500, 8508, 8509, 8515, 8526, 8527, 8541, 8542, 8548,
            13907, 13915, 13916, 13917, 13918, 13924, 13925, 13926, 13930, 13935, 13936, 13937,
            13938, 13949, 13958, 13959, 13960, 13961, 15166, 15176, 15183, 15184, 15194, 15200,
            15201, 15214, 15215, 15226, 15227, 22678, 22682, 22686, 22690, 22692, 22697, 22700,
            22701, 22707, 22708, 22710, 22714, 22717, 22721, 22723, 22724, 22730, 22731, 22733,
            22737, 22742, 22743, 22749, 22750, 22759, 22760, 22766, 22767, 22769, 22773, 22871,
            22874, 22878, 22881, 22883, 22888, 22896, 22897, 22900, 22901, 22903, 22906, 22914,
            22917, 22924, 22925, 22928, 22929, 22931, 22934, 22939, 22940, 22943, 22944, 22957,
            22958, 22961, 22962, 22964, 22967, 26294, 26299, 26302, 26319, 26320, 26338, 26353,
            26362, 26363, 26381, 26393, 26394, 26414, 26437, 29081, 29082, 29083, 29085, 29087,
            29088, 29090, 29093, 29096, 29099, 29100, 29102, 29105, 29106, 29108, 29111, 29112,
            29114, 29116, 29117, 29119, 29122, 29123, 29125, 29129, 29130, 29132, 29140, 29142,
            29144, 29147, 29148, 29150, 29165, 29167, 29170, 29172, 29174, 29178, 29188, 29191,
            29195, 29197, 29206, 29208, 29215, 29218, 29222, 29224, 29230, 29233, 29246, 29250,
            29254, 29256, 29563, 29567, 29574, 29580, 29581, 29585, 29590, 29595, 29596, 29600,
            29608, 29609, 29619, 29620, 29624, 29853, 29863, 29869, 29881, 29882, 29890, 29898,
            29907, 29908, 29916, 29929, 29930, 29948, 29949, 29957, 32167, 32173, 32179, 32189,
            32196, 32204, 32211, 32218, 32226, 32240, 32248, 44507, 44508, 44509, 55473, 55479,
        ]
        self.assertEqual(len(reported_line_numbers), 360)
        self.assertEqual(len(set(reported_line_numbers)), 360)
        self.assertEqual(reported_line_numbers, sorted(reported_line_numbers))
        profile_occurrences = [
            (line_number, *parse_json_line(profile_blob, line_number))
            for line_number in reported_line_numbers
        ]
        profile_rows = {(key, digest) for _, key, digest in profile_occurrences}
        self.assertEqual(len(profile_rows), 360)
        for _, key, digest in profile_occurrences:
            values = [mapping[key] for mapping in profile_maps if key in mapping]
            self.assertEqual(values, [digest])
        source_rows = {(key, digest) for key, digest in profile_rows
                       if key.endswith(('.java', '.kt'))}
        html_rows = {key for key, _ in profile_rows if key.endswith('.html')}
        self.assertEqual(len(source_rows), 7)
        self.assertEqual(len(html_rows), 353)
        for key, digest in source_rows:
            self.assertEqual(
                digest, hashlib.sha256(git_blob(profile_head, key)).hexdigest())

        canonical_profile_lines = ''.join(
            f'{line_number}\t{key}\t{digest}\n'
            for line_number, key, digest in profile_occurrences)
        self.assertEqual(
            hashlib.sha256(canonical_profile_lines.encode('utf-8')).hexdigest(),
            'ed4163812589de05acbf59cca735edc78ec747ffaa998c348f6fef79c009178b')
        canonical_profile_pairs = ''.join(
            f'{key}\t{digest}\n' for key, digest in sorted(profile_rows))
        self.assertEqual(
            hashlib.sha256(canonical_profile_pairs.encode('utf-8')).hexdigest(),
            '69be3b95b5910fb20b07ccb558363e42232b51f961a051b4c94c2d40aefbc335')

        observations = {
            'policy': (policy_path, policy_occurrences),
            'receipt': (receipt_path, receipt_occurrences),
            'profile': (profile_path, profile_occurrences),
        }
        expected_occurrences = 0
        all_tuples = set()
        expected_rows = {}
        for name, (outer_path, occurrences) in observations.items():
            expected_occurrences += len(occurrences)
            tuples = {(outer_path, key, digest) for _, key, digest in occurrences}
            all_tuples.update(tuples)
            expected_rows[name] = {(key, digest) for _, key, digest in occurrences}
        self.assertEqual(expected_occurrences, 366)
        self.assertEqual(len(all_tuples), 365)
        self.assertEqual([len(expected_rows[name]) for name in ('policy', 'receipt', 'profile')],
                         [1, 4, 360])

        for name, (outer_path, occurrences) in observations.items():
            with self.subTest(source=name):
                suffix = {
                    'policy': 'CON.11 reviewed dependency policy public input digest',
                    'receipt': 'CON.11 reviewed immutable dependency receipt public input digests',
                    'profile': 'CON.11 reviewed Dokka r19 public profile exact source digest rows',
                }[name]
                group = by_description[suffix]
                path_pattern = '^' + re.escape(outer_path) + '$'
                self.assertEqual(group['targetRules'], ['generic-api-key'])
                self.assertEqual(group['condition'], 'AND')
                self.assertEqual(group['regexTarget'], 'line')
                self.assertEqual(group['paths'], [path_pattern])
                ordered_rows = sorted(expected_rows[name])
                expected_patterns = [
                    r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                    for key, digest in ordered_rows
                ]
                self.assertEqual(group['regexes'], expected_patterns)
                self.assertEqual(len(group['regexes']), len(set(group['regexes'])))
                source_blob = {
                    'policy': policy_blob,
                    'receipt': receipt_blob,
                    'profile': profile_blob,
                }[name]
                source_lines = source_blob.decode('utf-8').splitlines()
                for line_number, key, digest in occurrences:
                    line = source_lines[line_number - 1]
                    self.assertEqual(parse_json_line(source_blob, line_number), (key, digest))
                    self.assertEqual(
                        sum(re.fullmatch(pattern, line) is not None
                            for pattern in group['regexes']), 1)
                for (key, digest), pattern in zip(
                        ordered_rows, group['regexes'], strict=True):
                    line = f'  "{key}": "{digest}",'
                    self.assertIsNotNone(re.fullmatch(pattern, line))
                    wrong_digest = '0' * 64 if digest != '0' * 64 else '1' * 64
                    unrelated_digest = 'a' * 64 if digest != 'a' * 64 else 'b' * 64
                    for rejected_line in [
                        line.replace(digest, wrong_digest),
                        line.replace('"' + key + '"', '"unrelated-key"'),
                        f'  "unrelated-key": "{unrelated_digest}",',
                        line + ' "credential": "synthetic-secret"',
                    ]:
                        self.assertIsNone(re.fullmatch(pattern, rejected_line))
                self.assertIsNone(re.fullmatch(path_pattern, outer_path + '.backup'))
                self.assertIsNone(re.fullmatch(path_pattern, 'src/secrets.json'))

    def test_historical_task_branch_evidence_is_exact_and_independent_of_deleted_branches(self):
        fixtures = {path.name for path in HISTORY_DIR.glob('*.gz')}
        self.assertEqual(fixtures, {blob_id + '.gz' for blob_id, reachable in HISTORICAL_BLOBS.values()
                                    if reachable is None})
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        for reachable in {reachable for _, reachable in HISTORICAL_BLOBS.values() if reachable is not None}:
            self.assertEqual(subprocess.run(['git', 'merge-base', '--is-ancestor', reachable, head],
                                            cwd=ROOT, check=False).returncode, 0)
        for (commit, path), (blob_id, reachable) in HISTORICAL_BLOBS.items():
            with self.subTest(commit=commit, path=path):
                data = frozen_git_blob(commit, path)
                self.assertEqual(hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest(), blob_id)
                if reachable is None:
                    self.assertTrue(path.startswith(('eng/policy/',)))
        # A byte-for-byte mutation of any frozen copy is refused by the blob identity check.
        victim = next((key, blob_id) for key, (blob_id, reachable) in HISTORICAL_BLOBS.items() if reachable is None)
        original = (HISTORY_DIR / (victim[1] + '.gz')).read_bytes()
        data = gzip.decompress(original)
        mutated = data[:-2] + (b'0' if data[-2:-1] != b'0' else b'1') + data[-1:]
        self.assertNotEqual(hashlib.sha1(b'blob %d\0' % len(mutated) + mutated).hexdigest(), victim[1])


    def test_con15_secret_scan_allowlists_bind_only_exact_public_digest_tuples(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        self.assertEqual(len(config['allowlists']), 100)
        groups = config['allowlists'][70:72]
        self.assertEqual([row['description'] for row in groups], [
            'CON.15 reviewed dependency policy public input digest',
            'CON.15 reviewed immutable dependency receipt public input digests',
        ])
        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-15-r1.json'
        access_key = 'eng/policy/contract-access.json'
        receipt_keys = [
            access_key,
            'eng/provenance/records/dokka-combokeys-licence-r1.json',
            'eng/provenance/records/dokka-object-keys-licence-r1.json',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
        ]
        # Bind the immutable CON.15 policy/receipt snapshot at the commit that introduced the receipt, so later
        # tasks may advance the live policy and receipt chain without invalidating this historical binding.
        scan_head = subprocess.check_output(
            ['git', 'log', '--diff-filter=A', '--format=%H', '--', receipt_path], cwd=ROOT, text=True).split()[-1]
        self.assertEqual(subprocess.run(
            ['git', 'merge-base', '--is-ancestor', scan_head, 'HEAD'], cwd=ROOT, check=False).returncode, 0)

        def snapshot(path):
            return subprocess.check_output(['git', 'show', f'{scan_head}:{path}'], cwd=ROOT)

        self.assertEqual(snapshot(receipt_path).replace(b'\r\n', b'\n'),
                         (ROOT / receipt_path).read_bytes().replace(b'\r\n', b'\n'))
        policy = json.loads(snapshot(policy_path))
        receipt = json.loads(snapshot(receipt_path))
        self.assertEqual(policy['reviewReceipt'], receipt_path)
        self.assertEqual(receipt['review'], policy['review'])
        self.assertEqual(receipt['review']['previousReceipt'] != receipt_path, True)
        hashes = receipt['review']['inputHashes']
        self.assertEqual(hashes, policy['inputHashes'])
        for key in receipt_keys:
            self.assertEqual(hashlib.sha256(snapshot(key).replace(b'\r\n', b'\n')).hexdigest(), hashes[key])
        expected = [
            (policy_path, r'^eng/policy/dependency\-policy\.json$', [access_key]),
            (receipt_path, r'^eng/policy/dependency\-reviews/con\-15\-r1\.json$', receipt_keys),
        ]
        for group, (path, path_pattern, keys) in zip(groups, expected, strict=True):
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path_pattern])
            self.assertIsNotNone(re.fullmatch(group['paths'][0], path))
            for wrong_path in (path + '.backup', 'src/secrets.json', 'eng/policy/dependency-reviews/con-15-r2.json'):
                self.assertIsNone(re.fullmatch(group['paths'][0], wrong_path))
            self.assertEqual(len(group['regexes']), len(keys))
            for key, pattern in zip(keys, group['regexes'], strict=True):
                digest = hashes[key]
                self.assertEqual(pattern, rf'(?s)^\s*"{re.escape(key)}":\s*"{digest}",?\s*$')
                self.assertIsNotNone(re.fullmatch(pattern, f'  "{key}": "{digest}",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "{key}": "' + '0' * 64 + '",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "credential": "{digest}",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "{key}": "{digest}", "credential": "other"'))
            actual_lines = [
                line for line in snapshot(path).decode('utf-8').splitlines()
                if any(re.fullmatch(pattern, line) for pattern in group['regexes'])
            ]
            # The policy carries the access digest in inputHashes and in review.inputHashes.
            self.assertEqual(len(actual_lines), 2 if path == policy_path else len(keys))
        # The earlier CON.11 digest row is retained only for its own historical policy/receipt snapshots.
        self.assertNotEqual(hashes[access_key], '99e2e46d33a86a1486ecdc71d314f553a224433259cbf9c93e93417d635a9188')

    def test_con07_secret_scan_allowlists_bind_only_exact_public_digest_tuples(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        self.assertEqual(len(config['allowlists']), 100)
        groups = config['allowlists'][74:77]
        self.assertEqual([row['description'] for row in groups], [
            'CON.07 reviewed dependency policy public input digest',
            'CON.07 reviewed immutable dependency receipt public input digests',
            'CON.07 reviewed Dokka r20 public profile exact source digest rows',
        ])
        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-07-r1.json'
        profile_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r20.json'
        access_key = 'eng/policy/contract-access.json'
        # The policy that named this receipt is bound at the commit that introduced the receipt, so later
        # tasks may advance the live policy and receipt chain without invalidating this historical binding.
        scan_head = subprocess.check_output(
            ['git', 'log', '--diff-filter=A', '--format=%H', '--', receipt_path], cwd=ROOT, text=True).split()[-1]
        self.assertEqual(subprocess.run(
            ['git', 'merge-base', '--is-ancestor', scan_head, 'HEAD'], cwd=ROOT, check=False).returncode, 0)
        policy = json.loads(subprocess.check_output(['git', 'show', f'{scan_head}:{policy_path}'], cwd=ROOT))
        receipt = json.loads((ROOT / receipt_path).read_text(encoding='utf-8'))
        profile = json.loads((ROOT / profile_path).read_text(encoding='utf-8'))
        self.assertEqual(policy['reviewReceipt'], receipt_path)
        self.assertEqual(receipt['review'], policy['review'])
        self.assertEqual(receipt['review']['previousReceipt'], 'eng/policy/dependency-reviews/con-14-r1.json')
        hashes = receipt['review']['inputHashes']
        self.assertEqual(hashes, policy['inputHashes'])
        receipt_keys = [
            access_key,
            'eng/provenance/records/dokka-combokeys-licence-r1.json',
            'eng/provenance/records/dokka-object-keys-licence-r1.json',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
        ]
        for key in receipt_keys:
            actual_bytes = (ROOT / key).read_bytes() if key != access_key else committed_with(receipt_path, key)
            self.assertEqual(hashlib.sha256(actual_bytes.replace(b'\r\n', b'\n')).hexdigest(), hashes[key])
        profile_rows = set(profile['inputs'].items())
        for module in profile['modules'].values():
            profile_rows.update(module['pages'].items())
        expected = [
            (policy_path, r'^eng/policy/dependency\-policy\.json$', [(access_key, hashes[access_key])], 2),
            (receipt_path, r'^eng/policy/dependency\-reviews/con\-07\-r1\.json$',
             [(key, hashes[key]) for key in receipt_keys], 4),
            (profile_path, r'^eng/provenance/artifact\-profiles/dokka\-2\-2\-0\-r20\.json$', None, 776),
        ]
        prefix = '(?s)^\\s*"'
        separator = '":\\s*"'
        suffix = '",?\\s*$'
        for group, (path, path_pattern, rows, line_count) in zip(groups, expected, strict=True):
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path_pattern])
            self.assertIsNotNone(re.fullmatch(group['paths'][0], path))
            for wrong_path in (path + '.backup', 'src/secrets.json', 'eng/policy/dependency-reviews/con-07-r2.json'):
                self.assertIsNone(re.fullmatch(group['paths'][0], wrong_path))
            self.assertEqual(len(group['regexes']), len(set(group['regexes'])))
            parsed = []
            for pattern in group['regexes']:
                self.assertTrue(pattern.startswith(prefix) and pattern.endswith(suffix), pattern)
                escaped_key, digest = pattern[len(prefix):-len(suffix)].split(separator)
                self.assertRegex(digest, r'^[0-9a-f]{64}$')
                key = re.sub(r'\\(.)', r'\1', escaped_key)
                parsed.append((key, digest))
                self.assertEqual(pattern, rf'(?s)^\s*"{re.escape(key)}":\s*"{digest}",?\s*$')
                self.assertIsNotNone(re.fullmatch(pattern, f'  "{key}": "{digest}",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "{key}": "' + '0' * 64 + '",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "credential": "{digest}",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "{key}": "{digest}", "credential": "other"'))
            self.assertEqual(parsed, sorted(parsed))
            if rows is not None:
                self.assertEqual(parsed, sorted(rows))
            else:
                self.assertEqual(len(parsed), 776)
                self.assertTrue(set(parsed) <= profile_rows)
                self.assertEqual(hashlib.sha256(''.join(
                    f'generic-api-key\t{path}\t{key}\t{digest}\n' for key, digest in parsed).encode('utf-8')).hexdigest(),
                    '363de168145ff560022fafbd6155f3fff30e53facf70ad9e9f8c321371a42b1d')
            compiled = {pair: re.compile(pattern) for pair, pattern in zip(parsed, group['regexes'], strict=True)}
            actual_lines = []
            for line in (ROOT / path).read_text(encoding='utf-8').splitlines():
                found = re.fullmatch(r'\s*"([^"]+)":\s*"([0-9a-f]{64})",?\s*', line)
                if found and (found.group(1), found.group(2)) in compiled:
                    self.assertIsNotNone(compiled[(found.group(1), found.group(2))].fullmatch(line))
                    actual_lines.append(line)
            # The policy carries the access digest in inputHashes and in review.inputHashes only while this task's
            # digest is the active one; a later task moves the policy on and its own exact rows take over.
            current_access = json.loads((ROOT / policy_path).read_text(encoding='utf-8'))['inputHashes'][access_key]
            superseded = path == policy_path and current_access != hashes[access_key]
            self.assertEqual(len(actual_lines), 0 if superseded else line_count)
        # The immutable predecessor rows remain exactly the earlier CON.15 allowance, never rebound to this digest.
        self.assertNotEqual(hashes[access_key], 'a3487a2842c117ef2be76807dce4550cc10927d099fadcce201cae76b08cc69e')



    def test_con26_secret_scan_allowlists_bind_only_observed_public_digest_tuples(self):
        # Security 37503752501/job 112407047628 observed ten occurrences of nine public input tuples.
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        previous = subprocess.check_output(['git', 'show',
            'f3d2f7cc64ac5cff627a916cc561f721655fa446:.gitleaks.toml'], cwd=ROOT)
        self.assertEqual(config['allowlists'][:83], tomllib.loads(previous.decode())['allowlists'])
        accepted = subprocess.check_output(['git', 'show', '8715f6e2462153fac44bccac2dd9e8b55adafc5f:.gitleaks.toml'], cwd=ROOT)
        self.assertEqual(config['allowlists'][:85], tomllib.loads(accepted.decode())['allowlists'])
        self.assertTrue((ROOT / '.gitleaks.toml').read_bytes().replace(b'\r\n', b'\n')
                        .startswith(previous.replace(b'\r\n', b'\n')))
        groups = config['allowlists'][89:92]
        self.assertEqual([row['description'] for row in groups], [
            'CON.26 reviewed dependency policy public input digest',
            'CON.26 reviewed immutable dependency receipt r1 public input digests',
            'CON.26 reviewed immutable dependency receipt r2 public input digests',
        ])
        keys = ['eng/policy/contract-access.json',
                'eng/provenance/records/dokka-combokeys-licence-r1.json',
                'eng/provenance/records/dokka-object-keys-licence-r1.json',
                'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        observations = [
            ('f3d2f7cc64ac5cff627a916cc561f721655fa446', 'eng/policy/dependency-policy.json', 2, [keys[0]]),
            ('eb8849aa7b9e096f4310ec0de16d0e443c11926d', 'eng/policy/dependency-reviews/con-26-r1.json', 4, keys),
            ('f3d2f7cc64ac5cff627a916cc561f721655fa446', 'eng/policy/dependency-reviews/con-26-r2.json', 4, keys),
        ]
        tuples = []
        for group, (commit, path, occurrence_count, selected) in zip(groups, observations, strict=True):
            self.assertEqual(set(group), {'description', 'targetRules', 'condition', 'paths', 'regexTarget', 'regexes'})
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertNotIn('aws-access-token', group['targetRules'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], ['^' + re.escape(path) + '$'])
            for other in [path + '.backup', 'src/secrets.json', 'eng/policy/dependency-reviews/con-26-r3.json']:
                self.assertIsNone(re.fullmatch(group['paths'][0], other))
            source = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT).decode()
            document = json.loads(source)
            hashes = document['inputHashes'] if path == POLICY else document['review']['inputHashes']
            expected = []
            for key in sorted(selected):
                digest = hashes[key]
                historical = subprocess.check_output(['git', 'show', commit + ':' + key], cwd=ROOT)
                self.assertEqual(hashlib.sha256(historical.replace(b'\r\n', b'\n')).hexdigest(), digest)
                pattern = rf'(?s)^\s*"{re.escape(key)}":\s*"{digest}",?\s*$'
                expected.append(pattern)
                line = f'  "{key}": "{digest}",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for rejected in [line.replace(digest, '0' * 64),
                                 line.replace(key, 'credential'),
                                 line + ' "token": "synthetic-secret"',
                                 line + '\n"token": "synthetic-secret"']:
                    self.assertIsNone(re.fullmatch(pattern, rejected))
                tuples.append(('generic-api-key', path, key, digest))
            self.assertEqual(group['regexes'], expected)
            self.assertEqual(sum(any(re.fullmatch(pattern, line) for pattern in expected)
                                 for line in source.splitlines()), occurrence_count)
        self.assertEqual(len(tuples), 9)
        canonical = ''.join('\t'.join(row) + '\n' for row in sorted(tuples))
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(),
                         '9db3cd5d69899fb0416554a390966c4d36c1b00d19c7656003b8eec751d63878')

    def test_con25_secret_scan_allowlists_bind_only_exact_public_digest_tuples(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        self.assertEqual(len(config['allowlists']), 100)
        groups = config['allowlists'][80:83]
        self.assertEqual([row['description'] for row in groups], [
            'CON.25 reviewed dependency policy public input digest',
            'CON.25 reviewed immutable dependency receipt public input digests',
            'CON.25 reviewed Dokka r21 public profile exact source digest rows',
        ])
        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-25-r1.json'
        profile_path = 'eng/provenance/artifact-profiles/dokka-2-2-0-r21.json'
        access_key = 'eng/policy/contract-access.json'
        scan_head = subprocess.check_output(
            ['git', 'log', '--diff-filter=A', '--format=%H', '--', receipt_path], cwd=ROOT, text=True).split()[-1]
        receipt = json.loads((ROOT / receipt_path).read_text(encoding='utf-8'))
        profile = json.loads((ROOT / profile_path).read_text(encoding='utf-8'))
        self.assertEqual(receipt['review']['previousReceipt'], 'eng/policy/dependency-reviews/gov-05-r1.json')
        hashes = receipt['review']['inputHashes']
        receipt_keys = [
            access_key,
            'eng/provenance/records/dokka-combokeys-licence-r1.json',
            'eng/provenance/records/dokka-object-keys-licence-r1.json',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
        ]
        for key in receipt_keys:
            historical = subprocess.check_output(['git', 'show', f'{scan_head}:{key}'], cwd=ROOT)
            self.assertEqual(hashlib.sha256(historical.replace(b'\r\n', b'\n')).hexdigest(), hashes[key])
        profile_rows = set(profile['inputs'].items())
        for module in profile['modules'].values():
            profile_rows.update(module['pages'].items())
        expected = [
            (policy_path, r'^eng/policy/dependency\-policy\.json$', [(access_key, hashes[access_key])]),
            (receipt_path, r'^eng/policy/dependency\-reviews/con\-25\-r1\.json$', [(key, hashes[key]) for key in receipt_keys]),
            (profile_path, r'^eng/provenance/artifact\-profiles/dokka\-2\-2\-0\-r21\.json$', None),
        ]
        prefix = '(?s)^\\s*"'
        separator = '":\\s*"'
        suffix = '",?\\s*$'
        for group, (path, path_pattern, rows) in zip(groups, expected, strict=True):
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path_pattern])
            self.assertIsNotNone(re.fullmatch(group['paths'][0], path))
            for wrong_path in (path + '.backup', 'src/secrets.json', 'eng/policy/dependency-reviews/con-25-r2.json'):
                self.assertIsNone(re.fullmatch(group['paths'][0], wrong_path))
            self.assertEqual(len(group['regexes']), len(set(group['regexes'])))
            parsed = []
            for pattern in group['regexes']:
                self.assertTrue(pattern.startswith(prefix) and pattern.endswith(suffix), pattern)
                escaped_key, digest = pattern[len(prefix):-len(suffix)].split(separator)
                self.assertRegex(digest, r'^[0-9a-f]{64}$')
                key = re.sub(r'\\(.)', r'\1', escaped_key)
                parsed.append((key, digest))
                self.assertEqual(pattern, rf'(?s)^\s*"{re.escape(key)}":\s*"{digest}",?\s*$')
                self.assertIsNotNone(re.fullmatch(pattern, f'  "{key}": "{digest}",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "{key}": "' + '0' * 64 + '",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "credential": "{digest}",'))
                self.assertIsNone(re.fullmatch(pattern, f'  "{key}": "{digest}", "credential": "other"'))
            self.assertEqual(parsed, sorted(parsed))
            if rows is not None:
                self.assertEqual(parsed, sorted(rows))
            else:
                self.assertEqual(len(parsed), 806)
                self.assertTrue(set(parsed) <= profile_rows)
                self.assertEqual(hashlib.sha256(''.join(
                    f'generic-api-key\t{path}\t{key}\t{digest}\n' for key, digest in parsed).encode('utf-8')).hexdigest(),
                    'ea4a8e35e0af1ec8afb9e178b5361abc403c6074c410e5c491aa5ba660c829df')

    def test_con17_later_service_receipt_chain_and_secret_scan_allowlist(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        self.assertEqual(len(config['allowlists']), 100)
        group = config['allowlists'][77]
        self.assertEqual(group['description'], 'CON.17 reviewed immutable dependency receipt public input digests')
        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-17-later-services-r1.json'
        record_path = 'eng/provenance/records/con17-later-service-descriptors-r1.json'
        access_key = 'eng/policy/contract-access.json'
        policy = json.loads((ROOT / policy_path).read_text(encoding='utf-8'))
        receipt = json.loads((ROOT / receipt_path).read_text(encoding='utf-8'))
        # This receipt is the active one only until a later task supersedes it; its content stays bound either way.
        self.assertEqual(receipt['review']['previousReceipt'], 'eng/policy/dependency-reviews/con-07-r1.json')
        if policy['reviewReceipt'] == receipt_path:
            self.assertEqual(receipt['closure'], policy['closure'])
        previous = json.loads((ROOT / receipt['review']['previousReceipt']).read_text(encoding='utf-8'))
        self.assertEqual(receipt['closure'], previous['closure'])
        self.assertEqual(receipt['review']['frameworkVersions'], previous['review']['frameworkVersions'])
        hashes = receipt['review']['inputHashes']
        # The only dependency input that differs from the previous receipt is the new immutable provenance record.
        self.assertEqual({key for key in hashes if hashes.get(key) != previous['review']['inputHashes'].get(key)}, {record_path})
        self.assertEqual(hashes[record_path], hashlib.sha256((ROOT / record_path).read_bytes().replace(b'\r\n', b'\n')).hexdigest())
        if policy['reviewReceipt'] == receipt_path:
            self.assertEqual(receipt['review'], policy['review'])
            self.assertEqual(hashes, policy['inputHashes'])
        keys = [
            access_key,
            'eng/provenance/records/dokka-combokeys-licence-r1.json',
            'eng/provenance/records/dokka-object-keys-licence-r1.json',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj',
        ]
        self.assertEqual(group['targetRules'], ['generic-api-key'])
        self.assertEqual(group['condition'], 'AND')
        self.assertEqual(group['regexTarget'], 'line')
        self.assertEqual(group['paths'], [r'^eng/policy/dependency\-reviews/con\-17\-later\-services\-r1\.json$'])
        for wrong_path in (receipt_path + '.backup', 'src/secrets.json', 'eng/policy/dependency-reviews/con-17-later-services-r2.json',
                           policy_path):
            self.assertIsNone(re.fullmatch(group['paths'][0], wrong_path))
        self.assertEqual(len(group['regexes']), len(keys))
        for key, pattern in zip(keys, group['regexes'], strict=True):
            digest = hashes[key]
            actual_bytes = (ROOT / key).read_bytes() if key != access_key else committed_with(receipt_path, key)
            self.assertEqual(hashlib.sha256(actual_bytes.replace(b'\r\n', b'\n')).hexdigest(), digest)
            self.assertEqual(pattern, rf'(?s)^\s*"{re.escape(key)}":\s*"{digest}",?\s*$')
            self.assertIsNotNone(re.fullmatch(pattern, f'  "{key}": "{digest}",'))
            self.assertIsNone(re.fullmatch(pattern, f'  "{key}": "' + '0' * 64 + '",'))
            self.assertIsNone(re.fullmatch(pattern, f'  "credential": "{digest}",'))
            self.assertIsNone(re.fullmatch(pattern, f'  "{key}": "{digest}", "credential": "other"'))
        compiled = [re.compile(pattern) for pattern in group['regexes']]
        matched = [line for line in (ROOT / receipt_path).read_text(encoding='utf-8').splitlines()
                   if any(item.fullmatch(line) for item in compiled)]
        self.assertEqual(len(matched), len(keys))

    def test_con17_later_service_provenance_record_binds_every_pinned_descriptor(self):
        window = json.loads((ROOT / 'eng/compatibility/later-services-window.json').read_text(encoding='utf-8'))
        record = json.loads((ROOT / 'eng/provenance/records/con17-later-service-descriptors-r1.json').read_text(encoding='utf-8'))
        inventory = json.loads((ROOT / 'eng/provenance/files.json').read_text(encoding='utf-8'))
        self.assertEqual(record['kind'], 'generated')
        self.assertEqual(record['verification']['kind'], 'regeneration')
        self.assertIn('not extracted from or compared with the published package bytes', record['verification']['expected'])
        self.assertEqual({row['path']: row['sha256'] for row in record['targets']},
                         {pin['previousAndMinimum']: pin['sha256'] for pin in window['pins']})
        for pin in window['pins']:
            self.assertEqual(inventory['reused'][pin['previousAndMinimum']], record['id'])
            self.assertNotIn(pin['previousAndMinimum'], inventory['firstParty'])
            self.assertEqual(hashlib.sha256((ROOT / pin['previousAndMinimum']).read_bytes()).hexdigest(), pin['sha256'])
        self.assertEqual({item['commit'] for item in record['generation']['inputs']},
                         {candidate['sourceCommit'] for version, candidate in window['candidates'].items()
                          if version in {pin['candidate'] for pin in window['pins']}})

    def test_con14_secret_scan_allowlists_bind_only_observed_public_digest_tuples(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        self.assertEqual(len(config['allowlists']), 100)
        groups = config['allowlists'][72:74]
        by_description = {row['description']: row for row in groups}
        self.assertEqual(len(groups), 2)
        self.assertEqual(set(by_description), {
            'CON.14 reviewed dependency policy public input digest',
            'CON.14 reviewed immutable dependency receipt public input digests',
        })

        policy_path = 'eng/policy/dependency-policy.json'
        receipt_path = 'eng/policy/dependency-reviews/con-14-r1.json'

        def git_text(*args):
            return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

        def git_blob(commit, path):
            return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)

        # The immutable receipt's introducing commit is the scan commit observed by hosted Security
        # run 36915931079 job 110549768370. It is found by content path so that it stays valid when
        # the same bytes are rebased onto a newer main; it requires retained (merge-commit) history.
        scan_head = git_text('log', '--diff-filter=A', '--format=%H', '--', receipt_path).splitlines()[-1]
        self.assertEqual(subprocess.run(
            ['git', 'merge-base', '--is-ancestor', scan_head, 'HEAD'], cwd=ROOT, check=False).returncode, 0)
        self.assertEqual(git_blob(scan_head, receipt_path), (ROOT / receipt_path).read_bytes().replace(b'\r\n', b'\n'))

        def parse_json_line(blob, line_number):
            lines = blob.decode('utf-8').splitlines()
            self.assertLessEqual(line_number, len(lines))
            match = re.fullmatch(r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})",?\s*', lines[line_number - 1])
            self.assertIsNotNone(match)
            return match.group(1), match.group(2)

        policy_blob = git_blob(scan_head, policy_path)
        policy_document = json.loads(policy_blob)
        policy_occurrences = [(line_number, *parse_json_line(policy_blob, line_number)) for line_number in (19, 2494)]
        self.assertEqual(len({(key, digest) for _, key, digest in policy_occurrences}), 1)
        self.assertEqual(policy_occurrences[0][1], 'eng/policy/contract-access.json')
        for _, key, digest in policy_occurrences:
            self.assertEqual(policy_document['inputHashes'][key], digest)
            self.assertEqual(digest, hashlib.sha256(git_blob(scan_head, key)).hexdigest())

        receipt_blob = git_blob(scan_head, receipt_path)
        receipt_hashes = json.loads(receipt_blob)['review']['inputHashes']
        receipt_occurrences = [(line_number, *parse_json_line(receipt_blob, line_number))
                               for line_number in (22, 79, 146, 202)]
        self.assertEqual(
            [key for _, key, _ in receipt_occurrences],
            ['eng/policy/contract-access.json', 'eng/provenance/records/dokka-combokeys-licence-r1.json',
             'eng/provenance/records/dokka-object-keys-licence-r1.json',
             'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj'])
        self.assertEqual([digest for _, _, digest in receipt_occurrences],
                         [receipt_hashes[key] for _, key, _ in receipt_occurrences])
        for _, key, digest in receipt_occurrences:
            self.assertEqual(digest, hashlib.sha256(git_blob(scan_head, key)).hexdigest())

        observations = {
            'CON.14 reviewed dependency policy public input digest': (policy_path, policy_occurrences, policy_blob),
            'CON.14 reviewed immutable dependency receipt public input digests': (receipt_path, receipt_occurrences, receipt_blob),
        }
        self.assertEqual(len(policy_occurrences) + len(receipt_occurrences), 6)
        for description, (outer_path, occurrences, source_blob) in observations.items():
            with self.subTest(source=outer_path):
                group = by_description[description]
                path_pattern = '^' + re.escape(outer_path) + '$'
                self.assertEqual(group['targetRules'], ['generic-api-key'])
                self.assertEqual(group['condition'], 'AND')
                self.assertEqual(group['regexTarget'], 'line')
                self.assertEqual(group['paths'], [path_pattern])
                rows = {(key, digest) for _, key, digest in occurrences}
                ordered_rows = sorted(rows)
                expected_patterns = [
                    r'(?s)^\s*"' + re.escape(key) + r'":\s*"' + digest + r'",?\s*$'
                    for key, digest in ordered_rows
                ]
                self.assertEqual(group['regexes'], expected_patterns)
                self.assertEqual(len(group['regexes']), len(set(group['regexes'])))
                source_lines = source_blob.decode('utf-8').splitlines()
                for line_number, key, digest in occurrences:
                    line = source_lines[line_number - 1]
                    self.assertEqual(
                        sum(re.fullmatch(pattern, line) is not None for pattern in group['regexes']), 1)
                actual_matches = []
                for line_number, line in enumerate(source_lines, start=1):
                    parsed = re.fullmatch(r'\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})",?\s*', line)
                    if parsed and (parsed.group(1), parsed.group(2)) in rows:
                        actual_matches.append((line_number, parsed.group(1), parsed.group(2)))
                self.assertEqual(actual_matches, occurrences)
                for (key, digest), pattern in zip(ordered_rows, group['regexes'], strict=True):
                    line = f'  "{key}": "{digest}",'
                    self.assertIsNotNone(re.fullmatch(pattern, line))
                    wrong_digest = '0' * 64 if digest != '0' * 64 else '1' * 64
                    unrelated_digest = 'a' * 64 if digest != 'a' * 64 else 'b' * 64
                    for rejected_line in [
                        line.replace(digest, wrong_digest),
                        line.replace('"' + key + '"', '"unrelated-key"'),
                        f'  "unrelated-key": "{unrelated_digest}",',
                        line + ' "credential": "synthetic-secret"',
                    ]:
                        self.assertIsNone(re.fullmatch(pattern, rejected_line))
                self.assertIsNone(re.fullmatch(path_pattern, outer_path + '.backup'))
                self.assertIsNone(re.fullmatch(path_pattern, 'src/secrets.json'))

    def test_con28_scan_exceptions_bind_only_the_six_observed_public_source_rows(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        groups = config['allowlists'][83:85]
        self.assertEqual(len(config['allowlists']), 100)
        self.assertEqual([group['description'] for group in groups], [
            'Reviewed CON.28 exact public contract-access source SHA256',
            'Reviewed CON.28 retained public provenance and PublicApi source SHA256 rows'])
        receipt_path = 'eng/policy/dependency-reviews/con-28-r1.json'
        policy_path = 'eng/policy/dependency-policy.json'
        # Hosted Security37528038788/job112489953061 reported these six redacted rows.
        # Locate the retained introducing commit so later compatible consumers cannot rewrite this evidence.
        scan_head = subprocess.check_output(
            ['git', 'log', '--diff-filter=A', '--format=%H', '--', receipt_path], cwd=ROOT, text=True).splitlines()[-1]
        self.assertEqual(subprocess.run(
            ['git', 'merge-base', '--is-ancestor', scan_head, 'HEAD'], cwd=ROOT, check=False).returncode, 0)
        frozen = lambda path: subprocess.check_output(['git', 'show', scan_head + ':' + path], cwd=ROOT).replace(b'\r\n', b'\n')
        receipt = json.loads(frozen(receipt_path))
        self.assertEqual(frozen(receipt_path), (ROOT / receipt_path).read_bytes().replace(b'\r\n', b'\n'))
        inputs = receipt['review']['inputHashes']
        keys = ['eng/policy/contract-access.json',
                'eng/provenance/records/dokka-combokeys-licence-r1.json',
                'eng/provenance/records/dokka-object-keys-licence-r1.json',
                'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        for key in keys:
            self.assertEqual(inputs[key], hashlib.sha256(frozen(key)).hexdigest())
        predecessor = receipt['review']['previousReceipt']
        self.assertEqual(predecessor, 'eng/policy/dependency-reviews/con-25-r1.json')
        self.assertEqual(receipt['closure'], json.loads(frozen(predecessor))['closure'])
        expected_paths = [
            r'^eng/policy/(dependency-policy\.json|dependency-reviews/con-28-r1\.json)$',
            r'^eng/policy/dependency-reviews/con-28-r1\.json$']
        for group, path_pattern, selected in zip(groups, expected_paths, [keys[:1], keys[1:]], strict=True):
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path_pattern])
            self.assertEqual(group['regexes'], [
                rf'(?s)^\s*"{re.escape(key)}":\s*"{inputs[key]}",?\s*$' for key in selected])
            for key, pattern in zip(selected, group['regexes'], strict=True):
                line = f'  "{key}": "{inputs[key]}",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for denied in [line.replace(inputs[key], '0' * 64), line.replace(key, 'api_key'),
                               line + ' "credential": "synthetic-secret"', '"credential": "synthetic-secret" ' + line]:
                    self.assertIsNone(re.fullmatch(pattern, denied))
            for denied in [receipt_path + '.backup', 'src/secrets.json', 'eng/policy/dependency-reviews/con-28-r2.json']:
                self.assertIsNone(re.fullmatch(path_pattern, denied))
        self.assertIsNotNone(re.fullmatch(expected_paths[0], policy_path))
        self.assertIsNotNone(re.fullmatch(expected_paths[0], receipt_path))
        self.assertIsNone(re.fullmatch(expected_paths[1], policy_path))
        observed = {policy_path: [19, 2515], receipt_path: [22, 85, 154, 210]}
        permissions = set()
        matches = 0
        for path, line_numbers in observed.items():
            lines = frozen(path).decode('utf-8').splitlines()
            selected_groups = [group for group in groups if re.fullmatch(group['paths'][0], path)]
            matched_numbers = []
            for number, line in enumerate(lines, 1):
                patterns = [pattern for group in selected_groups for pattern in group['regexes']]
                if any(re.fullmatch(pattern, line) for pattern in patterns):
                    self.assertEqual(sum(re.fullmatch(pattern, line) is not None for pattern in patterns), 1)
                    matched_numbers.append(number)
                    key, digest = next(iter(json.loads('{' + line.strip().rstrip(',') + '}').items()))
                    permissions.add(('generic-api-key', path, key, digest))
            self.assertEqual(matched_numbers, line_numbers)
            matches += len(matched_numbers)
        self.assertEqual(matches, 6)
        self.assertEqual(len(permissions), 5)
        canonical = ''.join('\t'.join(row) + '\n' for row in sorted(permissions)).encode('utf-8')
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         'b68979869fe5ae4883fc60689a9411cd34781b4007f1bdf32ea44522c5d3b9d7')

    def test_con26_consumer_scan_exceptions_bind_only_four_public_access_hash_rows(self):
        # Security37540778304/job112532979781 and successor112534023652 observed exactly four rows.
        config_bytes = (ROOT / '.gitleaks.toml').read_bytes().replace(b'\r\n', b'\n')
        config = tomllib.loads(config_bytes.decode())
        previous = subprocess.check_output(['git', 'show',
            '83c9bd64607355fa3ebc2eef09f2fa2341e7a6ad:.gitleaks.toml'], cwd=ROOT).replace(b'\r\n', b'\n')
        self.assertEqual(config['allowlists'][:85] + config['allowlists'][89:89 + len(tomllib.loads(previous.decode())['allowlists']) - 85], tomllib.loads(previous.decode())['allowlists'])
        self.assertEqual(config['allowlists'][:85] + config['allowlists'][89:92], tomllib.loads(previous.decode())['allowlists'])
        self.assertEqual(len(config['allowlists']), 100)
        groups = config['allowlists'][92:94]
        self.assertEqual([group['description'] for group in groups], [
            'CON.26 actual published policy consumer final public access SHA256',
            'CON.26 actual accepted cohort core public access SHA256'])
        key = 'eng/policy/contract-access.json'
        final_sha = '9ca13f767b08d3d28cac9450f2cb7ccb540cb3928978ad9810d70156c04f8307'
        core_sha = '17549663c7fd55d44de7c75f2903c2c78e72442a38739bf9a8218a7c28cf53e5'
        source = '171b12fc73c990bb51d05cbbd79a45bcb00b1bf4'
        expected_paths = [r'^eng/policy/(dependency-policy\.json|dependency-reviews/con-26-r2\.json)$',
                          r'^eng/policy/dependency-reviews/con-26-r1\.json$']
        for group, path, digest in zip(groups, expected_paths, [final_sha, core_sha], strict=True):
            self.assertEqual(set(group), {'description', 'targetRules', 'condition', 'paths', 'regexTarget', 'regexes'})
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertNotIn('aws-access-token', group['targetRules'])
            self.assertNotIn('github-pat', group['targetRules'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path])
            pattern = rf'(?s)^\s*"eng/policy/contract-access\.json":\s*"{digest}",?\s*$'
            self.assertEqual(group['regexes'], [pattern])
            line = f'  "{key}": "{digest}",'
            self.assertIsNotNone(re.fullmatch(pattern, line))
            for rejected in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                             line.replace(digest, core_sha if digest == final_sha else final_sha),
                             line + ' "credential": "synthetic-secret"',
                             line + '\n"credential": "synthetic-secret"',
                             '"credential": "synthetic-secret" ' + line]:
                self.assertIsNone(re.fullmatch(pattern, rejected))
            for rejected in ['src/secrets.json', 'eng/policy/dependency-reviews/con-26-r3.json',
                             'eng/policy/dependency-policy.json.backup']:
                self.assertIsNone(re.fullmatch(path, rejected))
        frozen = lambda path: subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT).replace(b'\r\n', b'\n')
        for commit, digest in [('94ecd02ae37f48806226ae79c8e73ab78b108332', core_sha), (source, final_sha)]:
            actual = subprocess.check_output(['git', 'show', commit + ':' + key], cwd=ROOT).replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(actual).hexdigest(), digest)
        observed = {POLICY: [19, 2546], 'eng/policy/dependency-reviews/con-26-r1.json': [22],
                    'eng/policy/dependency-reviews/con-26-r2.json': [22]}
        tuples, occurrences = set(), 0
        for path, line_numbers in observed.items():
            selected = [group for group in groups if re.fullmatch(group['paths'][0], path)]
            self.assertEqual(len(selected), 1)
            matched = []
            for number, line in enumerate(frozen(path).decode().splitlines(), 1):
                if re.fullmatch(selected[0]['regexes'][0], line):
                    matched.append(number)
                    actual_key, digest = next(iter(json.loads('{' + line.strip().rstrip(',') + '}').items()))
                    self.assertEqual(actual_key, key)
                    tuples.add(('generic-api-key', path, actual_key, digest))
            self.assertEqual(matched, line_numbers)
            occurrences += len(matched)
        self.assertEqual(occurrences, 4)
        self.assertEqual(len(tuples), 3)
        # Path AND line must reject swapping the core/final digests between owning receipts.
        self.assertIsNone(re.fullmatch(expected_paths[0], 'eng/policy/dependency-reviews/con-26-r1.json'))
        self.assertIsNone(re.fullmatch(expected_paths[1], POLICY))
        self.assertIsNone(re.fullmatch(expected_paths[1], 'eng/policy/dependency-reviews/con-26-r2.json'))

    def test_con26_gov25_consumer_scan_binds_six_observed_rows_and_four_public_sources(self):
        # Actual pinned8.30.1 full-history diagnostic at immutable b321 observed exactly these six public SHA rows.
        source = 'b32193784f17b3c6c3689fbb4651b60a732703bd'
        frozen = lambda path: subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT).replace(b'\r\n', b'\n')
        config_bytes = (ROOT / '.gitleaks.toml').read_bytes().replace(b'\r\n', b'\n')
        previous = frozen('.gitleaks.toml')
        config = tomllib.loads(config_bytes.decode())
        self.assertEqual(config['allowlists'][:85] + config['allowlists'][89:89 + len(tomllib.loads(previous.decode())['allowlists']) - 85], tomllib.loads(previous.decode())['allowlists'])
        self.assertEqual(config['allowlists'][:85] + config['allowlists'][89:94], tomllib.loads(previous.decode())['allowlists'])
        self.assertEqual(len(config['allowlists']), 100)
        groups = config['allowlists'][94:96]
        self.assertEqual([group['description'] for group in groups], [
            'CON.26 actual GOV25 published consumer public access SHA256',
            'CON.26 immutable receipt r3 historical public source SHA256 rows'])
        access = 'eng/policy/contract-access.json'
        receipt = 'eng/policy/dependency-reviews/con-26-r3.json'
        tuples = {
            access: 'e8c200306c928f898871194663910ec244caafe4baf9fc9e1c1ce30e2becd346',
            'eng/provenance/records/dokka-combokeys-licence-r1.json': '75219d61672002f0bb242fed0fd93a0886f07d944e0b9e1b1f72132f59df1b41',
            'eng/provenance/records/dokka-object-keys-licence-r1.json': '55621ecc7032745ca46e56d13133dc22a3bd808d80966d737427b5d6fc5bd096',
            'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj': '986b7a97734cd5d0630e548da897869de322a112c087c2d0df6a0bfc98b8784c',
        }
        expected_paths = [r'^eng/policy/(dependency-policy\.json|dependency-reviews/con-26-r3\.json)$',
                          r'^eng/policy/dependency-reviews/con-26-r3\.json$']
        permitted = [[access], list(tuples)[1:]]
        for group, path, keys in zip(groups, expected_paths, permitted, strict=True):
            self.assertEqual(set(group), {'description', 'targetRules', 'condition', 'paths', 'regexTarget', 'regexes'})
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path])
            expected = [rf'(?s)^\s*"{re.escape(key)}":\s*"{tuples[key]}",?\s*$' for key in keys]
            self.assertEqual(group['regexes'], expected)
            for key, pattern in zip(keys, expected, strict=True):
                digest = tuples[key]
                line = f'  "{key}": "{digest}",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                self.assertEqual(hashlib.sha256(frozen(key)).hexdigest(), digest)
                for rejected in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                                 line.replace(digest, next(value for value in tuples.values() if value != digest)),
                                 line + ' "credential": "synthetic-secret"',
                                 line + '\n"credential": "synthetic-secret"',
                                 '"credential": "synthetic-secret" ' + line,
                                 line.replace('"' + digest + '"', digest)]:
                    self.assertIsNone(re.fullmatch(pattern, rejected))
            for rejected in ['src/secrets.json', POLICY + '.backup',
                             'eng/policy/dependency-reviews/con-26-r1.json',
                             'eng/policy/dependency-reviews/con-26-r2.json',
                             'eng/policy/dependency-reviews/con-26-r4.json']:
                self.assertIsNone(re.fullmatch(path, rejected))
        # The three historical permissions apply to the exact r3 receipt only, never the mutable policy.
        self.assertIsNone(re.fullmatch(expected_paths[1], POLICY))
        observed = {POLICY: [19, 2516], receipt: [22, 85, 154, 211]}
        permissions, occurrences = set(), 0
        for path, line_numbers in observed.items():
            selected = [group for group in groups if re.fullmatch(group['paths'][0], path)]
            matched = []
            for number, line in enumerate(frozen(path).decode().splitlines(), 1):
                if any(re.fullmatch(pattern, line) for group in selected for pattern in group['regexes']):
                    matched.append(number)
                    key, digest = next(iter(json.loads('{' + line.strip().rstrip(',') + '}').items()))
                    self.assertEqual(tuples[key], digest)
                    permissions.add(('generic-api-key', path, key, digest))
            self.assertEqual(matched, line_numbers)
            occurrences += len(matched)
        self.assertEqual(occurrences, 6)
        self.assertEqual(len(permissions), 5)
        self.assertEqual(len({(key, digest) for _, _, key, digest in permissions}), 4)


    def test_con26_regression_scan_binds_only_four_verified_public_digest_lines(self):
        # The pinned339-commit scan reported four exact public fixture constants; keep history and scope explicit.
        prior_source = 'cea00fdaa0bfa981e9515b0807b87077d920c6e3'
        fixture_source = '5fb50bcf2b4b665efcd3bcac8fa1a533e166ea3f'
        public_source = 'b32193784f17b3c6c3689fbb4651b60a732703bd'
        tracked = 'tests/tooling/test_dependency_admission.py'
        frozen = lambda source, path: subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT).replace(b'\r\n', b'\n')
        previous = frozen(prior_source, '.gitleaks.toml')
        current = (ROOT / '.gitleaks.toml').read_bytes().replace(b'\r\n', b'\n')
        config = tomllib.loads(current.decode())
        self.assertEqual(config['allowlists'][:85] + config['allowlists'][89:89 + len(tomllib.loads(previous.decode())['allowlists']) - 85], tomllib.loads(previous.decode())['allowlists'])
        self.assertEqual(config['allowlists'][:85] + config['allowlists'][89:96], tomllib.loads(previous.decode())['allowlists'])
        self.assertEqual(len(config['allowlists']), 100)
        group = config['allowlists'][96]
        self.assertEqual(set(group), {'description', 'targetRules', 'condition', 'paths', 'regexTarget', 'regexes'})
        self.assertEqual(group['description'], 'CON.26 regression fixture exact verified public source SHA256 lines')
        self.assertEqual(group['targetRules'], ['generic-api-key'])
        self.assertEqual(group['condition'], 'AND')
        self.assertEqual(group['regexTarget'], 'line')
        self.assertEqual(group['paths'], [r'^tests/tooling/test_dependency_admission\.py$'])
        lines = frozen(fixture_source, tracked).decode().splitlines()
        numbers = [3220, 3221, 3222, 3223]
        self.assertEqual(len(group['regexes']), 4)
        observations = []
        for index, number in enumerate(numbers):
            line = lines[number - 1]
            parsed = re.fullmatch(r"\s*(access|'([^']+)'):\s*'([a-f0-9]{64})',", line)
            self.assertIsNotNone(parsed)
            line_key, quoted_key, digest = parsed.groups()
            source_path = quoted_key or 'eng/policy/contract-access.json'
            if quoted_key is None:
                self.assertIn("        access = 'eng/policy/contract-access.json'", lines)
            self.assertEqual(hashlib.sha256(frozen(public_source, source_path)).hexdigest(), digest)
            expected = rf"(?s)^\s*{re.escape(line_key)}:\s*'{digest}',\s*$"
            self.assertEqual(group['regexes'][index], expected)
            matches = lambda path, text, rule='generic-api-key': (rule in group['targetRules']
                and any(re.fullmatch(pattern, path) for pattern in group['paths'])
                and any(re.fullmatch(pattern, text) for pattern in group['regexes']))
            self.assertTrue(matches(tracked, line))
            for wrong in ['tests/tooling/test_dependency_admissionXpy', 'x/' + tracked,
                          tracked + '.backup', 'eng/policy/dependency-policy.json']:
                self.assertFalse(matches(wrong, line))
            self.assertFalse(matches(tracked, line, 'github-pat'))
            self.assertFalse(matches(tracked, line.replace(digest, '0' * 64)))
            self.assertFalse(matches(tracked, line.replace(line_key, 'changed_key', 1)))
            self.assertFalse(matches(tracked, line + " token='adjacent-credential'"))
            self.assertFalse(matches(tracked, line + "\n token='adjacent-credential'"))
            self.assertFalse(matches(tracked, 'wrapped(' + line + ')'))
            self.assertFalse(matches(tracked, line.replace("'" + digest + "'", '"' + digest + '"')))
            observations.append((source_path, digest))
        self.assertEqual(len(observations), 4)
        self.assertEqual(len(set(observations)), 4)



    def test_con31_scan_allowances_preserve_the_accepted_prefix_and_only_exact_public_tuples(self):
        config = tomllib.loads((ROOT / '.gitleaks.toml').read_text(encoding='utf-8'))
        accepted = tomllib.loads(subprocess.check_output(
            ['git', 'show', '8715f6e2462153fac44bccac2dd9e8b55adafc5f:.gitleaks.toml'], cwd=ROOT).decode('utf-8'))
        self.assertEqual(config['extend'], accepted['extend'])
        self.assertEqual(len(config['allowlists']), 100)
        self.assertEqual(config['allowlists'][:85], accepted['allowlists'])
        access_hashes = [
            '7f7006a49be969a4c8855f1f05f916117279cfe04076f7b6a10bc64e4dd83ae5',
            'bd3cd1d7e7fb8f7e06e48930607af469db4134e41a649d4b8251933936a6e686',
            '80e6402d69fee1913bfffbb0ebc8006c741d37f47f44a0b0536339881ce219dc',
        ]
        keys = ['eng/policy/contract-access.json',
                'eng/provenance/records/dokka-combokeys-licence-r1.json',
                'eng/provenance/records/dokka-object-keys-licence-r1.json',
                'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        shared = ['75219d61672002f0bb242fed0fd93a0886f07d944e0b9e1b1f72132f59df1b41',
                  '55621ecc7032745ca46e56d13133dc22a3bd808d80966d737427b5d6fc5bd096',
                  '986b7a97734cd5d0630e548da897869de322a112c087c2d0df6a0bfc98b8784c']
        paths = ['eng/policy/dependency-policy.json'] + [f'eng/policy/dependency-reviews/con-31-r{n}.json' for n in (1, 2, 3)]
        rows = [[(keys[0], digest) for digest in access_hashes]] + [list(zip(keys, [digest, *shared], strict=True)) for digest in access_hashes]
        self.assertEqual([len(group['regexes']) for group in config['allowlists'][85:89]], [3, 4, 4, 4])
        for group, path, permitted in zip(config['allowlists'][85:89], paths, rows, strict=True):
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], ['^' + path.replace('.', r'\.') + '$'])
            self.assertEqual(group['regexes'], [rf'(?s)^\s*"{re.escape(key)}":\s*"{digest}",?\s*$' for key, digest in permitted])
            for (key, digest), pattern in zip(permitted, group['regexes'], strict=True):
                line = f'  "{key}": "{digest}",'
                self.assertIsNotNone(re.fullmatch(pattern, line))
                for denied in [line.replace(digest, '0' * 64), line.replace(key, 'api_key'),
                               line + ' "credential": "synthetic-secret"', '"credential": "synthetic-secret" ' + line,
                               line.replace(key, key + '.backup')]:
                    self.assertIsNone(re.fullmatch(pattern, denied))
            for denied in [path + '.backup', 'src/secrets.json', 'eng/policy/dependency-reviews/con-31-r4.json']:
                self.assertIsNone(re.fullmatch(group['paths'][0], denied))
        for n, digest in enumerate(access_hashes, 1):
            path = paths[n]
            introducing = subprocess.check_output(
                ['git', 'log', '--diff-filter=A', '--format=%H', '--', path], cwd=ROOT, text=True).splitlines()[-1]
            receipt = json.loads(subprocess.check_output(['git', 'show', introducing + ':' + path], cwd=ROOT))
            for key, expected in zip(keys, [digest, *shared], strict=True):
                frozen = subprocess.check_output(['git', 'show', introducing + ':' + key], cwd=ROOT).replace(b'\r\n', b'\n')
                self.assertEqual(hashlib.sha256(frozen).hexdigest(), expected)
                self.assertEqual(receipt['review']['inputHashes'][key], expected)

    def test_con26_gov26_scan_binds_only_measured_historical_and_canonical_public_rows(self):
        historical = 'b5e8842ed2d4af596622f21d9a63ead49b65661f'
        canonical = '69f93397d8b19a0f900a4b02a9ae49b19f642f6e'
        prior = '8c35cc81562db8866291235c95dcaa5f9b828311'
        frozen = lambda commit, path: subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT).replace(b'\r\n', b'\n')
        config_bytes = (ROOT / '.gitleaks.toml').read_bytes().replace(b'\r\n', b'\n')
        previous = frozen(prior, '.gitleaks.toml')
        self.assertTrue(config_bytes.startswith(previous))
        config = tomllib.loads(config_bytes.decode())
        self.assertEqual(config['allowlists'][:97], tomllib.loads(previous.decode())['allowlists'])
        self.assertEqual(len(config['allowlists']), 100)
        groups = config['allowlists'][97:100]
        self.assertEqual([len(group['regexes']) for group in groups], [1, 3, 1])
        self.assertEqual([group['description'] for group in groups], [
            'CON.26 actual GOV26 historical published consumer public access SHA256',
            'CON.26 historical receipt r4 public source SHA256 rows',
            'CON.26 actual accepted CON31 canonical candidate public access SHA256'])
        access = 'eng/policy/contract-access.json'
        receipt = 'eng/policy/dependency-reviews/con-26-r4.json'
        keys = [access, 'eng/provenance/records/dokka-combokeys-licence-r1.json',
                'eng/provenance/records/dokka-object-keys-licence-r1.json',
                'src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj']
        hashes = json.loads(frozen(historical, receipt))['review']['inputHashes']
        current = json.loads(frozen(canonical, POLICY))['inputHashes']
        expected = [
            (historical, r'^eng/policy/(dependency-policy\.json|dependency-reviews/con-26-r4\.json)$', [(access, hashes[access])]),
            (historical, r'^eng/policy/dependency-reviews/con-26-r4\.json$', [(key, hashes[key]) for key in keys[1:]]),
            (canonical, r'^eng/policy/(dependency-policy\.json|dependency-reviews/con-26-r1\.json)$', [(access, current[access])])]
        self.assertNotEqual(hashes[access], current[access])
        for group, (commit, path, values) in zip(groups, expected, strict=True):
            self.assertEqual(set(group), {'description', 'targetRules', 'condition', 'paths', 'regexTarget', 'regexes'})
            self.assertEqual(group['targetRules'], ['generic-api-key'])
            self.assertEqual(group['condition'], 'AND')
            self.assertEqual(group['regexTarget'], 'line')
            self.assertEqual(group['paths'], [path])
            patterns = [rf'(?s)^\s*"{re.escape(key)}":\s*"{digest}",?\s*$' for key, digest in values]
            self.assertEqual(group['regexes'], patterns)
            for key, digest in values:
                self.assertEqual(hashlib.sha256(frozen(commit, key)).hexdigest(), digest)
                line = f'  "{key}": "{digest}",'
                matches = lambda name, text, rule='generic-api-key': (rule in group['targetRules']
                    and any(re.fullmatch(item, name) for item in group['paths'])
                    and any(re.fullmatch(item, text) for item in group['regexes']))
                good_path = receipt if commit == historical else 'eng/policy/dependency-reviews/con-26-r1.json'
                self.assertTrue(matches(good_path, line))
                for rejected in [good_path + '.backup', 'x/' + good_path, 'src/secrets.json',
                                 'eng/policy/dependency-reviews/con-26-r2.json']:
                    self.assertFalse(matches(rejected, line))
                self.assertFalse(matches(good_path, line, 'github-pat'))
                for rejected in [line.replace(digest, '0' * 64), line.replace(key, 'credential'),
                                 line + ' "token": "adjacent-secret"', line + '\n"token": "adjacent-secret"',
                                 '"token": "adjacent-secret" ' + line, line.replace('"' + digest + '"', digest),
                                 '"credential": "synthetic-secret"']:
                    self.assertFalse(matches(good_path, rejected))
        # Current versus historical access tuples never cross receipt authority.
        self.assertIsNone(re.fullmatch(groups[0]['paths'][0], 'eng/policy/dependency-reviews/con-26-r1.json'))
        self.assertIsNone(re.fullmatch(groups[2]['paths'][0], receipt))
        self.assertIsNone(re.fullmatch(groups[1]['paths'][0], POLICY))
        observations = [(historical, POLICY, [19, 2516]), (historical, receipt, [22, 85, 154, 211]),
                        (canonical, POLICY, [19, 2519]), (canonical, 'eng/policy/dependency-reviews/con-26-r1.json', [22])]
        tuples, inputs, count = set(), set(), 0
        for commit, path, numbers in observations:
            matched = []
            for number, line in enumerate(frozen(commit, path).decode().splitlines(), 1):
                if any(any(re.fullmatch(item, path) for item in group['paths'])
                       and any(re.fullmatch(item, line) for item in group['regexes']) for group in groups):
                    matched.append(number)
                    key, digest = next(iter(json.loads('{' + line.strip().rstrip(',') + '}').items()))
                    self.assertEqual(hashlib.sha256(frozen(commit, key)).hexdigest(), digest)
                    tuples.add((path, key, digest)); inputs.add((key, digest)); count += 1
            self.assertEqual(matched, numbers)
        self.assertEqual(count, 9)
        self.assertEqual(len(tuples), 7)
        self.assertEqual(len(inputs), 5)


if __name__ == '__main__':
    unittest.main()
