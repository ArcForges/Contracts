# SPDX-License-Identifier: Apache-2.0
"""Independent configuration profile oracle; never provider or activation evidence."""
import copy
from datetime import datetime
from fractions import Fraction
import ipaddress
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / 'internal/ai-http/v1/configuration.schema.json'
# Owner merges the independent vectors into this admitted aggregate fixture path.
FIXTURE = ROOT / 'fixtures/internal/con-12-configuration.json'


def shape(value, node, schema):
    if '$ref' in node:
        return shape(value, schema['$defs'][node['$ref'].split('/')[-1]], schema)
    kind = node.get('type')
    if kind == 'object':
        if not isinstance(value, dict): return False
        if not node.get('minProperties', 0) <= len(value) <= node.get('maxProperties', 10**6): return False
        props = node.get('properties', {})
        if not set(node.get('required', [])).issubset(value): return False
        for key, child in value.items():
            if key in props:
                if not shape(child, props[key], schema): return False
            elif isinstance(node.get('additionalProperties'), dict):
                if not shape(key, node.get('propertyNames', {}), schema) or not shape(child, node['additionalProperties'], schema): return False
            else: return False
    elif kind == 'array':
        if not isinstance(value, list) or not node.get('minItems', 0) <= len(value) <= node.get('maxItems', 10**6): return False
        if not all(shape(item, node['items'], schema) for item in value): return False
    elif kind == 'string':
        if not isinstance(value, str) or not node.get('minLength', 0) <= len(value) <= node.get('maxLength', 10**6): return False
        if 'pattern' in node and re.search(node['pattern'], value) is None: return False
        if 'canonicalDecimal' in node.get('x-arcforges-rules', []) and (len(value.replace('.', '').lstrip('0')) > 28 or len(value.partition('.')[2]) > 9): return False
        if 'uint64String' in node.get('x-arcforges-rules', []) and int(value) > 2**64 - 1: return False
        if 'nonzeroUuid' in node.get('x-arcforges-rules', []) and value == '00000000-0000-0000-0000-000000000000': return False
    elif kind == 'integer':
        if type(value) is not int or not node.get('minimum', -10**100) <= value <= node.get('maximum', 10**100): return False
    elif kind == 'boolean' and type(value) is not bool: return False
    if 'const' in node and value != node['const']: return False
    if 'enum' in node and value not in node['enum']: return False
    return True


def static_configuration(value):
    """Closed-field/reference checks only. Secrets, pinned artifacts and external readiness are owner checks."""
    if value['version'] == value['parentVersion']: return False
    if int(value['funding']['defaultRunBudget']) > int(value['funding']['maximumCustomerBudget']): return False
    if value['email']['transactionalDomain'].lower() == value['email']['broadcastDomain'].lower(): return False
    identity = value['identity']
    if identity['realmKind'] == 'official' and (set(identity['enabledMethods']) - {'passkey', 'email'} or any(p['kind'] not in {'passkey', 'email'} for p in identity['providers'])): return False
    if len(set(identity['enabledMethods'])) != len(identity['enabledMethods']): return False
    if value['operatorIdentity']['issuer'] == identity['publicOrigin'] or any(p['issuer'] == value['operatorIdentity']['issuer'] for p in identity['providers']): return False
    collections = [('offers', 'offerId'), ('entitlementProfiles', 'id'), ('customerTariffs', 'id'), ('supplierPrices', 'id'), ('serviceKeys', 'keyId')]
    for name, key in collections:
        if len({row[key] for row in value[name]}) != len(value[name]): return False
    models = value['models']
    if len({(row['modelId'], row['purpose']) for row in models}) != len(models): return False
    if len({p['id'] for p in identity['providers']}) != len(identity['providers']): return False
    profiles = {p['id'] for p in value['entitlementProfiles']}
    tariffs = {p['id']: p for p in value['customerTariffs']}
    prices = {p['id']: p for p in value['supplierPrices']}
    model_ids = {p['modelId'] for p in models}
    if any(p['modelId'] not in model_ids for p in [*tariffs.values(), *prices.values()]): return False
    for offer in value['offers']:
        if offer['entitlementProfileId'] not in profiles: return False
        if (offer['kind'] == 'credits') == ('interval' in offer): return False
        if len(set(offer['regionSet'])) != len(offer['regionSet']): return False
    currency = value['funding']['operatorExposureLimit']['currency']
    if any(p['currency'] != currency for p in prices.values()) and 'fxSnapshotHash' not in value['funding']: return False
    search_budget = value['search']['operatorBudget']
    if search_budget['currency'] != currency: return False
    if Fraction(search_budget['amount']) > Fraction(value['funding']['operatorExposureLimit']['amount']): return False
    for model in models:
        price = prices.get(model['supplierPriceId'])
        if price is None or price['modelId'] != model['modelId'] or price['provider'] != model['provider']: return False
        if int(model['maxOutputTokens']) > int(model['contextTokens']): return False
        if len(set(model['inputKinds'])) != len(model['inputKinds']): return False
        route = model['route']
        if model['purpose'] == 'embedding' and route != '@cf/baai/bge-m3': return False
        if model['purpose'] == 'rerank' and route != '@cf/baai/bge-reranker-base': return False
        if model['purpose'] in {'customerInference', 'platformCompaction'} and route not in {'@cf/openai/gpt-oss-120b', '@cf/openai/gpt-oss-20b', '@cf/google/gemma-4-26b-a4b-it'}: return False
        if 'image' in model['inputKinds'] and (route != '@cf/google/gemma-4-26b-a4b-it' or model['purpose'] != 'customerInference'): return False
        if model['purpose'] != 'customerInference' and 'customerTariffId' in model: return False
        if 'customerTariffId' in model:
            tariff = tariffs.get(model['customerTariffId'])
            if tariff is None or tariff['modelId'] != model['modelId']: return False
        elif model['purpose'] == 'customerInference' and model['enabled']: return False
        if 'image' in model['inputKinds'] and ('imagePrice' not in price or ('customerTariffId' in model and 'imageMicrounits' not in tariffs[model['customerTariffId']])): return False
        if 'audio' in model['inputKinds'] and ('audioPerSecond' not in price or ('customerTariffId' in model and 'audioMicrounitsPerSecond' not in tariffs[model['customerTariffId']])): return False
    try:
        def inspect(node):
            if isinstance(node, dict):
                for key, item in node.items():
                    if key in {'effectiveAt', 'validFrom', 'activatesAt', 'retiresAt'}: datetime.fromisoformat(item.replace('Z', '+00:00'))
                    inspect(item)
            elif isinstance(node, list):
                for item in node: inspect(item)
        inspect(value)
        keys = value['serviceKeys']
        for key in keys:
            if datetime.fromisoformat(key['activatesAt']) >= datetime.fromisoformat(key['retiresAt']): return False
        for i, a in enumerate(keys):
            for b in keys[i+1:]:
                if a['direction'] != b['direction']: continue
                overlap = (min(datetime.fromisoformat(a['retiresAt']), datetime.fromisoformat(b['retiresAt'])) - max(datetime.fromisoformat(a['activatesAt']), datetime.fromisoformat(b['activatesAt']))).total_seconds()
                if overlap > 900: return False
    except (ValueError, OverflowError): return False
    external = [identity['publicOrigin'], value['operatorIdentity']['issuer'], value['operatorIdentity']['audience'], value['observability']['otlpEndpoint'], value['status']['externalOrigin'], *value['origins']['providerEgressOrigins']]
    external += [p['issuer'] for p in identity['providers']]
    external += [u for p in identity['providers'] for u in p['redirectUris']]
    for url in external:
        host = urlsplit(url).hostname or ''
        if host.lower() == 'localhost' or host.lower().endswith(('.localhost', '.local', '.internal')): return False
        if re.search(r'(^|\.)0x[0-9a-f]+($|\.)', host, re.I): return False
        if re.fullmatch(r'[0-9.]+', host):
            if not re.fullmatch(r'(0|[1-9][0-9]{0,2})(\.(0|[1-9][0-9]{0,2})){3}', host): return False
            try: address = ipaddress.ip_address(host)
            except ValueError: return False
            denied = ['0.0.0.0/8','10.0.0.0/8','127.0.0.0/8','224.0.0.0/3','169.254.0.0/16','172.16.0.0/12','192.168.0.0/16','100.64.0.0/10','198.18.0.0/15','192.0.0.0/16','198.51.100.0/24','203.0.113.0/24']
            if any(address in ipaddress.ip_network(block) for block in denied): return False
    return True


def admitted(value, schema):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()) <= 1048576 and shape(value, schema, schema) and static_configuration(value)


class ConfigurationCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA.read_text(encoding='utf-8-sig'))
        local = ROOT / '.con12-config-vectors.json'
        data = json.loads((local if local.is_file() else FIXTURE).read_text(encoding='utf-8-sig'))
        cls.vectors = data if data.get('schemaVersion') == 'configuration-fixtures.v1' else data['configuration']

    def test_complete_section_inventory(self):
        sections = {'identity', 'offers', 'entitlementProfiles', 'customerTariffs', 'supplierPrices', 'funding', 'models', 'search', 'commerce', 'objects', 'backup', 'launchCapacity', 'release', 'policy', 'email', 'push', 'operatorIdentity', 'serviceKeys', 'origins', 'observability', 'status'}
        self.assertEqual(sections, set(self.schema['required']) - {'schemaVersion', 'version', 'parentVersion', 'effectiveAt', 'realmId'})
        self.assertTrue(all(name.startswith('Configuration') for name in self.schema['$defs']))

    def test_independent_vectors(self):
        for case in self.vectors['cases']:
            with self.subTest(case=case['id']):
                value = copy.deepcopy(self.vectors['valid'])
                if 'path' in case:
                    target = value
                    for key in case['path'][:-1]: target = target[key]
                    if case.get('delete'): del target[case['path'][-1]]
                    else: target[case['path'][-1]] = case['value']
                self.assertEqual(case['valid'], admitted(value, self.schema))

    def test_duplicate_stable_ids_and_key_overlap(self):
        value = copy.deepcopy(self.vectors['valid'])
        value['offers'].append(copy.deepcopy(value['offers'][0]))
        self.assertFalse(admitted(value, self.schema))
        value = copy.deepcopy(self.vectors['valid'])
        value['serviceKeys'].append({**value['serviceKeys'][0], 'keyId': 'fixture.second'})
        self.assertFalse(admitted(value, self.schema))

    def test_fixture_is_not_activation_evidence(self):
        self.assertIn('not-activation', self.vectors['evidenceClass'])
        self.assertFalse(self.vectors['valid']['commerce']['paymentEnabled'])
        self.assertTrue(self.vectors['valid']['identity']['publicOrigin'].endswith('.invalid'))

if __name__ == '__main__':
    unittest.main()
