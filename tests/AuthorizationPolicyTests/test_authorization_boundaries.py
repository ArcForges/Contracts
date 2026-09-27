# SPDX-License-Identifier: Apache-2.0
"""Independent boundary negatives over declared metadata and fixture snapshots."""
import copy
import json
from pathlib import Path
import unittest

from assertions import AUTHORIZATION_FIELDS, ROOT, assert_identity_declaration, fixture_decision, metadata, report


class AuthorizationBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(Path(__file__).with_name('boundary-fixtures.json').read_text())

    def test_actual_matrix_preserves_pending_and_all_effective_fields(self):
        actual = report()
        self.assertEqual(actual['identityIntegration']['status'], 'pending')
        self.assertEqual(set(actual['identityIntegration']['requiredProducers']), {'CLOUD.11', 'PLT.38'})
        matrix = actual['matrix']
        self.assertEqual(len(matrix['operations']), matrix['registered'] + matrix['pending'] + matrix['reserved'])
        self.assertEqual({r['operationId'] for r in matrix['operations']},
                         {r['operationId'] for r in metadata.load(ROOT / 'eng/operation-scope-manifest.json')['operations']})
        for row in matrix['operations']:
            if row['status'] == 'registered':
                self.assertEqual(set(row['authorization']), AUTHORIZATION_FIELDS | {'actorKinds'})
                self.assertTrue(row['metadataSource'])
                self.assertTrue(row['sourceRule'])
            else:
                self.assertNotIn('reachableActors', row)

    def test_every_hostile_snapshot_has_independent_expected_denial(self):
        identifiers = set()
        for row in self.fixture['cases']:
            self.assertNotIn(row['id'], identifiers)
            identifiers.add(row['id'])
            with self.subTest(case=row['id']):
                self.assertEqual(fixture_decision(row['input']), row['expected'])

    def test_owner_chain_requirements_cannot_be_removed(self):
        original = self.fixture['identityDeclaration']
        assert_identity_declaration(original)
        for actor in ('agent', 'automation', 'deployment-service'):
            for requirement in original['rules'][actor]:
                value = copy.deepcopy(original)
                value['rules'][actor].remove(requirement)
                with self.subTest(actor=actor, missing=requirement), self.assertRaises(ValueError):
                    assert_identity_declaration(value)

    def test_no_customer_service_principal_organization_or_bare_user_authority(self):
        for kind in ('customer-service-principal', 'organization'):
            value = copy.deepcopy(self.fixture['identityDeclaration'])
            value['authorityKinds'].append(kind)
            with self.assertRaises(ValueError):
                assert_identity_declaration(value)
        value = copy.deepcopy(self.fixture['identityDeclaration'])
        value['identityKey'] = ['userId']
        with self.assertRaises(ValueError):
            assert_identity_declaration(value)


if __name__ == '__main__':
    unittest.main()
