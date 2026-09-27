# SPDX-License-Identifier: Apache-2.0
"""Independent offline resolution oracle, not a signed targeting runtime."""
import json
from pathlib import Path
import unittest


class PolicyDecisions(unittest.TestCase):
    def test_normative_resolution_vectors(self):
        data = json.loads((Path(__file__).resolve().parents[2] / 'fixtures/public/con-12-extension-policy.json').read_text())['policyDecisions']
        for row in data['limits']:
            self.assertEqual(min(row['compiled'], row['realm'], row['workspace']), row['expected'], row['id'])
        for row in data['presentation']:
            self.assertEqual(next(value for value in (row['user'], row['experiment'], row['default']) if value is not None), row['expected'], row['id'])
        for row in data['paidAdmission']:
            self.assertEqual(row['bundleCurrent'] and row['configuredTariff'] is not None, row['expected'], row['id'])


if __name__ == '__main__':
    unittest.main()
