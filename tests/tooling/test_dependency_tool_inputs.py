# SPDX-License-Identifier: Apache-2.0
"""An effective native tool selection change must invalidate dependency admission."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eng'))
from dependency_admission import input_hashes


class DependencyToolInputs(unittest.TestCase):
    def test_selector_and_validation_changes_require_fresh_admission_hashes(self):
        with tempfile.TemporaryDirectory(prefix='contracts-tool-inputs-') as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            fixtures = {
                'eng/native-toolchain.json': b'{"llvm":{"version":"23.1.5"}}\n',
                'eng/native_toolchain.py': b'# SPDX-License-Identifier: Apache-2.0\nVERSION = "23.1.5"\n',
                'eng/check_toolchain.py': b'# SPDX-License-Identifier: Apache-2.0\nEXPECTED = "11.0.100"\n',
            }
            for name, content in fixtures.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            (root / 'README.md').write_text('Unrelated documentation.\n', encoding='utf-8')
            original = input_hashes(root)
            self.assertEqual(set(original), set(fixtures))
            for name, content in fixtures.items():
                with self.subTest(input=name):
                    path = root / name
                    changed = content.replace(b'23.1.5', b'23.1.6').replace(b'11.0.100', b'11.0.101')
                    path.write_bytes(changed)
                    observed = input_hashes(root)
                    self.assertEqual({key for key in original if original[key] != observed[key]}, {name})
                    self.assertEqual(observed[name], hashlib.sha256(changed).hexdigest())
                    path.write_bytes(content)
            (root / 'eng/native-toolchain.json').unlink()
            self.assertNotEqual(input_hashes(root), original)


if __name__ == '__main__':
    unittest.main()
