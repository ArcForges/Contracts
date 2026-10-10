# SPDX-License-Identifier: Apache-2.0
"""Closed union/root-bundle compiler negatives, without transport or owner runtime."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))
from generate_shapes import (JsonShapes, bundle_external_models, bundle_type_imports,
                             compile_bundle_roots, schema_roots, generate)


def record(title, properties):
    return {"title": title, "type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def sample():
    schema = record("Envelope", {"body": {"$ref": "#/$defs/Body"}})
    schema["x-arcforges-max-bytes"] = 1024
    schema["$defs"] = {
        "Body": {"title": "Body", "oneOf": [{"$ref": "#/$defs/Entries"}, {"$ref": "#/$defs/Shards"}]},
        "Entries": record("Entries", {"entries": {"type": "array", "items": {"type": "string"}, "maxItems": 3}}),
        "Shards": record("Shards", {"shards": {"type": "array", "items": {"type": "string"}, "maxItems": 3}}),
    }
    return schema


def bundle_of_roots(definitions, *names):
    return {"title": "RouteBundle", "$defs": definitions,
            "oneOf": [{"$ref": f"#/$defs/{name}"} for name in names]}


def reachable_number_fields(root):
    definitions = root.get("$defs", {})
    fields = set()
    visited_refs = set()

    def visit(node, owner=None, field=None):
        if "$ref" in node:
            name = node["$ref"].removeprefix("#/$defs/")
            if name in visited_refs:
                return
            visited_refs.add(name)
            target = definitions[name]
            visit(target, target.get("title", owner), field)
            return
        if node.get("type") == "number":
            fields.add((owner, field))
            return
        if node.get("type") == "object":
            current = node.get("title", owner)
            for name, child in node.get("properties", {}).items():
                visit(child, current, name)
        elif node.get("type") == "array":
            visit(node["items"], owner, field)
        elif "oneOf" in node:
            for child in node["oneOf"]:
                visit(child, owner, field)

    visit(root, root.get("title"))
    return fields


class JsonShapeUnions(unittest.TestCase):
    def test_accepted_seed_outputs_unchanged(self):
        mappings = [
            # CON.40: the public seeds keep their C# outputs; their @arcforges/api-client TypeScript root is retired.
            ("public/http/v1/schema.json", "ArcForges.Contracts.PublicApi.Http.V1", "src/public/dotnet/ArcForges.Contracts.PublicApi", "src/public/dotnet/ArcForges.Contracts.Validation", None),
            ("public/http/v1/inventory.schema.json", "ArcForges.Sdk.Contracts.Inventory.V1", "src/public/dotnet/ArcForges.Sdk.Contracts", "src/public/dotnet/ArcForges.Contracts.Validation", None),
            ("internal/ai-http/v1/configuration.schema.json", "ArcForges.Contracts.CloudInternal.Http.V1", "src/internal/dotnet/ArcForges.Contracts.CloudInternal", "src/internal/dotnet/ArcForges.Contracts.CloudInternal", "src/internal/ts/ai-internal"),
        ]
        for source, namespace, models, checks, tsroot in mappings:
            schema = json.loads((ROOT / source).read_text())
            outputs = JsonShapes(schema, namespace).generate()
            title = schema["title"]
            paths = [f"{models}/Generated/Shapes/{title}.g.cs", f"{checks}/Generated/Shapes/{title}Validator.g.cs"]
            if tsroot is None:
                self.assertFalse((ROOT / "src/public/ts/api-client").exists())
            else:
                paths.append(f"{tsroot}/src/shapes/gen/{title}.ts")
            for path, output in zip(paths, outputs):
                self.assertEqual((ROOT / path).read_text().strip(), output.strip(), path)

    def test_closed_presence_union_generates_typed_converter(self):
        models, checks, ts = JsonShapes(sample(), "Example").generate()
        self.assertIn("public abstract record Body;", models)
        self.assertIn("public sealed record BodyEntries(Entries Value) : Body;", models)
        self.assertIn("matched != 1", models)
        self.assertIn("EnvelopeJsonContext.Default.Entries", models)
        self.assertIn("export type Body = Entries | Shards;", ts)
        self.assertIn(" != 1) return false;", checks)
        self.assertNotIn("JsonPolymorphic", models)

    def test_string_object_union_keeps_wire_scalar_and_typed_model(self):
        schema = sample()
        schema["$defs"]["StableTarget"] = {"title": "StableTarget", "type": "string", "pattern": "^id-[a-z]+$"}
        schema["$defs"]["Body"]["oneOf"].append({"$ref": "#/$defs/StableTarget"})
        models, _, ts = JsonShapes(schema, "Example").generate()
        self.assertIn("public sealed record BodyStableTarget(string Value) : Body;", models)
        self.assertIn("EnvelopeJsonContext.Default.String", models)
        self.assertIn("export type Body = Entries | Shards | string;", ts)

    def test_open_alternative_refused(self):
        schema = sample()
        schema["$defs"]["Entries"]["additionalProperties"] = True
        with self.assertRaisesRegex(ValueError, "close additionalProperties"):
            JsonShapes(schema, "Example").generate()

    def test_map_union_alternative_refused(self):
        schema = sample()
        schema["$defs"]["Labels"] = {"title": "Labels", "type": "object",
                                    "propertyNames": {"type": "string", "pattern": "^[a-z]+$"},
                                    "additionalProperties": {"type": "string"}, "maxProperties": 16}
        schema["$defs"]["Body"]["oneOf"].append({"$ref": "#/$defs/Labels"})
        with self.assertRaisesRegex(ValueError, "Union alternatives"):
            JsonShapes(schema, "Example").generate()

    def test_unimplemented_union_constraint_refused(self):
        schema = sample()
        schema["$defs"]["Body"]["not"] = {"const": "x"}
        with self.assertRaisesRegex(ValueError, "Union nodes"):
            JsonShapes(schema, "Example").generate()

    def test_duplicate_branch_refused(self):
        schema = sample()
        schema["$defs"]["Body"]["oneOf"][1] = {"$ref": "#/$defs/Entries"}
        with self.assertRaisesRegex(ValueError, "Duplicate union branch"):
            JsonShapes(schema, "Example").generate()

    def test_bundle_preserves_independent_limits_and_local_refs(self):
        first = sample()
        definitions = first.pop("$defs")
        second = copy.deepcopy(first)
        second["title"] = "Other"
        second["x-arcforges-max-bytes"] = 512
        definitions.update(Envelope=first, Other=second)
        bundle = {"title": "Bundle", "$defs": definitions,
                  "oneOf": [{"$ref": "#/$defs/Envelope"}, {"$ref": "#/$defs/Other"}]}
        roots = schema_roots(bundle)
        self.assertEqual([r["x-arcforges-max-bytes"] for r in roots], [1024, 512])
        for root in roots:
            models, _, _ = JsonShapes(root, "Example." + root["title"]).generate()
            self.assertNotIn("class Bundle", models)

    def test_bundle_invalid_reference_and_duplicate_root_refused(self):
        for alternatives in [[{"$ref": "other.json"}], [{"$ref": "#/$defs/Missing"}]]:
            with self.assertRaises(ValueError):
                schema_roots({"oneOf": alternatives})
        root = record("Same", {})
        with self.assertRaisesRegex(ValueError, "Duplicate root"):
            schema_roots({"$defs": {"A": root, "B": root}, "oneOf": [{"$ref": "#/$defs/A"}, {"$ref": "#/$defs/B"}]})

    def test_root_bundle_can_select_named_closed_route_unions(self):
        definitions = {
            "StartRequest": record("StartRequest", {"start": {"type": "string"}}),
            "ContinueRequest": record("ContinueRequest", {"continuation": {"type": "string"}}),
            "RouteRequest": {"title": "RouteRequest", "oneOf": [
                {"$ref": "#/$defs/StartRequest"}, {"$ref": "#/$defs/ContinueRequest"}], "x-arcforges-max-bytes": 1024},
            "TextA": {"title": "TextA", "type": "string", "pattern": "^.+$"},
            "TextB": {"title": "TextB", "type": "string", "pattern": "^.+$"},
            "AmbiguousText": {"title": "AmbiguousText", "oneOf": [
                {"$ref": "#/$defs/TextA"}, {"$ref": "#/$defs/TextB"}], "x-arcforges-max-bytes": 1024},
        }
        roots = schema_roots(bundle_of_roots(definitions, "RouteRequest", "AmbiguousText"))
        self.assertEqual([root["title"] for root in roots], ["RouteRequest", "AmbiguousText"])
        request_models, _, request_ts = JsonShapes(roots[0], "Example").generate()
        self.assertIn("public abstract record RouteRequest;", request_models)
        self.assertIn("export type RouteRequest = StartRequest | ContinueRequest;", request_ts)
        self.assertIn("RouteRequest", request_models)

    def test_root_bundle_rejects_open_or_non_reference_union_branches(self):
        definitions = {
            "Open": record("Open", {"name": {"type": "string"}}),
            "Route": {"title": "Route", "oneOf": [{"$ref": "#/$defs/Open"}, {"type": "string", "title": "Inline"}],
                      "x-arcforges-max-bytes": 1024},
        }
        with self.assertRaisesRegex(ValueError, "explicit local definition refs"):
            schema_roots(bundle_of_roots(definitions, "Route"))
        definitions["Route"]["oneOf"] = [{"$ref": "#/$defs/Open"}, {"$ref": "#/$defs/Open"}]
        with self.assertRaisesRegex(ValueError, "Duplicate union branch type"):
            # Duplicate branch refs are rejected as an ambiguous exact-one profile.
            JsonShapes(schema_roots(bundle_of_roots(definitions, "Route"))[0], "Example").generate()

    def test_bundle_roots_emit_one_canonical_shared_model_and_union(self):
        definitions = {
            "RootA": record("RootA", {"choice": {"$ref": "#/$defs/SharedChoice"}}),
            "RootB": record("RootB", {"choice": {"$ref": "#/$defs/SharedChoice"}}),
            "SharedChoice": {"title": "SharedChoice", "oneOf": [
                {"$ref": "#/$defs/ChoiceA"}, {"$ref": "#/$defs/ChoiceB"}]},
            "ChoiceA": record("ChoiceA", {"first": {"type": "string"}}),
            "ChoiceB": record("ChoiceB", {"second": {"type": "string"}}),
        }
        for name in ("RootA", "RootB"):
            definitions[name]["x-arcforges-max-bytes"] = 1024
        roots, compilers, owners = compile_bundle_roots(
            bundle_of_roots(definitions, "RootA", "RootB"), "Example")
        self.assertEqual([root["title"] for root in roots], ["RootA", "RootB"])
        self.assertEqual(owners["SharedChoice"], 0)
        generated = []
        for index, compiler in enumerate(compilers):
            external = bundle_external_models(index, compiler, owners)
            cs, _, ts = compiler.generate(external)
            imports = bundle_type_imports(index, compilers, owners)
            if imports:
                ts = ts.replace("// Generated by eng/generate_shapes.py; do not edit.\n",
                                "// Generated by eng/generate_shapes.py; do not edit.\n" + imports, 1)
            generated.append((cs, ts))
        csharp, typescript = zip(*generated, strict=True)
        self.assertEqual(sum(code.count("public abstract record SharedChoice;") for code in csharp), 1)
        self.assertEqual(sum(code.count("internal sealed class SharedChoiceConverter") for code in csharp), 1)
        self.assertEqual(sum(code.count("public sealed record SharedChoiceChoiceA") for code in csharp), 1)
        self.assertEqual(sum(code.count("export type SharedChoice =") for code in typescript), 1)
        self.assertEqual(sum(code.count("export interface ChoiceA {") for code in typescript), 1)
        self.assertIn('import type { ChoiceA, ChoiceB, SharedChoice } from "./RootA.js";', typescript[1])

    def test_bundle_rejects_same_model_name_with_different_canonical_schema(self):
        definitions = {
            "RootA": record("RootA", {"shared": {
                "title": "SharedRecord", "type": "object", "properties": {"left": {"type": "string"}},
                "required": ["left"], "additionalProperties": False}}),
            "RootB": record("RootB", {"shared": {
                "title": "SharedRecord", "type": "object", "properties": {"right": {"type": "string"}},
                "required": ["right"], "additionalProperties": False}}),
        }
        for name in ("RootA", "RootB"):
            definitions[name]["x-arcforges-max-bytes"] = 1024
        with self.assertRaisesRegex(ValueError, "Conflicting canonical schema definitions for bundled model SharedRecord"):
            compile_bundle_roots(bundle_of_roots(definitions, "RootA", "RootB"), "Example")

    def test_con10_bundle_reaches_only_its_nine_finite_number_fields(self):
        authored = json.loads((ROOT / "internal/ai-http/v1/schema.json").read_text(encoding="utf-8"))
        roots, compilers, owners = compile_bundle_roots(
            authored, "ArcForges.Contracts.CloudInternal.Http.V1")
        expected = {
            ("StructuredValueAsNumber", "number"),
            ("MeasurementValueAsValue", "value"),
            ("Calibration", "scale"),
            ("Calibration", "offset"),
            ("TriggerConfiguration", "threshold"),
            ("TriggerConfiguration", "hysteresis"),
            ("MeasurementThreshold", "value"),
            ("SelectedSample", "value"),
            ("CursorResult", "deltaValue"),
        }
        self.assertEqual(len(roots), 30)
        self.assertEqual(set().union(*(reachable_number_fields(root) for root in roots)), expected)

        for index, (root, compiler) in enumerate(zip(roots, compilers, strict=True)):
            expected_count = len(reachable_number_fields(root))
            _, validator, typescript = compiler.generate(bundle_external_models(index, compiler, owners))
            self.assertEqual(validator.count("!global::System.Double.IsFinite(number)"), expected_count,
                             root["title"])
            self.assertEqual(typescript.count("!Number.isFinite(number)"), expected_count,
                             root["title"])
            if expected_count:
                self.assertIn("StrictJsonNumber", typescript, root["title"])
            else:
                self.assertNotIn("StrictJsonNumber", typescript, root["title"])

    def test_finite_numbers_and_utf8_byte_bounds_are_compiled_narrowly(self):
        schema = record("NumericEnvelope", {
            "count": {"type": "integer", "minimum": 1, "maximum": 4},
            "value": {"type": "number", "minimum": -10.5, "maximum": 10.5},
            "cursor": {"type": "string", "maxLength": 8192, "x-arcforges-max-utf8-bytes": 4096},
        })
        schema["x-arcforges-max-bytes"] = 16384
        models, checks, ts = JsonShapes(schema, "Example").generate()
        self.assertIn("public required double Value", models)
        self.assertIn("global::System.Double.IsFinite(number)", checks)
        self.assertIn("global::System.Text.Encoding.UTF8.GetByteCount(text) > 4096", checks)
        self.assertIn("new TextEncoder().encode(value).byteLength > 4096", ts)
        self.assertIn("Number.isFinite(number)", ts)

        for invalid in [
            {"type": "integer", "x-arcforges-max-utf8-bytes": 4},
            {"type": "string", "x-arcforges-max-utf8-bytes": True},
            {"type": "string", "x-arcforges-max-utf8-bytes": 0},
            {"type": "number", "minimum": float("inf")},
            {"type": "number", "enum": [1.25]},
        ]:
            candidate = record("Invalid", {"value": invalid})
            candidate["x-arcforges-max-bytes"] = 1024
            with self.subTest(schema=invalid), self.assertRaises(ValueError):
                JsonShapes(candidate, "Example").generate()

    @unittest.skipUnless(shutil.which("node"), "Existing pinned Node runtime required for generated TypeScript diagnostic")
    def test_generated_typescript_finite_number_integer_lexeme_utf8_and_union_runtime(self):
        numeric = record("NumericEnvelope", {
            "count": {"type": "integer", "minimum": 1, "maximum": 4},
            "value": {"type": "number", "minimum": -10.5, "maximum": 10.5},
            "cursor": {"type": "string", "maxLength": 8192, "x-arcforges-max-utf8-bytes": 4096},
        })
        numeric["x-arcforges-max-bytes"] = 16384
        definitions = {
            "StartRequest": record("StartRequest", {"start": {"type": "string"}}),
            "ContinueRequest": record("ContinueRequest", {"continuation": {"type": "string"}}),
            "RouteRequest": {"title": "RouteRequest", "oneOf": [
                {"$ref": "#/$defs/StartRequest"}, {"$ref": "#/$defs/ContinueRequest"}], "x-arcforges-max-bytes": 1024},
            "TextA": {"title": "TextA", "type": "string", "pattern": "^.+$"},
            "TextB": {"title": "TextB", "type": "string", "pattern": "^.+$"},
            "AmbiguousText": {"title": "AmbiguousText", "oneOf": [
                {"$ref": "#/$defs/TextA"}, {"$ref": "#/$defs/TextB"}], "x-arcforges-max-bytes": 1024},
        }
        roots = schema_roots(bundle_of_roots(definitions, "RouteRequest", "AmbiguousText"))
        with tempfile.TemporaryDirectory(prefix="arcforges-json-numeric-") as directory:
            folder = Path(directory)
            for schema in [numeric, *roots]:
                (folder / (schema["title"] + ".ts")).write_text(JsonShapes(schema, "Example").generate()[2], encoding="utf-8")
            runner = folder / "run.mjs"
            runner.write_text('''import assert from "node:assert/strict";
import * as numeric from "./NumericEnvelope.ts";
import * as route from "./RouteRequest.ts";
import * as ambiguous from "./AmbiguousText.ts";
const valid = {count: 2, value: 1.25, cursor: "é".repeat(2048)};
assert.equal(numeric.isNumericEnvelope(valid), true);
assert.deepEqual(numeric.tryParseNumericEnvelopeJson(JSON.stringify(valid)), {ok: true, value: valid});
assert.equal(numeric.tryParseNumericEnvelopeJson(JSON.stringify({...valid, cursor: "a".repeat(4097)})).ok, false);
assert.equal(numeric.tryParseNumericEnvelopeJson(JSON.stringify({...valid, cursor: "é".repeat(2048) + "a"})).ok, false);
assert.equal(numeric.tryParseNumericEnvelopeJson('{"count":2.0,"value":1,"cursor":""}').ok, false);
assert.equal(numeric.tryParseNumericEnvelopeJson('{"count":2e0,"value":1,"cursor":""}').ok, false);
assert.equal(numeric.tryParseNumericEnvelopeJson('{"count":2,"value":1e0,"cursor":""}').ok, true);
assert.equal(numeric.tryParseNumericEnvelopeJson('{"count":2,"value":1e999,"cursor":""}').ok, false);
assert.equal(numeric.isNumericEnvelope({...valid, value: Number.NaN}), false);
assert.equal(numeric.isNumericEnvelope({...valid, value: Number.POSITIVE_INFINITY}), false);
assert.equal(numeric.isNumericEnvelope({...valid, value: Number.NEGATIVE_INFINITY}), false);
assert.equal(numeric.isNumericEnvelope({...valid, value: 10.5001}), false);
assert.equal(numeric.isNumericEnvelope({...valid, count: 2.5}), false);
assert.equal(numeric.tryParseNumericEnvelopeJson('{"count":2,"value":1,"cursor":"\\ud800"}').failure, "malformed");
assert.equal(numeric.tryParseNumericEnvelopeJson(Uint8Array.of(0x22, 0xc3, 0x28, 0x22)).failure, "malformed");
for (const item of [{start:"x"}, {continuation:"y"}])
  assert.deepEqual(route.tryParseRouteRequestJson(route.serializeRouteRequestJson(item)), {ok:true, value:item});
assert.equal(route.isRouteRequest({}), false);
assert.equal(route.isRouteRequest({start:"x", continuation:"y"}), false);
assert.equal(ambiguous.isAmbiguousText("both"), false);
''', encoding="utf-8")
            result = subprocess.run([shutil.which("node"), "--experimental-transform-types", str(runner)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nonbundle_duplicate_model_collision_refused_before_any_output_write(self):
        first = sample()
        second = copy.deepcopy(first)
        second["title"] = "Other"
        with patch("generate_shapes.schema_roots", return_value=[first, second]), patch("generate_shapes.emit") as write:
            with self.assertRaisesRegex(ValueError, "Duplicate generated schema model names"):
                generate()
            write.assert_not_called()

    def test_localized_map_has_typed_model_and_bounded_keys(self):
        schema = sample()
        schema["properties"]["labels"] = {"type": "object", "propertyNames": {"type": "string", "pattern": "^[A-Za-z-]+$", "maxLength": 35},
                                            "additionalProperties": {"type": "string", "maxLength": 256}, "minProperties": 1, "maxProperties": 16}
        models, checks, ts = JsonShapes(schema, "Example").generate()
        self.assertIn("Dictionary<string, string>", models)
        self.assertIn("seen.Count > 16", checks)
        self.assertIn("labels?: Record<string, string>", ts)
        self.assertIn("keys.length > 16", ts)
        schema["properties"]["labels"]["propertyNames"]["enum"] = ["en"]
        with self.assertRaisesRegex(ValueError, "Unsupported typed-map"):
            JsonShapes(schema, "Example").generate()

    def test_untyped_and_unbounded_maps_refused(self):
        for value in [True, {"type": "object", "additionalProperties": False, "properties": {}}]:
            schema = sample()
            schema["properties"]["map"] = {"type": "object", "additionalProperties": value,
                                            "propertyNames": {"type": "string", "pattern": "^[a-z]+$"}, "maxProperties": 5}
            with self.assertRaises(ValueError):
                JsonShapes(schema, "Example").generate()

    def test_recursive_refs_receive_bounded_checks_and_preorder_validation(self):
        schema = record("Tree", {"node": {"$ref": "#/$defs/Node"}})
        schema["x-arcforges-max-bytes"] = 1024
        schema["$defs"] = {"Node": record("Node", {"children": {"type": "array", "maxItems": 3, "items": {"$ref": "#/$defs/Node"}}})}
        _, checks, ts = JsonShapes(schema, "Example").generate()
        self.assertIn("if (depth >= 128)", checks)
        self.assertIn("property.Value, depth + 1", checks)
        self.assertIn("item, depth + 1", ts)
        self.assertLess(ts.index("if (!isTree(value))"), ts.index("JSON.stringify(orderTree(value))"))

    @unittest.skipUnless(shutil.which("node"), "Existing pinned Node runtime required for generated TypeScript diagnostic")
    def test_generated_typescript_executes_closed_shapes_and_rejects_cycles(self):
        envelope = sample()
        envelope["$defs"]["StableTarget"] = {"title": "StableTarget", "type": "string", "pattern": "^id-[a-z]+$"}
        envelope["$defs"]["Body"]["oneOf"].append({"$ref": "#/$defs/StableTarget"})
        envelope["properties"]["labels"] = {"type": "object", "propertyNames": {"type": "string", "pattern": "^[A-Za-z-]+$"},
                                              "additionalProperties": {"type": "string", "maxLength": 5}, "maxProperties": 2}
        envelope["properties"]["maps"] = {"type": "array", "maxItems": 3, "items": copy.deepcopy(envelope["properties"]["labels"])}
        tree = record("Tree", {"node": {"$ref": "#/$defs/Node"}})
        tree["x-arcforges-max-bytes"] = 1024
        tree["$defs"] = {"Node": record("Node", {"children": {"type": "array", "maxItems": 3, "items": {"$ref": "#/$defs/Node"}}})}
        with tempfile.TemporaryDirectory(prefix="arcforges-json-unit-") as directory:
            folder = Path(directory)
            for schema in [envelope, tree]:
                (folder / (schema["title"] + ".ts")).write_text(JsonShapes(schema, "Example").generate()[2], encoding="utf-8")
            runner = folder / "run.mjs"
            runner.write_text('''import assert from "node:assert/strict";
import * as envelope from "./Envelope.ts";
import * as tree from "./Tree.ts";
const valid = {body: {entries: ["one"]}, labels: {en: "Hello"}, maps: [{fr: "Salut"}]};
assert.equal(envelope.isEnvelope(valid), true);
assert.deepEqual(envelope.tryParseEnvelopeJson(envelope.serializeEnvelopeJson(valid)), {ok: true, value: valid});
assert.deepEqual(envelope.tryParseEnvelopeJson(envelope.serializeEnvelopeJson({body:"id-alice"})), {ok: true, value: {body:"id-alice"}});
assert.equal(envelope.isEnvelope({body:"invalid"}), false);
for (const value of [{body:{}}, {body:{entries:[],shards:[]}}, {body:{entries:[],unknown:true}},
                     {body:{entries:[]},labels:{"not a locale":"Hi"}}, {body:{entries:[]},labels:{en:"Too long"}},
                     {body:{entries:[]},labels:{en:"Hi",de:"Hi",fr:"Hi"}}]) assert.equal(envelope.isEnvelope(value), false);
assert.equal(envelope.tryParseEnvelopeJson('{"body":{"entries":[],"entries":[]}}').ok, false);
assert.equal(tree.isTree({node:{children:[]}}), true);
const cycle = {children:[]}; cycle.children.push(cycle);
assert.equal(tree.isTree({node:cycle}), false);
assert.throws(() => tree.serializeTreeJson({node:cycle}), error => error.failure === "invalid");
''', encoding="utf-8")
            result = subprocess.run([shutil.which("node"), "--experimental-transform-types", str(runner)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
