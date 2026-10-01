# SPDX-License-Identifier: Apache-2.0
"""Offline producer policy: hostile metadata must not create reachable authority."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("operation_scope", ROOT / "eng/check_operation_scope.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


# Frozen, task-owned transport oracle. Do not derive expected rows from the gate's
# CF_SERVICE_OPERATIONS table; the parity assertion below checks that table.
CF_SERVICE_EXPECTATIONS = {
    'cf.ai.authorize': ('resource-owner', 'authorize', 'Q'),
    'cf.ai.claim': ('assistant', 'claim', 'IW'),
    'cf.ai.renew': ('assistant', 'renew', 'IW'),
    'cf.ai.reconcile': ('assistant', 'reconcile', 'Q'),
    'cf.ai.context': ('assistant', 'context', 'Q'),
    'cf.ai.model-intent': ('assistant', 'model-intent', 'IW'),
    'cf.ai.model-outcome': ('assistant', 'model-outcome', 'IW'),
    'cf.ai.settle': ('assistant', 'settle', 'IW'),
    'cf.ai.prepare-tools': ('assistant', 'prepare-tools', 'IW'),
    'cf.ai.cloud-tool': ('assistant', 'cloud-tool', 'IW'),
    'cf.ai.wait': ('assistant', 'wait', 'IW'),
    'cf.ai.finalize': ('assistant', 'finalize', 'IW'),
    'cf.ai.stream-state': ('assistant', 'stream-state', 'IW'),
    'cf.ai.late-outcome': ('assistant', 'late-outcome', 'IW'),
}

# Independent frozen CON.15 route oracle copied literally from manifest11's closed route-tuple table:
# (scope, method and path, idempotency, source, sourceRule). It is not derived from the checker table.
CF_CON15_SOURCE = 'internal/cf-http/v1/schema.json'
CF_CON15_DOC = 'docs/architecture/contracts/05-cloudflare-integration.md'
CF_CON15_EXPECTATIONS = {
    'cf.objects.authorize': ('resource-owner', 'POST /internal/objects/v1/authorize', 'Q', CF_CON15_SOURCE, CF_CON15_DOC + '#3-exact-internal-ports'),
    'cf.objects.part-receipt': ('resource-owner', 'POST /internal/objects/v1/part-receipt', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#3-exact-internal-ports'),
    'cf.objects.verification': ('resource-owner', 'POST /internal/objects/v1/verification', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#3-exact-internal-ports'),
    'cf.objects.job-grant': ('resource-owner', 'POST /internal/objects/v1/job-grant', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#9-job-authorized-objects-control-inventory-and-resource-budgets'),
    'cf.objects.job-authorize': ('resource-owner', 'POST /internal/objects/v1/job-authorize', 'Q', CF_CON15_SOURCE, CF_CON15_DOC + '#9-job-authorized-objects-control-inventory-and-resource-budgets'),
    'cf.objects.job-read': ('resource-owner', 'GET /internal/objects/v1/jobs/{grantId}', 'Q', CF_CON15_SOURCE, CF_CON15_DOC + '#9-job-authorized-objects-control-inventory-and-resource-budgets'),
    'cf.objects.job-write': ('resource-owner', 'PUT /internal/objects/v1/jobs/{grantId}', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#9-job-authorized-objects-control-inventory-and-resource-budgets'),
    'cf.ai.dispatch': ('assistant', 'POST /internal/ai/v1/dispatch', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#3-exact-internal-ports'),
    'cf.ai.control': ('assistant', 'POST /internal/ai/v1/control', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#3-exact-internal-ports'),
    'cf.ai.delete': ('account', 'POST /internal/ai/v1/delete', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#3-exact-internal-ports'),
    'cf.ai.web-search': ('assistant', 'POST /internal/ai/v1/web-search', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#execution-owner-and-web-search-additions'),
    'cf.ai.inference-job': ('resource-owner', 'POST /internal/ai/v1/inference-job', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#8-session-bindings-inference-jobs-and-deployment-transitions'),
    'cf.ai.inference-lease': ('resource-owner', 'POST /internal/ai/v1/inference-lease', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#8-session-bindings-inference-jobs-and-deployment-transitions'),
    'cf.ai.inference-input': ('resource-owner', 'POST /internal/ai/v1/inference-input', 'Q', CF_CON15_SOURCE, CF_CON15_DOC + '#8-session-bindings-inference-jobs-and-deployment-transitions'),
    'cf.ai.inference-outcome': ('resource-owner', 'POST /internal/ai/v1/inference-outcome', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#8-session-bindings-inference-jobs-and-deployment-transitions'),
    'cf.ai.inference-late-outcome': ('resource-owner', 'POST /internal/ai/v1/inference-late-outcome', 'IW', CF_CON15_SOURCE, CF_CON15_DOC + '#8-session-bindings-inference-jobs-and-deployment-transitions'),
    'cf.ai.inference-state': ('resource-owner', 'POST /internal/ai/v1/inference-state', 'Q', CF_CON15_SOURCE, CF_CON15_DOC + '#8-session-bindings-inference-jobs-and-deployment-transitions'),
}
# The public session-ticket facade is not a private cf-service operation.
PUBLIC_TICKET_BINDINGS = ('GET /objects/v1/{ticketId}', 'PUT /objects/v1/{ticketId}/parts/{partNumber}')

# Independent frozen CON.11 exception evidence. This is deliberately separate
# from the checker constants so changing either side alone fails the test.
CON11_PRIVATE_BINDING = 'arcforges.cf.v1.RunStreamService/Run'
CON11_PRIVATE_SOURCE = 'internal/proto/arcforges/cf/v1/stream.proto'
CON11_PRIVATE_FIXTURE = 'fixtures/internal/con-11-run-stream.json'
CON11_PRIVATE_RPC_VECTOR = {
    'id': 'cloudinternal.run-stream.run',
    'service': 'arcforges.cf.v1.RunStreamService',
    'method': 'Run',
    'input': 'RunStreamRequest',
    'output': 'arcforges.events.v1.StreamFrame',
    'streamType': 'serverStreaming',
    'requestFields': [['execution', 1], ['attemptId', 2], ['generation', 3]],
}


class OperationScopeTests(unittest.TestCase):
    def task_create_row(self):
        return {
            'operationId': 'task.create',
            'binding': gate.TASK_CREATE_BINDING,
            'kind': 'proto',
            'source': gate.TASK_CREATE_SOURCE,
            'scope': 'assistant',
            'surface': 'public',
            'profile': 'human-owner',
            'sourceRule': gate.TASK_CREATE_SOURCE_RULE,
            'idempotency': 'CC',
            'authorization': {
                'capability': None,
                'risk': 'R2+',
                'approval': 'perPlanStep',
                'stepUp': False,
                'localPresence': False,
                'egress': 'ownedContent',
                'patEligible': False,
                'actorKinds': ['human'],
            },
        }

    def public_approval_row(self):
        return {
            'operationId': 'approval.decide',
            'binding': 'arcforges.publicapi.v1.ApprovalService/Decide',
            'kind': 'proto',
            'source': 'public/proto/arcforges/publicapi/v1/chat.proto',
            'scope': 'assistant',
            'surface': 'public',
            'profile': 'public-human-approval-decision',
            'sourceRule': 'docs/architecture/contracts/01-public-api-operations.md#rule-tk-02',
            'idempotency': 'IW',
            'authorization': {
                'capability': None,
                'risk': {'from': 'verifiedApprovalProposal.effectiveRisk'},
                'approval': 'foregroundProposal',
                'stepUp': {'from': 'verifiedApprovalProposal.stepUp'},
                'localPresence': {'from': 'verifiedApprovalProposal.localPresence'},
                'egress': 'none',
                'patEligible': False,
                'actorKinds': ['human'],
            },
        }

    def cf_service_row(self, operation):
        scope, route, idempotency = CF_SERVICE_EXPECTATIONS[operation]
        return {
            'operationId': operation,
            'binding': f'POST /internal/ai/v1/{route}',
            'kind': 'http',
            'source': 'internal/ai-http/v1/schema.json',
            'scope': scope,
            'surface': 'cf-internal',
            'profile': 'cf-service',
            'sourceRule': 'docs/architecture/contracts/05-cloudflare-integration.md#3-exact-internal-ports',
            'idempotency': idempotency,
            'authorization': {
                'capability': None,
                'risk': 'R1',
                'approval': 'none',
                'stepUp': False,
                'localPresence': False,
                'egress': 'none',
                'patEligible': False,
                'actorKinds': ['service'],
            },
        }

    def inprocess_row(self, approval=False):
        owner, interface, method = (('Chat', 'IChatOperations', 'SubmitApproval') if approval
                                    else ('Platform', 'ICapabilityProvider', 'Invoke'))
        namespace = f'ArcForges.Contracts.LocalRpc.{owner}'
        row = {'operationId': f'{interface}.{method}', 'kind': 'in-process',
               'binding': f'{namespace}.Ports.{interface}.{method}Async',
               'source': f'src/internal/dotnet/{namespace}/Generated/InprocessPorts.g.cs',
               'scope': 'in-process', 'surface': 'in-process',
               'profile': 'human-approval-decision' if approval else 'in-process-invocation',
               'sourceRule': 'docs/architecture/contracts/02-local-rpc-operations.md#closed-in-process-authorization-profiles'}
        if approval:
            row['idempotency'] = 'IW'
            row['authorization'] = {'capability': None, 'risk': {'from': 'verifiedApprovalProposal.effectiveRisk'},
                'approval': 'foregroundProposal', 'stepUp': {'from': 'verifiedApprovalProposal.stepUp'},
                'localPresence': {'from': 'verifiedApprovalProposal.localPresence'},
                'egress': 'none', 'patEligible': False, 'actorKinds': ['human']}
        else:
            row['idempotency'] = {'from': 'admittedCapability.idempotency'}
            row['authorization'] = {field: {'from': 'admittedCapability.' +
                ('operationId' if field == 'capability' else field)} for field in gate.FIELDS - {'patEligible'}}
            row['authorization']['patEligible'] = False
            row['delegation'] = {'intersectOriginalActor': True, 'requireCurrentGrant': True,
                'denyHumanOnly': True, 'requireRegisteredProductHandler': True}
        return row

    def test_exact_inprocess_profiles_and_closed_bindings(self):
        for approval in (False, True):
            row = self.inprocess_row(approval)
            actors, derived = gate.authorization(row, set())
            self.assertEqual(actors, ['human'] if approval else [])
            self.assertEqual(set(derived), {'risk', 'stepUp', 'localPresence'} if approval else gate.FIELDS - {'patEligible'})
            for field, wrong in [('operationId', 'ICapabilityProvider.Describe'), ('surface', 'public'),
                                 ('scope', 'account'), ('kind', 'proto'), ('binding', 'Invented.InvokeAsync'),
                                 ('source', 'internal/proto/arcforges/local/platform/v1/inprocess.proto')]:
                hostile = copy.deepcopy(row); hostile[field] = wrong
                with self.subTest(approval=approval, field=field), self.assertRaises(ValueError):
                    gate.authorization(hostile, set())
            for field, wrong in [('patEligible', True), ('actorKinds', ['agent']), ('risk', {'from': 'caller.risk'})]:
                hostile = copy.deepcopy(row); hostile['authorization'][field] = wrong
                with self.subTest(approval=approval, field=field), self.assertRaises(ValueError):
                    gate.authorization(hostile, set())

    def test_inprocess_invocation_requires_current_registered_handler(self):
        row = self.inprocess_row()
        for guard in row['delegation']:
            for invalid in (False, 1, 1.0, None, 'true'):
                hostile = copy.deepcopy(row); hostile['delegation'][guard] = invalid
                with self.subTest(guard=guard, invalid=invalid), self.assertRaisesRegex(ValueError, 'incomplete delegated'):
                    gate.authorization(hostile, set())
        hostile = copy.deepcopy(row)
        hostile['delegation']['requireLaunchRole'] = hostile['delegation'].pop('requireRegisteredProductHandler')
        with self.assertRaisesRegex(ValueError, 'incomplete delegated'):
            gate.authorization(hostile, set())
        hostile = copy.deepcopy(row); hostile['profile'] = 'delegated-invocation'
        with self.assertRaises(ValueError):
            gate.authorization(hostile, set())

    def test_approval_proposal_cannot_be_fixed_or_caller_claimed(self):
        row = self.inprocess_row(True)
        for field, wrong in [('risk', 'R1'), ('risk', 'R3'), ('risk', {'from': 'verifiedApprovalProposal.risk'}),
                             ('stepUp', False), ('localPresence', False), ('approval', 'none'),
                             ('capability', row['operationId']), ('egress', 'ownedContent')]:
            hostile = copy.deepcopy(row); hostile['authorization'][field] = wrong
            with self.subTest(field=field, wrong=wrong), self.assertRaises(ValueError):
                gate.authorization(hostile, set())
        hostile = copy.deepcopy(row); hostile['delegation'] = self.inprocess_row()['delegation']
        with self.assertRaisesRegex(ValueError, 'metadata contradicts'):
            gate.authorization(hostile, set())

    def test_public_approval_profile_is_separate_and_exact(self):
        row = self.public_approval_row()
        actors, derived = gate.authorization(row, set())
        self.assertEqual(actors, ['human'])
        self.assertEqual(set(derived), {'risk', 'stepUp', 'localPresence'})
        for field, wrong in [('risk', 'R2'), ('risk', {'from': 'verifiedApprovalProposal.risk'}),
                             ('approval', 'none'), ('stepUp', False), ('localPresence', False),
                             ('egress', 'ownedContent'), ('patEligible', True),
                             ('actorKinds', ['agent'])]:
            hostile = copy.deepcopy(row)
            hostile['authorization'][field] = wrong
            with self.subTest(field=field, wrong=wrong), self.assertRaises(ValueError):
                gate.authorization(hostile, set())
        for field, wrong in [('operationId', 'approval.list'), ('profile', 'human-owner'),
                             ('scope', 'account'), ('surface', 'in-process'),
                             ('binding', 'arcforges.publicapi.v1.ApprovalService/List'),
                             ('source', 'internal/proto/arcforges/local/chat/v1/inprocess.proto'),
                             ('sourceRule', 'docs/architecture/contracts/02-local-rpc-operations.md#profiles'),
                             ('idempotency', 'Q')]:
            hostile = copy.deepcopy(row)
            hostile[field] = wrong
            with self.subTest(field=field, wrong=wrong), self.assertRaises(ValueError):
                gate.authorization(hostile, set())

    def test_task_create_r2plus_is_one_exact_public_registry_binding(self):
        row = self.task_create_row()
        self.assertEqual(gate.authorization(row, set()), (['human'], []))

        context_mutations = [
            ('operationId', 'task.get'),
            ('binding', 'arcforges.publicapi.v1.TaskService/Get'),
            ('kind', 'http'),
            ('source', 'public/proto/arcforges/publicapi/v1/content.proto'),
            ('scope', 'product-owner'),
            ('surface', 'in-process'),
            ('profile', 'tool-delegation'),
            ('sourceRule', 'docs/architecture/contracts/01-public-api-operations.md#1-general'),
        ]
        for field, wrong in context_mutations:
            hostile = copy.deepcopy(row)
            hostile[field] = wrong
            with self.subTest(field=field, wrong=wrong), self.assertRaises(ValueError):
                gate.authorization(hostile, set())

        hostile = copy.deepcopy(row)
        hostile['authorization']['actorKinds'] = ['agent']
        with self.assertRaises(ValueError):
            gate.authorization(hostile, set())

        for wrong in ('R2', 'R3', 'r2+', 'R2 +', 'R2++'):
            hostile = copy.deepcopy(row)
            hostile['authorization']['risk'] = wrong
            with self.subTest(risk=wrong), self.assertRaises(ValueError):
                gate.authorization(hostile, set())

        for field in sorted(gate.FIELDS - {'risk'}):
            hostile = copy.deepcopy(row)
            hostile['authorization'][field] = 'R2+'
            with self.subTest(authorization_field=field), self.assertRaises(ValueError):
                gate.authorization(hostile, set())

    def break_glass_row(self):
        return {
            'operationId': 'operator.startBreakGlass',
            'binding': 'arcforges.operator.v1.OperatorService/StartBreakGlass',
            'kind': 'proto',
            'source': 'internal/proto/arcforges/operator/v1/operator.proto',
            'scope': 'operator',
            'surface': 'operator',
            'profile': 'operator',
            'sourceRule': 'docs/architecture/contracts/04-protobuf-wire-registry.md#91-complete-operator-authorization-and-call-context',
            'idempotency': 'CC',
            'authorization': {
                'capability': None,
                'risk': 'R4',
                'approval': 'alarmedIncident',
                'stepUp': True,
                'localPresence': False,
                'egress': 'caseBoundRecovery',
                'patEligible': False,
                'actorKinds': ['operator'],
            },
        }

    def test_operator_break_glass_r4_is_one_exact_operator_binding(self):
        row = self.break_glass_row()
        self.assertEqual(gate.authorization(row, set()), (['operator'], []))

        context_mutations = [
            ('operationId', 'operator.endBreakGlass'),
            ('binding', 'arcforges.operator.v1.OperatorService/EndBreakGlass'),
            ('kind', 'http'),
            ('source', 'internal/proto/arcforges/operator/v1/other.proto'),
            ('scope', 'account'),
            ('surface', 'public'),
            ('profile', 'human-owner'),
            ('idempotency', 'IW'),
        ]
        for field, wrong in context_mutations:
            hostile = copy.deepcopy(row)
            hostile[field] = wrong
            with self.subTest(field=field, wrong=wrong), self.assertRaises(ValueError):
                gate.authorization(hostile, set())

        for field, wrong in [('actorKinds', ['human']), ('actorKinds', ['operator', 'service']),
                             ('patEligible', True), ('capability', 'operator.startBreakGlass'),
                             ('localPresence', True), ('stepUp', 'yes'), ('stepUp', False)]:
            hostile = copy.deepcopy(row)
            hostile['authorization'][field] = wrong
            with self.subTest(authorization_field=field, wrong=wrong), self.assertRaises(ValueError):
                gate.authorization(hostile, set())

        for wrong in ('R5', 'r4', 'R4+', 'R4 ', 'R 4', 'R4.0'):
            hostile = copy.deepcopy(row)
            hostile['authorization']['risk'] = wrong
            with self.subTest(risk=wrong), self.assertRaisesRegex(ValueError, 'unclassified risk'):
                gate.authorization(hostile, set())

        other = copy.deepcopy(row)
        other.update(operationId='operator.endBreakGlass', idempotency='IW',
                     binding='arcforges.operator.v1.OperatorService/EndBreakGlass')
        with self.assertRaisesRegex(ValueError, 'unclassified risk'):
            gate.authorization(other, set())
        public = self.task_create_row()
        public['authorization']['risk'] = 'R4'
        with self.assertRaises(ValueError):
            gate.authorization(public, set())
        human = self.cf_service_row('cf.ai.authorize')
        human['authorization']['risk'] = 'R4'
        with self.assertRaises(ValueError):
            gate.authorization(human, set())

    def test_cf_service_ports_are_exact_closed_transport_bindings(self):
        self.assertEqual(gate.CF_SERVICE_OPERATIONS, CF_SERVICE_EXPECTATIONS)
        operations = list(CF_SERVICE_EXPECTATIONS)
        auth_mutations = {
            'capability': 'capability.read',
            'risk': 'R2',
            'approval': 'foregroundProposal',
            'stepUp': True,
            'localPresence': True,
            'egress': 'ownedContent',
            'patEligible': True,
            'actorKinds': ['human'],
        }

        for index, operation in enumerate(operations):
            with self.subTest(operation=operation):
                row = self.cf_service_row(operation)
                self.assertEqual(gate.authorization(row, set()), (['service'], []))
            wrong_operation = operations[(index + 1) % len(operations)]
            expected_scope, _, expected_idempotency = CF_SERVICE_EXPECTATIONS[operation]
            wrong_scope = 'assistant' if expected_scope == 'resource-owner' else 'resource-owner'
            wrong_idempotency = 'IW' if expected_idempotency == 'Q' else 'Q'
            mutations = [
                ('operationId', wrong_operation),
                ('binding', 'POST /internal/ai/v1/' + CF_SERVICE_EXPECTATIONS[wrong_operation][1]),
                ('kind', 'proto'),
                ('source', 'internal/ai/v1/schema.json'),
                ('scope', wrong_scope),
                ('surface', 'public'),
                ('profile', 'human-owner'),
                ('sourceRule', 'docs/architecture/contracts/05-cloudflare-integration.md#2-legacy'),
                ('idempotency', wrong_idempotency),
            ]
            for field, wrong in mutations:
                hostile = copy.deepcopy(row)
                hostile[field] = wrong
                with self.subTest(operation=operation, field=field, wrong=wrong):
                    with self.assertRaises(ValueError):
                        gate.authorization(hostile, set())

            for field, wrong in auth_mutations.items():
                hostile = copy.deepcopy(row)
                hostile['authorization'][field] = wrong
                with self.subTest(operation=operation, authorization_field=field, wrong=wrong):
                    with self.assertRaises(ValueError):
                        gate.authorization(hostile, set())

        hostile = self.cf_service_row('cf.ai.authorize')
        hostile['operationId'] = 'cf.ai.unknown'
        with self.assertRaisesRegex(ValueError, 'unregistered CF service operation'):
            gate.authorization(hostile, set())

    def con15_row(self, operation):
        scope, binding, idempotency, source, source_rule = CF_CON15_EXPECTATIONS[operation]
        return {
            'operationId': operation,
            'binding': binding,
            'kind': 'http',
            'source': source,
            'scope': scope,
            'surface': 'cf-internal',
            'profile': 'cf-service',
            'sourceRule': source_rule,
            'idempotency': idempotency,
            'authorization': {
                'capability': None,
                'risk': 'R1',
                'approval': 'none',
                'stepUp': False,
                'localPresence': False,
                'egress': 'none',
                'patEligible': False,
                'actorKinds': ['service'],
            },
        }

    def test_con15_private_routes_are_exactly_the_17_literal_tuples_beside_the_14_con10_rows(self):
        self.assertEqual(len(CF_CON15_EXPECTATIONS), 17)
        self.assertEqual(gate.CON15_CF_SERVICE_OPERATIONS, CF_CON15_EXPECTATIONS)
        self.assertFalse(set(CF_CON15_EXPECTATIONS) & set(CF_SERVICE_EXPECTATIONS))
        self.assertEqual(len(gate.CF_SERVICE_OPERATIONS), 14)
        self.assertEqual(gate.CF_SERVICE_OPERATIONS, CF_SERVICE_EXPECTATIONS)

    def test_con15_each_route_has_a_positive_and_every_tuple_and_authorization_field_is_mutation_tested(self):
        operations = list(CF_CON15_EXPECTATIONS)
        auth_mutations = {
            'capability': 'capability.read',
            'risk': 'R2',
            'approval': 'foregroundProposal',
            'stepUp': True,
            'localPresence': True,
            'egress': 'ownedContent',
            'patEligible': True,
            'actorKinds': ['human'],
        }
        self.assertEqual(set(auth_mutations), gate.FIELDS)
        for index, operation in enumerate(operations):
            row = self.con15_row(operation)
            with self.subTest(operation=operation, case='positive'):
                self.assertEqual(gate.authorization(row, set()), (['service'], []))
            expected_scope, expected_binding, expected_idempotency, _, _ = CF_CON15_EXPECTATIONS[operation]
            other = operations[(index + 1) % len(operations)]
            other_binding = CF_CON15_EXPECTATIONS[other][1]
            method, _, path = expected_binding.partition(' ')
            mutations = [
                ('operationId', other),
                ('binding', other_binding),
                ('binding', ('GET ' if method != 'GET' else 'POST ') + path),
                ('binding', expected_binding.replace('/internal/', '/')),
                ('kind', 'proto'),
                ('source', 'internal/ai-http/v1/schema.json'),
                ('source', 'internal/storage-http/v1/schema.json'),
                ('scope', 'assistant' if expected_scope != 'assistant' else 'resource-owner'),
                ('surface', 'public'),
                ('profile', 'human-owner'),
                ('sourceRule', 'docs/architecture/contracts/05-cloudflare-integration.md#2-http-framing-and-authentication'),
                ('idempotency', 'IW' if expected_idempotency == 'Q' else 'Q'),
            ]
            for field, wrong in mutations:
                hostile = copy.deepcopy(row)
                hostile[field] = wrong
                with self.subTest(operation=operation, field=field, wrong=wrong), self.assertRaises(ValueError):
                    gate.authorization(hostile, set())
            for field, wrong in auth_mutations.items():
                hostile = copy.deepcopy(row)
                hostile['authorization'][field] = wrong
                with self.subTest(operation=operation, authorization_field=field), self.assertRaises(ValueError):
                    gate.authorization(hostile, set())
            hostile = copy.deepcopy(row)
            hostile['authorization']['risk'] = 'R2+'
            with self.subTest(operation=operation, authorization_field='risk', wrong='R2+'), self.assertRaises(ValueError):
                gate.authorization(hostile, set())

    def test_con15_rejects_unlisted_cf_service_rows_and_public_ticket_routes(self):
        hostile = self.con15_row('cf.objects.job-read')
        hostile['operationId'] = 'cf.objects.ticket-read'
        with self.assertRaisesRegex(ValueError, 'unregistered CF service operation'):
            gate.authorization(hostile, set())
        for operation, binding in (('cf.objects.job-read', PUBLIC_TICKET_BINDINGS[0]),
                                   ('cf.objects.job-write', PUBLIC_TICKET_BINDINGS[1]),
                                   ('cf.objects.authorize', PUBLIC_TICKET_BINDINGS[0])):
            row = self.con15_row(operation)
            row['binding'] = binding
            with self.subTest(operation=operation, binding=binding), self.assertRaisesRegex(ValueError, 'exact CF HMAC transport binding'):
                gate.authorization(row, set())
        for operation in ('cf.objects.public-ticket-read', 'cf.objects.public-ticket-write'):
            row = self.con15_row('cf.objects.job-read')
            row['operationId'] = operation
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, 'unregistered CF service operation'):
                gate.authorization(row, set())
        # A cf-service profile cannot be assigned to any ordinary operation.
        row = self.cf_service_row('cf.ai.claim')
        row['operationId'] = 'workspace.list'
        with self.assertRaisesRegex(ValueError, 'unregistered CF service operation'):
            gate.authorization(row, set())

    def test_con15_real_export_and_oracle_rows_match_the_independent_tuples(self):
        export = gate.load(ROOT / 'eng/operations/con-15.json')
        self.assertEqual(export['schemaVersion'], 'operation-metadata.v1')
        self.assertEqual([row['operationId'] for row in export['operations']], sorted(CF_CON15_EXPECTATIONS))
        for row in export['operations']:
            self.assertEqual(row, self.con15_row(row['operationId']))
        manifest = gate.load(ROOT / 'eng/operation-scope-manifest.json')
        self.assertEqual(len(manifest['operations']), 342)
        scopes = {row['operationId']: row['scope'] for row in manifest['operations']}
        for operation, (scope, *_rest) in CF_CON15_EXPECTATIONS.items():
            self.assertEqual(scopes[operation], scope)
        for operation in CF_SERVICE_EXPECTATIONS:
            self.assertIn(operation, scopes)
        self.assertIn('events.poll', scopes)
        self.assertEqual(manifest['oracle']['commit'], '8f71424337ebb5d802e22f4813f4394235aa9a87')
        self.assertEqual(manifest['oracle']['sha256'],
                         '53e6992b89e9a13cca3528ffedbe79519499a289b59884811149dd30b6f73462')

    def test_closed_operations_cannot_downgrade_to_generic_profiles(self):
        for approval in (False, True):
            row = self.inprocess_row(approval)
            row.pop('delegation', None)
            row['idempotency'] = 'IW'
            row['authorization'] = {'capability': None, 'risk': 'R1', 'approval': 'none',
                'stepUp': False, 'localPresence': False, 'egress': 'none',
                'patEligible': False, 'actorKinds': ['human']}
            for profile in ('product-handler', 'human-owner', 'tool-delegation'):
                row['profile'] = profile
                with self.subTest(approval=approval, profile=profile), self.assertRaisesRegex(ValueError, 'required closed'):
                    gate.authorization(row, set())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = "public/proto/arcforges/extensions/v1/extensions.proto"
        path = self.root / self.source
        path.parent.mkdir(parents=True)
        path.write_text('syntax = "proto3"; package arcforges.extensions.v1; '
                        'service ExtensionHostService { rpc RenewLease(Request) returns (Reply); }')
        self.row = copy.deepcopy(gate.load(ROOT / "eng/operations/extensions-baseline.json")["operations"][0])
        self.manifest = {"schemaVersion": "operation-scope.v1", "operations": [
            {"operationId": self.row["operationId"], "scope": "private-helper"},
            {"operationId": "workspace.list", "scope": "account"},
            {"operationId": "deviceSso.reserved", "scope": "future"}],
            "idempotencyExamples": [], "toolAllowlist": []}

    def write(self, rows=None):
        path = self.root / "eng/operations/example.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schemaVersion": "operation-metadata.v1", "operations":
                                   [self.row] if rows is None else rows}))

    def fails(self, phrase, rows=None):
        self.write(rows)
        with self.assertRaisesRegex(ValueError, phrase):
            gate.audit(self.root, self.manifest)

    def install_con11_projection(self, *, source=CON11_PRIVATE_SOURCE,
                                 package='arcforges.cf.v1', service='RunStreamService', method='Run',
                                 rpc_vectors=None, fixture_schema='con-11-run-stream.v1', sibling=False):
        export = self.root / 'eng/operations/con-11.json'
        export.parent.mkdir(parents=True, exist_ok=True)
        export.write_text(json.dumps({'schemaVersion': 'operation-metadata.v1', 'operations': []}))

        proto = self.root / source
        proto.parent.mkdir(parents=True, exist_ok=True)
        proto.write_text(f'syntax = "proto3"; package {package}; service {service} {{ '
                         f'rpc {method}(RunStreamRequest) returns (stream StreamFrame); }}')
        if sibling:
            extra = proto.parent / 'unexpected.proto'
            extra.write_text('syntax = "proto3"; package arcforges.cf.v1; '
                             'service UnexpectedInternalService { rpc Extra(Request) returns (Reply); }')

        fixture = self.root / CON11_PRIVATE_FIXTURE
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(json.dumps({'schemaVersion': fixture_schema,
                                       'rpcVectors': copy.deepcopy(rpc_vectors if rpc_vectors is not None
                                                                    else [CON11_PRIVATE_RPC_VECTOR])}))

    def test_real_retained_methods_and_pending_inventory(self):
        result = gate.audit(ROOT)
        self.assertEqual(result["result"], "passed")
        oracle = gate.load(ROOT / "eng/operation-scope-manifest.json")
        self.assertEqual(len(result["operations"]), len(oracle["operations"]))
        self.assertEqual(result["registered"] + result["pending"] + result["reserved"], len(oracle["operations"]))
        self.assertEqual((result["registered"], result["pending"], result["reserved"],
                          len(result["operations"])), (280, 55, 7, 342))
        self.assertEqual(result["privateServiceProjections"], [{
            "binding": CON11_PRIVATE_BINDING,
            "source": CON11_PRIVATE_SOURCE,
            "fixture": CON11_PRIVATE_FIXTURE,
            "rpcVectorId": "cloudinternal.run-stream.run",
        }])
        self.assertNotIn(CON11_PRIVATE_BINDING,
                         {row.get("binding") for row in result["operations"]})
        methods = gate.proto_methods(ROOT)
        self.assertEqual(result["migrationExamples"], sorted(binding for binding, source in gate.EXAMPLES.items()
                         if methods.get(binding) == source))

    def test_con11_private_projection_is_reported_outside_operation_matrix(self):
        self.install_con11_projection()
        self.write()
        result = gate.audit(self.root, self.manifest)
        self.assertEqual(result['privateServiceProjections'], [{
            'binding': CON11_PRIVATE_BINDING,
            'source': CON11_PRIVATE_SOURCE,
            'fixture': CON11_PRIVATE_FIXTURE,
            'rpcVectorId': 'cloudinternal.run-stream.run',
        }])
        self.assertEqual((result['registered'], result['pending'], result['reserved']), (1, 1, 1))
        self.assertEqual(len(result['operations']), 3)
        self.assertNotIn(CON11_PRIVATE_BINDING,
                         {row.get('binding') for row in result['operations']})

    def test_con11_private_projection_rejects_wrong_source(self):
        self.install_con11_projection(source='internal/proto/arcforges/cf/v1/other.proto')
        self.write()
        with self.assertRaisesRegex(ValueError, 'missing or wrong source binding'):
            gate.audit(self.root, self.manifest)

    def test_con11_private_projection_rejects_wrong_service_or_method(self):
        for service, method in (('RenamedRunStreamService', 'Run'), ('RunStreamService', 'Other')):
            with self.subTest(service=service, method=method):
                self.install_con11_projection(service=service, method=method)
                self.write()
                with self.assertRaisesRegex(ValueError, 'missing or wrong source binding'):
                    gate.audit(self.root, self.manifest)

    def test_con11_private_projection_rejects_public_relocation(self):
        self.install_con11_projection(source='public/proto/arcforges/cf/v1/stream.proto')
        self.write()
        with self.assertRaisesRegex(ValueError, 'missing or wrong source binding'):
            gate.audit(self.root, self.manifest)

    def test_con11_private_projection_rejects_mutated_or_extra_fixture_rpc(self):
        mutated = copy.deepcopy(CON11_PRIVATE_RPC_VECTOR)
        mutated['requestFields'][0][1] = 99
        for vectors in ([mutated], [CON11_PRIVATE_RPC_VECTOR, {**CON11_PRIVATE_RPC_VECTOR, 'id': 'extra'}]):
            with self.subTest(vectors=vectors):
                self.install_con11_projection(rpc_vectors=vectors)
                self.write()
                with self.assertRaisesRegex(ValueError, 'fixture RPC vector mismatch'):
                    gate.audit(self.root, self.manifest)

    def test_con11_private_projection_rejects_wrong_fixture_identity(self):
        self.install_con11_projection(fixture_schema='invented-run-stream.v1')
        self.write()
        with self.assertRaisesRegex(ValueError, 'fixture identity mismatch'):
            gate.audit(self.root, self.manifest)

    def test_con11_private_projection_cannot_be_exported_as_an_operation(self):
        row = copy.deepcopy(self.row)
        row.update(operationId='workspace.list', binding=CON11_PRIVATE_BINDING,
                   source=CON11_PRIVATE_SOURCE, scope='account')
        self.fails('private RunStream projection must not have an operation export', [row])

    def test_con11_private_projection_rejects_unclassified_internal_sibling(self):
        self.install_con11_projection(sibling=True)
        self.write()
        with self.assertRaisesRegex(ValueError, 'unclassified registered method: arcforges.cf.v1.UnexpectedInternalService/Extra'):
            gate.audit(self.root, self.manifest)

    def test_deterministic_complete_matrix(self):
        self.write()
        result = gate.audit(self.root, self.manifest)
        self.assertEqual(result, gate.audit(self.root, self.manifest))
        self.assertEqual((result["registered"], result["pending"], result["reserved"]), (1, 1, 1))

    def test_compatibility_class_is_exactly_scoped_to_con08(self):
        row = {name: None for name in gate.ROW_REQUIRED}
        row.update(operationId="entitlement.getSnapshot", compatibilityClass="frozen")
        gate.validate_operation_export_fields(gate.CON08_EXPORT, row)

        for path, hostile in (
            (gate.CON08_EXPORT, {**row, "compatibilityClass": None}),
            (gate.CON08_EXPORT, {**row, "compatibilityClass": "additive-open"}),
            (gate.CON08_EXPORT, {**row, "operationId": "invented.operation"}),
            (gate.CON08_EXPORT, {key: value for key, value in row.items() if key != "compatibilityClass"}),
            ("eng/operations/example.json", row),
        ):
            with self.subTest(path=path, row=hostile), self.assertRaises(ValueError):
                gate.validate_operation_export_fields(path, hostile)

        # A CON.08 operation in another export may not carry this task's metadata.
        with self.assertRaisesRegex(ValueError, "permitted only"):
            gate.validate_operation_export_fields("eng/operations/example.json", row)

    def test_compatibility_class_unknown_extra_still_fails_closed(self):
        row = {name: None for name in gate.ROW_REQUIRED}
        row.update(operationId="entitlement.getSnapshot", compatibilityClass="frozen", futureClass="invented")
        with self.assertRaisesRegex(ValueError, "unknown operation export fields"):
            gate.validate_operation_export_fields(gate.CON08_EXPORT, row)

    def test_all_eight_fields_are_mandatory(self):
        original = copy.deepcopy(self.row)
        for field in gate.FIELDS:
            with self.subTest(field=field):
                self.row = copy.deepcopy(original)
                del self.row["authorization"][field]
                self.fails("eight authorization fields")

    def test_unknown_registered_method(self):
        self.fails("unclassified registered method", [])

    def test_duplicate_export(self):
        self.fails("duplicate export", [self.row, self.row])

    def test_duplicate_operation_binding(self):
        duplicate = copy.deepcopy(self.row)
        duplicate.update(operationId='workspace.list', scope='account')
        self.fails('ambiguous binding', [self.row, duplicate])

    def test_nonexistent_binding(self):
        self.row["binding"] += "Missing"
        self.fails("nonexistent service method")

    def test_source_escape(self):
        self.row["source"] = "../outside.proto"
        self.fails("invalid source path")

    def test_reserved_registration(self):
        self.row["operationId"] = "deviceSso.reserved"
        self.fails("reserved future operation")

    def test_unknown_operation(self):
        self.row["operationId"] = "invented.grant"
        self.fails("unclassified operation")

    def test_nonexistent_idempotency_example(self):
        self.manifest["idempotencyExamples"] = ["identity.revokeDevice"]
        self.fails("nonexistent idempotency example")

    def test_public_local_schema_import(self):
        with (self.root / self.source).open("a") as stream:
            stream.write('\nimport "arcforges/local/v1/bootstrap.proto";')
        self.fails("public import of local schema")

    def test_unknown_risk(self):
        self.row["authorization"]["risk"] = "R9"
        self.fails("unclassified risk")

    def test_boolean_is_not_string(self):
        self.row["authorization"]["stepUp"] = "false"
        self.fails("ambiguous stepUp")

    def test_helper_cannot_claim_public_human_profile(self):
        self.row["profile"] = "human-owner"
        self.row["authorization"]["actorKinds"] = ["human"]
        self.fails("profile surface mismatch")

    def test_peer_cannot_claim_service_identity(self):
        self.row["authorization"]["actorKinds"] = ["service"]
        self.fails("profile identity mismatch")

    def test_helper_pat_denied(self):
        self.row["authorization"]["patEligible"] = True
        self.fails("forbidden PAT")

    def test_human_only_tool_denied_even_if_allowlisted(self):
        self.manifest["operations"].append({"operationId": "approval.decide", "scope": "account"})
        self.manifest["toolAllowlist"] = ["approval.decide"]
        self.fails("forbidden or unclassified tool")

    def test_scope_mismatch(self):
        self.row["scope"] = "account"
        self.fails("scope disagrees")

    def test_unclassified_profile(self):
        self.row["profile"] = "default"
        self.fails("unclassified source profile")

    def test_partial_derived_descriptor_denied(self):
        self.row["profile"] = "delegated-invocation"
        self.row["idempotency"] = {"from": "admittedCapability.idempotency"}
        self.row["authorization"]["risk"] = {"from": "admittedCapability.risk"}
        self.fails("partial delegated descriptor")

    def test_unknown_descriptor_expression(self):
        self.row["profile"] = "delegated-invocation"
        self.row["idempotency"] = {"from": "admittedCapability.idempotency"}
        self.row["authorization"]["risk"] = {"from": "caller.risk"}
        self.fails("unsupported derived risk")

    def test_fixed_lifecycle_cannot_silently_lower_risk(self):
        self.row["authorization"]["risk"] = "R0"
        self.fails("lifecycle metadata disagrees")

    def test_delegated_actor_and_grant_constraints_are_complete(self):
        row = copy.deepcopy(self.row)
        row.update(operationId="IExtensionHost.Invoke", profile="delegated-invocation")
        row["idempotency"] = {"from": "admittedCapability.idempotency"}
        row["authorization"] = {field: {"from": "admittedCapability." +
            ("operationId" if field == "capability" else field)} for field in gate.FIELDS - {"patEligible"}}
        row["authorization"]["patEligible"] = False
        row["delegation"] = {"intersectOriginalActor": True, "requireCurrentGrant": True,
                             "denyHumanOnly": True, "requireLaunchRole": True}
        actors, derived = gate.authorization(row, set())
        self.assertEqual(actors, [])
        self.assertEqual(set(derived), gate.FIELDS - {"patEligible"})
        for constraint in row["delegation"]:
            hostile = copy.deepcopy(row)
            hostile["delegation"][constraint] = False
            with self.subTest(constraint=constraint), self.assertRaisesRegex(ValueError, "incomplete delegated"):
                gate.authorization(hostile, set())

    def test_operator_customer_credential_substitution(self):
        self.row.update(operationId="operator.suspend", scope="operator", surface="operator", profile="operator")
        self.row["authorization"]["actorKinds"] = ["human"]
        with self.assertRaisesRegex(ValueError, "profile identity mismatch"):
            gate.authorization(self.row, set())

    def test_cf_customer_credential_substitution(self):
        self.row.update(operationId="compute.dispatch", surface="cf-internal", profile="cf-service")
        self.row["authorization"]["actorKinds"] = ["human"]
        with self.assertRaisesRegex(ValueError, "profile identity mismatch"):
            gate.authorization(self.row, set())

    def test_public_local_presence_denied(self):
        self.row.update(operationId="workspace.list", scope="account", surface="public", profile="human-owner")
        self.row["authorization"]["actorKinds"] = ["human"]
        self.row["authorization"]["localPresence"] = True
        with self.assertRaisesRegex(ValueError, "public local-presence"):
            gate.authorization(self.row, set())

    def test_tool_requires_explicit_admission(self):
        self.row.update(operationId="workspace.list", scope="account", surface="public", profile="tool-delegation")
        self.row["authorization"].update(capability="workspace.list", actorKinds=["agent"])
        with self.assertRaisesRegex(ValueError, "tool is not explicitly admitted"):
            gate.authorization(self.row, set())
        self.assertEqual(gate.authorization(self.row, {"workspace.list"})[0], ["agent"])

    def test_tool_profile_cannot_disguise_noncustomer_credentials(self):
        self.row.update(operationId="workspace.list", scope="account", surface="public", profile="tool-delegation")
        self.row["authorization"]["capability"] = "workspace.list"
        for actor in ("operator", "service", "provider", "preauth", "helper-parent"):
            self.row["authorization"]["actorKinds"] = [actor]
            with self.subTest(actor=actor), self.assertRaisesRegex(ValueError, "profile identity mismatch"):
                gate.authorization(self.row, {"workspace.list"})

    def test_operator_profile_cannot_disguise_account_surface(self):
        self.row.update(operationId="workspace.list", scope="account", surface="in-process", profile="operator")
        self.row["authorization"]["actorKinds"] = ["operator"]
        with self.assertRaisesRegex(ValueError, "profile surface mismatch"):
            gate.authorization(self.row, set())

    def test_duplicate_json_key_denied(self):
        path = self.root / "duplicate.json"
        path.write_text('{"risk":"R0","risk":"R3"}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            gate.load(path)

    def test_bootstrap_exact_launch_profile(self):
        row = copy.deepcopy(self.row)
        row.update(operationId="ILocalBootstrap.Challenge", profile="launch-bootstrap-only", idempotency="NI",
                   launchRoles={"from": "verifiedLaunchProfile.callerRoles"}, requireLaunchRole=True)
        row["authorization"]["actorKinds"] = {"from": "verifiedLaunchProfile.actorKinds"}
        self.assertEqual(gate.authorization(row, set()), ([], ["actorKinds"]))
        hostile = copy.deepcopy(row)
        hostile["authorization"]["actorKinds"] = {"from": "caller.actorKinds"}
        with self.assertRaisesRegex(ValueError, "unsupported bootstrap"):
            gate.authorization(hostile, set())
        for mutation in ({"requireLaunchRole": False}, {"operationId": "identity.changePassword"},
                         {"launchRoles": ["helper-parent", "helper-child"]}, {"idempotency": "IW"}):
            hostile = {**row, **mutation}
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "incomplete bootstrap"):
                gate.authorization(hostile, set())

    def test_nonobject_export_denied(self):
        self.fails("row object required", [None])

    def test_export_cannot_spoof_generated_matrix_status(self):
        for field, value in (("status", "pending"), ("reachableActors", ["human"]),
                             ("metadataSource", "invented.json"), ("actorKind", "human")):
            row = {**self.row, field: value}
            with self.subTest(field=field):
                self.fails("unknown operation export fields", [row])

    def test_duplicate_oracle_denied(self):
        self.manifest["operations"].append(self.manifest["operations"][0])
        self.fails("ambiguous oracle row")

    def test_proto_options_and_streaming_discovery(self):
        (self.root / self.source).write_text('package p; service S { '
            'rpc Stream(stream Req) returns(stream Res) { option (x) = {a: "b"}; } '
            'rpc Next(Req) returns(Res); } // rpc Fake(Req) returns(Res);')
        self.assertEqual(set(gate.proto_methods(self.root)), {"p.S/Stream", "p.S/Next"})

    def test_option_strings_cannot_hide_actual_methods(self):
        (self.root / self.source).write_text('package p; service S { '
            'option (x) = "} // rpc Fake(Req) returns(Res);"; '
            'rpc Actual(Req) returns(Res); }')
        self.assertEqual(set(gate.proto_methods(self.root)), {"p.S/Actual"})

    def test_migration_exemption_is_not_wildcard(self):
        (self.root / self.source).write_text('package arcforges.hello.v1; service HelloService { '
                                            'rpc SayHello(Req) returns(Res); }')
        self.fails("unclassified registered method", [])


if __name__ == "__main__":
    unittest.main()
