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
        self.assertEqual(len(config['allowlists']), 51)
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
        self.assertEqual([len(item['regexes']) for item in config['allowlists']], [4, 2, 15, 4, 15, 45, 60, 4, 4, 4, 4, 4, 60, 2, 4, 15, 4, 3, 2, 1, 4, 1, 4, 1, 4, 3, 7, 164, 4, 7, 164, 2, 6, 4, 8, 6, 10, 1, 4, 164, 1, 4, 164, 2, 5, 197, 1, 4, 208, 5, 1])

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
        committed_policy = json.loads(subprocess.check_output(
            ['git', 'show', head + ':' + policy_path], cwd=ROOT, text=True))
        committed_receipt = json.loads(subprocess.check_output(
            ['git', 'show', head + ':' + receipt_path], cwd=ROOT, text=True))
        self.assertEqual(committed_policy, policy)
        self.assertEqual(committed_receipt, receipt)
        old_access_digest = historical_policy['inputHashes'][access_key]
        current_access_digest = policy['inputHashes'][access_key]
        con08_access_digest = receipt['review']['inputHashes'][access_key]
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
        active_access_line = f'  "{access_key}": "{current_access_digest}",'
        self.assertFalse(any(re.fullmatch(pattern, active_access_line) for pattern in ext02_group['regexes']))
        self.assertTrue(any(re.fullmatch(pattern, active_access_line) for pattern in con09_policy_group['regexes']))
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
        current_policy = committed_json(head, policy_path)
        ext02_receipt = json.loads((ROOT / 'eng/policy/dependency-reviews/ext-02-r1.json')
                                   .read_text(encoding='utf-8'))
        old_access_digest = base_policy['inputHashes'][access_key]
        active_access_digest = current_policy['inputHashes'][access_key]
        self.assertEqual(old_access_digest,
                         ext02_receipt['review']['inputHashes'][access_key])
        self.assertEqual(active_access_digest,
                         '86d2b588471d30595c5b1eeb8ea99e180f7cd42b52fb2452a5b6b476e529a533')
        self.assertNotEqual(active_access_digest, old_access_digest)
        policy_rows = {(access_key, active_access_digest)}
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
        current_policy_text = subprocess.check_output(
            ['git', 'show', head + ':' + policy_path], cwd=ROOT, text=True)
        self.assertEqual(len(matching_lines(historical_policy_text, policy_group)), 0)
        self.assertEqual(len(matching_lines(current_policy_text, policy_group)), 2)

        ext02_policy_group = next(row for row in config['allowlists']
                                  if row['description'] == 'Reviewed EXT.02 exact public dependency-input hashes' and
                                  row['paths'] == [r'^eng/policy/dependency-policy\.json$'])
        con08_policy_group = next(row for row in config['allowlists']
                                  if row['description'].startswith('CON08 exact observed') and
                                  row['paths'] == [path_patterns[policy_path]])
        old_line = f'  "{access_key}": "{old_access_digest}",'
        active_line = f'  "{access_key}": "{active_access_digest}",'
        self.assertTrue(any(re.fullmatch(pattern, old_line) for pattern in ext02_policy_group['regexes']))
        self.assertFalse(any(re.fullmatch(pattern, active_line) for pattern in ext02_policy_group['regexes']))
        self.assertFalse(any(re.fullmatch(pattern, active_line) for pattern in con08_policy_group['regexes']))
        self.assertTrue(any(re.fullmatch(pattern, active_line) for pattern in policy_group['regexes']))

        self.assertEqual(sum(len(rows) for rows in expected_rows.values()), 214)
        self.assertEqual(208 + 5 + 2, 215)


if __name__ == '__main__':
    unittest.main()

