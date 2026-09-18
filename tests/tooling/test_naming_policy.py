# SPDX-License-Identifier: Apache-2.0
"""Adversarial naming checks over real temporary Git repositories."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eng'))
from check_naming import POLICY_PATH, declaration_hash, load_policy, scan_repository, validate_policy


class NamingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='naming-git-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.policy = load_policy()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Naming Test')
        self.git('config', 'user.email', 'naming@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        self.git('remote', 'add', 'origin', 'https://github.com/ArcForges/Contracts.git')
        self.write('README.md', b'Current contract inventory.\n')
        self.git('add', 'README.md')
        self.git('-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
        self.forbidden = self.policy['forbiddenNames'][0]['name']
        self.reference = self.policy['referenceRepositoryNames'][0]

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True).stdout

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def scan(self, policy=None):
        return scan_repository(self.root, 'Contracts', policy or self.policy)

    def exception(self, path, data, names=None):
        policy = deepcopy(self.policy)
        policy['provenanceExceptions'] = [{'repository': 'Contracts', 'path': path,
            'sha256': hashlib.sha256(data).hexdigest(), 'names': names or [self.reference],
            'reason': 'Exact upstream identity in a reviewed provenance record.'}]
        return validate_policy(policy)

    def test_current_identity_set_and_no_unnecessary_exceptions(self):
        self.assertEqual({p['id'] for p in self.policy['products']}, {'arcnotes', 'arcscope', 'arcslate', 'companion'})
        self.assertEqual(len(self.policy['provenanceExceptions']), 1)
        self.assertEqual(self.policy['provenanceExceptions'][0]['repository'], 'DesktopPlatform')
        self.assertEqual(self.scan()['status'], 'pass')
        self.assertFalse(self.scan()['dirty'])

    def test_all_forbidden_names_in_mixed_case_identifier_substrings(self):
        for item in self.policy['forbiddenNames']:
            with self.subTest(name=item['name']):
                self.write('src/new.cs', ('class Prefix' + item['name'].swapcase() + 'Adapter {}').encode())
                self.assertEqual(self.scan()['status'], 'fail')

    def test_tracked_generated_ignored_source_is_still_scanned(self):
        self.write('.gitignore', b'generated/\n')
        self.write('generated/client.cs', self.forbidden.encode())
        self.git('add', '-f', 'generated/client.cs')
        self.assertEqual(self.scan()['status'], 'fail')

    def test_root_config_tests_and_docs_are_in_inventory(self):
        for path in ['config.json', 'tests/fixture.json', 'docs/old-notes.md', 'assets/strings.resx']:
            with self.subTest(path=path):
                target = self.write(path, self.forbidden.encode())
                self.assertEqual(self.scan()['status'], 'fail')
                target.unlink()

    def test_ignored_build_outputs_are_not_source(self):
        self.write('.gitignore', b'artifacts/\n')
        self.write('artifacts/package.bin', self.forbidden.encode())
        self.assertEqual(self.scan()['status'], 'pass')

    def test_forbidden_paths_fail_even_with_clean_contents(self):
        self.write('src/' + self.forbidden.lower() + 'Client.cs', b'Clean content')
        self.assertTrue(any(f['kind'] == 'forbidden path' for f in self.scan()['findings']))

    def test_utf16_resources_and_binary_bytes(self):
        for encoding in ['utf-8', 'utf-16-le', 'utf-16-be']:
            with self.subTest(encoding=encoding):
                self.write('assets/resource.dat', b'\xff' + self.forbidden.swapcase().encode(encoding))
                self.assertEqual(self.scan()['status'], 'fail')

    def test_missing_tracked_file_fails_closed(self):
        (self.root / 'README.md').unlink()
        self.assertTrue(any(f['kind'] == 'unreadable inventory file' for f in self.scan()['findings']))

    def test_symlink_git_mode_is_rejected(self):
        blob = self.git('rev-parse', 'HEAD:README.md').decode().strip()
        self.git('update-index', '--add', '--cacheinfo', f'120000,{blob},link')
        self.write('link', b'README.md')
        self.assertTrue(any(f['kind'] == 'unsupported Git entry' for f in self.scan()['findings']))

    def test_provenance_exception_requires_exact_hash_and_is_used(self):
        path = 'docs/provenance/media-reference.md'
        data = ('Reference repository: ' + self.reference + '\n').encode()
        self.write(path, data)
        policy = self.exception(path, data)
        self.assertEqual(self.scan()['status'], 'fail')
        self.assertEqual(self.scan(policy)['exceptionsUsed'], [path])
        self.assertEqual(self.scan(policy)['status'], 'pass')
        self.write(path, data + b'changed')
        self.assertEqual(self.scan(policy)['status'], 'fail')

    def test_exception_does_not_admit_other_terms_or_identifiers(self):
        path = 'eng/provenance/media-reference.json'
        for content in [self.reference + 'Adapter', self.reference + ' ' + self.forbidden]:
            with self.subTest(content=content):
                data = content.encode()
                self.write(path, data)
                self.assertEqual(self.scan(self.exception(path, data))['status'], 'fail')

    def test_stale_absent_and_unused_exceptions_fail(self):
        path = 'docs/provenance/media-reference.md'
        data = b'No reference name appears.'
        policy = self.exception(path, data)
        self.assertEqual(self.scan(policy)['status'], 'fail')
        self.write(path, data)
        self.assertEqual(self.scan(policy)['status'], 'fail')

    def test_exception_cannot_target_source_glob_or_other_forbidden_name(self):
        for path in ['src/reference.cs', 'docs/provenance/*.md', 'docs/provenance/../../src/a.md']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.exception(path, b'data')
        with self.assertRaises(ValueError):
            self.exception('docs/provenance/source.md', b'data', [self.forbidden])

    def test_policy_is_not_a_free_text_exemption(self):
        policy = deepcopy(self.policy)
        policy['forbiddenNames'][0]['note'] = self.forbidden
        with self.assertRaises(ValueError):
            validate_policy(policy)
        policy = deepcopy(self.policy)
        policy['extra'] = 'arbitrary bypass'
        with self.assertRaises(ValueError):
            validate_policy(policy)

    def test_duplicate_json_keys_and_incomplete_forbidden_set_fail(self):
        duplicate = POLICY_PATH.read_text(encoding='utf-8').replace('{', '{"schemaVersion": 0,', 1)
        path = self.write('policy.json', duplicate.encode())
        with self.assertRaises(ValueError):
            load_policy(path)
        policy = deepcopy(self.policy)
        policy['forbiddenNames'].pop()
        with self.assertRaises(ValueError):
            validate_policy(policy)

    def test_invalid_product_and_association_ownership_fail(self):
        for mutation in ('retired', 'association', 'duplicate'):
            policy = deepcopy(self.policy)
            if mutation == 'retired':
                policy['products'][0]['id'] = policy['retiredProductIds'][0]
            elif mutation == 'association':
                policy['products'][0]['fileAssociations'] = policy['products'][1]['fileAssociations']
            else:
                policy['products'][0]['applicationIds'] = policy['products'][1]['applicationIds']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_policy(policy)

    def test_wrong_owner_missing_namespace_and_lost_migration_fail(self):
        for key, value in [('owners', ['Cloud']), ('namespaces', ['Unowned']), ('legacyApplicationIds', [])]:
            policy = deepcopy(self.policy)
            policy['products'][3][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_policy(policy)

    def test_copied_policy_path_is_not_a_second_authority(self):
        self.write('eng/policy/product-names.json', POLICY_PATH.read_bytes())
        self.assertEqual(self.scan()['status'], 'fail')

    def test_legacy_artifact_exception_cannot_expand(self):
        for key, value in [('path', 'artifacts/other.json'), ('repository', 'Contracts'), ('sha256', '0' * 64)]:
            policy = deepcopy(self.policy)
            policy['provenanceExceptions'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_policy(policy)

    def test_fake_repository_identity_fails(self):
        self.git('remote', 'set-url', 'origin', 'https://example.invalid/ArcForges/Contracts.git')
        with self.assertRaises(ValueError):
            self.scan()

    def test_cli_real_git_scan_report_and_failure_exit_code(self):
        command = [sys.executable, str(POLICY_PATH.parents[1] / 'check_naming.py'),
                   '--repository', f'Contracts={self.root}', '--report', str(self.root / 'artifacts/report.json')]
        self.write('.gitignore', b'artifacts/\n')
        result = subprocess.run(command, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.root / 'artifacts/report.json').read_text())
        self.assertEqual(report['repositories'][0]['commit'], self.git('rev-parse', 'HEAD').decode().strip())
        self.assertEqual(report['repositories'][0]['status'], 'pass')
        self.write('source.txt', self.forbidden.encode())
        result = subprocess.run(command, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads((self.root / 'artifacts/report.json').read_text())['repositories'][0]['status'], 'fail')


    def derived_fixture(self):
        self.git('remote', 'set-url', 'origin', 'https://github.com/ArcForges/DesktopPlatform.git')
        policy = deepcopy(self.policy)
        policy['provenanceExceptions'] = []
        registration = policy['derivedDeclarations'][0]
        value = {'schemaVersion': 1, 'license': 'AGPL-3.0-only',
                 'source': {'repository': 'ArcForges/ArcForges-Design', 'commit': registration['designCommit'],
                            'path': 'docs/requirements/01-normative-glossary-and-invariants.md',
                            'sha256': registration['sourceSha256']},
                 'spaces': [{'name': x, 'label': x, 'rule': 'A separate space.'}
                            for x in ('domain', 'wire', 'UI', 'storage', 'commercial')],
                 'terms': [{'section': '1', 'line': 20, 'term': 'Current', 'names': ['Current'],
                            'namespace': 'shared', 'spaces': ['domain'], 'status': 'active', 'definition': 'Current term.'}],
                 'forbiddenAliases': [{'section': '8', 'line': 100, 'term': self.forbidden,
                                       'reason': 'Obsolete declaration.', 'instead': 'No runtime alias.'}]}
        registration['declarationSha256'] = declaration_hash(value['forbiddenAliases'])
        return validate_policy(policy), value

    def scan_derived(self, policy, value):
        self.write('eng/policy/glossary-terms.json', json.dumps(value).encode())
        return scan_repository(self.root, 'DesktopPlatform', policy)

    def test_exact_derived_declaration_is_validated_and_reported(self):
        policy, value = self.derived_fixture()
        report = self.scan_derived(policy, value)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['declarationsUsed'], ['eng/policy/glossary-terms.json'])

    def test_changed_declaration_or_source_identity_is_rejected(self):
        for key in ('declaration', 'commit', 'sha256'):
            policy, value = self.derived_fixture()
            if key == 'declaration':
                value['forbiddenAliases'][0]['instead'] = 'Changed declaration.'
            else:
                value['source'][key] = '0' * len(value['source'][key])
            with self.subTest(key=key):
                self.assertEqual(self.scan_derived(policy, value)['status'], 'fail')

    def test_derived_envelope_and_nested_fields_are_closed(self):
        for key in ('root', 'space', 'term', 'alias'):
            policy, value = self.derived_fixture()
            target = value if key == 'root' else value[{'space': 'spaces', 'term': 'terms', 'alias': 'forbiddenAliases'}[key]][0]
            target['unexpected'] = 'No arbitrary extension.'
            with self.subTest(key=key):
                self.assertEqual(self.scan_derived(policy, value)['status'], 'fail')

    def test_derived_non_declaration_values_are_scanned_after_json_decoding(self):
        policy, value = self.derived_fixture()
        value['terms'][0]['definition'] = self.forbidden
        data = json.dumps(value).replace(self.forbidden, ''.join('\\u' + format(ord(c), '04x') for c in self.forbidden))
        self.write('eng/policy/glossary-terms.json', data.encode())
        self.assertEqual(scan_repository(self.root, 'DesktopPlatform', policy)['status'], 'fail')

    def test_copied_declaration_is_not_admitted(self):
        policy, value = self.derived_fixture()
        self.write('docs/copied.json', json.dumps(value).encode())
        self.assertEqual(self.scan_derived(policy, value)['status'], 'fail')

    def test_derived_registration_cannot_change_owner_path_or_shape(self):
        for key, value in [('repository', 'Contracts'), ('path', 'src/policy.json'),
                           ('designCommit', '0' * 40), ('declarationSha256', '*')]:
            policy = deepcopy(self.policy)
            policy['derivedDeclarations'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_policy(policy)

    def test_derived_duplicate_json_keys_fail(self):
        policy, value = self.derived_fixture()
        self.write('eng/policy/glossary-terms.json', json.dumps(value).replace('{', '{"schemaVersion": 1,', 1).encode())
        self.assertEqual(scan_repository(self.root, 'DesktopPlatform', policy)['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
