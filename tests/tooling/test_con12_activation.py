# SPDX-License-Identifier: Apache-2.0
"""Offline activation decision oracle; readiness inputs are symbolic attestations."""
import json
from pathlib import Path
import unittest


class ActivationBoundary(unittest.TestCase):
    def test_candidate_refusal_keeps_current_configuration(self):
        fixture = json.loads((Path(__file__).resolve().parents[2] / 'fixtures/internal/con-12-configuration.json').read_text())['activation']
        self.assertIn('not provider validation', fixture['evidenceBoundary'])
        for row in fixture['vectors']:
            value = row['input']
            activate = (all(value[key] == 'verified' for key in ('commercialCredential', 'modelCredential', 'signature'))
                        and value['distinctApproval'] and value['replicasReady'])
            with self.subTest(case=row['id']):
                self.assertEqual(row['expected'], {'activate': activate, 'servingVersion': value['candidateVersion'] if activate else value['currentVersion']})


if __name__ == '__main__':
    unittest.main()
