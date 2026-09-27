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
from generate_shapes import JsonShapes, schema_roots, generate


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


class JsonShapeUnions(unittest.TestCase):
    def test_accepted_seed_outputs_unchanged(self):
        mappings = [
            ("public/http/v1/schema.json", "ArcForges.Contracts.PublicApi.Http.V1", "src/public/dotnet/ArcForges.Contracts.PublicApi", "src/public/dotnet/ArcForges.Contracts.Validation", "src/public/ts/api-client"),
            ("public/http/v1/inventory.schema.json", "ArcForges.Sdk.Contracts.Inventory.V1", "src/public/dotnet/ArcForges.Sdk.Contracts", "src/public/dotnet/ArcForges.Contracts.Validation", "src/public/ts/api-client"),
            ("internal/ai-http/v1/schema.json", "ArcForges.Contracts.CloudInternal.Http.V1", "src/internal/dotnet/ArcForges.Contracts.CloudInternal", "src/internal/dotnet/ArcForges.Contracts.CloudInternal", "src/internal/ts/ai-internal"),
        ]
        for source, namespace, models, checks, tsroot in mappings:
            schema = json.loads((ROOT / source).read_text())
            outputs = JsonShapes(schema, namespace).generate()
            title = schema["title"]
            paths = [f"{models}/Generated/Shapes/{title}.g.cs", f"{checks}/Generated/Shapes/{title}Validator.g.cs", f"{tsroot}/src/shapes/gen/{title}.ts"]
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

    def test_shared_bundle_model_collision_refused_before_any_output_write(self):
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
