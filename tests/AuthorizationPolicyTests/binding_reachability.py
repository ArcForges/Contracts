# SPDX-License-Identifier: Apache-2.0
"""Classify identity, workspace, device and session bindings of the operation catalogue.

Static check over declared metadata only: the authored operation exports (through the
operation matrix) against the identity facts that the Cloud and Platform producers
declared, as pinned in `producer-declarations.json`. It is not authentication, runtime
enforcement or proof that any operation handler exists.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from producer_declarations import load, require, validate_snapshot

CLASSIFICATION = Path(__file__).with_name('binding-classification.json')
DOMAINS = {'identity', 'workspace', 'device'}
BINDINGS = {'user', 'authenticationIdentity', 'session', 'device', 'workspace', 'apiToken', 'flow'}
TOOL_ACTORS = {'agent', 'automation', 'extension'}
# Tables are the producer-declared homes of each binding; `references` and `unique` are the
# declared relations the binding's ownership and realm claims rest on.
BINDING_FACTS = {
    'user': {'table': 'identity_user', 'realm': True},
    'authenticationIdentity': {'table': 'identity_auth_identity', 'references': ['user_id>identity_user'],
                               'unique': ['realm_id+provider_id+subject'], 'realm': True},
    'session': {'table': 'identity_session', 'references': ['user_id>identity_user', 'device_id>device_device']},
    'device': {'table': 'device_device', 'references': ['user_id>identity_user']},
    'workspace': {'table': 'workspace_workspace', 'references': ['owner_user_id>identity_user'],
                  'unique': ['realm_id+owner_user_id'], 'realm': True},
    'apiToken': {'table': 'identity_api_token', 'references': ['user_id>identity_user', 'workspace_id>workspace_workspace']},
    'flow': {'table': 'identity_browser_auth_flow'},
}
FLOW_TABLES = ('identity_browser_auth_flow', 'identity_recovery_flow', 'identity_native_authorization',
               'identity_step_up_challenge', 'identity_security_flow')
# Concepts that must not exist in the declared identity, device or workspace model.
FORBIDDEN = re.compile(r'(member|invit|seat|shared_?editor|team|organi[sz]ation|service_?principal)', re.I)
# The operator access `role` column is a separate operator identity, not workspace membership (WO-05).
ALLOWED_ROLE_COLUMNS = {('identity_operator_access', 'role')}
OBLIGATION_STATUSES = {'bound', 'declared-port', 'pending-producer'}


def load_classification(path: Path = CLASSIFICATION) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _words(name: str) -> bool:
    return FORBIDDEN.search(name) is not None


def check_vocabulary(cloud: dict) -> None:
    for table, facts in cloud['tables'].items():
        require(not _words(table), f'identity boundary violation: model concept in table {table}')
        for column in facts['columns']:
            require(not _words(column), f'identity boundary violation: model concept in {table}.{column}')
            require(column != 'role' or (table, column) in ALLOWED_ROLE_COLUMNS,
                    f'identity boundary violation: role concept in {table}.{column}')
    kinds = cloud['identifierTypes']
    require(sorted(kinds) == ['AuthIdentityId', 'RealmId', 'UserId', 'WorkspaceId'],
            'identity boundary violation: authentication identity, user, workspace and realm are not four distinct identifiers')


def check_binding_facts(cloud: dict) -> dict:
    """Every binding is declared by the producer and owned by exactly the user it names."""
    declared = {}
    tables = cloud['tables']
    for binding, spec in BINDING_FACTS.items():
        table = tables.get(spec['table'])
        require(table is not None, f'binding {binding} has no declared producer table {spec["table"]}')
        for reference in spec.get('references', []):
            require(reference in table['references'], f'identity boundary violation: {spec["table"]} lacks declared owner relation {reference}')
        for unique in spec.get('unique', []):
            require(unique in table['unique'], f'identity boundary violation: {spec["table"]} lacks declared uniqueness {unique}')
        if spec.get('realm'):
            require('realm_id' in table['columns'], f'identity boundary violation: {spec["table"]} is not realm scoped')
        declared[binding] = spec['table']
    for flow in FLOW_TABLES:
        require(flow in tables, f'flow table {flow} is not declared')
    return declared


def reaches_user(cloud: dict, table: str, seen: frozenset = frozenset()) -> bool:
    if table == 'identity_user':
        return True
    if table in seen or table not in cloud['tables']:
        return False
    targets = [ref.split('>')[1] for ref in cloud['tables'][table]['references']]
    return any(reaches_user(cloud, target, seen | {table}) for target in targets)


def classify(matrix: dict, classification: dict, cloud: dict) -> dict:
    check_vocabulary(cloud)
    declared = check_binding_facts(cloud)
    for binding, table in declared.items():
        require(binding in {'user', 'flow'} or reaches_user(cloud, table),
                f'identity boundary violation: {binding} does not reach its owning user')
    plans = {plan['name']: plan for plan in cloud['plans']}
    rows = {row['operationId']: row for row in matrix['operations'] if row['status'] == 'registered'
            and row['operationId'].split('.')[0] in DOMAINS}
    entries = {}
    for entry in classification['operations']:
        require(entry['operationId'] not in entries, f'ambiguous binding classification: {entry["operationId"]}')
        entries[entry['operationId']] = entry
    missing = sorted(set(rows) - set(entries))
    require(not missing, f'operation without an authorization binding: {missing[0] if missing else ""}')
    stale = sorted(set(entries) - set(rows))
    require(not stale, f'binding classification names no registered operation: {stale[0] if stale else ""}')
    result = []
    for operation, entry in sorted(entries.items()):
        row, bindings = rows[operation], entry['bindings']
        auth = row['authorization']
        require(bindings and len(bindings) == len(set(bindings)) and set(bindings) <= BINDINGS,
                f'{operation}: unclassified or ambiguous bindings')
        actors = set(auth['actorKinds'])
        require(not actors & TOOL_ACTORS, f'{operation}: tool actor reaches an identity-bearing binding')
        if actors == {'preauth'}:
            require(row['profile'] == 'one-use-auth' and ({'flow', 'session'} & set(bindings)),
                    f'{operation}: pre-authentication operation without a flow or session binding')
        else:
            require(actors == {'human'} and row['profile'] == 'human-owner',
                    f'{operation}: owner binding reachable by a non-owner actor')
        if auth['patEligible']:
            require(row['idempotency'] == 'Q' and set(bindings) <= {'workspace', 'user'},
                    f'{operation}: automation token reaches a binding it may not mutate')
        if 'workspace' in bindings and actors == {'human'}:
            require('owner_user_id>identity_user' in cloud['tables']['workspace_workspace']['references'],
                    f'{operation}: workspace binding without the direct owner relation')
        plan = entry.get('plan')
        if plan is not None:
            require(plan in plans, f'{operation}: plan {plan} is not declared by the producer pin')
            require((plans[plan]['access'] == 'read') == (row['idempotency'] == 'Q'),
                    f'{operation}: idempotency {row["idempotency"]} contradicts {plans[plan]["access"]} plan {plan}')
        result.append({'operationId': operation, 'profile': row['profile'], 'idempotency': row['idempotency'],
                       'actorKinds': sorted(actors), 'bindings': sorted(bindings),
                       'producerTables': sorted({declared[b] for b in bindings}), 'plan': plan,
                       'model': 'declared', 'behavior': 'not-bound'})
    return {'domains': sorted(DOMAINS), 'classified': len(result), 'operations': result,
            'bindingTables': dict(sorted(declared.items()))}


def _fact(snapshot: dict, spec: dict) -> bool:
    cloud = snapshot['producers']['cloud']['declared']
    platform = snapshot['producers']['platform']['declared']
    check = spec['check']
    if check == 'references':
        table = cloud['tables'].get(spec['table'])
        return table is not None and spec['reference'] in table['references']
    if check == 'tableExists':
        return spec['table'] in cloud['tables']
    if check == 'noReferenceTo':
        table = cloud['tables'].get(spec['table'])
        return table is not None and not any(ref.endswith('>' + spec['target']) for ref in table['references'])
    if check == 'unique':
        table = cloud['tables'].get(spec['table'])
        return table is not None and spec['columns'] in table['unique']
    if check == 'pointStep':
        number = platform['steps'].get(spec['step'])
        return number is not None and number in platform['pointSteps'].get(spec['point'], [])
    raise ValueError(f'unknown producer fact check {check}')


def bind_identity_chain(declaration: dict, classification: dict, snapshot: dict) -> list:
    """Bind every owner/deployment chain obligation to a producer fact, or name it pending."""
    chain = classification['identityChain']
    required = {obligation for rules in declaration['rules'].values() for obligation in rules}
    entries = {entry['obligation']: entry for entry in chain}
    require(len(entries) == len(chain), 'ambiguous identity chain obligation')
    require(set(entries) == required, f'identity chain obligations differ from the declaration: {sorted(set(entries) ^ required)}')
    out = []
    for name in sorted(entries):
        entry = entries[name]
        status = entry['status']
        require(status in OBLIGATION_STATUSES, f'{name}: unclassified obligation status')
        if status == 'pending-producer':
            require(entry.get('requires') == [] and entry.get('reason'), f'{name}: pending obligation without a named reason')
        else:
            require(entry['requires'], f'{name}: {status} obligation without producer facts')
            for spec in entry['requires']:
                require(_fact(snapshot, spec), f'{name}: producer fact not declared at the pin: {spec}')
        if status == 'declared-port':
            require(entry.get('limit'), f'{name}: port-declared obligation without its stated limit')
        out.append({'obligation': name, 'status': status, 'facts': len(entry['requires']),
                    **({'reason': entry['reason']} if 'reason' in entry else {}),
                    **({'limit': entry['limit']} if 'limit' in entry else {})})
    return out


def bound_report(matrix: dict, declaration: dict, classification: dict | None = None, snapshot: dict | None = None) -> dict:
    classification = classification or load_classification()
    snapshot = snapshot or load()
    validate_snapshot(snapshot)
    cloud = snapshot['producers']['cloud']['declared']
    binding_matrix = classify(matrix, classification, cloud)
    obligations = bind_identity_chain(declaration, classification, snapshot)
    return {
        'bindingMatrix': binding_matrix,
        'identityIntegration': {
            'status': 'bound-to-declared-producer-metadata',
            'producers': {name: {'task': e['task'], 'repository': e['repository'], 'commit': e['commit'], 'factsDigest': e['factsDigest']}
                          for name, e in sorted(snapshot['producers'].items())},
            'obligations': obligations,
            'statusCounts': {s: sum(1 for o in obligations if o['status'] == s) for s in sorted(OBLIGATION_STATUSES)},
            'limits': classification['limits'],
        },
    }
