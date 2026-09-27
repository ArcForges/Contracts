# SPDX-License-Identifier: Apache-2.0
"""Admission rejection tests use committed inputs and synthetic mutations only."""
import copy
import json
import hashlib
import subprocess
from pathlib import Path
import sys
import re
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eng'))
from dependency_admission import ROOT, POLICY, audit, inventory, immutable_coordinates, major_upgrade, pinned, stable_dependency, validate


class DependencyAdmission(unittest.TestCase):
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
        self.assertEqual(len(config['allowlists']), 32)
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
        self.assertEqual([len(item['regexes']) for item in config['allowlists']], [4, 2, 15, 4, 15, 45, 60, 4, 4, 4, 4, 4, 60, 2, 4, 15, 4, 3, 2, 1, 4, 1, 4, 1, 4, 3, 7, 164, 2, 6, 4, 8])


if __name__ == '__main__':
    unittest.main()

