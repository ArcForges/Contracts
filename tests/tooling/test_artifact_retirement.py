# SPDX-License-Identifier: Apache-2.0
"""A deliberate module retirement must not permit arbitrary lost artifacts."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from check_provenance import ROOT, retired_contract_artifact


class ArtifactRetirement(unittest.TestCase):
    def test_receipt_requires_exact_owner_target_history_and_removed_source(self):
        relative = "eng/provenance/retirements/contracts-client-wp03-00.json"
        receipt = json.loads((ROOT / relative).read_text())
        target = {key: receipt[key] for key in ("project", "package", "kind")}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(receipt))
            catalog = root / "eng/contract-packages.json"
            catalog.write_text(json.dumps({"packages": [{"id": receipt["replacementPackage"]}]}))
            self.assertTrue(retired_contract_artifact(root, "Contracts", target, receipt["previousRecord"], [relative]))
            self.assertFalse(retired_contract_artifact(root, "Mobile", target, receipt["previousRecord"], [relative]))
            self.assertFalse(retired_contract_artifact(root, "Contracts", {**target, "project": "contracts-proto"}, receipt["previousRecord"], [relative]))
            self.assertFalse(retired_contract_artifact(root, "Contracts", target, receipt["previousRecord"], []))
            with self.assertRaisesRegex(ValueError, "accepted record"):
                retired_contract_artifact(root, "Contracts", target, "unrelated-r1", [relative])
            catalog.write_text(json.dumps({"packages": [{"id": receipt["replacementPackage"]}, {"id": receipt["package"]}]}))
            with self.assertRaisesRegex(ValueError, "catalog"):
                retired_contract_artifact(root, "Contracts", target, receipt["previousRecord"], [relative])
            catalog.write_text(json.dumps({"packages": [{"id": receipt["replacementPackage"]}]}))
            (root / receipt["sourceRoot"]).mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "producer sources"):
                retired_contract_artifact(root, "Contracts", target, receipt["previousRecord"], [relative])


if __name__ == "__main__":
    unittest.main()
