# SPDX-License-Identifier: Apache-2.0
"""Offline declaration assertions; never a production authorization engine."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('operation_metadata', ROOT / 'eng/check_operation_scope.py')
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)

AUTHORIZATION_FIELDS = {'capability', 'risk', 'approval', 'stepUp', 'localPresence', 'egress', 'patEligible'}


def assert_identity_declaration(declaration: dict) -> None:
    """Validate a test-only normalized owner/deployment rule declaration.

    This is an assertion contract for future producer evidence adapters, not an
    emitted Cloud or Platform contract or a claim those adapters already exist.
    """
    required = {'schemaVersion', 'authorityKinds', 'identityKey', 'rules'}
    metadata.require(set(declaration) == required and declaration['schemaVersion'] == 'identity-assertion-fixture.v1',
                     'unclassified identity declaration')
    metadata.require(declaration['identityKey'] == ['realmId', 'userId'], 'bare user identity')
    metadata.require(set(declaration['authorityKinds']) == {'human-owner', 'operator', 'deployment-service'},
                     'independent customer service-principal or organization authority')
    rules = declaration['rules']
    expected = {
        'agent': {'userSession', 'workspaceOwner', 'currentPermission', 'currentServiceEligibility'},
        'automation': {'workspaceOwner', 'currentPermission', 'currentServiceEligibility', 'recheckAtTrigger'},
        'deployment-service': {'explicitProvisioning', 'workspaceOwner', 'currentPermission', 'currentServiceEligibility'},
        'operator': {'separateOperatorIdentity'},
    }
    metadata.require(set(rules) == set(expected), 'unclassified identity rule')
    for kind, obligations in expected.items():
        metadata.require(isinstance(rules[kind], list) and len(rules[kind]) == len(set(rules[kind]))
                         and set(rules[kind]) == obligations, f'{kind}: owner/deployment chain missing or ambiguous')


def fixture_decision(case: dict) -> str:
    """Evaluate independent symbolic boundary snapshots, not process credentials."""
    actor = case['originalActor']
    chain = case['actorChain']
    allowed = {'human', 'agent', 'automation', 'extension'}
    if actor not in allowed or not isinstance(chain, list) or not chain or chain[0] != actor:
        return 'identity-chain'
    if any(kind in {'operator', 'service', 'provider', 'preauth', 'organization', 'customer-service-principal'} for kind in chain):
        return 'identity-substitution'
    # The first identity stays the original actor. Later links can attenuate to
    # a tool identity, never recover human authority. The claim names the current
    # link, and every tool link retains tool restrictions for the whole chain.
    if any(kind not in allowed for kind in chain) or 'human' in chain[1:] or len(chain) > 16:
        return 'identity-chain'
    if case['claimedActor'] != chain[-1]:
        return 'identity-substitution'
    if case['ownerRealm'] != case['credentialRealm'] or case['ownerUser'] != case['workspaceOwner']:
        return 'owner-chain'
    if case['processCredential'] != 'valid':
        return 'credential'
    if case['ownerPermission'] != 'current':
        return 'owner-permission'
    if case['ownerServiceEligibility'] != 'current':
        return 'owner-service-eligibility'
    if set(chain) & metadata.TOOL_ACTORS and (case['humanOnly'] or not case['catalogueTool']):
        return 'tool-reachability'
    if case['resourceAuthorization'] != 'current':
        return 'resource'
    if case['boundary'] != 'none':
        grant = case['egressGrant']
        expected = {name: case[name] for name in ('sourceVersion', 'purpose', 'destination')}
        if grant != expected or case['sourcePolicy'] != 'current':
            return 'egress'
        if case['boundary'] == 'context' and case['sourceKind'] == 'raw-scope-capture':
            return 'raw-context'
        if case['boundary'] == 'connector' and (case['definitionHash'] != case['grantDefinitionHash']
                                               or case['providerOrigin'] not in case['grantedOrigins']
                                               or not set(case['requestedScopes']) <= set(case['grantedScopes'])):
            return 'connector-egress'
    return 'admissible-fixture'


def report(root: Path = ROOT) -> dict:
    matrix = metadata.audit(root)
    registered = [row for row in matrix['operations'] if row['status'] == 'registered']
    for row in registered:
        metadata.require(set(row['authorization']) == AUTHORIZATION_FIELDS | {'actorKinds'},
                         'incomplete authorization matrix fields')
    fixture = metadata.load(Path(__file__).with_name('boundary-fixtures.json'))
    assert_identity_declaration(fixture['identityDeclaration'])
    results = []
    for case in fixture['cases']:
        actual = fixture_decision(case['input'])
        metadata.require(actual == case['expected'], f"fixture assertion differs: {case['id']}")
        results.append({'id': case['id'], 'actual': actual, 'result': 'passed'})
    return {'schemaVersion': 'authorization-boundary-evidence.v1', 'result': 'passed',
            'coverage': 'offline declared metadata and symbolic hostile fixtures only',
            'authorizationFields': sorted(AUTHORIZATION_FIELDS), 'actorClassification': 'actorKinds',
            'matrix': matrix, 'fixtureResults': results,
            'identityIntegration': {'status': 'pending', 'requiredProducers': ['CLOUD.11', 'PLT.38'],
                                    'reason': 'Actual producer declarations and original receipts have not been bound; fixture decisions do not substitute for them.'}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    options = parser.parse_args()
    result = report()
    options.report.parent.mkdir(parents=True, exist_ok=True)
    options.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f"Authorization assertions passed: {len(result['fixtureResults'])} fixtures; identity integration pending.")
