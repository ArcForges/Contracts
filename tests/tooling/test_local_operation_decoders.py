# SPDX-License-Identifier: Apache-2.0
"""CON.43: the DP-03 local-operation emitter is deterministic, closed and refuses drift and unprofiled operations.

Needs artifacts/local-dispatch.binpb, which ``eng/contracts.py generate`` (and so ``pack``) writes first.
"""
import copy
import json
from pathlib import Path
import random
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))
import local_operations as lo  # noqa: E402

OUTPUT = "src/internal/dotnet/ArcForges.Contracts.LocalRpc.Dispatch/Generated/Operations"
# Independent frozen inventory (registry 04 section 6 minus the AZ-04 human-only decision); not read from the emitter.
ELIGIBLE = [
    "IChatOperations.AppendUserMessage", "IChatOperations.CreateConversation", "IChatOperations.GetConversation",
    "IChatOperations.ListConversations", "IChatOperations.OpenArtifact", "IChatOperations.StartAgentTurn",
    "IScopeOperations.CompareSessions", "IScopeOperations.CreateAnnotation", "IScopeOperations.CreateFinding",
    "IScopeOperations.GenerateReport", "IScopeOperations.GetConfigurationSnapshot", "IScopeOperations.GetSession",
    "IScopeOperations.GetStructuredContext", "IScopeOperations.ListCaptures", "IScopeOperations.ListSessions",
    "IScopeOperations.RunAnalysis", "IScopeOperations.RunMeasurement", "IScopeOperations.StartCapture",
    "IScopeOperations.StopCapture",
]
NOT_ELIGIBLE = [
    "IArtifactHandler.DescribeArtifactKinds", "IArtifactHandler.Resolve", "IArtifactHandler.RenderPreview",
    "IArtifactHandler.Open", "ICapabilityProvider.Describe", "ICapabilityProvider.EvaluateAvailability",
    "ICapabilityProvider.Invoke", "IContextProvider.DescribeContextKinds", "IContextProvider.ProvideContext",
    "IDeepLinkTarget.HandleDeepLink", "ILocalEvents.Poll", "IProductLifecycle.GetState",
    "IProductLifecycle.PrepareForShutdown", "IProductLifecycle.GetJob", "IResourceAccess.GetMetadata",
    "IResourceAccess.OpenRead", "IResourceAccess.Release", "IResourceAccess.ReadChunk", "IChatOperations.SubmitApproval",
]
ADMITTED = "IScopeOperations.CreateAnnotation"
REFLECTIVE = re.compile(r"System\.Reflection|Google\.Protobuf\.Reflection|MakeGenericType|Activator\.|Type\.GetType|"
                        r"Assembly\.|\btypeof\(|GetType\(\)|Dictionary<|\bdynamic\b|JsonParser|JsonFormatter|Reflection\.Emit")


def type_name(operation: str) -> str:
    interface, method = operation.split(".")
    return ("Chat" if interface == "IChatOperations" else "Scope") + method + "Operation"


class LocalOperationEmitterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = lo.load_inputs(ROOT)
        cls.files = lo.render(cls.inputs)

    def variant(self, rows=None, manifest=None, ports=None) -> lo.Inputs:
        return lo.Inputs(self.inputs.model, self.inputs.namespaces, self.inputs.constraints,
                         copy.deepcopy(self.inputs.rows) if rows is None else rows,
                         copy.deepcopy(self.inputs.manifest) if manifest is None else manifest,
                         self.inputs.ports if ports is None else ports)

    def rows_with(self, operation: str, change) -> list:
        rows = copy.deepcopy(self.inputs.rows)
        for index, row in enumerate(rows):
            if row["operationId"] == operation:
                result = change(row)
                if result is None:
                    del rows[index]
                else:
                    rows[index] = result
                return rows
        raise AssertionError("row not found " + operation)

    def allowlist_cases(self, files) -> list:
        text = files[f"{OUTPUT}/LocalToolAllowlist.g.cs"]
        return re.findall(r'case "([^"]*)":', text)

    def test_committed_output_matches_generation(self):
        lo.generate(check=True)

    def test_rendering_is_deterministic_and_input_order_independent(self):
        self.assertEqual(self.files, lo.render(self.inputs))
        shuffled_rows = copy.deepcopy(self.inputs.rows)
        random.Random(43).shuffle(shuffled_rows)
        messages = list(self.inputs.model["messages"].items())
        random.Random(7).shuffle(messages)
        model = dict(self.inputs.model, messages=dict(messages))
        constraints = list(self.inputs.constraints.items())
        random.Random(11).shuffle(constraints)
        ports = {owner: dict(reversed(list(interfaces.items()))) for owner, interfaces in reversed(list(self.inputs.ports.items()))}
        permuted = lo.Inputs(model, dict(reversed(list(self.inputs.namespaces.items()))), dict(constraints), shuffled_rows,
                             copy.deepcopy(self.inputs.manifest), ports)
        self.assertEqual(self.files, lo.render(permuted))
        self.assertEqual(list(self.files), sorted(self.files, key=lo.ordinal))

    def test_ordinal_order_matches_dotnet_ordinal(self):
        self.assertEqual(lo.ordered(["b", "B", "a", "_", "A", "aa"]), ["A", "B", "_", "a", "aa", "b"])

    def test_check_refuses_changed_missing_and_stale_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lo.sync(self.files, root, check=False)
            lo.sync(self.files, root, check=True)
            target = root / OUTPUT / "LocalToolAllowlist.g.cs"
            original = target.read_bytes()
            target.write_bytes(original + b"// edited\n")
            with self.assertRaisesRegex(ValueError, "Stale generated local operations: .*LocalToolAllowlist"):
                lo.sync(self.files, root, check=True)
            target.unlink()
            with self.assertRaisesRegex(ValueError, "LocalToolAllowlist"):
                lo.sync(self.files, root, check=True)
            target.write_bytes(original)
            stale = root / OUTPUT / "ScopeRetiredOperation.g.cs"
            stale.write_text("// stale\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ScopeRetiredOperation"):
                lo.sync(self.files, root, check=True)
            lo.sync(self.files, root, check=False)
            self.assertFalse(stale.exists())
            lo.sync(self.files, root, check=True)
            with self.assertRaisesRegex(ValueError, "outside"):
                lo.sync({"src/elsewhere.g.cs": "x"}, root, check=False)

    def test_operation_without_declared_profile_fails_generation(self):
        for change in (lambda row: None, lambda row: dict(row, profile="unclassified"),
                       lambda row: dict(row, operationId="IScopeOperations.Renamed")):
            with self.subTest(change=change):
                with self.assertRaisesRegex(ValueError, "declared profile row: IScopeOperations.StopCapture"):
                    lo.render(self.variant(rows=self.rows_with("IScopeOperations.StopCapture", change)))
        duplicated = copy.deepcopy(self.inputs.rows)
        duplicated.append(dict(next(r for r in duplicated if r["operationId"] == "IChatOperations.GetConversation"),
                               operationId="IChatOperations.GetConversationCopy"))
        with self.assertRaisesRegex(ValueError, "declared profile row: IChatOperations.GetConversation"):
            lo.render(self.variant(rows=duplicated))

    def test_exactly_one_schema_decoder_and_encoder_per_eligible_method(self):
        self.assertEqual([item.operation_id for item in lo.operations(self.inputs)], ELIGIBLE)
        operation_files = sorted(path for path in self.files if path.endswith("Operation.g.cs") and not path.endswith("/LocalOperation.g.cs"))
        self.assertEqual(operation_files, sorted(f"{OUTPUT}/{type_name(op)}.g.cs" for op in ELIGIBLE))
        everything = "".join(self.files.values())
        for operation in ELIGIBLE:
            text = self.files[f"{OUTPUT}/{type_name(operation)}.g.cs"]
            for member in ("public const string RequestSchema =", "public const string ResultSchema =",
                           "public static bool TryDecode(", "public static bool TryEncodeResult(",
                           "public static bool TryDecodeResult(", "public static bool TryEncodeArguments("):
                self.assertEqual(text.count(member), 1, operation + " " + member)
            self.assertEqual(everything.count(f'public const string OperationId = "{operation}";'), 1)
        for operation in NOT_ELIGIBLE:
            self.assertNotIn(f'"{operation}"', everything, operation)
        self.assertFalse(any("SubmitApproval" in path for path in self.files))
        self.assertNotIn("SubmitApproval", everything)

    def test_schema_text_is_canonical_and_closed(self):
        text = self.files[f"{OUTPUT}/ScopeCreateAnnotationOperation.g.cs"]
        literal = re.search(r'public const string RequestSchema = (".*");\n', text).group(1)
        schema_text = json.loads(literal)
        schema = json.loads(schema_text)
        self.assertEqual(schema_text, json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        self.assertEqual((schema["dialect"], schema["schemaId"], schema["maxDepth"], schema["maxItems"]),
                         ("arcforges.local-operation-schema.v1",
                          "arcforges.local.scope.v1.ScopeOperationsServiceCreateAnnotationRequest", 16, 200))
        root = schema["definitions"][schema["root"]]
        self.assertTrue(root["closed"])
        self.assertNotIn("meta", root["fields"])
        self.assertEqual(sorted(name for name, field in root["fields"].items() if field["required"]),
                         ["annotationId", "range", "sessionId", "text"])
        self.assertEqual(root["fields"]["annotationId"], {"format": "uuid", "kind": "text", "required": True})
        self.assertEqual(root["fields"]["text"]["maxUtf8Bytes"], 262144)
        sample = schema["definitions"]["arcforges.publicapi.v1.SampleRange"]["fields"]["from"]
        self.assertEqual((sample["kind"], sample["minimum"], sample["maximum"]), ("integer", 0, 9223372036854775807))

    def test_allowlist_holds_exactly_the_gate_admitted_operation(self):
        self.assertEqual(self.allowlist_cases(self.files), [ADMITTED])
        self.assertEqual([item.operation_id for item in lo.operations(self.inputs) if item.admitted], [ADMITTED])
        for operation in ELIGIBLE:
            text = self.files[f"{OUTPUT}/{type_name(operation)}.g.cs"]
            expected = "true" if operation == ADMITTED else "false"
            self.assertIn(f"public const bool IsAdmitted = {expected};", text, operation)

    def test_allowlist_is_empty_without_the_admission(self):
        def revert(row):
            row = copy.deepcopy(row)
            row["authorization"]["capability"] = None
            row["authorization"]["actorKinds"] = ["human", "product-handler"]
            return row
        files = lo.render(self.variant(rows=self.rows_with(ADMITTED, revert)))
        self.assertEqual(self.allowlist_cases(files), [])
        self.assertIn("Keys { get; } =\n    [\n    ];", files[f"{OUTPUT}/LocalToolAllowlist.g.cs"])
        self.assertEqual(set(files), set(self.files))

    def test_capability_without_gate_admission_refuses_generation(self):
        def claim(row):
            row = copy.deepcopy(row)
            row["authorization"]["capability"] = row["operationId"]
            row["authorization"]["actorKinds"] = ["human", "product-handler", "agent"]
            return row
        with self.assertRaises(ValueError):
            lo.render(self.variant(rows=self.rows_with("IScopeOperations.CreateFinding", claim)))
        changed = self.rows_with(ADMITTED, lambda row: dict(row, idempotency="IW"))
        with self.assertRaises(ValueError):
            lo.render(self.variant(rows=changed))

    def test_manifest_allowlist_is_not_a_second_admission_source(self):
        manifest = copy.deepcopy(self.inputs.manifest)
        manifest["toolAllowlist"] = ["IScopeOperations.CreateFinding"]
        files = lo.render(self.variant(manifest=manifest))
        self.assertEqual(self.allowlist_cases(files), [ADMITTED])

    def test_human_only_and_infrastructure_methods_get_nothing(self):
        ports = copy.deepcopy(self.inputs.ports)
        self.assertIn("SubmitApproval", ports["Chat"]["IChatOperations"][1])
        names = [item.operation_id for item in lo.operations(self.inputs)]
        self.assertNotIn("IChatOperations.SubmitApproval", names)
        self.assertFalse(any(name.split(".")[0] in {i for i in ports["Platform"]} for name in names))

    def test_output_stays_inside_the_dispatch_package(self):
        for path in self.files:
            self.assertTrue(path.startswith(OUTPUT + "/") and path.endswith(".g.cs"), path)
            self.assertNotIn("/", path[len(OUTPUT) + 1:])

    def test_output_is_non_reflective_generated_source(self):
        for path, text in self.files.items():
            self.assertTrue(text.startswith("// SPDX-License-Identifier: Apache-2.0\n// <auto-generated />\n"), path)
            self.assertNotIn("\r", text, path)
            self.assertIsNone(REFLECTIVE.search(text), path)
            self.assertIn("namespace ArcForges.Contracts.LocalRpc.Dispatch;", text, path)

    def test_emitter_refuses_reflective_output(self):
        original = lo.VALUE_CODEC
        try:
            lo.VALUE_CODEC = original + "\n// Activator.CreateInstance\n"
            with self.assertRaisesRegex(ValueError, "forbidden reflective token"):
                lo.render(self.inputs)
        finally:
            lo.VALUE_CODEC = original


if __name__ == "__main__":
    unittest.main()
