# SPDX-License-Identifier: Apache-2.0
"""Resource admission and semantic checks against the actual Maven candidate."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
import documentation_tools as documentation
from maven_tools import zip_contents


class DocumentationAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"index.html": b"API 1.0.0-ci.1.1", "script.js": b"reviewed script",
                    "ui-kit/ui-kit.min.css": b"@font-face{src:url(font.woff)}body{font-family:system-ui}",
                    "ui-kit/fonts/font.woff": b"excluded font"}
        self.policy = {"fixed": {
            "script.js": {"upstreamSha256": documentation.sha(self.raw["script.js"]),
                          "distributedSha256": documentation.sha(self.raw["script.js"])},
            "ui-kit/ui-kit.min.css": {"upstreamSha256": documentation.sha(self.raw["ui-kit/ui-kit.min.css"]),
                                      "distributedSha256": documentation.sha(b"body{font-family:system-ui}")}},
            "excluded": {"ui-kit/fonts/font.woff": documentation.sha(b"excluded font")},
            "modules": {"fixture": {"pages": {"index.html": documentation.sha(b"API {version}")}}},
            "fontTransform": {"declarations": 1}}

    def test_known_transform_retains_api_and_uses_system_fonts(self):
        result = documentation.admit(self.raw, "fixture", "1.0.0-ci.1.1", self.policy)
        self.assertNotIn("ui-kit/fonts/font.woff", result)
        self.assertEqual(result["ui-kit/ui-kit.min.css"], b"body{font-family:system-ui}")
        self.assertEqual(result["index.html"], b"API 1.0.0-ci.1.1")
        self.raw["index.html"] = b"API 1.0.0-ci.999.2"
        documentation.admit(self.raw, "fixture", "1.0.0-ci.999.2", self.policy)

    def test_unknown_missing_and_changed_resources_fail(self):
        changes = [lambda d: d.update({"extra.js": b"unreviewed"}), lambda d: d.pop("index.html"),
                   lambda d: d.update({"script.js": b"changed code"}),
                   lambda d: d.update({"index.html": b"incomplete API 1.0.0-ci.1.1"}),
                   lambda d: d.update({"ui-kit/fonts/font.woff": b"new font"})]
        for change in changes:
            with self.subTest(change=change):
                raw = copy.deepcopy(self.raw)
                change(raw)
                with self.assertRaises(ValueError):
                    documentation.admit(raw, "fixture", "1.0.0-ci.1.1", self.policy)

    def test_distinct_npm_names_cannot_share_a_normalized_record_id(self):
        # object-assign and object.assign are different MIT implementations.
        # A punctuation-normalized slug must never discard either obligation.
        policy = {"components": [{"name": "object-assign", "version": "4.1.1", "record": "same-r1"},
                                 {"name": "object.assign", "version": "4.1.7", "record": "same-r1"}]}
        with self.assertRaisesRegex(ValueError, "duplicate provenance IDs"):
            documentation.verify_components(policy, {})


class DocumentationArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        directory = cls.root / "artifacts/packages"
        cls.manifest = json.loads((directory / "manifest.json").read_bytes())
        bundle = next(row for row in cls.manifest["files"] if row["kind"] == "maven")
        cls.files = zip_contents((directory / bundle["name"]).read_bytes())

    def fixture(self, module):
        name = f"io/github/arcforges/{module}/{self.manifest.get('mavenVersion', self.manifest['version'])}/{module}-{self.manifest.get('mavenVersion', self.manifest['version'])}-javadoc.jar"
        return self.files[name], zip_contents(self.files[name])

    def test_every_actual_archive_has_closed_members_full_notices_and_public_api(self):
        for module in documentation.MODULES:
            with self.subTest(module=module):
                archive, docs = self.fixture(module)
                receipt = documentation.verify(docs, module, self.manifest, archive)
                self.assertEqual(receipt["archiveSha256"], hashlib.sha256(archive).hexdigest())
                self.assertEqual(set(receipt["members"]), set(docs))
                self.assertGreater(len(receipt["recordIds"]), 80)
                self.assertNotIn(b"@font-face", docs["ui-kit/ui-kit.min.css"])

    def test_actual_archive_resource_mutations_fail_semantic_checks(self):
        archive, original = self.fixture("contract-fixtures")
        changes = [lambda d: d.update({"script.js": b"GPL replacement"}),
                   lambda d: d.update({"ui-kit/fonts/extra.woff2": b"font"}),
                   lambda d: d.update({"scripts/main.js": d["scripts/main.js"] + b"/* changed */"}),
                   lambda d: d.pop("index.html"),
                   lambda d: d.update({"NOTICE": d["NOTICE"].replace(b"webpack", b"missing", 1)}),
                   lambda d: d.update({"META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\nExtra: changed\n\n"})]
        for change in changes:
            with self.subTest(change=change):
                docs = copy.deepcopy(original)
                change(docs)
                with self.assertRaises(ValueError):
                    documentation.verify(docs, "contract-fixtures", self.manifest, archive)


if __name__ == "__main__":
    unittest.main()
