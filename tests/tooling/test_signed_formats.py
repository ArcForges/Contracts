# SPDX-License-Identifier: Apache-2.0
"""Independent offline CON.16 vectors; fixture trust is never production authority."""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate property")
        result[key] = value
    return result

def shape(value, schema, document):
    if "$ref" in schema:
        return shape(value, document["$defs"][schema["$ref"].split("/")[-1]], document)
    if "oneOf" in schema:
        return sum(shape(value, branch, document) for branch in schema["oneOf"]) == 1
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict): return False
        properties = schema["properties"]
        if not set(schema.get("required", [])).issubset(value): return False
        if schema.get("additionalProperties") is False and set(value) - set(properties): return False
        return all(shape(item, properties[key], document) for key, item in value.items())
    if kind == "array":
        return isinstance(value, list) and schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", float("inf")) and all(shape(item, schema["items"], document) for item in value)
    if kind == "string":
        if not isinstance(value, str): return False
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", float("inf")): return False
        if "pattern" in schema and re.search(schema["pattern"], value) is None: return False
        if "uint64String" in schema.get("x-arcforges-rules", []) and (not value.isascii() or not value.isdecimal() or int(value) > 2**64 - 1): return False
    if kind == "integer" and (type(value) is not int or not schema.get("minimum", -float("inf")) <= value <= schema.get("maximum", float("inf"))): return False
    if "const" in schema and value != schema["const"]: return False
    if "enum" in schema and value not in schema["enum"]: return False
    return True

VERIFY = r"""
const { webcrypto } = require('node:crypto');
let input = ''; process.stdin.setEncoding('utf8'); process.stdin.on('data', x => input += x);
process.stdin.on('end', async () => {
 const rows = JSON.parse(input), results = [];
 for (const row of rows) {
  const key = await webcrypto.subtle.importKey('raw', Buffer.from(row.key, 'base64url'), {name:'Ed25519'}, false, ['verify']);
  results.push(await webcrypto.subtle.verify('Ed25519', key, Buffer.from(row.signature,'base64url'), Buffer.from(row.bytes,'utf8')));
 }
 process.stdout.write(JSON.stringify(results));
});
"""

class SignedFormats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((ROOT / "fixtures/public/con-16-signed-formats.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((ROOT / "public/http/v1/signed-formats.schema.json").read_text(encoding="utf-8"))
        cls.documents = {item["id"]: item for item in cls.fixture["documents"]}
        cls.values = {}
        rows = []
        for case in cls.fixture["cases"]:
            value = copy.deepcopy(cls.documents[case["document"]]["value"])
            if "mutation" in case:
                change = case["mutation"]; target = value
                for part in change["path"][:-1]: target = target[part]
                target[change["path"][-1]] = change["value"]
            cls.values[case["id"]] = value
            rows.append({"key": cls.fixture["trustRoots"][0]["publicKey"], "signature": value["signature"], "bytes": canonical({k:v for k,v in value.items() if k != "signature"})})
        result = subprocess.run(["node", "-e", VERIFY], input=json.dumps(rows), text=True, capture_output=True, check=True)
        cls.signatures = dict(zip((case["id"] for case in cls.fixture["cases"]), json.loads(result.stdout)))

    def test_independent_canonical_bytes(self):
        for item in self.documents.values():
            with self.subTest(document=item["id"]):
                value = item["value"]
                self.assertEqual(canonical(value), item["canonicalDocument"])
                self.assertEqual(digest(value), item["documentSha256"])
                self.assertEqual(canonical({k:v for k,v in value.items() if k != "signature"}), item["canonicalUnsigned"])
                self.assertTrue(shape(value, self.schema, self.schema))
                if "body" in value:
                    self.assertEqual(canonical(value["body"]), item["canonicalBody"])
                    self.assertEqual(digest(value["body"]), value["bodyHash"])

    def evaluate(self, case):
        value = self.values[case["id"]]
        context = self.fixture["context"] | case
        if not shape(value, self.schema, self.schema): return "shape"
        realm = value["schemaVersion"] == "realm.v1"
        android = value["schemaVersion"] == "android-update.v1"
        if not context["trustPinned"]: return "untrusted-realm"
        key = self.fixture["trustRoots"][0]
        if not realm and value["keyId"] != key["keyId"]: return "unknown-key"
        if key["keyId"] in case.get("revokedKeyIds", []): return "revoked-key"
        if value["realmId"] != context["realmId"]: return "realm"
        if realm and any(value[k] != v for k, v in context["pinnedOrigins"].items()): return "origin"
        if not realm and value["channel"] != ("direct" if android else context["channel"]): return "channel"
        if "body" in value and digest(value["body"]) != value["bodyHash"]: return "body-hash"
        if not self.signatures[case["id"]]: return "signature"
        instant = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        try:
            issued, expires, now = (instant(value["issuedAt"]), instant(value["expiresAt"]), instant(context["now"]))
        except ValueError:
            return "timestamp"
        if expires <= now: return "expired"
        if not 0 < (expires-issued).total_seconds() <= (7 if realm or android else 1)*86400: return "expiry-window"
        if issued > now or not instant(case.get("trustNotBefore", key["notBefore"])) <= now < instant(case.get("trustNotAfter", key["notAfter"])): return "key-window"
        revision = "configGeneration" if realm else "revision"
        highest = "highestConfigGeneration" if realm else "highestRevision"
        if int(value[revision]) < int(context[highest]): return "rollback"
        if android and int(value["body"]["versionCode"]) < int(context["highestVersionCode"]): return "version-rollback"
        if android and value["body"]["signingCertificateSha256"] != context["installedCertificateSha256"]: return "certificate"
        body = value.get("body", {})
        if "shards" in body:
            shards = case.get("shards", [])
            if len(shards) != len(body["shards"]): return "shard-count"
            for reference, name in zip(body["shards"], shards):
                shard = self.documents[name]["value"]
                if digest(shard) != reference["sha256"]: return "shard-hash"
                if any(shard[k] != value[k] for k in ("schemaVersion", "realmId", "channel", "revision", "keyId")): return "shard-binding"
                if len(shard["body"]["entries"]) != reference["count"]: return "shard-count"
        if "previousRevocations" in case:
            current = {"|".join(row[k] for k in ("packageId", "version", "digest")) for row in body["entries"]}
            if set(case["previousRevocations"]) - current: return "revocation-removal"
        return "accepted"

    def test_consumer_state_vectors(self):
        for case in self.fixture["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(self.evaluate(case), case["expected"])

    def test_malformed_json(self):
        for case in self.fixture["malformedJson"]:
            with self.subTest(case=case["id"]), self.assertRaises(ValueError):
                json.loads(case["json"], object_pairs_hook=strict_pairs)

    def test_fixture_trust_cannot_be_mistaken_for_production(self):
        self.assertTrue(all(key["fixtureOnly"] for key in self.fixture["trustRoots"]))
        self.assertIn("never production", self.fixture["provenance"])
        self.assertGreater(int(self.fixture["context"]["highestRevision"]), 2**53)

if __name__ == "__main__":
    unittest.main()


