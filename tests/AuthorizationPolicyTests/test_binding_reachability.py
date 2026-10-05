# SPDX-License-Identifier: Apache-2.0
"""Binding reachability and owner-chain binding: positive coverage and hostile negatives."""
import copy
import json
from pathlib import Path
import unittest

import binding_reachability as br
from assertions import ROOT, metadata
from producer_declarations import load

FIXTURE = json.loads(Path(__file__).with_name('boundary-fixtures.json').read_text())


class BindingReachability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = metadata.audit(ROOT)
        cls.classification = br.load_classification()
        cls.snapshot = load()
        cls.cloud = cls.snapshot['producers']['cloud']['declared']

    def classify(self, matrix=None, classification=None, cloud=None):
        return br.classify(matrix or self.matrix, classification or self.classification, cloud or self.cloud)

    def row(self, matrix, operation):
        return next(r for r in matrix['operations'] if r['operationId'] == operation)

    def test_every_catalogue_identity_workspace_and_device_operation_is_classified(self):
        result = self.classify()
        expected = {r['operationId'] for r in self.matrix['operations']
                    if r['status'] == 'registered' and r['operationId'].split('.')[0] in br.DOMAINS}
        self.assertEqual({r['operationId'] for r in result['operations']}, expected)
        self.assertEqual(result['classified'], len(expected))
        for row in result['operations']:
            self.assertTrue(row['bindings'])
            self.assertEqual(row['behavior'], 'not-bound')
            self.assertFalse(set(row['actorKinds']) & br.TOOL_ACTORS)

    def test_session_device_workspace_and_identity_bindings_rest_on_declared_owner_relations(self):
        tables = self.classify()['bindingTables']
        self.assertEqual(tables['session'], 'identity_session')
        for binding in ('authenticationIdentity', 'session', 'device', 'workspace', 'apiToken'):
            self.assertTrue(br.reaches_user(self.cloud, tables[binding]), binding)

    def test_operation_without_an_authorization_binding_is_refused(self):
        value = copy.deepcopy(self.classification)
        value['operations'] = [e for e in value['operations'] if e['operationId'] != 'device.revoke']
        with self.assertRaisesRegex(ValueError, 'without an authorization binding: device.revoke'):
            self.classify(classification=value)

    def test_new_catalogue_operation_must_be_classified(self):
        matrix = copy.deepcopy(self.matrix)
        added = copy.deepcopy(self.row(matrix, 'device.rename'))
        added['operationId'] = 'device.forget'
        matrix['operations'].append(added)
        with self.assertRaisesRegex(ValueError, 'without an authorization binding: device.forget'):
            self.classify(matrix=matrix)

    def test_empty_unknown_or_duplicate_bindings_are_refused(self):
        for label, bindings in {'empty': [], 'unknown': ['organization'], 'duplicate': ['device', 'device']}.items():
            value = copy.deepcopy(self.classification)
            next(e for e in value['operations'] if e['operationId'] == 'device.rename')['bindings'] = bindings
            with self.subTest(label), self.assertRaisesRegex(ValueError, 'unclassified or ambiguous'):
                self.classify(classification=value)

    def test_stale_or_ambiguous_classification_entries_are_refused(self):
        value = copy.deepcopy(self.classification)
        value['operations'].append({'operationId': 'device.forget', 'bindings': ['device']})
        with self.assertRaisesRegex(ValueError, 'names no registered operation'):
            self.classify(classification=value)
        value = copy.deepcopy(self.classification)
        value['operations'].append(copy.deepcopy(value['operations'][0]))
        with self.assertRaisesRegex(ValueError, 'ambiguous binding classification'):
            self.classify(classification=value)

    def test_binding_without_declared_producer_table_is_refused(self):
        for table in ('identity_session', 'device_device', 'workspace_workspace', 'identity_browser_auth_flow'):
            cloud = copy.deepcopy(self.cloud)
            del cloud['tables'][table]
            with self.subTest(table), self.assertRaisesRegex(ValueError, 'no declared producer table|flow table'):
                self.classify(cloud=cloud)

    def test_identity_boundary_violations_in_the_declared_model_are_refused(self):
        def drop(table, relation):
            cloud = copy.deepcopy(self.cloud)
            cloud['tables'][table]['references'].remove(relation)
            return cloud

        def add_column(table, column):
            cloud = copy.deepcopy(self.cloud)
            cloud['tables'][table]['columns'].append(column)
            return cloud

        def add_table(name):
            cloud = copy.deepcopy(self.cloud)
            cloud['tables'][name] = {'columns': ['user_id'], 'references': ['user_id>identity_user'], 'unique': []}
            return cloud

        def drop_unique(table):
            cloud = copy.deepcopy(self.cloud)
            cloud['tables'][table]['unique'] = []
            return cloud

        def drop_realm(table):
            cloud = copy.deepcopy(self.cloud)
            cloud['tables'][table]['columns'].remove('realm_id')
            return cloud

        cases = {
            'workspace owner is not a user': drop('workspace_workspace', 'owner_user_id>identity_user'),
            'session detached from user': drop('identity_session', 'user_id>identity_user'),
            'device detached from user': drop('device_device', 'user_id>identity_user'),
            'credential detached from user': drop('identity_auth_identity', 'user_id>identity_user'),
            'more than one workspace per owner': drop_unique('workspace_workspace'),
            'credential not unique per realm': drop_unique('identity_auth_identity'),
            'workspace not realm scoped': drop_realm('workspace_workspace'),
            'membership table': add_table('workspace_membership'),
            'seat column': add_column('workspace_workspace', 'seat_count'),
            'role column on workspace': add_column('workspace_workspace', 'role'),
            'organization table': add_table('identity_organization'),
            'invitation column': add_column('identity_user', 'invitation_id'),
            'service principal': add_table('identity_service_principal'),
        }
        for label, cloud in cases.items():
            with self.subTest(label), self.assertRaisesRegex(ValueError, 'identity boundary violation|no declared'):
                self.classify(cloud=cloud)

    def test_operator_access_role_is_the_only_role_column(self):
        cloud = copy.deepcopy(self.cloud)
        self.assertIn('role', cloud['tables']['identity_operator_access']['columns'])
        br.check_vocabulary(cloud)
        cloud['tables']['identity_operator_session']['columns'].append('role')
        with self.assertRaises(ValueError):
            br.check_vocabulary(cloud)

    def test_authentication_identity_must_stay_distinct_from_user(self):
        cloud = copy.deepcopy(self.cloud)
        cloud['identifierTypes'] = ['RealmId', 'UserId', 'WorkspaceId']
        with self.assertRaisesRegex(ValueError, 'four distinct identifiers'):
            self.classify(cloud=cloud)

    def test_tool_actors_never_reach_an_identity_bearing_binding(self):
        for operation in ('identity.removeAuthIdentity', 'device.revoke', 'workspace.get', 'identity.createApiToken'):
            for actor in ('agent', 'automation', 'extension'):
                matrix = copy.deepcopy(self.matrix)
                self.row(matrix, operation)['authorization']['actorKinds'].append(actor)
                with self.subTest(operation=operation, actor=actor), self.assertRaisesRegex(ValueError, 'tool actor'):
                    self.classify(matrix=matrix)

    def test_owner_binding_reachable_only_by_the_owner_profile(self):
        matrix = copy.deepcopy(self.matrix)
        self.row(matrix, 'device.list')['authorization']['actorKinds'] = ['operator']
        with self.assertRaisesRegex(ValueError, 'non-owner actor'):
            self.classify(matrix=matrix)
        matrix = copy.deepcopy(self.matrix)
        self.row(matrix, 'device.list')['profile'] = 'one-use-auth'
        with self.assertRaisesRegex(ValueError, 'non-owner actor'):
            self.classify(matrix=matrix)

    def test_pre_authentication_operations_need_a_flow_or_session_binding(self):
        value = copy.deepcopy(self.classification)
        next(e for e in value['operations'] if e['operationId'] == 'identity.beginAuthentication')['bindings'] = ['user']
        with self.assertRaisesRegex(ValueError, 'without a flow or session binding'):
            self.classify(classification=value)

    def test_automation_token_cannot_reach_a_mutating_binding(self):
        for operation in ('device.revoke', 'identity.removeAuthIdentity', 'workspace.updateSettings'):
            matrix = copy.deepcopy(self.matrix)
            self.row(matrix, operation)['authorization']['patEligible'] = True
            with self.subTest(operation), self.assertRaisesRegex(ValueError, 'automation token'):
                self.classify(matrix=matrix)

    def test_declared_plan_must_exist_and_match_the_operation_access(self):
        value = copy.deepcopy(self.classification)
        next(e for e in value['operations'] if e['operationId'] == 'identity.getProfile')['plan'] = 'identity.user-rename'
        with self.assertRaisesRegex(ValueError, 'contradicts write plan'):
            self.classify(classification=value)
        value = copy.deepcopy(self.classification)
        next(e for e in value['operations'] if e['operationId'] == 'identity.getProfile')['plan'] = 'identity.unknown'
        with self.assertRaisesRegex(ValueError, 'not declared by the producer pin'):
            self.classify(classification=value)
        value = copy.deepcopy(self.classification)
        next(e for e in value['operations'] if e['operationId'] == 'identity.updateProfile')['plan'] = 'identity.user-load'
        with self.assertRaisesRegex(ValueError, 'contradicts read plan'):
            self.classify(classification=value)

    def test_stale_plan_in_the_pin_is_refused(self):
        cloud = copy.deepcopy(self.cloud)
        cloud['plans'] = [p for p in cloud['plans'] if p['name'] != 'identity.credential-revoke']
        with self.assertRaisesRegex(ValueError, 'identity.credential-revoke is not declared'):
            self.classify(cloud=cloud)


class IdentityChainBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.declaration = FIXTURE['identityDeclaration']
        cls.classification = br.load_classification()
        cls.snapshot = load()

    def bind(self, classification=None, snapshot=None):
        return br.bind_identity_chain(self.declaration, classification or self.classification, snapshot or self.snapshot)

    def test_every_declared_obligation_is_bound_or_names_why_it_is_not(self):
        result = {o['obligation']: o for o in self.bind()}
        required = {o for rules in self.declaration['rules'].values() for o in rules}
        self.assertEqual(set(result), required)
        self.assertEqual(result['currentPermission']['status'], 'bound')
        self.assertEqual(result['currentServiceEligibility']['status'], 'declared-port')
        self.assertEqual(result['recheckAtTrigger']['status'], 'pending-producer')
        for obligation in result.values():
            if obligation['status'] == 'pending-producer':
                self.assertTrue(obligation['reason'])
            else:
                self.assertGreater(obligation['facts'], 0)

    def test_owner_validates_last_and_permission_is_judged_at_the_service_point(self):
        platform = self.snapshot['producers']['platform']['declared']
        steps = platform['steps']
        self.assertEqual(platform['pointSteps']['OwnerFinalValidation'], [steps['OwnerValidation']])
        self.assertIn(steps['CapabilityPermission'], platform['pointSteps']['ServiceDecision'])
        self.assertIn(steps['ScopeValid'], platform['pointSteps']['ServiceDecision'])
        self.assertNotIn(steps['OwnerValidation'], platform['pointSteps']['ServiceDecision'])

    def test_removed_producer_fact_refuses_the_bound_obligation(self):
        mutations = {
            'owner validation dropped': lambda s: s['producers']['platform']['declared']['pointSteps'].update(OwnerFinalValidation=[]),
            'permission step dropped': lambda s: s['producers']['platform']['declared']['pointSteps'].update(ServiceDecision=[1, 2, 3, 4]),
            'actor identity not at transport': lambda s: s['producers']['platform']['declared']['pointSteps'].update(TransportBoundary=[5]),
            'session detached from user': lambda s: s['producers']['cloud']['declared']['tables']['identity_session']['references'].clear(),
            'owner relation dropped': lambda s: s['producers']['cloud']['declared']['tables']['workspace_workspace']['references'].clear(),
            'operator identity merged into user': lambda s: s['producers']['cloud']['declared']['tables']['identity_operator_access']['references'].append('user_id>identity_user'),
            'operator table removed': lambda s: s['producers']['cloud']['declared']['tables'].pop('identity_operator_session'),
        }
        for label, mutate in mutations.items():
            snapshot = copy.deepcopy(self.snapshot)
            mutate(snapshot)
            with self.subTest(label), self.assertRaisesRegex(ValueError, 'producer fact not declared at the pin'):
                self.bind(snapshot=snapshot)

    def test_classification_cannot_overclaim_or_drop_obligations(self):
        value = copy.deepcopy(self.classification)
        entry = next(e for e in value['identityChain'] if e['obligation'] == 'recheckAtTrigger')
        entry['status'] = 'bound'
        with self.assertRaisesRegex(ValueError, 'without producer facts'):
            self.bind(classification=value)
        value = copy.deepcopy(self.classification)
        next(e for e in value['identityChain'] if e['obligation'] == 'recheckAtTrigger').pop('reason')
        with self.assertRaisesRegex(ValueError, 'without a named reason'):
            self.bind(classification=value)
        value = copy.deepcopy(self.classification)
        next(e for e in value['identityChain'] if e['obligation'] == 'currentServiceEligibility').pop('limit')
        with self.assertRaisesRegex(ValueError, 'without its stated limit'):
            self.bind(classification=value)
        value = copy.deepcopy(self.classification)
        value['identityChain'] = [e for e in value['identityChain'] if e['obligation'] != 'workspaceOwner']
        with self.assertRaisesRegex(ValueError, 'differ from the declaration'):
            self.bind(classification=value)
        value = copy.deepcopy(self.classification)
        next(e for e in value['identityChain'] if e['obligation'] == 'userSession')['status'] = 'enforced'
        with self.assertRaisesRegex(ValueError, 'unclassified obligation status'):
            self.bind(classification=value)

    def test_new_declared_obligation_must_be_classified(self):
        declaration = copy.deepcopy(self.declaration)
        declaration['rules']['automation'].append('ownerSeat')
        with self.assertRaises(ValueError):
            br.bind_identity_chain(declaration, self.classification, self.snapshot)


class BoundReport(unittest.TestCase):
    def test_report_pins_producers_and_states_limits(self):
        report = br.bound_report(metadata.audit(ROOT), FIXTURE['identityDeclaration'])
        integration = report['identityIntegration']
        self.assertEqual(integration['status'], 'bound-to-declared-producer-metadata')
        self.assertEqual(set(integration['producers']), {'cloud', 'platform'})
        self.assertEqual(integration['statusCounts'], {'bound': 4, 'declared-port': 1, 'pending-producer': 2})
        self.assertTrue(integration['limits'])
        self.assertEqual(report['bindingMatrix']['classified'], 49)

    def test_a_hand_edited_snapshot_is_refused_before_classification(self):
        snapshot = load()
        snapshot['producers']['cloud']['declared']['plans'].pop()
        with self.assertRaises(ValueError):
            br.bound_report(metadata.audit(ROOT), FIXTURE['identityDeclaration'], snapshot=snapshot)


if __name__ == '__main__':
    unittest.main()
