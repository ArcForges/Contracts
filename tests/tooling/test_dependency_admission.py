# SPDX-License-Identifier: Apache-2.0
"""Admission rejection tests use committed inputs and synthetic mutations only."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eng'))
from dependency_admission import ROOT, POLICY, audit, inventory, immutable_coordinates, pinned, validate


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

    def test_public_internal_guard_required(self):
        self.policy['publicInternalGate'] = ''
        with self.assertRaisesRegex(ValueError, 'Public/internal'):
            validate(self.policy, self.graph)


if __name__ == '__main__':
    unittest.main()
