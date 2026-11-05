# SPDX-License-Identifier: Apache-2.0
"""Independent offline CON.07 vectors: identity exports, package registration and authentication HTTP exceptions."""
import json
from pathlib import Path
import re
import sys
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
            if rule == "int64" and not -(2**63) <= int(value) <= 2**63 - 1:
                return False
            if rule == "canonicalDecimal" and (value == "-0" or ("." in value and value.endswith("0"))):
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
    if rule == "mobileClientRedirect":
        # AF-CTR-04 (part CM): the release client takes the https App Link form, the debug client the private-use scheme form.
        return {"arcforges.android": True, "arcforges.android.local": False}.get(value["clientId"]) == value["redirectUri"].startswith("https://")
    if rule == "mobileAuthorizeFlow":
        return value["authorizeUrl"].endswith("/mobile/authorize#flow=" + value["flowId"])
    if rule == "webBrowserErrorAdvice":
        # AF-CTR-05 (part C1, Q14): the foundation rules retryAdvice and arcError, and the message key form.
        retry = value["retry"]
        return (value["messageKey"] == f"error.{value['category']}.{value['code']}"
                and (retry["mode"] == "afterTime") == ("retryAt" in retry)
                and (retry["mode"] == "reconcile") == ("reconciliationOperation" in retry)
                and not (retry["mode"] == "afterTime" and value["effect"] == "unknown"))
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
                         "WebBrowserSession": load("public/http/v1/web-browser.schema.json"),
                         # AF-CTR-04 (part CM): the native authorization of an arcforges-mobile installation.
                         "MobileNativeAuth": load("public/http/v1/mobile-native.schema.json"),
                         # AF-CTR-05 (part C1, Q14): the error body of the WebBrowserSession routes; it has no route of its own.
                         "WebBrowserSessionError": load("public/http/v1/web-browser-error.schema.json")}
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
            ("GET", "/session/v1/web/providers/{providerId}/callback"), ("POST", "/session/v1/mobile/begin"), ("POST", "/session/v1/mobile/token"),
        }
        actual = set()
        self.assertNotIn("x-arcforges-routes", self.documents["WebBrowserSessionError"])
        for bundle, document in self.documents.items():
            if bundle == "WebBrowserSessionError":
                continue
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
            client_redirects = {"NativeAuth": {"NativeAuthorizeCallbackSuccess", "NativeAuthorizeCallbackFailure"},
                                "MobileNativeAuth": {"MobileAuthorizeCallbackSuccess", "MobileAuthorizeCallbackFailure"}}.get(bundle, set())
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

    def test_mobile_native_document_is_closed_cookieless_and_issuer_bound(self):
        # AF-CTR-04 (part CM; MOB protocol review MB-2, MB-3, MB-6, MB-11, MB-12, MB-16, MB-17).
        mobile = self.documents["MobileNativeAuth"]
        defs = mobile["$defs"]
        self.assertEqual((mobile["title"], mobile["x-arcforges-schema-version"]), ("MobileNativeAuth", "1"))
        self.assertNotIn("$id", mobile)
        self.assertEqual([ref["$ref"].split("/")[-1] for ref in mobile["oneOf"]],
                         ["MobileBeginRequest", "MobileBeginResponse", "MobileAuthorizeCallbackSuccess", "MobileAuthorizeCallbackFailure",
                          "MobileTokenRequest", "MobileTokenResponse"])
        self.assertTrue(all(name.startswith("Mobile") for name in defs))
        for other in ("BrowserSession", "NativeAuth", "WebBrowserSession"):
            self.assertFalse(set(defs) & set(self.documents[other]["$defs"]), other)
        # The routes: native JSON, exact paths, no cookie of any kind, no Origin or CSRF, begin anonymous, token by the code.
        routes = mobile["x-arcforges-routes"]
        self.assertEqual([(r["id"], r["method"], r["path"], r["credential"]) for r in routes],
                         [("mobile.begin", "POST", "/session/v1/mobile/begin", "anonymous"),
                          ("mobile.token", "POST", "/session/v1/mobile/token", "authorization-code")])
        for bundle, document in self.documents.items():
            for route in document.get("x-arcforges-routes", []):
                if route["id"].startswith("mobile.") or route["path"].startswith("/session/v1/mobile/"):
                    with self.subTest(route=route["id"]):
                        self.assertEqual(bundle, "MobileNativeAuth")
                        self.assertNotIn("cookie", route["credential"])
                        self.assertEqual((route["origin"], route["csrf"], route["setCookie"], route["cache"]), ("none", "none", "none", "no-store"))
                        self.assertTrue(all(document["$defs"][root].get("x-arcforges-wire", "json") == "json"
                                            for root in route["request"] + route["response"]))
                self.assertEqual(route["credential"] == "anonymous", route["id"] == "mobile.begin", route["id"])
        # Mix-up defence (MB-2): both callbacks carry the issuer, required; the begin reply's page URL names its flow.
        success, failure = defs["MobileAuthorizeCallbackSuccess"], defs["MobileAuthorizeCallbackFailure"]
        self.assertEqual(list(success["properties"]), ["code", "state", "iss"])
        self.assertEqual(list(failure["properties"]), ["error", "state", "iss"])
        for callback in (success, failure):
            self.assertEqual(callback["required"], list(callback["properties"]))
            self.assertEqual(callback["x-arcforges-wire"], "form-urlencoded")
            self.assertEqual(callback["properties"]["iss"], defs["MobileAuthorizeCallbackSuccess"]["properties"]["iss"])
        self.assertEqual(failure["properties"]["error"], {"type": "string", "const": "access_denied"})
        self.assertEqual(defs["MobileBeginResponse"]["x-arcforges-rules"], ["mobileAuthorizeFlow"])
        self.assertEqual(defs["MobileBeginResponse"]["properties"]["authorizeUrl"]["maxLength"], 512)
        self.assertEqual(success["properties"]["iss"]["maxLength"] + len("/mobile/authorize#flow=") + 36, 512)
        # The clients, the redirect forms and the PKCE bounds.
        for root in ("MobileBeginRequest", "MobileTokenRequest"):
            node = defs[root]
            self.assertEqual(node["x-arcforges-rules"], ["mobileClientRedirect"], root)
            self.assertEqual(node["properties"]["clientId"]["enum"], ["arcforges.android", "arcforges.android.local"], root)
            self.assertEqual(node["required"], list(node["properties"]), root)
            self.assertEqual(node["x-arcforges-max-bytes"], 4096, root)
        self.assertEqual(defs["MobileBeginRequest"]["properties"]["codeChallengeMethod"], {"type": "string", "const": "S256"})
        self.assertEqual((defs["MobileBeginRequest"]["properties"]["state"]["minLength"], defs["MobileBeginRequest"]["properties"]["state"]["maxLength"]), (16, 128))
        self.assertEqual((defs["MobileTokenRequest"]["properties"]["codeVerifier"]["minLength"], defs["MobileTokenRequest"]["properties"]["codeVerifier"]["maxLength"]), (43, 128))
        self.assertEqual(defs["MobileTokenRequest"]["properties"]["code"], success["properties"]["code"])
        # The installation claim (MB-12) and the delivered session: arcforges-mobile only, an account session that authenticates.
        claim = defs["MobileInstallationClaim"]
        self.assertEqual(claim["properties"]["product"]["enum"], ["arcforges-mobile"])
        self.assertEqual(defs["MobileTokenInstalledProduct"]["properties"]["product"]["enum"], ["arcforges-mobile"])
        self.assertEqual(claim["properties"]["installationId"]["x-arcforges-rules"], ["nonzeroUuid"])
        self.assertNotIn("+", claim["properties"]["appVersion"]["pattern"])
        self.assertNotIn("model", claim["properties"])
        token = defs["MobileTokenResponse"]["properties"]
        self.assertEqual((token["scope"], token["purpose"]), ({"type": "string", "const": "account"}, {"type": "string", "const": "authenticate"}))
        native = self.documents["NativeAuth"]["$defs"]["NativeTokenResponse"]["properties"]
        self.assertEqual(set(token) - set(native), {"scope"})
        self.assertEqual(set(native) - set(token), set())
        # The contract statements the app relies on (MB-2, MB-16, MB-17, MB-11).
        text = json.dumps(mobile)
        for phrase in ("identity.authorizeMobile", "byte-equal to the derived value", "RFC 9207", "valid for at most 2 minutes (the center's policy)", "one use",
                       "CONFLICT/code_reused and revokes the session family", "makes a new installation ID", "begins a new attempt",
                       "exactly one pending attempt", "without build metadata",
                       "as the app reports it", "Loopback redirects are not admitted", "access_denied as cancelled in the browser",
                       "AUTHORIZATION/permission_denied", "STATE/not_activated", "RESOURCE/rate_limited", "RESOURCE/overloaded",
                       "The app checks state and iss as for a success",
                       "admitted only by a self-hosted center configured for that scheme and never by an official-hosted center",
                       "fresh, random PKCE verifier and a fresh, random state (each from at least 32 random bytes",
                       "flowId is the begin reply's", "or its flow was ended by a wrong verifier or a binding mismatch"):
            self.assertIn(phrase, text, phrase)
        for root in ("MobileBeginRequest", "MobileTokenRequest"):
            self.assertIn("STATE/not_activated while the center's mobile surface is off", defs[root]["description"], root)
        # Only PublicApi owns the new document; the frozen documents keep their pinned bytes.
        catalog = load("eng/contract-packages.json")["packages"]
        owners = [row["id"] for row in catalog if "public/http/v1/mobile-native.schema.json" in row["jsonSchemas"]]
        self.assertEqual(owners, ["ArcForges.Contracts.PublicApi"])
        # (The CON.17 window pins each frozen document's canonical content, read here with the window's own function.)
        sys.path.insert(0, str(ROOT / "eng"))
        from check_compatibility import schema_identity
        pins = {row["path"]: row["sha256"] for row in load("eng/compatibility/later-services-window.json")["schemas"]}
        for frozen in ("public/http/v1/browser.schema.json", "public/http/v1/native-auth.schema.json"):
            self.assertEqual(schema_identity((ROOT / frozen).read_bytes())[0], pins[frozen], frozen)
        self.assertNotIn("public/http/v1/mobile-native.schema.json", pins)
        # The vectors M replays: each mix-up, redirect and claim refusal is present with its outcome.
        vectors = {vector["id"]: vector for vector in self.fixture["httpVectors"]}
        for vector_id, valid in (("mobile-callback-success", True), ("mobile-callback-success-missing-iss", False),
                                 ("mobile-callback-failure", True), ("mobile-callback-failure-missing-iss", False),
                                 ("mobile-begin-reply-other-flow", False), ("mobile-begin-reply-http-official", False),
                                 ("mobile-begin-release-with-private-scheme", False), ("mobile-begin-loopback-name", False),
                                 ("mobile-begin-loopback-ip", False), ("mobile-begin-app-version-build-metadata", False),
                                 ("mobile-begin-product-node", False), ("mobile-begin-platform-ios", False),
                                 ("mobile-token-noncanonical-code", False), ("mobile-token-response-node-scope", False)):
            with self.subTest(vector=vector_id):
                self.assertEqual(vectors[vector_id]["valid"], valid)
        mobile_roots = {root for root, bundle in self.root_bundle.items() if bundle == "MobileNativeAuth"}
        self.assertGreaterEqual(sum(1 for vector in self.fixture["httpVectors"] if vector["root"] in mobile_roots), 100)
        self.assertTrue(all(vector["id"].startswith("mobile-") == (vector["root"] in mobile_roots) for vector in self.fixture["httpVectors"]))

    def test_web_browser_error_document_is_the_center_error_body(self):
        # AF-CTR-05 (part C1; Plan decision Q14; ArcForges-Design web.md "Contract gap"): the JSON body of a refused
        # WebBrowserSession route, in a new version-1 companion document; WebBrowserSession itself is unchanged.
        error = self.documents["WebBrowserSessionError"]
        defs = error["$defs"]
        self.assertEqual((error["title"], error["x-arcforges-schema-version"]), ("WebBrowserSessionError", "1"))
        self.assertNotIn("$id", error)
        self.assertEqual([ref["$ref"] for ref in error["oneOf"]], ["#/$defs/WebBrowserErrorReply"])
        self.assertTrue(all(name.startswith("WebBrowserError") or name == "WebBrowserArcError" for name in defs))
        for other in ("BrowserSession", "NativeAuth", "WebBrowserSession", "MobileNativeAuth"):
            self.assertFalse(set(defs) & set(self.documents[other]["$defs"]), other)
        # The members and their order are those of the center's errorOf (Cloud center/internal/pages/jsonout.go).
        members = {name: list(node["properties"]) for name, node in defs.items() if "properties" in node}
        self.assertEqual(members["WebBrowserErrorReply"], ["error"])
        self.assertEqual(members["WebBrowserArcError"], ["category", "code", "messageKey", "retry", "effect", "correlationId", "details"])
        self.assertEqual(defs["WebBrowserArcError"]["required"], ["category", "code", "messageKey", "retry", "effect", "correlationId"])
        self.assertEqual(members["WebBrowserErrorRetry"], ["mode", "retryAt", "reconciliationOperation"])
        self.assertEqual(members["WebBrowserErrorStateFailure"], ["state", "reason", "resource"])
        self.assertEqual(members["WebBrowserErrorResource"], ["kind", "id"])
        self.assertEqual(members["WebBrowserErrorLimitFailure"], ["limitName", "maximum", "recoveryAt"])
        self.assertEqual(members["WebBrowserErrorRevisionConflict"], ["expected", "actual"])
        self.assertEqual([ref["$ref"].split("/")[-1] for ref in defs["WebBrowserErrorDetails"]["oneOf"]],
                         ["WebBrowserErrorStateDetails", "WebBrowserErrorLimitDetails", "WebBrowserErrorRevisionDetails"])
        arc = defs["WebBrowserArcError"]["properties"]
        self.assertEqual(arc["category"]["enum"], ["validation", "authentication", "authorization", "entitlement", "conflict", "state",
                                                   "resource", "execution", "internal"])
        self.assertEqual(defs["WebBrowserErrorRetry"]["properties"]["mode"]["enum"], ["never", "afterTime", "sameCommand", "reconcile"])
        self.assertEqual(arc["effect"]["enum"], ["didNotHappen", "happened", "unknown"])
        self.assertEqual(defs["WebBrowserArcError"]["x-arcforges-rules"], ["webBrowserErrorAdvice"])
        self.assertEqual(defs["WebBrowserErrorReply"]["x-arcforges-max-bytes"], 16384)
        text = json.dumps(error)
        for phrase in ("403 for authentication, authorization and entitlement", "400 for validation, conflict, state and RESOURCE/quota_exceeded",
                       "404 for STATE/not_found and STATE/not_activated", "429 for RESOURCE/rate_limited", "503 otherwise",
                       "never mean that the center did not see the request", "LimitFailure.available is not carried",
                       "which stays unchanged"):
            self.assertIn(phrase, text, phrase)
        # The companion is owned by PublicApi only, it is not a pinned frozen document, and WebBrowserSession has no error root.
        catalog = load("eng/contract-packages.json")["packages"]
        self.assertEqual([row["id"] for row in catalog if "public/http/v1/web-browser-error.schema.json" in row["jsonSchemas"]],
                         ["ArcForges.Contracts.PublicApi"])
        pins = {row["path"] for row in load("eng/compatibility/later-services-window.json")["schemas"]}
        self.assertNotIn("public/http/v1/web-browser-error.schema.json", pins)
        self.assertFalse([name for name in self.documents["WebBrowserSession"]["$defs"] if "Error" in name])
        # The center's replies validate; each refusal the rules exclude is refused.
        vectors = {vector["id"]: vector for vector in self.fixture["httpVectors"]}
        for vector_id, valid in (("web-browser-error-rate-limited", True), ("web-browser-error-internal-unknown-never", True),
                                 ("web-browser-error-reconcile-with-operation", True), ("web-browser-error-not-found", True),
                                 ("web-browser-error-unknown-with-after-time", False), ("web-browser-error-after-time-without-retry-at", False),
                                 ("web-browser-error-reconcile-without-operation", False), ("web-browser-error-operation-without-reconcile", False),
                                 ("web-browser-error-message-key-of-another-code", False), ("web-browser-error-two-details", False),
                                 ("web-browser-error-missing-correlation-id", False), ("web-browser-error-limit-with-available", False)):
            with self.subTest(vector=vector_id):
                self.assertEqual((vectors[vector_id]["root"], vectors[vector_id]["valid"]), ("WebBrowserErrorReply", valid))
        roots = [vector for vector in self.fixture["httpVectors"] if vector["root"] == "WebBrowserErrorReply"]
        self.assertEqual(len(roots), 45)
        self.assertTrue(all(vector["id"].startswith("web-browser-error-") for vector in roots))

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
