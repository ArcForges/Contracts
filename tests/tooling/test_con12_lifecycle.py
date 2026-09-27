# SPDX-License-Identifier: Apache-2.0
"""Offline contracts08 section 3 oracle; no ZIP bytes, secrets or broker execution."""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def lifecycle_decision(case):
    """Project declared metadata into normative decisions, never perform the effects."""
    event = case["event"]
    data = case["input"]
    if event == "archiveMetadata":
        paths = data["paths"]
        portable = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")
        malformed = data["compressedBytes"] > 268435456 or data["expandedBytes"] > 1073741824
        malformed |= len(paths) > 10000 or data["largestFileBytes"] > 134217728
        malformed |= data["hasSymlink"] or data["hasUndeclaredFile"]
        malformed |= len(paths) != len({p.lower() for p in paths})
        for path in paths:
            malformed |= portable.fullmatch(path) is None
            for segment in path.split("/"):
                malformed |= segment in {".", ".."} or segment.endswith(".")
                malformed |= re.match(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", segment, re.I) is not None
        return {"documentDecision": "reject" if malformed else "metadataAccepted", "executionAllowed": False, "archiveByteVerificationStillRequired": True}
    if event == "updatePermissionExpansion":
        increased = not set(data["newPermissions"]).issubset(data["oldPermissions"])
        return {"candidateState": "awaitingConsent" if increased and not data["consented"] else "staged", "runningPackageHash": data["oldPackageHash"], "coexistingExecutableVersionsAllowed": False}
    if event == "revokeDuringWork":
        return {"admitNewCalls": False, "runningAction": "stopAtSafePoint" if data["grantsReducible"] else "terminateProcess", "deleteProductOutput": False}
    if event == "rollback":
        compatible = data["minCompatibleSchema"] <= data["currentPrivateSchema"] <= data["maxCompatibleSchema"]
        allowed = compatible and not data["targetRevoked"]
        return {"rollbackAllowed": allowed, "packageState": "staged" if allowed else "disabled", "preservePrivateState": True}
    if event == "unknownEffect":
        return {"safeRetryAllowed": data["reconciledNoEffect"] and data["currentAdmissionValid"], "preserveCommandFence": True, "reinstallResetsFence": False}
    if event == "disconnect":
        return {"orderedActions": ["revokeGrants", "invalidateSecretRef", "bestEffortProviderRevocation"], "newCallsAllowed": False, "retainSecretValueInHistory": False}
    if event == "secretProjection":
        # This is an allowlisted metadata projection, never a live credential read.
        return {key: data[key] for key in ("connectionId", "status", "secretRef")}
    raise ValueError("unknown lifecycle oracle event")


class LifecycleContractVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        aggregate = json.loads((ROOT / "fixtures/public/con-12-extension-policy.json").read_text(encoding="utf-8-sig"))
        cls.fixture = aggregate["lifecycle"]

    def test_declared_metadata_and_transition_decisions(self):
        names = set()
        for case in self.fixture["vectors"]:
            with self.subTest(case=case["id"]):
                self.assertNotIn(case["id"], names)
                names.add(case["id"])
                self.assertEqual(lifecycle_decision(case), case["expected"])

    def test_required_lifecycle_scenarios_are_not_runtime_claims(self):
        cases = {case["id"]: case for case in self.fixture["vectors"]}
        self.assertIn("offline", self.fixture["evidenceBoundary"].lower())
        self.assertIn("not", self.fixture["evidenceBoundary"].lower())
        for name in ("archive-traversal", "archive-case-collision", "archive-symlink", "permission-expansion-awaits-consent", "revoke-running-grants-not-reducible", "rollback-incompatible-private-schema", "rollback-revoked-target", "unknown-effect-after-reinstall", "disconnect-local-first", "secret-value-never-projected"):
            self.assertIn(name, cases)
        projected = cases["secret-value-never-projected"]["expected"]
        self.assertNotIn("secretValue", projected)
        self.assertNotIn("fixture-secret-marker", json.dumps(projected))


if __name__ == "__main__":
    unittest.main()
