# SPDX-License-Identifier: Apache-2.0
"""Admission rejection tests use committed inputs and synthetic mutations only."""
import copy
import json
import hashlib
from pathlib import Path
import sys
import re
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eng'))
from dependency_admission import ROOT, POLICY, audit, inventory, immutable_coordinates, major_upgrade, pinned, stable_dependency, validate


class DependencyAdmission(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / POLICY).read_text())
        self.graph = inventory(ROOT)

    def test_current_closure(self):
        self.assertEqual(audit(stable=True)['result'], 'passed')

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
        self.assertEqual(len(config['allowlists']), 11)
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
        latest_pages = json.loads((ROOT / 'eng/provenance/artifact-profiles/dokka-2-2-0-r6.json').read_text())['modules']['contracts-proto']['pages']
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
        ]
        for allow, source_rows, permitted, excluded in zip(config['allowlists'][1:], new_sources,
                ['eng/policy/dependency-reviews/wp03-00-r1.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r4.json',
                 'eng/policy/dependency-reviews/wp03-01-r1.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r5.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r5.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r6.json',
                 'eng/policy/dependency-reviews/wp03-01-r2.json',
                 'eng/policy/dependency-reviews/wp03-02-r1.json',
                 'eng/policy/dependency-reviews/dependabot-2026-09-26-prettier-3-9-8.json',
                 'eng/policy/dependency-reviews/dependabot-2026-09-26-grpc-2-84-0.json'],
                ['eng/provenance/artifact-profiles/dokka-2-2-0-r4.json',
                 'eng/policy/dependency-policy.json',
                 'eng/policy/dependency-reviews/wp03-00-r1.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r4.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r4.json',
                 'eng/provenance/artifact-profiles/dokka-2-2-0-r5.json',
                 'eng/policy/dependency-reviews/wp03-01-r1.json',
                 'eng/policy/dependency-reviews/wp03-01-r2.json',
                 'eng/policy/dependency-reviews/wp03-02-r1.json',
                 'eng/policy/dependency-reviews/dependabot-2026-09-26-prettier-3-9-8.json'], strict=True):
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
        for source in sources:
            self.assertEqual(grpc_receipt['review']['inputHashes'][source], self.policy['inputHashes'][source])
        self.assertEqual([len(item['regexes']) for item in config['allowlists']], [4, 2, 15, 4, 15, 45, 60, 4, 4, 4, 4])


if __name__ == '__main__':
    unittest.main()
