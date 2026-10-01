# SPDX-License-Identifier: Apache-2.0
"""Closed source-root and reference bindings for CON.15 schema bundles."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
import generate_shapes  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
ROOT_DIR = ROOT
CF_SCHEMA_PATH = ROOT / "internal/cf-http/v1/schema.json"
D1_SCHEMA_PATH = ROOT / "internal/storage-http/v1/schema.json"
AI_SCHEMA_PATH = ROOT / "internal/ai-http/v1/schema.json"
CANONICAL_PREFIX = "../../ai-http/v1/schema.json#/$defs/"
EXPECTED_CANONICAL_DEFS = frozenset(
    {
        "ArcError",
        "ByteRange",
        "ExecutionOwner",
        "ModelUsage",
        "ResourceRef",
        "ResourceVersionRef",
        "SessionBinding",
    }
)
EXPECTED_CF_ROOTS = frozenset(
    {
        "ObjectAuthorizeRequest",
        "ObjectAuthorizeResponse",
        "ObjectPartReceiptRequest",
        "ObjectPartReceiptResponse",
        "ObjectVerificationRequest",
        "ObjectVerificationResponse",
        "ObjectJobGrantRequest",
        "ObjectJobGrantResponse",
        "ObjectJobAuthorizeRequest",
        "ObjectJobAuthorizeResponse",
        "WorkerObjectJobRequest",
        "WorkerObjectJobResponse",
        "WorkerDispatchRequest",
        "WorkerDispatchResponse",
        "WorkerControlRequest",
        "WorkerControlResponse",
        "WorkerDeleteRequest",
        "WorkerDeleteResponse",
        "WorkerWebSearchRequest",
        "WorkerWebSearchResponse",
        "InferenceJobRequest",
        "InferenceJobResponse",
        "InferenceLeaseRequest",
        "InferenceLeaseResponse",
        "InferenceInputRequest",
        "InferenceInputResponse",
        "InferenceOutcomeRequest",
        "InferenceOutcomeResponse",
        "InferenceLateOutcomeRequest",
        "InferenceLateOutcomeResponse",
        "InferenceStateRequest",
        "InferenceStateResponse",
        "BackupManifest",
        "CfDeletionTarget",
        "CfDeletionReceipt",
    }
)
EXPECTED_D1_ROOTS = frozenset({"ExecutePlanRequest", "ExecutePlanResponse"})
EXPECTED_IDENTITIES = frozenset(
    {
        ("CloudflareInternalHttpContractBundle", "1"),
        ("D1ExecutePlanContractBundle", "1"),
    }
)


def _bundle_roots(schema, expected_roots):
    definitions = schema.get("$defs")
    roots = schema.get("oneOf")
    if not isinstance(definitions, dict) or not isinstance(roots, list):
        raise ValueError("bundle must expose a $defs map and root oneOf list")

    names = []
    for row in roots:
        reference = row.get("$ref") if isinstance(row, dict) else None
        if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
            raise ValueError(f"bundle root is not a local definition: {reference!r}")
        name = reference.removeprefix("#/$defs/")
        if not name or "/" in name or name not in definitions:
            raise ValueError(f"bundle root does not name an exact local definition: {reference!r}")
        names.append(name)

    if len(names) != len(set(names)):
        raise ValueError("bundle root list contains a duplicate")
    if set(names) != set(expected_roots):
        missing = sorted(set(expected_roots) - set(names))
        extra = sorted(set(names) - set(expected_roots))
        raise ValueError(f"bundle root set mismatch: missing={missing}, extra={extra}")
    for name in names:
        if definitions[name].get("title") != name:
            raise ValueError(f"root {name!r} must retain its exact schema title")
    return set(names)


def _reference_closure(schema, canonical_schema, expected_external):
    definitions = schema.get("$defs", {})
    canonical_definitions = canonical_schema.get("$defs", {})
    found_external = set()

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                reference = node["$ref"]
                if not isinstance(reference, str):
                    raise ValueError(f"$ref must be a string: {reference!r}")
                if reference.startswith("#/$defs/"):
                    name = reference.removeprefix("#/$defs/")
                    if not name or "/" in name or name not in definitions:
                        raise ValueError(f"unlisted local reference: {reference!r}")
                elif reference in expected_external:
                    name = reference.removeprefix(CANONICAL_PREFIX)
                    if name not in EXPECTED_CANONICAL_DEFS or name not in canonical_definitions:
                        raise ValueError(f"canonical target is missing or not allowlisted: {reference!r}")
                    found_external.add(reference)
                else:
                    raise ValueError(f"unlisted non-local reference: {reference!r}")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    if found_external != set(expected_external):
        missing = sorted(set(expected_external) - found_external)
        extra = sorted(found_external - set(expected_external))
        raise ValueError(f"canonical reference set mismatch: missing={missing}, extra={extra}")
    return found_external


def _replace_first_canonical_reference(node, replacement):
    if isinstance(node, dict):
        if node.get("$ref") in {CANONICAL_PREFIX + name for name in EXPECTED_CANONICAL_DEFS}:
            node["$ref"] = replacement
            return True
        for value in node.values():
            if _replace_first_canonical_reference(value, replacement):
                return True
    elif isinstance(node, list):
        for value in node:
            if _replace_first_canonical_reference(value, replacement):
                return True
    return False


class Con15SchemaRootBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cf_schema = json.loads(CF_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.d1_schema = json.loads(D1_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.ai_schema = json.loads(AI_SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_exact_cf_and_d1_root_sets_and_unique_schema_identities(self):
        self.assertEqual(_bundle_roots(self.cf_schema, EXPECTED_CF_ROOTS), set(EXPECTED_CF_ROOTS))
        self.assertEqual(_bundle_roots(self.d1_schema, EXPECTED_D1_ROOTS), set(EXPECTED_D1_ROOTS))
        identities = {
            (schema.get("title"), schema.get("x-arcforges-schema-version"))
            for schema in (self.cf_schema, self.d1_schema)
        }
        self.assertEqual(identities, set(EXPECTED_IDENTITIES))
        self.assertEqual(len(identities), 2)

    def test_root_set_checker_rejects_missing_extra_and_duplicate_roots(self):
        mutations = (
            (self.cf_schema, EXPECTED_CF_ROOTS, "missing", lambda schema: schema["oneOf"].pop()),
            (
                self.cf_schema,
                EXPECTED_CF_ROOTS,
                "extra",
                lambda schema: schema["oneOf"].append({"$ref": "#/$defs/Identifier"}),
            ),
            (
                self.cf_schema,
                EXPECTED_CF_ROOTS,
                "duplicate",
                lambda schema: schema["oneOf"].append(copy.deepcopy(schema["oneOf"][0])),
            ),
            (self.d1_schema, EXPECTED_D1_ROOTS, "missing", lambda schema: schema["oneOf"].pop()),
            (
                self.d1_schema,
                EXPECTED_D1_ROOTS,
                "extra",
                lambda schema: schema["oneOf"].append({"$ref": "#/$defs/D1NullValue"}),
            ),
            (
                self.d1_schema,
                EXPECTED_D1_ROOTS,
                "duplicate",
                lambda schema: schema["oneOf"].append(copy.deepcopy(schema["oneOf"][0])),
            ),
        )
        for source, expected, label, mutate in mutations:
            with self.subTest(source=source["title"], mutation=label):
                candidate = copy.deepcopy(source)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    _bundle_roots(candidate, expected)

    def test_all_references_are_local_or_the_exact_seven_canonical_definitions(self):
        expected_external = {CANONICAL_PREFIX + name for name in EXPECTED_CANONICAL_DEFS}
        self.assertEqual(_reference_closure(self.cf_schema, self.ai_schema, expected_external), expected_external)
        self.assertEqual(_reference_closure(self.d1_schema, self.ai_schema, set()), set())

    def test_reference_checker_rejects_remote_alternate_and_missing_targets(self):
        invalid_references = (
            "https://attacker.example/schema.json#/$defs/ByteRange",
            "../other.json#/$defs/ByteRange",
            "/root.json#/$defs/ByteRange",
            "../../storage-http/v1/schema.json#/$defs/ExecutePlanRequest",
            "#/$defs/MissingDefinition",
            "#/$defs/Identifier/child",
        )
        expected_external = {CANONICAL_PREFIX + name for name in EXPECTED_CANONICAL_DEFS}
        for reference in invalid_references:
            with self.subTest(reference=reference):
                candidate = copy.deepcopy(self.cf_schema)
                self.assertTrue(_replace_first_canonical_reference(candidate, reference))
                with self.assertRaises(ValueError):
                    _reference_closure(candidate, self.ai_schema, expected_external)

    def test_generator_binds_only_the_seven_canonical_definitions_with_one_type_identity(self):
        allowed = generate_shapes.CON15_CANONICAL_REFERENCES
        self.assertEqual(allowed, EXPECTED_CANONICAL_DEFS)
        bound, closure = generate_shapes.bind_canonical_references(self.cf_schema, self.ai_schema, allowed)
        self.assertTrue(EXPECTED_CANONICAL_DEFS <= closure)
        self.assertNotIn("ai-http", json.dumps(bound))
        _, _, ai_owners = generate_shapes.compile_bundle_roots(self.ai_schema, "ArcForges.Contracts.CloudInternal.Http.V1")
        _, cf_compilers, cf_owners = generate_shapes.compile_bundle_roots(bound, "ArcForges.Contracts.CloudInternal.Http.V1")
        self.assertTrue(closure <= set(ai_owners))
        cf_models = set()
        for compiler in cf_compilers:
            cf_models |= compiler.collect_models()
        authored = set(self.cf_schema["$defs"])
        # Canonical models keep their CON.10 identity; no authored model may redefine one.
        self.assertFalse(authored & set(ai_owners))
        self.assertTrue(closure <= cf_models)
        self.assertFalse(set(self.d1_schema["$defs"]) & (set(ai_owners) | authored))

    def test_generator_refuses_unlisted_external_references_and_collisions(self):
        allowed = generate_shapes.CON15_CANONICAL_REFERENCES
        for reference in (
            "../../ai-http/v1/schema.json#/$defs/AiClaimRequest",
            "../../ai-http/v1/schema.json#/$defs/Missing",
            "../../ai-http/v1/configuration.schema.json#/$defs/ConfigurationDocument",
            "../../storage-http/v1/schema.json#/$defs/ExecutePlanRequest",
            "https://attacker.example/schema.json#/$defs/ByteRange",
            "../../ai-http/v1/schema.json",
        ):
            with self.subTest(reference=reference):
                candidate = copy.deepcopy(self.cf_schema)
                self.assertTrue(_replace_first_canonical_reference(candidate, reference))
                with self.assertRaises(ValueError):
                    generate_shapes.bind_canonical_references(candidate, self.ai_schema, allowed)
        collision = copy.deepcopy(self.cf_schema)
        collision["$defs"]["ByteRange"] = {"title": "ByteRange", "type": "object", "properties": {},
                                           "required": [], "additionalProperties": False}
        with self.assertRaises(ValueError):
            generate_shapes.bind_canonical_references(collision, self.ai_schema, allowed)
        with self.assertRaises(ValueError):
            generate_shapes.bind_canonical_references(self.cf_schema, self.ai_schema, frozenset({"SessionBinding"}))
        # The storage schema is registered without any canonical reference allowance.
        bound, closure = generate_shapes.bind_canonical_references(self.d1_schema, self.ai_schema, frozenset())
        self.assertEqual((bound, closure), (self.d1_schema, set()))
        smuggled = copy.deepcopy(self.d1_schema)
        smuggled["$defs"]["ExecutePlanRequest"]["properties"]["scope"] = {"$ref": CANONICAL_PREFIX + "ByteRange"}
        with self.assertRaises(ValueError):
            generate_shapes.bind_canonical_references(smuggled, self.ai_schema, frozenset())

    def test_generated_outputs_are_current_and_cover_every_root(self):
        generate_shapes.generate(check=True)
        for root, namespace_dir in (
            (EXPECTED_CF_ROOTS | EXPECTED_D1_ROOTS, "src/internal/dotnet/ArcForges.Contracts.CloudInternal/Generated/Shapes"),
        ):
            for name in sorted(root):
                with self.subTest(root=name):
                    self.assertTrue((ROOT_DIR / namespace_dir / f"{name}.g.cs").is_file())
                    self.assertTrue((ROOT_DIR / namespace_dir / f"{name}Validator.g.cs").is_file())
                    self.assertTrue((ROOT_DIR / "src/internal/ts/ai-internal/src/shapes/gen" / f"{name}.ts").is_file())


if __name__ == "__main__":
    unittest.main()
