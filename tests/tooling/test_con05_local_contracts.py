# SPDX-License-Identifier: Apache-2.0
"""Offline annex09 contract oracle: no OS transport or runtime authorization evidence."""
import hashlib
import hmac
import json
import pathlib
import re
import unittest
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
VECTORS = ROOT / 'fixtures/internal/con-05-extension-connector-bootstrap.json'


def bootstrap_admitted(value, secret):
    # Fixed launch record is independent of the untrusted confirmation fields.
    expected = ('launch-a', '10213243-5465-7687-98a9-bacbdcedfe0f',
                '11223344-5566-7788-99aa-bbccddeeff00', '22334455-6677-8899-aabb-ccddeeff0011')
    if (value['connection'], value['challengeId'], value['instanceId'], value['serverInstanceId']) != expected:
        return False
    if not value['parentAlive'] or value['consumed']:
        return False
    if not value['issuedMillis'] <= value['nowMillis'] < value['challengeExpiresMillis']:
        return False
    if not 0 < value['challengeExpiresMillis'] - value['issuedMillis'] <= 5000:
        return False
    client, server, proof = (bytes.fromhex(value[key]) for key in ('clientChallenge', 'serverChallenge', 'proof'))
    if any(len(part) != 32 for part in (secret, client, server, proof)):
        return False
    transcript = (b'arcforges.local.bootstrap.v1' + uuid.UUID(value['challengeId']).bytes + client + server
                  + uuid.UUID(value['instanceId']).bytes + uuid.UUID(value['serverInstanceId']).bytes)
    return hmac.compare_digest(proof, hmac.digest(secret, transcript, 'sha256'))


def connector_admitted(value):
    if not value['parentAlive'] or not value['owningParent']:
        return False
    if value['method'] == 'GetConnection':
        return True  # Recovery reads do not replay a mutating completion.
    if value['actor'] != 'human' or not all(value[key] for key in ('foreground', 'consented', 'stepUp')):
        return False
    if value['definitionHash'] != value['currentDefinitionHash']:
        return False
    if value['method'] == 'RevokeConnection':
        return value['expectedRevision'] == value['currentRevision']
    if value['method'] != 'CompleteConnection' or value['state'] != 'awaitingAuthorization':
        return False
    if value['nowMillis'] >= value['flowExpiresMillis'] or value['flowConsumed']:
        return False
    if not set(value['scopes']).issubset(value['allowedScopes']):
        return False
    if value['authKind'] == 'oauth2':
        return value['proofKind'] == 'callbackReceipt' and value['origin'] in value['allowedOrigins']
    return value['authKind'] == 'personalToken' and value['proofKind'] == 'personalToken'


class LocalContractCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads(VECTORS.read_text(encoding='utf-8'))

    def test_canonical_hmac_transcript(self):
        source = self.vectors
        transcript = (b'arcforges.local.bootstrap.v1' + bytes.fromhex('102132435465768798a9bacbdcedfe0f')
                      + bytes(range(32, 64)) + bytes(range(64, 96))
                      + bytes.fromhex('112233445566778899aabbccddeeff00')
                      + bytes.fromhex('2233445566778899aabbccddeeff0011'))
        self.assertEqual(transcript.hex(), source['transcriptHex'])
        digest = hmac.digest(bytes(range(32)), transcript, 'sha256').hex()
        self.assertEqual('6011473a98e397c8cfb77018cd6f20e7c281d6d81448821f1e4b636ca96c73e0', digest)
        self.assertEqual(digest, source['expectedProofHex'])
        self.assertNotEqual(hashlib.sha256(transcript).hexdigest(), digest)

    def test_bootstrap_vectors(self):
        for case in self.vectors['bootstrap']:
            with self.subTest(case=case['id']):
                self.assertEqual(case['valid'], bootstrap_admitted(case['input'], bytes.fromhex(self.vectors['testOnlySecretHex'])))

    def test_extension_receiver_roles(self):
        methods = {'parent': {'Handshake', 'RenewLease', 'Invoke'}, 'child': {'Invoke', 'Stop'}}
        for case in self.vectors['extensionDirections']:
            with self.subTest(case=case['id']):
                admitted = case['child'] == 'extension' and case['method'] in methods.get(case['receiver'], set())
                self.assertEqual(case['valid'], admitted)

    def test_connector_state_and_recovery_vectors(self):
        for case in self.vectors['connector']:
            with self.subTest(case=case['id']):
                self.assertEqual(case['valid'], connector_admitted(case['input']))
        self.assertEqual({'configured', 'awaitingAuthorization', 'connected', 'expired', 'revoked', 'failed'}, set(self.vectors['connectorStates']))

    def test_nonce_lease_vectors(self):
        for case in self.vectors['nonceLease']:
            with self.subTest(case=case['id']):
                admitted = (case['nonceBytes'] == 32 and case['sameConnection'] and case['parentAlive']
                            and case['issuedMillis'] <= case['nowMillis'] < case['expiresMillis']
                            and 0 < case['expiresMillis'] - case['issuedMillis'] <= 30000)
                self.assertEqual(case['valid'], admitted)

    def test_retired_services_are_not_active(self):
        manifest = json.loads((ROOT / 'eng/local-contract-retirements.json').read_text(encoding='utf-8'))
        retired = {name for row in manifest['retired'] for name in row['names']}
        self.assertTrue({'IHubRegistry', 'IHubRouting', 'DeviceSsoBrokerService'} <= retired)
        active = set()
        for tree in ('public/proto', 'internal/proto'):
            for path in (ROOT / tree).rglob('*.proto'):
                text = re.sub(r'//[^\n]*|/\*.*?\*/', '', path.read_text(encoding='utf-8'), flags=re.S)
                active.update(re.findall(r'\bservice\s+([A-Za-z_][A-Za-z_0-9]*)\s*\{', text))
        self.assertFalse(active & retired, f'Retired active gRPC registration: {active & retired}')


if __name__ == '__main__':
    unittest.main()

