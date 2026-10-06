# SPDX-License-Identifier: Apache-2.0
"""Negative generation tests use synthetic descriptors, never a registry or live service."""
import copy
import sys
import tempfile
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
import generate_operation_catalog as catalog


class OperationCatalogTests(unittest.TestCase):
    def setUp(self):
        self.owners, self.models, self.rows = [], {}, []
        for owner, namespace, operation in [("ArcForges.Contracts.PublicApi", "publicapi", "workspace.list"),
                                            ("ArcForges.Contracts.Events", "events", "events.poll")]:
            filename = f"arcforges/{namespace}/v1/test.proto"
            source, service = "public/proto/" + filename, f"arcforges.{namespace}.v1.TestService"
            self.owners.append({"id": owner, "kind": "nuget", "access": "public", "proto": [source]})
            self.models[owner] = {"files": {filename: {"services": {"." + service: {"Read": {}}}}}}
            self.rows.append({"status": "registered", "surface": "public", "kind": "proto",
                "operationId": operation, "binding": service + "/Read", "source": source,
                "scope": "account", "idempotency": "Q", "profile": "human-owner", "sourceRule": "rule#read",
                "authorization": {"capability": None, "risk": "R1", "approval": "none", "stepUp": False,
                    "localPresence": False, "egress": "none", "patEligible": operation == "workspace.list", "actorKinds": ["human"]}})

    def project(self, rows=None):
        return catalog.project({"operations": self.rows if rows is None else rows}, self.owners, self.models)

    def test_projects_exact_owned_methods_and_ignores_other_surfaces(self):
        private = copy.deepcopy(self.rows[0])
        private.update(operationId="operator.read", surface="operator", source="internal/proto/operator.proto")
        result = self.project([private, *reversed(self.rows)])
        self.assertEqual([row["operationId"] for row in result["ArcForges.Contracts.PublicApi"]], ["workspace.list"])
        self.assertEqual([row["operationId"] for row in result["ArcForges.Contracts.Events"]], ["events.poll"])

    def test_duplicate_operation_or_binding_is_rejected(self):
        for key in ("operationId", "binding"):
            row = copy.deepcopy(self.rows[1]); row[key] = self.rows[0][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "duplicate public catalog"):
                self.project([self.rows[0], row])

    def test_wrong_method_owner_private_leakage_and_nonproto_are_rejected(self):
        for key, value, message in [("binding", "arcforges.publicapi.v1.TestService/Absent", "descriptor mismatch"),
                ("source", self.rows[1]["source"], "descriptor mismatch"),
                ("source", "internal/proto/operator.proto", "unowned or nonpublic"), ("kind", "http", "non-proto")]:
            rows = copy.deepcopy(self.rows); rows[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, message): self.project(rows)

    def test_missing_metadata_or_compiled_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "missing public catalog metadata"): self.project(self.rows[1:])
        self.models[self.owners[0]["id"]]["files"].clear()
        with self.assertRaisesRegex(ValueError, "missing compiled catalog source"): self.project()

    def test_owner_inventory_cannot_expand_or_lose_public_boundary(self):
        self.owners[0]["access"] = "internal"
        with self.assertRaisesRegex(ValueError, "public NuGet owner"): self.project()
        self.owners.pop()
        with self.assertRaisesRegex(ValueError, "exact public catalog package owners"): self.project()

    def test_derived_requirements_remain_sources_instead_of_false_literals(self):
        row = copy.deepcopy(self.rows[0])
        row["authorization"].update(risk={"from": "verifiedApprovalProposal.effectiveRisk"},
            stepUp={"from": "verifiedApprovalProposal.stepUp"}, localPresence={"from": "verifiedApprovalProposal.localPresence"})
        code = catalog.render("ArcForges.Contracts.PublicApi", [row])
        for source in ("effectiveRisk", "stepUp", "localPresence"): self.assertIn('null, "verifiedApprovalProposal.' + source + '"', code)
        row["authorization"]["risk"] = {"from": "value", "extra": True}
        with self.assertRaisesRegex(ValueError, "unsupported derived catalog value"): catalog.render("ArcForges.Contracts.PublicApi", [row])

    def test_deterministic_render_and_stale_output_rejection(self):
        code = catalog.render("ArcForges.Contracts.PublicApi", self.project()["ArcForges.Contracts.PublicApi"])
        self.assertEqual(code, catalog.render("ArcForges.Contracts.PublicApi", [self.rows[0]]))
        self.assertIn("StringComparer.Ordinal", code)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "generated.g.cs"
            catalog.emit(target, code, False); catalog.emit(target, code, True)
            target.write_text(code + "changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale generated operation catalog"): catalog.emit(target, code, True)


if __name__ == "__main__": unittest.main()
