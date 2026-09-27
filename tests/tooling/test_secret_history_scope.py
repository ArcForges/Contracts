# SPDX-License-Identifier: Apache-2.0
"""The reviewed history includes deleted secrets but excludes unrelated refs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
OPTIONS = ['--full-history', '--diff-filter=tuxdb', 'HEAD']


class SecretHistoryScope(unittest.TestCase):
    def test_workflow_retains_pinned_redacted_full_history_scan(self):
        workflow = (ROOT / '.github/workflows/security.yml').read_text()
        self.assertIn('fetch-depth: 0', workflow)
        self.assertIn('gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f', workflow)
        self.assertIn('git /repo --redact --no-banner --verbose --config /repo/.gitleaks.toml', workflow)
        self.assertIn('--log-opts="' + ' '.join(OPTIONS) + '"', workflow)

    def test_deleted_reviewed_content_remains_visible_without_sibling_branch(self):
        with tempfile.TemporaryDirectory(prefix='secret-history-') as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE, text=True)
            git('init', '-q', '-b', 'reviewed')
            git('config', 'user.name', 'History test')
            git('config', 'user.email', 'history@example.invalid')
            git('config', 'core.autocrlf', 'false')
            def commit(text):
                (root / 'fixture.txt').write_text(text)
                git('add', 'fixture.txt')
                git('-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            commit('synthetic-review-history-marker')
            ancestor = git('rev-parse', 'HEAD').strip()
            commit('safe current content')
            git('switch', '-qc', 'unrelated', ancestor)
            commit('synthetic-unrelated-branch-marker')
            git('switch', '-q', 'reviewed')
            reviewed = git('log', '-p', '-U0', *OPTIONS)
            self.assertIn('+synthetic-review-history-marker', reviewed)
            self.assertNotIn('synthetic-unrelated-branch-marker', reviewed)
            self.assertIn('synthetic-unrelated-branch-marker', git('log', '-p', '-U0', '--full-history', '--all'))


if __name__ == '__main__':
    unittest.main()
