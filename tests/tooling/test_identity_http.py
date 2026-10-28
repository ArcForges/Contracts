# SPDX-License-Identifier: Apache-2.0
"""Independent offline CON.07 vectors: identity exports, package registration and authentication HTTP exceptions."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
FORM_BOUND = 16384
UNRESERVED_ENCODE = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
NATIVE_CLIENTS = {
    "arcscope.desktop": "com.arcforges.arcscope:/auth/callback",
    "companion.android": "https://account.arcforges.com/native/android/callback",
    "companion.android.selfhost": "com.arcforges.mobile:/auth/callback",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate property")
        result[key] = value
    return result


def hexvalue(byte):
    if 0x30 <= byte <= 0x39:
        return byte - 0x30
    if 0x61 <= byte <= 0x66:
        return byte - 0x61 + 10
    if 0x41 <= byte <= 0x46:
        return byte - 0x41 + 10
    return -1


def decode_component(data):
    out = bytearray()
    i = 0
    while i < len(data):
        byte = data[i]
        if byte == 0x2B:
            out.append(0x20)
        elif byte == 0x25:
            if i + 2 >= len(data) or hexvalue(data[i + 1]) < 0 or hexvalue(data[i + 2]) < 0:
                return None
            out.append(hexvalue(data[i + 1]) * 16 + hexvalue(data[i + 2]))
            i += 2
        elif byte < 0x21 or byte > 0x7E:
            return None
        else:
            out.append(byte)
        i += 1
    try:
        text = bytes(out).decode("utf-8")
    except UnicodeDecodeError:
        return None
    return None if any(ord(c) < 0x20 or ord(c) == 0x7F for c in text) else text


def decode_form(data):
    if not data:
        return None
    result = {}
    segments = data.split(b"&")
    for segment in segments:
        index = segment.find(b"=")
        if index <= 0:
            return None
        name, value = decode_component(segment[:index]), decode_component(segment[index + 1:])
        if name is None or value is None or name in result:
            return None
        result[name] = value
    return result


def encode_component(text):
    return "".join(chr(b) if b in UNRESERVED_ENCODE else "%%%02X" % b for b in text.encode("utf-8"))


def encode_form(value, order):
    return "&".join(f"{encode_component(k)}={encode_component(value[k])}" for k in order if k in value)


def scalar_length(text):
    return len(text)  # Python strings are Unicode scalar sequences once surrogate pairs are decoded.


def shape(value, schema, document):
    if "$ref" in schema:
        return shape(value, document["$defs"][schema["$ref"].split("/")[-1]], document)
    if "oneOf" in schema:
        return sum(1 for branch in schema["oneOf"] if shape(value, branch, document)) == 1
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return False
        properties = schema["properties"]
        if not set(schema.get("required", [])).issubset(value) or set(value) - set(properties):
            return False
        if not all(shape(item, properties[key], document) for key, item in value.items()):
            return False
        return all(rule_ok(rule, value) for rule in schema.get("x-arcforges-rules", []))
    if kind == "array":
        return (isinstance(value, list) and schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 10**9)
                and all(shape(item, schema["items"], document) for item in value))
    if kind == "string":
        if not isinstance(value, str):
            return False
        if not schema.get("minLength", 0) <= scalar_length(value) <= schema.get("maxLength", 10**9):
            return False
        if "x-arcforges-max-utf8-bytes" in schema and len(value.encode("utf-8")) > schema["x-arcforges-max-utf8-bytes"]:
            return False
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            return False
        if "const" in schema and value != schema["const"]:
            return False
        if "enum" in schema and value not in schema["enum"]:
            return False
        for rule in schema.get("x-arcforges-rules", []):
            if rule == "nonzeroUuid" and value == "00000000-0000-0000-0000-000000000000":
                return False
            if rule == "uint64String" and int(value) > 2**64 - 1:
                return False
            if rule == "positiveInt64String" and not 0 < int(value) <= 2**63 - 1:
                return False
        return True
    if kind == "integer":
        return (type(value) is int and schema.get("minimum", -(10**18)) <= value <= schema.get("maximum", 10**18)
                and ("enum" not in schema or value in schema["enum"]))
    if kind == "boolean":
        return isinstance(value, bool) and ("const" not in schema or value == schema["const"])
    raise ValueError("unsupported schema type " + str(kind))


def rule_ok(rule, value):
    if rule == "authChallengePurpose":
        recover = value["purpose"] == "recover"
        method, recovery = "method" in value, "recoveryMethod" in value
        return (recovery and not method) if recover else (method and not recovery)
    if rule == "nativeClientRedirect":
        return NATIVE_CLIENTS.get(value["client_id"]) == value["redirect_uri"]
    raise ValueError("unknown rule " + rule)


def failure_of(text, root, document, wire):
    """Return None when valid, otherwise malformed/tooLarge/invalid exactly like the generated codecs."""
    data = text.encode("utf-8")
    schema = {"$ref": "#/$defs/" + root}
    bound = document["$defs"][root]["x-arcforges-max-bytes"]
    if len(data) > bound:
        return "tooLarge"
    if wire == "form-urlencoded":
        value = decode_form(data)
        if value is None:
            return "malformed"
    else:
        if data.startswith(b"\xef\xbb\xbf"):
            return "malformed"
        try:
            value = json.loads(text, object_pairs_hook=strict_pairs)
        except (ValueError, RecursionError):
            return "malformed"
    return None if shape(value, schema, document) else "invalid"


class IdentityHttpExceptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load("fixtures/public/con-07-identity.json")
        cls.documents = {"BrowserSession": load("public/http/v1/browser.schema.json"), "NativeAuth": load("public/http/v1/native-auth.schema.json"),
                         # AF-CTR-03: the browser session of an arcforges-web installation, beside the frozen document.
                         "WebBrowserSession": load("public/http/v1/web-browser.schema.json")}
        cls.root_bundle = {root: bundle for bundle, doc in cls.documents.items() for root in (ref["$ref"].split("/")[-1] for ref in doc["oneOf"])}

    def test_vectors_match_an_independent_schema_interpreter(self):
        self.assertGreaterEqual(len(self.fixture["httpVectors"]), 100)
        for vector in self.fixture["httpVectors"]:
            document = self.documents[self.root_bundle[vector["root"]]]
            node = document["$defs"][vector["root"]]
            self.assertEqual(node.get("x-arcforges-wire", "json"), vector["wire"], vector["id"])
            failure = failure_of(vector["text"], vector["root"], document, vector["wire"])
            if vector["valid"]:
                self.assertIsNone(failure, vector["id"])
                if vector["wire"] == "form-urlencoded":
                    decoded = decode_form(vector["text"].encode("utf-8"))
                    order = list(node["properties"])
                    self.assertEqual(encode_form(decoded, order), vector["canonical"], vector["id"])
                else:
                    value = json.loads(vector["text"], object_pairs_hook=strict_pairs)
                    if "canonical" in vector:
                        self.assertEqual(json.dumps(value, separators=(",", ":"), ensure_ascii=False), vector["canonical"], vector["id"])
            else:
                self.assertEqual(failure, vector["failure"], vector["id"])

    def test_every_root_has_at_least_one_positive_and_one_negative_vector(self):
        for root in self.root_bundle:
            rows = [vector for vector in self.fixture["httpVectors"] if vector["root"] == root]
            self.assertTrue(any(row["valid"] for row in rows), root + " positive")
            self.assertTrue(any(not row["valid"] for row in rows), root + " negative")

    def test_form_roots_are_string_only_16_kib_and_json_roots_are_closed(self):
        for bundle, document in self.documents.items():
            for root in self.root_bundle:
                if self.root_bundle[root] != bundle:
                    continue
                node = document["$defs"][root]
                self.assertIs(node["additionalProperties"], False, root)
                bound = node["x-arcforges-max-bytes"]
                self.assertTrue(1 <= bound <= 4 * 1024 * 1024, root)
                if node.get("x-arcforges-wire") == "form-urlencoded":
                    self.assertEqual(bound, FORM_BOUND, root)
                    for name, child in node["properties"].items():
                        resolved = document["$defs"][child["$ref"].split("/")[-1]] if "$ref" in child else child
                        self.assertEqual(resolved["type"], "string", f"{root}.{name}")
                else:
                    self.assertNotIn("x-arcforges-wire", node, root)
        native_token = self.documents["NativeAuth"]["$defs"]["NativeTokenRequest"]
        self.assertEqual(native_token["x-arcforges-wire"], "form-urlencoded")
        self.assertEqual(list(native_token["properties"]), ["grant_type", "code", "code_verifier", "client_id", "redirect_uri", "installationId"])
        self.assertEqual(native_token["properties"]["grant_type"]["const"], "authorization_code")

    def test_routes_are_closed_and_match_the_authoritative_session_surface(self):
        expected_paths = {
            ("GET", "/session/v1/bootstrap"), ("POST", "/session/v1/authentication/begin"), ("POST", "/session/v1/authentication/complete"),
            ("POST", "/session/v1/enrollment/complete"), ("POST", "/session/v1/recovery/begin"), ("POST", "/session/v1/recovery/complete"),
            ("POST", "/session/v1/step-up/begin"), ("POST", "/session/v1/step-up/complete"), ("POST", "/session/v1/logout"),
            ("GET", "/session/v1/providers/{providerId}/callback"), ("GET", "/session/v1/native/authorize"), ("POST", "/session/v1/native/token"),
            ("GET", "/session/v1/web/bootstrap"), ("POST", "/session/v1/web/authentication/begin"), ("POST", "/session/v1/web/authentication/complete"),
            ("POST", "/session/v1/web/enrollment/complete"), ("POST", "/session/v1/web/recovery/begin"), ("POST", "/session/v1/web/recovery/complete"),
            ("POST", "/session/v1/web/step-up/begin"), ("POST", "/session/v1/web/step-up/complete"), ("POST", "/session/v1/web/logout"),
            ("GET", "/session/v1/web/providers/{providerId}/callback"),
        }
        actual = set()
        for bundle, document in self.documents.items():
            roots = {ref["$ref"].split("/")[-1] for ref in document["oneOf"]}
            routes = document["x-arcforges-routes"]
            self.assertEqual([route["id"] for route in routes], [row["id"] for row in self.fixture["routes"][bundle]])
            for route in routes:
                actual.add((route["method"], route["path"]))
                self.assertEqual(route["cache"], "no-store")
                self.assertTrue(set(route["request"]) <= roots and set(route["response"]) <= roots, route["id"])
                if route["method"] == "POST" and route["id"].startswith(("browser.", "webBrowser.")):
                    self.assertEqual((route["csrf"], route["origin"]), ("required", "exact-configured"), route["id"])
                if route["method"] == "GET":
                    self.assertTrue(all(document["$defs"][root].get("x-arcforges-wire") == "form-urlencoded" for root in route["request"]), route["id"])
            used = {root for route in routes for root in route["request"] + route["response"]}
            # The two native callback queries travel to the client's registered redirect URI, not to a server route.
            client_redirects = {"NativeAuthorizeCallbackSuccess", "NativeAuthorizeCallbackFailure"} if bundle == "NativeAuth" else set()
            self.assertEqual(roots - used, client_redirects, bundle + " has no unrouted root")
            self.assertFalse(used - roots, bundle)
        self.assertEqual(actual, expected_paths)
        for bundle in ("BrowserSession", "WebBrowserSession"):
            browser_responses = {root for route in self.documents[bundle]["x-arcforges-routes"] for root in route["response"]}
            self.assertNotIn("NativeTokenResponse", browser_responses)
        native_properties = set(self.documents["NativeAuth"]["$defs"]["NativeTokenResponse"]["properties"])
        for root in self.root_bundle:
            if self.root_bundle[root] in ("BrowserSession", "WebBrowserSession"):
                props = set(self.documents[self.root_bundle[root]]["$defs"][root]["properties"])
                self.assertFalse({"accessToken", "refreshToken"} & props, root + " never carries native tokens")
        self.assertTrue({"accessToken", "refreshToken"} <= native_properties)

    def test_web_browser_document_mirrors_the_frozen_browser_document_with_the_arcforges_web_product(self):
        # AF-CTR-03: the CON.17 later-services window freezes BrowserSession, so the browser session of an
        # arcforges-web installation is its own closed document. It keeps the frozen document's meaning: the same
        # constraints, wires, bounds and route semantics, with its own definition names (generated names are unique per
        # output root), route identities and paths, and an installation claim that also admits arcforges-web.
        frozen, web = self.documents["BrowserSession"], self.documents["WebBrowserSession"]
        branded = ["arcscope", "companion"]
        self.assertEqual(frozen["$defs"]["BrowserInstallationClaim"]["properties"]["product"]["enum"], branded)
        self.assertEqual(web["$defs"]["WebBrowserInstallationClaim"]["properties"]["product"]["enum"], branded + ["arcforges-web"])
        self.assertEqual((web["title"], web["x-arcforges-schema-version"]), ("WebBrowserSession", "1"))
        self.assertNotIn("$id", frozen)
        mirror = json.loads(json.dumps(web))
        mirror["$defs"]["WebBrowserInstallationClaim"]["properties"]["product"]["enum"].remove("arcforges-web")
        text = json.dumps(mirror).replace('"/session/v1/web/', '"/session/v1/').replace('"webBrowser.', '"browser.')
        undone = json.loads(re.sub(r'(?<=["/])WebBrowser(?=[A-Z"])', "Browser", text))
        self.assertNotEqual(undone.pop("description"), frozen["description"])
        self.assertEqual(undone, {key: value for key, value in frozen.items() if key != "description"})
        frozen_paths = {(route["method"], route["path"]) for route in frozen["x-arcforges-routes"]}
        for route in web["x-arcforges-routes"]:
            self.assertTrue(route["id"].startswith("webBrowser.") and route["path"].startswith("/session/v1/web/"), route["id"])
            self.assertNotIn((route["method"], route["path"]), frozen_paths)
        self.assertFalse(set(web["$defs"]) & set(frozen["$defs"]))
        # Only PublicApi owns the new document; the retired api-client row keeps its historical schema list.
        catalog = load("eng/contract-packages.json")["packages"]
        owners = [row["id"] for row in catalog if "public/http/v1/web-browser.schema.json" in row["jsonSchemas"]]
        self.assertEqual(owners, ["ArcForges.Contracts.PublicApi"])
        # The product vectors: the new document admits arcforges-web and refuses the node and mobile products, the
        # frozen document refuses arcforges-web.
        vectors = {vector["id"]: vector for vector in self.fixture["httpVectors"]}
        for vector_id, root, valid in (
                ("web-browser-begin-authentication-arcforges-web", "WebBrowserBeginAuthenticationRequest", True),
                ("web-browser-begin-recovery-arcforges-web", "WebBrowserBeginRecoveryRequest", True),
                ("web-browser-begin-authentication-arcforges-node-refused", "WebBrowserBeginAuthenticationRequest", False),
                ("web-browser-begin-authentication-arcforges-mobile-refused", "WebBrowserBeginAuthenticationRequest", False),
                ("web-browser-begin-recovery-arcforges-node-refused", "WebBrowserBeginRecoveryRequest", False),
                ("browser-begin-authentication-arcforges-web-refused", "BrowserBeginAuthenticationRequest", False),
                ("browser-begin-recovery-arcforges-web-refused", "BrowserBeginRecoveryRequest", False)):
            with self.subTest(vector=vector_id):
                vector = vectors[vector_id]
                self.assertEqual((vector["root"], vector["valid"]), (root, valid))
                failure = failure_of(vector["text"], root, self.documents[self.root_bundle[root]], "json")
                self.assertEqual(failure, None if valid else "invalid")
        # Every BrowserSession vector is mirrored on the new document with the same bytes and outcome.
        for vector in self.fixture["httpVectors"]:
            if self.root_bundle[vector["root"]] == "BrowserSession" and not vector["id"].endswith("-arcforges-web-refused"):
                copy = vectors["web-" + vector["id"]]
                self.assertEqual(copy, {**vector, "id": "web-" + vector["id"], "root": "Web" + vector["root"]})

    def test_existing_transfer_http_schema_is_untouched(self):
        part = load("public/http/v1/schema.json")
        self.assertEqual(part["title"], "PartReceipt")
        self.assertEqual(list(part["properties"]), ["partNumber", "size", "sha256", "etag"])

    def test_package_registration_adds_no_identity_and_owns_every_new_input(self):
        catalog = {row["id"]: row for row in load("eng/contract-packages.json")["packages"]}
        # CON.43 (S61(1)) appends the one authorised boundary dispatch identity; this registration added none.
        # AF-CON-01 then appends the four flagship design packages, in this order, after it, and AF-CTR-01 the Go module.
        self.assertEqual(len(catalog), 26)
        self.assertEqual(list(catalog)[-6:], ["ArcForges.Contracts.LocalRpc.Dispatch", "ArcForges.Contracts.Node",
                                              "ArcForges.Contracts.Fleet", "ArcForges.Contracts.Peer",
                                              "ArcForges.Contracts.Relay", "github.com/ArcForges/Contracts/go"])
        identity = "public/proto/arcforges/publicapi/v1/identity.proto"
        owners = sorted(pid for pid, row in catalog.items() if identity in row["proto"])
        self.assertEqual(owners, ["@arcforges/proto", "ArcForges.Contracts.PublicApi", "github.com/ArcForges/Contracts/go",
                                  "io.github.arcforges:contracts-connect-client", "io.github.arcforges:contracts-proto"])
        # CON.40: the TypeScript and Kotlin owners are kept as retired rows; PublicApi is the one active C# owner and
        # the AF-CTR-01 Go module generates the center's Go bindings of the same file.
        retired = {pid for pid, row in catalog.items() if "retired" in row}
        self.assertEqual([pid for pid in owners if pid not in retired],
                         ["ArcForges.Contracts.PublicApi", "github.com/ArcForges/Contracts/go"])
        self.assertEqual(catalog["github.com/ArcForges/Contracts/go"]["kind"], "go")
        self.assertTrue(all(catalog[pid]["retired"]["task"] == "CON.40" for pid in owners if pid in retired))
        for schema in ("public/http/v1/browser.schema.json", "public/http/v1/native-auth.schema.json"):
            schema_owners = sorted(pid for pid, row in catalog.items() if schema in row["jsonSchemas"])
            self.assertEqual(schema_owners, ["@arcforges/api-client", "ArcForges.Contracts.PublicApi"])
            self.assertEqual([pid for pid in schema_owners if pid not in retired], ["ArcForges.Contracts.PublicApi"])

    def test_identity_proto_matches_the_independent_fixture_oracle(self):
        text = re.sub(r"//[^\n]*", "", (ROOT / "public/proto/arcforges/publicapi/v1/identity.proto").read_text(encoding="utf-8"))
        messages = {}
        for match in re.finditer(r"\nmessage (\w+) \{(.*?)\n\}", text, re.S):
            fields = re.findall(r"(?:optional |repeated )?[\w.]+ (\w+) = (\d+) \[json_name", match.group(2))
            messages[match.group(1)] = ",".join(f"{tag}:{name}" for name, tag in fields)
        for name, tags in self.fixture["records"].items():
            self.assertEqual(sorted(tags.split(","), key=lambda item: int(item.split(":")[0])), sorted(messages[name].split(","), key=lambda item: int(item.split(":")[0])), name)
        for row in self.fixture["operations"]:
            base = row["service"] + row["method"]
            self.assertEqual(messages[base + "Request"], row["requestTags"], row["id"])
            self.assertEqual(messages[base + "Value"], row["valueTags"], row["id"])
        services = {m.group(1): re.findall(r"rpc (\w+)\(", m.group(2)) for m in re.finditer(r"service (\w+) \{(.*?)\n\}", text, re.S)}
        self.assertEqual({f"arcforges.publicapi.v1.{k}": v for k, v in services.items()}, self.fixture["services"])
        self.assertEqual(len(self.fixture["operations"]), 49)

    def test_authorization_export_is_complete_and_matches_the_registry_classes(self):
        export = load("eng/operations/con-07.json")
        self.assertEqual(export["schemaVersion"], "operation-metadata.v1")
        rows = {row["operationId"]: row for row in export["operations"]}
        self.assertEqual(sorted(rows), sorted(row["id"] for row in self.fixture["operations"]))
        for row in rows.values():
            self.assertEqual(set(row["authorization"]), {"capability", "risk", "approval", "stepUp", "localPresence", "egress", "patEligible", "actorKinds"}, row["operationId"])
            self.assertIsNone(row["authorization"]["capability"])
            self.assertFalse(row["authorization"]["localPresence"])
            self.assertNotIn("compatibilityClass", row)
            if row["profile"] == "one-use-auth":
                self.assertEqual(row["authorization"]["actorKinds"], ["preauth"])
            else:
                self.assertEqual((row["profile"], row["authorization"]["actorKinds"]), ("human-owner", ["human"]))
        # Registry classes for the rows catalogue 01 states explicitly.
        stated = {
            "identity.beginPasskeyRegistration": ("NI", "R2", True), "identity.completePasskeyRegistration": ("IW", "R2", False),
            "identity.revokeSession": ("DE", "R2", False), "identity.revokeAllSessions": ("DE", "R3", True),
            "identity.listAuthIdentities": ("Q", "R1", False), "identity.removeAuthIdentity": ("DE", "R3", True),
            "identity.requestAccountDeletion": ("IW", "R4", True), "identity.cancelAccountDeletion": ("IW", "R3", False),
            "workspace.list": ("Q", "R1", False), "workspace.get": ("Q", "R1", False), "workspace.updateSettings": ("IW", "R2", False),
            "device.register": ("CC", "R2", False), "device.list": ("Q", "R1", False), "device.rename": ("IW", "R1", False),
            "device.setTrust": ("IW", "R3", True), "device.setRemoteEnabled": ("IW", "R3", True), "device.revoke": ("DE", "R3", True),
            "identity.generateRecoveryCodes": ("NI", "R3", True), "identity.createApiToken": ("CC", "R3", True),
            "identity.revokeApiToken": ("DE", "R3", False), "device.signOut": ("DE", "R3", False), "device.setRemotePolicy": ("IW", "R3", True),
            "workspace.requestDataDeletion": ("CC", "R4", True), "identity.updateProfile": ("IW", "R2", False),
            "identity.renameAuthIdentity": ("IW", "R2", False),
        }
        for operation, (idempotency, risk, step_up) in stated.items():
            row = rows[operation]
            self.assertEqual((row["idempotency"], row["authorization"]["risk"], row["authorization"]["stepUp"]), (idempotency, risk, step_up), operation)
        anonymous = {"identity.beginAuthentication", "identity.completeAuthentication", "identity.requestEmailCode", "identity.redeemEmailCode",
                     "identity.refreshSession", "identity.beginRecovery", "identity.completeRecovery", "identity.completeEnrollment", "identity.listAuthProviders"}
        self.assertEqual({op for op, row in rows.items() if row["profile"] == "one-use-auth"}, anonymous)
        self.assertEqual({op for op, row in rows.items() if row["authorization"]["patEligible"]}, {"workspace.list", "workspace.get"})
        self.assertEqual({op for op, row in rows.items() if row["authorization"]["risk"] == "R4"}, {"identity.requestAccountDeletion", "workspace.requestDataDeletion"})
        self.assertTrue(all(rows[op]["scope"] == "application-target" for op in rows if op.startswith("device.")))
        self.assertTrue(all(rows[op]["scope"] == "account" for op in rows if not op.startswith("device.")))


if __name__ == "__main__":
    unittest.main()
