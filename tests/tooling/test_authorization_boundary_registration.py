# SPDX-License-Identifier: Apache-2.0
"""Register the owned GOV.16 assertions with existing offline tooling discovery."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


class AuthorizationBoundaryRegistration(unittest.TestCase):
    def test_owned_assertions_and_build_evidence(self):
        for command in [
            ['-m', 'unittest', 'discover', '-s', 'tests/AuthorizationPolicyTests', '-v'],
            ['tests/AuthorizationPolicyTests/assertions.py', '--report', 'artifacts/evidence/authorization-boundaries.json'],
        ]:
            result = subprocess.run([sys.executable, *command], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
