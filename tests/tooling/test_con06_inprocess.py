# SPDX-License-Identifier: Apache-2.0
"""Independent registry04 inventory checks; no service execution or runtime authority."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'fixtures/internal/con-06-product-ports.json'
SOURCES = {
    'Platform': 'internal/proto/arcforges/local/platform/v1/inprocess.proto',
    'Chat': 'internal/proto/arcforges/local/chat/v1/chat.proto',
    'Scope': 'internal/proto/arcforges/local/scope/v1/scope.proto',
}


def blocks(text, declaration):
    result = {}
    for match in re.finditer(r'\b' + declaration + r'\s+(\w+)\s*\{', text):
        start, level, end = match.end(), 1, match.end()
        while level:
            if end >= len(text):
                raise ValueError('Unclosed declaration')
            level += (text[end] == '{') - (text[end] == '}')
            end += 1
        result[match[1]] = text[start:end - 1]
    return result


class InprocessContractCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))

    def test_independent_complete_port_inventory(self):
        ports = self.fixture['ports']
        self.assertEqual(sum(len(group) for group in ports.values()), 9)
        self.assertEqual(sum(len(methods) for group in ports.values() for methods in group.values()), 38)
        for owner, interfaces in ports.items():
            source = (ROOT / f'src/internal/dotnet/ArcForges.Contracts.LocalRpc.{owner}/Generated/InprocessPorts.g.cs').read_text()
            actual = blocks(source, 'interface')
            self.assertEqual(set(actual), set(interfaces))
            for interface, methods in interfaces.items():
                body = actual[interface]
                self.assertEqual(re.findall(r'> (\w+)Async\(', body), methods)
                service = interface[1:] + 'Service'
                for method in methods:
                    prefix = f'global::ArcForges.Contracts.LocalRpc.{owner}.V1.{service}{method}'
                    signature = (f'global::System.Threading.Tasks.ValueTask<{prefix}Response> {method}Async('
                                 f'{prefix}Request request, global::System.Threading.CancellationToken cancellationToken = default);')
                    self.assertIn(signature, body)
            for forbidden in ['Grpc.Core', 'CallInvoker', 'IServiceProvider', 'dynamic ', 'Reflection', 'BindService']:
                self.assertNotIn(forbidden, source)

    def test_all_38_owned_three_message_envelopes(self):
        for owner, interfaces in self.fixture['ports'].items():
            source = (ROOT / SOURCES[owner]).read_text()
            self.assertNotRegex(source, r'(?m)^\s*(service|rpc)\s+')
            messages = blocks(source, 'message')
            expected = set()
            for interface, methods in interfaces.items():
                for method in methods:
                    stem = interface[1:] + 'Service' + method
                    expected.update(stem + part for part in ['Request', 'Response', 'Value'])
                    request, response, value = (messages[stem + part] for part in ['Request', 'Response', 'Value'])
                    self.assertRegex(request, r'arcforges\.foundation\.v1\.RequestMeta meta = 1\b')
                    self.assertIn('reserved 2 to 9;', request)
                    self.assertRegex(response, r'arcforges\.foundation\.v1\.ResponseMeta meta = 1\b')
                    outcome = blocks(response, 'oneof')['outcome']
                    self.assertRegex(outcome, stem + r'Value value = 2\b')
                    self.assertRegex(outcome, r'arcforges\.foundation\.v1\.ArcError error = 3\b')
                    self.assertTrue(all(int(tag) >= 10 for tag in re.findall(r'=\s*(\d+)\s*\[', value)))
            actual = {name for name in messages if re.match(r'\w+Service\w+(Request|Response|Value)$', name)}
            self.assertEqual(actual, expected)

    def test_public_values_never_import_private_ports(self):
        for path in (ROOT / 'public/proto').rglob('*.proto'):
            source = path.read_text()
            self.assertNotRegex(source, r'import\s+"(?:internal/|arcforges/local/)')
            self.assertNotRegex(source, r'\barcforges\.local\.')
        public = (ROOT / 'public/proto/arcforges/publicapi/v1/inprocess-values.proto').read_text()
        self.assertNotRegex(public, r'(?m)^\s*(service|rpc)\s+')
        self.assertIn('reserved "timeline";', public)
        chat = (ROOT / SOURCES['Chat']).read_text()
        artifact = blocks(chat, 'message')['ChatOperationsServiceOpenArtifactRequest']
        self.assertIn('reserved 11;', artifact)
        self.assertNotRegex(artifact, r'\btarget_app_id\b\s*=')

    def test_fixture_corpus_has_positive_and_negative_domain_cases(self):
        rows = self.fixture['cases']
        self.assertGreaterEqual(len(rows), 70)
        self.assertEqual(len({row['id'] for row in rows}), len(rows))
        self.assertEqual({row['domain'] for row in rows}, {'decoder', 'turn', 'consent', 'hint', 'chunk'})
        typed = (ROOT / 'tests/StructureTests/Con06InprocessCases.cs').read_text()
        for domain in {row['domain'] for row in rows}:
            self.assertEqual({row['valid'] for row in rows if row['domain'] == domain}, {True, False})
        for row in rows:
            self.assertIn('case "' + row['case'] + '"', typed)
        # These prove absence/false and exact arithmetic bounds rather than only empty-message negatives.
        for case in ['searchable-false', 'cloud-index-false', '64-sources', '65-sources', 'last-address', 'overflow',
                     'spi-active-options', 'missing-active-bit', 'agent-with-turn', 'missing-sequence']:
            self.assertIn(case, {row['case'] for row in rows})

    def test_closed_decoder_and_consent_profiles_are_registered(self):
        scope = json.loads((ROOT / 'internal/proto/constraints/con-06-scope.json').read_text())['messages']
        decoder = scope['arcforges.local.scope.v1.DecoderOptions']
        self.assertEqual(decoder['fields']['kind']['enumValues'], ['uart', 'i2c', 'spi'])
        self.assertEqual(decoder['fields']['parity']['enumValues'], ['none', 'odd', 'even'])
        self.assertTrue(decoder['fields']['timeout']['required'])
        values = json.loads((ROOT / 'public/proto/constraints/inprocess-values.json').read_text())['messages']
        consent = values['arcforges.publicapi.v1.SourceConsentSpec']
        self.assertEqual(consent['fields']['sources']['maxItems'], 64)
        self.assertEqual(consent['fields']['purpose']['enumValues'], ['turnContext', 'webSearch', 'attachment'])
        patch = values['arcforges.publicapi.v1.KnowledgePolicyPatch']['fields']
        self.assertTrue(all(not field.get('required', False) for field in patch.values()))


if __name__ == '__main__':
    unittest.main()
