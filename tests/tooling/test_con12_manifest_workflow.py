# SPDX-License-Identifier: Apache-2.0
"""Independent profile boundaries, not archive or executable authorization evidence."""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class ManifestWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "public/http/v1/manifest.schema.json").read_text(encoding="utf-8-sig"))
        cls.workflow = json.loads((ROOT / "public/http/v1/workflow.schema.json").read_text(encoding="utf-8-sig"))
        cls.fixtures = json.loads((ROOT / "fixtures/public/con-12-extension-policy.json").read_text(encoding="utf-8-sig"))

    def test_closed_public_profiles_and_references(self):
        for schema in (self.manifest, self.workflow):
            def visit(node):
                if isinstance(node, dict):
                    if "$ref" in node:
                        self.assertIn(node["$ref"].removeprefix("#/$defs/"), schema["$defs"])
                    if node.get("type") == "object" and "properties" in node:
                        self.assertIs(node["additionalProperties"], False)
                    for child in node.values():
                        visit(child)
                elif isinstance(node, list):
                    for child in node:
                        visit(child)
            visit(schema)
        self.assertEqual(self.manifest["x-arcforges-rules"], ["manifestProfile"])
        self.assertEqual(self.workflow["x-arcforges-rules"], ["workflowGraph"])

    def test_six_contributions_and_seven_node_kinds(self):
        def kinds(schema, union):
            return {schema["$defs"][r["$ref"].split("/")[-1]]["properties"]["kind"]["const"] for r in schema["$defs"][union]["oneOf"]}
        self.assertEqual(kinds(self.manifest, "ManifestContribution"), {"skill", "template", "workflow", "mcp", "connector", "extension"})
        self.assertEqual(kinds(self.workflow, "WorkflowNode"), {"constant", "input", "select", "capability", "condition", "foreach", "output"})

    def test_decimal_independent_precision_and_canonical_vectors(self):
        # Decimal grammar and digit counts are independent of binary floats and host Decimal precision.
        for vector in self.fixtures["manifest"]["decimalVectors"]:
            text = vector["value"]
            lexical = re.fullmatch(r"(?:0|-?[1-9][0-9]*|-?(?:0|[1-9][0-9]*)\.[0-9]{0,8}[1-9])", text) is not None
            digits = len(text.replace("-", "").replace(".", "").lstrip("0"))
            self.assertEqual(lexical and digits <= 28, vector["valid"], text)
        for schema, prefix in ((self.manifest, "Manifest"), (self.workflow, "Workflow")):
            self.assertIn("canonicalDecimal", schema["$defs"][prefix + "DecimalValue"]["properties"]["value"]["x-arcforges-rules"])

    def test_normative_limits(self):
        self.assertEqual(self.manifest["properties"]["contributions"]["maxItems"], 256)
        self.assertEqual(self.manifest["properties"]["dependencies"]["maxItems"], 64)
        self.assertEqual(self.manifest["$defs"]["ManifestPrivateState"]["properties"]["maxBytes"]["maximum"], 268435456)
        limits = self.workflow["$defs"]["WorkflowLimits"]["properties"]
        self.assertEqual({k: v["maximum"] for k, v in limits.items()}, {"maxExpandedSteps": 256, "maxForEachNesting": 2, "maxPredicateDepth": 8, "maxPredicateNodes": 128})
        self.assertEqual(self.workflow["$defs"]["WorkflowForeachNode"]["properties"]["maxItems"]["maximum"], 100)

    def test_semantic_vectors_cover_non_shape_failures(self):
        vectors = self.fixtures["workflow"]["vectors"] + self.fixtures["manifest"]["vectors"]
        names = [x["name"] for x in vectors]
        self.assertEqual(len(names), len(set(names)))
        by_name = {x["name"]: x for x in vectors}
        for name in ("workflow.unordered-dag", "workflow.unordered-condition", "workflow.bounded-loop", "manifest.content-only", "manifest.numeric-prerelease-order"):
            self.assertTrue(by_name[name]["valid"])
        for name in ("workflow.cycle", "workflow.future-branch-output", "workflow.scope-escape", "workflow.expanded-budget", "workflow.incompatible-known-scalars", "manifest.case-collision", "manifest.unresolved-resource", "manifest.inverted-range", "manifest.inverted-migration-range"):
            self.assertFalse(by_name[name]["valid"])
        loop = by_name["workflow.expanded-budget"]["value"]
        # One input + one loop dispatch + 100 body steps = 102, exceeding declared 101.
        self.assertEqual(loop["limits"]["maxExpandedSteps"], 101)
        self.assertEqual(1 + 1 + loop["nodes"][1]["maxItems"] * len(loop["nodes"][1]["body"]), 102)


if __name__ == "__main__":
    unittest.main()
