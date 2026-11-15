# SPDX-License-Identifier: Apache-2.0
"""Offline qualification refusal cases; synthetic reports never establish native acceptance."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'eng'))
import check_go_dependency_inventory as collector
import dependency_admission as admission
import go_bindings


VERSIONS = {
    'google.golang.org/protobuf': 'v1.36.12', 'connectrpc.com/connect/v2': 'v2.0.2',
    'honnef.co/go/tools': 'v0.8.2', 'golang.org/x/vuln': 'v1.9.0',
    'golang.org/x/exp/typeparams': 'v0.0.0-20261113113407-e3970619a1a4',
    'golang.org/x/telemetry': 'v0.0.0-20261111153349-cdaf7e97dd7b',
    'golang.org/x/tools/go/expect': 'v0.1.1-deprecated',
}
COMMITS = {'golang.org/x/exp/typeparams': 'e3970619a1a4b3f898cbf8651d2ea7ae7541f583',
           'golang.org/x/telemetry': 'cdaf7e97dd7b573969ef84c8c901a29491c0728e'}
CHECKSUM = 'h1:' + 'A' * 43 + '='


def report(root, system):
    native = system.lower()
    main = {go_bindings.GO_MODULE: {'Path': go_bindings.GO_MODULE, 'Main': True}}
    for module in go_bindings.RUNTIME:
        main[module] = {'Path': module, 'Version': VERSIONS[module]}
    tools = {go_bindings.TOOLS_MODULE: {'Path': go_bindings.TOOLS_MODULE, 'Main': True},
             **{module: {'Path': module, 'Version': version} for module, version in VERSIONS.items()}}
    graphs = {'main': collector.module_graph(list(main.values()), go_bindings.GO_MODULE),
              'tools': collector.module_graph(list(tools.values()), go_bindings.TOOLS_MODULE)}

    def package(path, module):
        return {'importPath': path, 'standard': False, 'modulePath': module,
                'moduleVersion': VERSIONS.get(module, '')}

    closures = {}
    for name, path in go_bindings.TOOL_PACKAGES.items():
        module = next(module for module in VERSIONS if path.startswith(module + '/'))
        packages = [package(path, module)]
        if name == 'staticcheck':
            packages.append(package('golang.org/x/exp/typeparams', 'golang.org/x/exp/typeparams'))
        if name == 'govulncheck':
            packages.append(package('golang.org/x/telemetry/internal/counter', 'golang.org/x/telemetry'))
        closures['tool:' + name] = sorted(packages, key=lambda row: row['importPath'])
    closures['owned-packages-and-tests'] = [package(go_bindings.GO_MODULE + '/owned', go_bindings.GO_MODULE)]
    if system == 'Linux':
        closures['owned-packages-and-tests:race'] = copy.deepcopy(closures['owned-packages-and-tests'])
    config = {'GOVERSION': 'go1.27.4', 'GOROOT': 'synthetic-sdk', 'GOOS': native, 'GOARCH': 'amd64',
              'GOHOSTOS': native, 'GOHOSTARCH': 'amd64', 'CGO_ENABLED': '1' if system == 'Linux' else '0',
              'GOAMD64': 'v1', 'GOEXPERIMENT': '', 'GOMOD': str(root / 'go/go.mod'),
              'CC': 'clang' if system == 'Linux' else 'gcc', 'CXX': 'clang++' if system == 'Linux' else 'g++',
              **collector.APPLIED_ENVIRONMENT}
    arguments = [['version'], ['env', '-json', *collector.GO_ENV],
                 *[['list', '-mod=readonly', '-m', '-json', 'all']] * 2, *[['mod', 'graph']] * 2,
                 *[['list', '-mod=readonly', '-deps', '-json', path] for path in go_bindings.TOOL_PACKAGES.values()],
                 ['list', '-mod=readonly', '-deps', '-test', '-json', './...']]
    if system == 'Linux':
        arguments.append(['list', '-mod=readonly', '-race', '-deps', '-test', '-json', './...'])
    snapshot = collector.tree_snapshot(root)
    return {'schema': collector.SCHEMA, 'result': 'passed', 'unchangedSourceAndLocks': True,
            'policy': {'designCommit': admission.GO_QUALIFICATION_DESIGN, 'crossHostQualification': 'not-established'},
            'host': {'system': system, 'goExecutable': 'synthetic-go', 'appliedEnvironment': collector.APPLIED_ENVIRONMENT,
                     'goVersion': f'go version go1.27.4 {native}/amd64', 'configuration': config},
            'source': {**{key: value for key, value in snapshot.items() if key != 'files'},
                       'treeSha256': collector.sha(json.dumps(snapshot, sort_keys=True).encode())},
            'inputs': {name: {'sha256': collector.sha((root / name).read_bytes()),
                             'sha256Lf': collector.sha((root / name).read_bytes().replace(b'\r\n', b'\n'))}
                       for name in collector.INPUTS},
            'selectedGraphs': graphs,
            'moduleRequirements': {name: sorted([[go_bindings.GO_MODULE if name == 'main' else go_bindings.TOOLS_MODULE,
                                                  path + '@' + row['Version']]
                                                 for path, row in graph.items() if row.get('Version')])
                                   for name, graph in graphs.items()},
            'toolPackages': go_bindings.TOOL_PACKAGES, 'packageClosures': closures,
            'classification': collector.classification(graphs, closures),
            'commands': [{'argv': ['synthetic-go', *args], 'cwd': str(root / 'go'), 'exitCode': 0,
                          'stdoutSha256': 'a' * 64, 'stderrSha256': 'b' * 64} for args in arguments]}


class GoQualificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='contracts-go-qualification-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for name in {*admission.GO_CONTROL_INPUTS, *collector.INPUTS, 'go/internal/owned_test.go'}:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'goVersion': 'go1.27.4'}) if name == 'go/toolchain.json'
                            else 'Synthetic offline policy fixture\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], check=True)
        self.reports = {native: report(self.root, system) for native, system in [('windows', 'Windows'), ('linux', 'Linux')]}
        head = self.reports['windows']['source']['head']
        untagged = {}
        for module, (repository, maturity) in admission.GO_UNTAGGED.items():
            version = VERSIONS[module]
            untagged[module] = {'version': version, 'sourceCommit': COMMITS[module], 'checksum': CHECKSUM,
                'queriedAtUtc': '2026-11-15T00:00:00Z', 'repository': 'https://go.googlesource.com/' + repository.split('/')[1],
                'defaultBranch': 'master', 'versionQuery': {'source': f'https://proxy.golang.org/{module}/@v/{version}.info', 'sha256': 'c' * 64},
                'commitQuery': {'source': f'https://api.github.com/repos/{repository}/commits/master', 'sha256': 'd' * 64},
                'maturity': maturity, 'assessment': {'compatibility': 'fixture', 'security': 'fixture', 'licence': 'fixture'}}
        self.policy = {'schemaVersion': 1, 'repository': 'Contracts', 'review': {'goQualification': {'schema': admission.GO_QUALIFICATION_SCHEMA,
            'designCommit': admission.GO_QUALIFICATION_DESIGN, 'sourceCommit': head,
            'inputHashes': admission.go_qualification_inputs(self.root),
            'platforms': {native: {'sourceCommit': head, 'measuredAtUtc': '2026-11-15T00:00:00Z',
                                  'report': {'location': 'host-local synthetic fixture', 'sha256': 'e' * 64},
                                  'summary': admission.go_report_summary(value)} for native, value in self.reports.items()},
            'metadataOnly': ['go:golang.org/x/tools/go/expect@v0.1.1-deprecated'], 'untaggedDependencies': untagged}},
            'closure': {'go:' + module + '@' + VERSIONS[module]: {'integrity': CHECKSUM} for module in admission.GO_UNTAGGED}}

    def test_complete_reference_and_fresh_measurement_pass(self):
        for native, value in self.reports.items():
            with self.subTest(platform=native):
                result = admission.validate_current_go_measurement(self.policy, self.root, value)
                self.assertEqual(native, result['platform'])

    def test_five_lock_hashes_cannot_hide_changed_owned_source_or_build_configuration(self):
        for name in ('go/internal/owned_test.go', 'eng/go_bindings.py'):
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b'changed\n')
            with self.subTest(path=name), self.assertRaisesRegex(ValueError, 'source/configuration inputs changed'):
                admission.validate_go_qualification(self.policy, self.root)
            path.write_bytes(original)

    def test_ignored_go_source_cannot_hide_behind_a_clean_git_status(self):
        (self.root / '.git/info/exclude').write_text('go/ignored_test.go\n', encoding='utf-8')
        (self.root / 'go/ignored_test.go').write_text('package owned\n', encoding='utf-8')
        self.assertFalse(collector.tree_snapshot(self.root)['dirty'])
        with self.assertRaisesRegex(ValueError, 'Ignored or unregistered Go tree inputs'):
            admission.validate_go_qualification(self.policy, self.root)

    def test_missing_platform_unknown_candidate_and_used_candidate_are_refused(self):
        other_repository = copy.deepcopy(self.policy)
        other_repository['repository'] = 'Cloud'
        missing = copy.deepcopy(self.policy)
        del missing['review']['goQualification']['platforms']['linux']
        unknown = copy.deepcopy(self.policy)
        unknown['review']['goQualification']['metadataOnly'].append('go:unknown.invalid/module@v1.0.0')
        used = copy.deepcopy(self.policy)
        classification = used['review']['goQualification']['platforms']['linux']['summary']['classification']
        row = classification['metadataOnly'].pop()
        row['usedIn'] = ['owned-packages-and-tests:race']
        classification['actualDependencies'].append(row)
        invented = copy.deepcopy(self.policy)
        invented['review']['goQualification']['platforms']['windows']['summary']['classification']['namedCandidates'][0]['eligibleForThisHostConfiguration'] = True
        for value in (other_repository, missing, unknown, used, invented):
            with self.subTest(policy=value), self.assertRaises(ValueError):
                admission.validate_go_qualification(value, self.root)

    def test_failed_stale_dirty_or_incomplete_native_reports_are_refused(self):
        cases = []
        for mutation in ('failed', 'head', 'dirty', 'classification', 'tool', 'race', 'command', 'config', 'edge'):
            value = copy.deepcopy(self.reports['linux'])
            if mutation == 'failed': value['result'] = 'failed'
            if mutation == 'head': value['source']['head'] = '0' * 40
            if mutation == 'dirty': value['source']['dirty'] = True
            if mutation == 'classification': value['classification']['actualDependencies'].pop()
            if mutation == 'tool': del value['packageClosures']['tool:staticcheck']
            if mutation == 'race': del value['packageClosures']['owned-packages-and-tests:race']
            if mutation == 'command': value['commands'][-1]['exitCode'] = 1
            if mutation == 'config': value['host']['configuration']['GOEXPERIMENT'] = 'newinliner'
            if mutation == 'edge': value['moduleRequirements']['tools'].pop()
            cases.append((mutation, value))
        for mutation, value in cases:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                admission.validate_current_go_measurement(self.policy, self.root, value)

    def test_two_untagged_dependencies_require_exact_commit_checksum_and_official_evidence(self):
        for mutation in ('name', 'commit', 'checksum', 'branch', 'source', 'maturity', 'assessment'):
            value = copy.deepcopy(self.policy)
            untagged = value['review']['goQualification']['untaggedDependencies']
            row = untagged['golang.org/x/exp/typeparams']
            if mutation == 'name': untagged['golang.org/x/unknown'] = copy.deepcopy(row)
            if mutation == 'commit': row['sourceCommit'] = '0' * 40
            if mutation == 'checksum': row['checksum'] = 'h1:' + 'B' * 43 + '='
            if mutation == 'branch': row['defaultBranch'] = 'feature'
            if mutation == 'source': row['versionQuery']['source'] = 'https://example.invalid/latest'
            if mutation == 'maturity': row['maturity'] = 'stable API'
            if mutation == 'assessment': row['assessment']['security'] = ''
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                admission.validate_go_qualification(value, self.root)

    def test_a_new_unused_pseudo_module_has_no_general_exemption(self):
        value = copy.deepcopy(self.policy)
        value['closure']['go:example.invalid/unused@v0.0.0-20261111153349-123456789abc'] = {'integrity': CHECKSUM}
        with self.assertRaisesRegex(ValueError, 'Unqualified executable/selected Go prerelease'):
            admission.validate_go_qualification(value, self.root)


if __name__ == '__main__':
    unittest.main()
