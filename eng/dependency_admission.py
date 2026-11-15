# SPDX-License-Identifier: Apache-2.0
"""Check reviewed Contracts dependency inputs without restoring or contacting feeds."""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'eng/policy/dependency-policy.json'
CHECKS = {'compilation', 'aot-trim', 'compatibility', 'licence-provenance', 'security-sbom',
          'runtime-performance-migration', 'framework-runtime-posture'}
ALLOWED = {'Apache-2.0', 'MIT', 'BSD-2-Clause', 'BSD-3-Clause', '(Apache-2.0 AND BSD-3-Clause)', 'CDDL-1.1'}
# AFV2-ENV-01: whole cohort 1.0.0-ci.150.1, DesktopPlatform main f208d915, publication run 43678526078.
# 1.0.0-ci.124.1 is a rolled-back version and is never admitted.
BUILD_POLICY_VERSION = '1.0.0-ci.150.1'
BUILD_POLICY_KEY = 'nuget:arcforges.build.policy@' + BUILD_POLICY_VERSION
BUILD_POLICY_SCOPE = ('Exact build-only source-link policy engine for the non-packable Contracts ArchitectureTests host; '
                      'direct reference only, PrivateAssets=all, never a product/runtime or public package dependency.')
ARCHITECTURE_TEST_PROJECT = 'tests/ArchitectureTests/ArcForges.Contracts.ArchitectureTests.csproj'
ARCHITECTURE_TEST_LOCK = 'tests/ArchitectureTests/packages.lock.json'


def reject_unless(condition, reason):
    if not condition:
        raise ValueError(reason)


def pinned(version):
    reject_unless(isinstance(version, str) and re.fullmatch(r'\d+(?:\.\d+)+(?:[-.][A-Za-z0-9.-]+)?', version)
                  and 'SNAPSHOT' not in version, 'Floating or mutable selector: ' + str(version))


GO_SUMS = ('go/go.sum', 'go/tools/go.sum')
GO_VERSION = re.compile(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+incompatible)?')
GO_PUBLISHER = {'module': 'github.com/ArcForges/Contracts/go', 'tagPrefix': 'go/v', 'proxy': 'https://proxy.golang.org',
                'checksumDatabase': 'https://sum.golang.org', 'credential': 'github-token-contents-write'}
GO_QUALIFICATION_SCHEMA = 'arcforges.contracts.go-qualification.v1'
GO_QUALIFICATION_DESIGN = '2296e2fe37ad9ad1f7b65be871fea1f0b39ce7ad'
GO_UNTAGGED = {
    'golang.org/x/exp/typeparams': ('golang/exp', 'experimental; no compatibility promise'),
    'golang.org/x/telemetry': ('golang/telemetry', 'no API compatibility promise'),
}
GO_CONTROL_INPUTS = frozenset({
    '.python-version', 'global.json', 'eng/contracts.py', 'eng/go_bindings.py',
    'eng/check_go_dependency_inventory.py', 'eng/dependency_admission.py', 'eng/verify_steps.py',
    'eng/check_toolchain.py', 'eng/native_toolchain.py', 'eng/native-toolchain.json',
    'eng/package_catalog.py', 'eng/contract-packages.json',
})


def go_qualification_inputs(root):
    """Bind owned Go sources/tests, embeds and every checked-in invocation/configuration selector.

    The five module inputs alone cannot bind test build tags or newly imported packages.
    Policy/receipt documents are deliberately outside this fingerprint to avoid a source-commit cycle.
    """
    paths = [p for p in tracked(root) if p.startswith(('go/', '.github/workflows/')) or p in GO_CONTROL_INPUTS]
    reject_unless(GO_CONTROL_INPUTS <= set(paths), 'Incomplete Go qualification control inputs')
    present = {p.relative_to(root).as_posix() for p in (root / 'go').rglob('*') if p.is_file() or p.is_symlink()}
    reject_unless(present <= set(paths), 'Ignored or unregistered Go tree inputs cannot use a qualification reference')
    result = {}
    for name in paths:
        path = root / name
        reject_unless(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
                      'Go qualification input is missing, linked or outside the checkout: ' + name)
        result[name] = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    return result


def _go_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _go_fields(value, names, label):
    reject_unless(isinstance(value, dict) and set(value) == set(names.split()), 'Invalid Go ' + label + ' fields')


def _go_timestamp(value):
    reject_unless(isinstance(value, str), 'Go evidence requires an explicit UTC lookup time')
    parsed = datetime.fromisoformat(value.removesuffix('Z') + '+00:00' if value.endswith('Z') else value)
    reject_unless(parsed.utcoffset() == timedelta(0), 'Go evidence requires an explicit UTC lookup time')


def _go_key(row):
    reject_unless(isinstance(row, dict) and isinstance(row.get('path'), str)
                  and GO_VERSION.fullmatch(row.get('version', '')) is not None, 'Invalid Go classification identity')
    return 'go:' + row['path'] + '@' + row['version']


def go_report_summary(report):
    """Validate one collector result and derive the portable reviewed reference; never trust its classifications."""
    import check_go_dependency_inventory as collector
    import go_bindings
    reject_unless(report.get('schema') == collector.SCHEMA and report.get('result') == 'passed'
                  and report.get('unchangedSourceAndLocks') is True, 'Missing or failing current Go measurement')
    reject_unless(report.get('policy') == {'designCommit': GO_QUALIFICATION_DESIGN,
                  'crossHostQualification': 'not-established'}, 'Wrong Go measurement policy or invented host qualification')
    host = report['host']
    system = host['system']
    reject_unless(system in {'Windows', 'Linux'}, 'Go qualification supports only native Windows/Linux')
    native = system.lower()
    config = host['configuration']
    reject_unless(config.get('GOOS') == config.get('GOHOSTOS') == native
                  and config.get('GOARCH') == config.get('GOHOSTARCH') == 'amd64'
                  and config.get('GOAMD64') == 'v1' and config.get('GOEXPERIMENT') == '',
                  'Go measurement is not the existing native/default build configuration')
    reject_unless(host.get('appliedEnvironment') == collector.APPLIED_ENVIRONMENT
                  and all(config.get(key) == value for key, value in collector.APPLIED_ENVIRONMENT.items()
                          if key != 'GOTELEMETRY'), 'Wrong Go measurement query environment')
    reject_unless(config.get('CGO_ENABLED') == ('1' if system == 'Linux' else '0'), 'Unexpected Go cgo/race configuration')
    if system == 'Linux':
        reject_unless(config.get('CC') == 'clang' and config.get('CXX') == 'clang++', 'Go cgo must use the selected native LLVM compiler')
    reject_unless(host.get('goVersion') == f"go version {config.get('GOVERSION')} {native}/amd64",
                  'Inconsistent Go compiler identity')
    graphs = report['selectedGraphs']
    reject_unless(set(graphs) == {'main', 'tools'}, 'Both exact Contracts Go graphs are required')
    for name, identity in {'main': go_bindings.GO_MODULE, 'tools': go_bindings.TOOLS_MODULE}.items():
        reject_unless(collector.module_graph(list(graphs[name].values()), identity) == graphs[name],
                      'Go selected graph is not canonical')
    requirements = report['moduleRequirements']
    reject_unless(set(requirements) == set(graphs), 'Missing complete upstream Go requirement graph')
    for name, edges in requirements.items():
        reject_unless(isinstance(edges, list) and bool(edges) and all(isinstance(edge, list) and len(edge) == 2
                      and all(isinstance(node, str) and node for node in edge) for edge in edges)
                      and edges == sorted(edges) and len({tuple(edge) for edge in edges}) == len(edges),
                      'Invalid upstream Go requirement edges: ' + name)
        root_module = go_bindings.GO_MODULE if name == 'main' else go_bindings.TOOLS_MODULE
        reject_unless(any(edge[0] == root_module for edge in edges), 'Upstream Go graph lacks its Contracts root')
    expected = {'tool:' + name for name in go_bindings.TOOL_PACKAGES} | {'owned-packages-and-tests'}
    if system == 'Linux':
        expected.add('owned-packages-and-tests:race')
    closures = report['packageClosures']
    reject_unless(report.get('toolPackages') == go_bindings.TOOL_PACKAGES and set(closures) == expected,
                  'Missing or extra declared tool/owned-test Go closure')
    for context, packages in closures.items():
        graph = graphs['tools' if context.startswith('tool:') else 'main']
        records = []
        for package in packages:
            reject_unless(isinstance(package, dict) and set(package) <=
                          {'importPath', 'standard', 'modulePath', 'moduleVersion', 'imports', 'forTest'},
                          'Unrecognized measured Go package fields')
            record = {'ImportPath': package['importPath'], 'Standard': package['standard']}
            if 'modulePath' in package:
                record['Module'] = {'Path': package['modulePath'], 'Version': package['moduleVersion']}
            if 'imports' in package:
                record['Imports'] = package['imports']
            if 'forTest' in package:
                record['ForTest'] = package['forTest']
            records.append(record)
        reject_unless(collector.package_closure(records, graph) == packages, 'Go package closure is not canonical')
        target = go_bindings.TOOL_PACKAGES[context.removeprefix('tool:')] if context.startswith('tool:') else None
        reject_unless(any(package['importPath'] == target if target else package.get('modulePath') == go_bindings.GO_MODULE
                          for package in packages), 'Go closure is missing its declared tool or owned module')
    classification = collector.classification(graphs, closures)
    reject_unless(report.get('classification') == classification, 'Measured Go classification disagrees with actual packages')
    expected_commands = [['version'], ['env', '-json', *collector.GO_ENV]]
    expected_commands += [['list', '-mod=readonly', '-m', '-json', 'all']] * 2
    expected_commands += [['mod', 'graph']] * 2
    expected_commands += [['list', '-mod=readonly', '-deps', '-json', package]
                          for package in go_bindings.TOOL_PACKAGES.values()]
    expected_commands.append(['list', '-mod=readonly', '-deps', '-test', '-json', './...'])
    if system == 'Linux':
        expected_commands.append(['list', '-mod=readonly', '-race', '-deps', '-test', '-json', './...'])
    commands = report['commands']
    reject_unless(len(commands) == len(expected_commands), 'Incomplete Go query command evidence')
    for command, arguments in zip(commands, expected_commands, strict=True):
        reject_unless(command.get('argv') == [host['goExecutable'], *arguments] and command.get('exitCode') == 0
                      and all(re.fullmatch('[0-9a-f]{64}', command.get(key, ''))
                              for key in ('stdoutSha256', 'stderrSha256')), 'Missing or failing Go query evidence')
    # Absolute cache/source paths in go list -m are venue-specific; only the selected
    # identities are compared. Full upstream edges and complete package closures remain bound.
    selected = {name: {path: {'version': row.get('Version', ''), 'main': row.get('Main') is True}
                       for path, row in graph.items()} for name, graph in graphs.items()}
    excluded = {'GOROOT', 'GOMOD', 'GOTELEMETRY'} | ({'CC', 'CXX'} if system == 'Windows' else set())
    return {'configuration': {key: config[key] for key in collector.GO_ENV if key not in excluded},
            'selectedGraphsSha256': _go_digest(selected), 'moduleRequirementsSha256': _go_digest(requirements),
            'packageClosuresSha256': _go_digest(closures), 'classification': classification}


def validate_go_qualification(policy, root):
    """Check the reviewed two-host reference without treating it as fresh native execution."""
    import check_go_dependency_inventory as collector
    import go_bindings
    reject_unless(policy.get('schemaVersion') == 1 and policy.get('repository') == 'Contracts',
                  'Go qualification applies only to the Contracts dependency policy')
    qualification = policy['review'].get('goQualification')
    _go_fields(qualification, 'schema designCommit sourceCommit inputHashes platforms metadataOnly untaggedDependencies',
               'qualification')
    reject_unless(qualification['schema'] == GO_QUALIFICATION_SCHEMA and qualification['designCommit'] == GO_QUALIFICATION_DESIGN,
                  'Wrong Go qualification authority')
    baseline = qualification['sourceCommit']
    reject_unless(isinstance(baseline, str) and re.fullmatch('[0-9a-f]{40}', baseline), 'Go baseline must be a full commit')
    fingerprint = go_qualification_inputs(root)
    reject_unless(qualification['inputHashes'] == fingerprint, 'Go qualification source/configuration inputs changed')
    baseline_paths = set(subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', '--name-only', baseline], text=True).splitlines())
    relevant = {p for p in baseline_paths if p.startswith(('go/', '.github/workflows/')) or p in GO_CONTROL_INPUTS}
    reject_unless(relevant == set(fingerprint), 'Go baseline has different source/configuration input membership')
    subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', baseline, 'HEAD'], check=True, capture_output=True)
    for name, digest in fingerprint.items():
        data = subprocess.check_output(['git', '-C', str(root), 'show', baseline + ':' + name])
        reject_unless(hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest() == digest,
                      'Go qualification source baseline differs: ' + name)
    platforms = qualification['platforms']
    reject_unless(isinstance(platforms, dict) and set(platforms) == {'windows', 'linux'},
                  'Both native platform Go reference measurements are required')
    selected, used = set(), set()
    for native, reference in platforms.items():
        _go_fields(reference, 'sourceCommit measuredAtUtc report summary', 'platform reference')
        reject_unless(reference['sourceCommit'] == baseline, 'Go references were not measured at the same source commit')
        _go_timestamp(reference['measuredAtUtc'])
        _go_fields(reference['report'], 'location sha256', 'host report reference')
        reject_unless(isinstance(reference['report']['location'], str) and reference['report']['location']
                      and re.fullmatch('[0-9a-f]{64}', reference['report']['sha256']), 'Missing host-local Go evidence reference')
        summary = reference['summary']
        _go_fields(summary, 'configuration selectedGraphsSha256 moduleRequirementsSha256 packageClosuresSha256 classification',
                   'portable summary')
        reject_unless(all(re.fullmatch('[0-9a-f]{64}', summary[key]) for key in
                      ('selectedGraphsSha256', 'moduleRequirementsSha256', 'packageClosuresSha256')), 'Missing Go graph/closure digest')
        config = summary['configuration']
        expected_go = json.loads((root / 'go/toolchain.json').read_text(encoding='utf-8'))['goVersion']
        expected_config = {'GOVERSION': expected_go, 'GOOS': native, 'GOARCH': 'amd64', 'GOHOSTOS': native,
                           'GOHOSTARCH': 'amd64', 'CGO_ENABLED': '1' if native == 'linux' else '0', 'GOAMD64': 'v1',
                           'GOEXPERIMENT': '', 'GOFLAGS': '-mod=readonly', 'GOWORK': 'off', 'GOTOOLCHAIN': 'local'}
        if native == 'linux':
            expected_config.update(CC='clang', CXX='clang++')
        reject_unless(config == expected_config, 'Go reference changed the applicable platform/build configuration')
        classification = summary['classification']
        _go_fields(classification, 'actualDependencies metadataOnly namedCandidates', 'classification')
        reject_unless({row['path'] for row in classification['namedCandidates']} == collector.METADATA_CANDIDATES
                      and len(classification['namedCandidates']) == len(collector.METADATA_CANDIDATES),
                      'Go metadata candidate list differs from the nine approved names')
        rows = [*classification['actualDependencies'], *classification['metadataOnly']]
        keys = [_go_key(row) for row in rows]
        reject_unless(len(keys) == len(set(keys)), 'Duplicate Go selected dependency identity')
        contexts = {'tool:' + name for name in go_bindings.TOOL_PACKAGES} | {'owned-packages-and-tests'}
        if native == 'linux':
            contexts.add('owned-packages-and-tests:race')
        for row in rows:
            reject_unless(row.get('selectedIn') and set(row['selectedIn']) <= {'main', 'tools'}
                          and isinstance(row.get('usedIn'), list) and set(row['usedIn']) <= contexts,
                          'Go classification has an unknown scope')
        # Reconstruct just the selected/used identities to reject inconsistent
        # summary flags and named-candidate claims without importing host receipts.
        selected_graphs = {'main': {}, 'tools': {}}
        used_packages = {context: [] for context in contexts}
        for row in rows:
            for name in row['selectedIn']:
                previous = selected_graphs[name].setdefault(row['path'], {'Version': row['version']})
                reject_unless(previous['Version'] == row['version'], 'Conflicting selected Go versions in a summary')
            for context in row['usedIn']:
                used_packages[context].append({'modulePath': row['path'], 'moduleVersion': row['version']})
        reject_unless(collector.classification(selected_graphs, used_packages) == classification,
                      'Go reference classification or candidate flags are inconsistent')
        selected.update(keys)
        used.update(_go_key(row) for row in classification['actualDependencies'])
        reject_unless(all(row['usedIn'] for row in classification['actualDependencies'])
                      and all(not row['usedIn'] for row in classification['metadataOnly']), 'Inconsistent Go usage classification')
    used_paths = {key[3:].rsplit('@', 1)[0] for key in used}
    eligible = sorted(key for key in selected if key[3:].rsplit('@', 1)[0] in collector.METADATA_CANDIDATES
                      and key[3:].rsplit('@', 1)[0] not in used_paths)
    reject_unless(qualification['metadataOnly'] == eligible, 'Go metadata qualification includes a used or unapproved module')
    untagged = qualification['untaggedDependencies']
    reject_unless(isinstance(untagged, dict) and set(untagged) == set(GO_UNTAGGED), 'Only the two named untagged Go modules qualify')
    for module, (repository, maturity) in GO_UNTAGGED.items():
        row = untagged[module]
        _go_fields(row, 'version sourceCommit checksum queriedAtUtc repository defaultBranch versionQuery commitQuery maturity assessment',
                   'untagged dependency')
        match = re.fullmatch(r'v0\.0\.0-(\d{14})-([0-9a-f]{12})', row['version'])
        reject_unless(match is not None and re.fullmatch('[0-9a-f]{40}', row['sourceCommit'])
                      and row['sourceCommit'].startswith(match[2]), 'Untyped or floating Go pseudo-version/source identity')
        datetime.strptime(match[1], '%Y%m%d%H%M%S')
        _go_timestamp(row['queriedAtUtc'])
        reject_unless(row['repository'] == 'https://go.googlesource.com/' + repository.split('/')[1]
                      and row['defaultBranch'] == 'master' and row['maturity'] == maturity,
                      'Wrong ordinary upstream branch or missing maturity disclosure')
        _go_fields(row['versionQuery'], 'source sha256', 'proxy evidence')
        _go_fields(row['commitQuery'], 'source sha256', 'default-branch evidence')
        reject_unless(row['versionQuery']['source'] == f'https://proxy.golang.org/{module}/@v/{row["version"]}.info'
                      and row['commitQuery']['source'] == f'https://api.github.com/repos/{repository}/commits/master'
                      and all(re.fullmatch('[0-9a-f]{64}', row[key]['sha256']) for key in ('versionQuery', 'commitQuery')),
                      'Missing exact official Go proxy/default-branch evidence')
        _go_fields(row['assessment'], 'compatibility security licence', 'untagged assessment')
        reject_unless(all(isinstance(value, str) and value for value in row['assessment'].values()),
                      'Missing untagged Go dependency qualification assessment')
        key = 'go:' + module + '@' + row['version']
        reject_unless(re.fullmatch(r'h1:[A-Za-z0-9+/]{43}=', row['checksum']) and policy['closure'].get(key, {}).get('integrity') == row['checksum'],
                      'Untagged Go checksum does not match the complete admitted archive')
        for reference in platforms.values():
            matching = [item for item in reference['summary']['classification']['actualDependencies'] if _go_key(item) == key]
            reject_unless(len(matching) == 1 and matching[0]['selectedIn'] == ['tools']
                          and matching[0]['usedIn'] and all(name.startswith('tool:') for name in matching[0]['usedIn']),
                          'Untagged Go qualification is restricted to actual indirect tool implementation dependencies')
    allowed = set(eligible) | {'go:' + path + '@' + row['version'] for path, row in untagged.items()}
    for key in selected | {key for key in policy['closure'] if key.startswith('go:')}:
        reject_unless(key in allowed or stable_dependency(key), 'Unqualified executable/selected Go prerelease dependency: ' + key)
    return qualification


def validate_current_go_measurement(policy, root, report):
    """Called immediately after the existing native collector; no stored report substitutes for this execution."""
    import check_go_dependency_inventory as collector
    qualification = validate_go_qualification(policy, root)
    current = collector.tree_snapshot(root)
    source = report.get('source', {})
    reject_unless(not current['dirty'] and source.get('dirty') is False and source.get('head') == current['head']
                  and source.get('indexSha256') == current['indexSha256']
                  and source.get('statusSha256') == current['statusSha256']
                  and source.get('treeSha256') == collector.sha(json.dumps(current, sort_keys=True).encode()),
                  'Go measurement is stale or does not bind the clean current source commit')
    reject_unless(report.get('inputs') == {name: {'sha256': collector.sha((root / name).read_bytes()),
                  'sha256Lf': collector.sha((root / name).read_bytes().replace(b'\r\n', b'\n'))}
                  for name in collector.INPUTS}, 'Go measurement locks/toolchain differ from current inputs')
    summary = go_report_summary(report)
    native = report['host']['system'].lower()
    reject_unless(summary == qualification['platforms'][native]['summary'],
                  'Current native Go graph, upstream edges, actual closure or classification differs from its reviewed reference')
    return {'result': 'passed', 'platform': native, 'sourceCommit': current['head'],
            'metadataOnly': qualification['metadataOnly'], 'scope': 'Contracts Go qualification only'}


def go_sum_rows(root, path):
    """(module, version, h1 hash) of each module archive go.sum verifies; go.mod-only lines carry no code."""
    rows = []
    for line in (root / path).read_text(encoding='utf-8').splitlines():
        parts = line.split()
        reject_unless(len(parts) == 3 and parts[2].startswith('h1:'), 'Malformed go.sum line in ' + path)
        module, version, digest = parts
        if version.endswith('/go.mod'):
            continue
        reject_unless(GO_VERSION.fullmatch(version) is not None, 'Floating or invalid Go module version: ' + line)
        rows.append((module, version, digest))
    return rows


def go_tool_only(root):
    """Admitted Go archives that only the never-published tools module (go/tools) verifies: build tooling, outside
    the stable product closure, as the Build.Policy package is."""
    tools = {f'go:{module}@{version}' for module, version, _ in go_sum_rows(root, 'go/tools/go.sum')} \
        if (root / 'go/tools/go.sum').is_file() else set()
    runtime = {f'go:{module}@{version}' for module, version, _ in go_sum_rows(root, 'go/go.sum')} \
        if (root / 'go/go.sum').is_file() else set()
    return tools - runtime


def stable_dependency(key):
    if key == BUILD_POLICY_KEY:
        return True  # Test/build-only tooling is excluded from the stable product/runtime closure.
    if key == 'maven:com.google.guava:listenablefuture:9999.0-empty-to-avoid-conflict-with-guava':
        return True  # Released empty compatibility artifact, not a preview selector.
    if key.startswith('maven:'):
        return re.fullmatch(r'\d+(?:\.\d+)*(?:(?:-|\.)(?:jre|android|GA|Final|RELEASE))?',
                            key.rsplit(':', 1)[1], re.I) is not None
    return '-' not in key.rsplit('@', 1)[1]


def tracked(root):
    return sorted(set(subprocess.check_output(['git', '-C', str(root), 'ls-files', '--cached',
                                             '--others', '--exclude-standard'], text=True).splitlines()))


def input_paths(root):
    return [p for p in tracked(root) if p.endswith(('.csproj', '.props', '.targets', '.gradle.kts',
                '.lockfile', 'packages.lock.json', 'package.json', 'package-lock.json', 'verification-metadata.xml'))
            or p in {'global.json', 'NuGet.config', '.npmrc', '.node-version', '.java-version', '.python-version',
                     'gradle/libs.versions.toml', 'gradle/verification-metadata.xml',
                     'gradle/wrapper/gradle-wrapper.properties', 'eng/toolchain.json', 'eng/contract-packages.json', 'eng/policy/contract-access.json',
                     'go/go.mod', 'go/go.sum', 'go/tools/go.mod', 'go/tools/go.sum', 'go/toolchain.json'}
            or p.startswith(('eng/provenance/records/', 'eng/provenance/artifact-profiles/', 'eng/provenance/retirements/'))]


def input_hashes(root):
    return {p: hashlib.sha256((root / p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in input_paths(root)}


def inventory(root):
    result = {}
    verification = {}
    for metadata in [p for p in input_paths(root) if p.endswith('verification-metadata.xml')]:
        for component in ET.parse(root / metadata).findall('.//{*}component'):
            coordinate = ':'.join(component.get(k) for k in ['group', 'name', 'version'])
            artifacts = verification.setdefault(coordinate, {})
            for artifact in component.findall('./{*}artifact'):
                digests = sorted(e.get('value') for e in artifact.findall('./{*}sha256'))
                reject_unless(digests and all(re.fullmatch('[0-9a-f]{64}', h) for h in digests), 'Missing Maven artifact checksum')
                name = artifact.get('name')
                reject_unless(name not in artifacts or artifacts[name] == digests, 'Conflicting Maven checksum: ' + coordinate)
                artifacts[name] = digests
    def admit(key, integrity):
        reject_unless(key not in result or result[key] == integrity, 'Mutable version in locks: ' + key)
        reject_unless(integrity, 'Missing locked integrity: ' + key)
        result[key] = integrity
    for path in input_paths(root):
        if path.endswith('packages.lock.json'):
            for graph in json.loads((root / path).read_text())['dependencies'].values():
                for name, row in graph.items():
                    if row['type'].lower() != 'project':
                        pinned(row['resolved'])
                        admit('nuget:' + name.lower() + '@' + row['resolved'], row.get('contentHash'))
        elif path == 'package-lock.json':
            for name, row in json.loads((root / path).read_text())['packages'].items():
                if 'node_modules/' not in name or row.get('link'):
                    continue
                pinned(row['version'])
                reject_unless(row.get('resolved', '').startswith('https://registry.npmjs.org/'), 'Untrusted npm feed')
                admit('npm:' + name.rsplit('node_modules/', 1)[1] + '@' + row['version'], row.get('integrity'))
        elif path in GO_SUMS:
            # AF-CTR-01: every Go module archive that go.sum verifies, keyed by its exact module version.
            for module, version, digest in go_sum_rows(root, path):
                admit('go:' + module + '@' + version, digest)
        elif path.endswith('.lockfile'):
            for line in (root / path).read_text().splitlines():
                if not line.startswith('#') and ':' in line:
                    coordinate = line.split('=')[0]
                    pinned(coordinate.rsplit(':', 1)[1])
                    reject_unless(coordinate in verification, 'Unverified Maven coordinate: ' + coordinate)
                    admit('maven:' + coordinate, verification[coordinate])
    return result


def validate(policy, actual, stable=False, tool_only=frozenset()):
    reject_unless(policy['schemaVersion'] == 1 and policy['repository'] == 'Contracts', 'Wrong owner policy')
    reject_unless(set(actual) == set(policy['closure']), 'Unadmitted dependency closure')
    for key, digest in actual.items():
        entry = policy['closure'][key]
        reject_unless(entry['integrity'] == digest, 'Mutable admitted version: ' + key)
        if key == BUILD_POLICY_KEY:
            reject_unless(entry['licence'] == 'AGPL-3.0-only' and entry.get('scope') == BUILD_POLICY_SCOPE,
                          'Build.Policy AGPL exception is not the exact ArchitectureTests-only boundary')
        else:
            reject_unless(entry['licence'] in ALLOWED, 'Forbidden or unreviewed licence: ' + key)
        reject_unless(entry['evidence'] and all(re.fullmatch('[0-9a-f]{64}', e['sha256']) and e['source']
                                              for e in entry['evidence']), 'Missing exact source evidence')
        if stable and key not in tool_only:
            reject_unless(stable_dependency(key), 'Stable closure contains prerelease: ' + key)
    review = policy['review']
    reject_unless(review['owner'] and review['reviewer'] and review['maintenanceAssessment'], 'Missing review')
    reject_unless(re.fullmatch('[0-9a-f]{40}', review['baselineCommit']), 'Floating source tag')
    reject_unless(review['inputHashes'] == policy['inputHashes'], 'Upgrade receipt does not bind inputs')
    reject_unless(set(review['checks']) == CHECKS and all(review['checks'].values()), 'Missing upgrade evidence')
    reject_unless(policy['publisher'] == {'repository': 'ArcForges/Contracts', 'workflow': 'ci.yml',
                  'nuget': {'feed': 'https://api.nuget.org/v3/index.json', 'environment': 'nuget', 'credential': 'github-oidc'},
                  'npm': {'feed': 'https://registry.npmjs.org/', 'environment': 'npm', 'credential': 'github-oidc'},
                  'maven': {'environment': 'maven-central', 'credential': 'central-token-and-formal-pgp'},
                  'go': GO_PUBLISHER},
                  'Wrong publisher or feed')
    reject_unless(policy['publicInternalGate'] == 'eng/policy/contract-access.json', 'Public/internal guard missing')


def validate_architecture_policy_boundary(root, actual):
    """Keep Build.Policy out of every closure except the exact private test/build host."""
    host = root / ARCHITECTURE_TEST_PROJECT
    has_host = host.is_file()
    matches = [key for key in actual if key.lower().startswith('nuget:arcforges.build.policy@')]
    if not has_host:
        reject_unless(not matches, 'Build.Policy is admitted without its ArchitectureTests-only host')
        return

    reject_unless(len(matches) == 1 and matches[0] == BUILD_POLICY_KEY,
                  'Only ArcForges.Build.Policy ' + BUILD_POLICY_VERSION + ' is admitted')
    pin_path = root / 'Directory.Packages.props'
    reject_unless(pin_path.is_file(), 'Build.Policy exact central version pin is missing')
    pins = [item for item in ET.parse(pin_path).getroot().iter()
            if item.tag.split('}')[-1] == 'PackageVersion'
            and (item.get('Include') or '').casefold() == 'arcforges.build.policy']
    reject_unless(len(pins) == 1 and pins[0].get('Include') == 'ArcForges.Build.Policy'
                  and pins[0].get('Version') == BUILD_POLICY_VERSION,
                  'Build.Policy must have exactly one exact central pin')

    project = ET.parse(host).getroot()
    def values(name):
        return [element.text or '' for element in project.iter() if element.tag.split('}')[-1] == name]
    reject_unless(values('TargetFramework') == ['net11.0'] and values('OutputType') == ['Exe']
                  and values('IsTestProject') == ['true'] and values('IsPackable') == ['false']
                  and values('PackageLicenseExpression') == ['Apache-2.0']
                  and values('LicenceBoundary') == ['Apache'],
                  'Build.Policy host must retain Apache metadata as a non-packable ArchitectureTests executable')
    references = [item for item in project.iter() if item.tag.split('}')[-1] == 'PackageReference'
                  and (item.get('Include') or item.get('Update') or '').casefold() == 'arcforges.build.policy']
    reject_unless(len(references) == 1 and references[0].get('Include') == 'ArcForges.Build.Policy'
                  and references[0].get('Version') is None and references[0].get('VersionOverride') is None
                  and references[0].get('PrivateAssets', '').casefold() == 'all'
                  and references[0].get('GeneratePathProperty', '').casefold() == 'true',
                  'Build.Policy must be one exact central, PrivateAssets=all architecture-test reference')
    all_references = []
    for path in input_paths(root):
        if path.endswith(('.csproj', '.props', '.targets')):
            for item in ET.parse(root / path).getroot().iter():
                if item.tag.split('}')[-1] == 'PackageReference' and (item.get('Include') or item.get('Update') or '').casefold() == 'arcforges.build.policy':
                    all_references.append(path)
    reject_unless(all_references == [ARCHITECTURE_TEST_PROJECT],
                  'Build.Policy PackageReference must exist only in the ArchitectureTests project')
    imports = [item.get('Project', '').replace('\\', '/') for item in project.iter()
               if item.tag.split('}')[-1] == 'Import']
    reject_unless('$(PkgArcForges_Build_Policy)/tools/architecture/ArchitecturePolicy.props' in imports,
                  'ArchitectureTests must explicitly import the packaged shared policy engine')

    locks = []
    for path in input_paths(root):
        if not path.endswith('packages.lock.json'):
            continue
        document = json.loads((root / path).read_text())
        for framework, graph in document['dependencies'].items():
            for name, row in graph.items():
                if name.casefold() == 'arcforges.build.policy':
                    locks.append((path, framework, name, row))
    reject_unless(len(locks) == 1 and locks[0][0] == ARCHITECTURE_TEST_LOCK
                  and locks[0][2] == 'ArcForges.Build.Policy'
                  and locks[0][3].get('type', '').casefold() == 'direct'
                  and locks[0][3].get('resolved') == BUILD_POLICY_VERSION
                  and locks[0][3].get('contentHash') == actual[BUILD_POLICY_KEY],
                  'Build.Policy must be only the exact direct ArchitectureTests locked dependency')
    reject_unless(not locks[0][3].get('dependencies'),
                  'Build.Policy test/build-only package must not expand its dependency closure')

    project_references = []
    for path in input_paths(root):
        if path.endswith(('.csproj', '.props', '.targets')):
            for item in ET.parse(root / path).getroot().iter():
                if item.tag.split('}')[-1] == 'ProjectReference':
                    project_references.append((path, item.get('Include', '').replace('\\', '/')))
    for path, reference in project_references:
        if path == ARCHITECTURE_TEST_PROJECT:
            continue
        target = (root / Path(path).parent / reference).resolve()
        reject_unless(not target.is_relative_to(host.resolve()),
                      'ArchitectureTests host cannot be referenced by another project: ' + path)

    catalog = json.loads((root / 'eng/contract-packages.json').read_text())
    reject_unless(all(row.get('project') != ARCHITECTURE_TEST_PROJECT for row in catalog.get('packages', [])),
                  'ArchitectureTests cannot enter the public/internal package catalog')


def immutable_coordinates(policy, receipts):
    accepted = {}
    for snapshot in [*receipts, policy]:
        for key, row in snapshot['closure'].items():
            artifacts = row['integrity'] if isinstance(row['integrity'], dict) else {'archive': row['integrity']}
            for artifact, digest in artifacts.items():
                identity = key + '!/' + artifact
                reject_unless(identity not in accepted or accepted[identity] == digest, 'Historical immutable version changed: ' + identity)
                accepted[identity] = digest


def frameworks(root):
    # CON.40 retired the Gradle/Kotlin toolchain (gradle/libs.versions.toml); its pins leave the selection.
    selected = {'dotnetSdk': json.loads((root / 'global.json').read_text())['sdk']['version'],
                'node': (root / '.node-version').read_text().strip()}
    if (root / 'go/toolchain.json').is_file():
        # AF-CTR-01: the pinned Go release of the Go bindings module.
        selected['go'] = json.loads((root / 'go/toolchain.json').read_text())['goVersion'].removeprefix('go')
    return selected


def major_upgrade(before, after):
    changed = {key for key, version in after['frameworkVersions'].items()
               if key in before['frameworkVersions'] and version.split('.')[0] != before['frameworkVersions'][key].split('.')[0]}
    if changed:
        review = after.get('frameworkMajorReview', {})
        reject_unless(set(review.get('changed', [])) == changed and review.get('owner')
                      and all(review.get(key) for key in ['nativeAotTrim', 'androidKotlinArtR8', 'transport', 'localCoverage']),
                      'Missing framework major runtime-posture review')


def review_history(root, policy):
    from check_provenance import baseline, git
    compared = baseline(root, os.environ.get('GITHUB_SHA') if os.environ.get('GITHUB_REF', '').startswith('refs/tags/') else None)
    prefix = 'eng/policy/dependency-reviews/'
    for path in git(root, 'ls-tree', '-r', '--name-only', compared, '--', prefix).decode().splitlines():
        reject_unless((root / path).is_file() and (root / path).read_bytes().replace(b'\r\n', b'\n')
                      == git(root, 'show', compared + ':' + path).replace(b'\r\n', b'\n'), 'Historical review modified or deleted: ' + path)
    paths = [p for p in tracked(root) if p.startswith(prefix) and p.endswith('.json')]
    reject_unless(policy['reviewReceipt'] in paths, 'Missing immutable review receipt')
    reject_unless(json.loads((root / policy['reviewReceipt']).read_text()) == {'review': policy['review'], 'closure': policy['closure']},
                  'Current policy does not match review receipt')
    receipts, visited, cursor = [], set(), policy['reviewReceipt']
    while cursor is not None:
        reject_unless(cursor in paths and cursor not in visited, 'Invalid predecessor review chain')
        visited.add(cursor)
        receipt = json.loads((root / cursor).read_text())
        receipts.insert(0, receipt)
        cursor = receipt['review']['previousReceipt']
    reject_unless(visited == set(paths), 'Dropped retained review from chain')
    reject_unless(policy['review']['frameworkVersions'] == frameworks(root), 'Framework selections differ from review')
    for previous, current in zip(receipts, receipts[1:]):
        major_upgrade(previous['review'], current['review'])
    immutable_coordinates(policy, receipts)


def audit(root=ROOT, stable=False):
    policy = json.loads((root / POLICY).read_text())
    reject_unless(policy['inputHashes'] == input_hashes(root), 'Dependency input drift requires reviewed upgrade receipt')
    actual = inventory(root)
    validate(policy, actual, stable, go_tool_only(root))
    if (root / 'go/toolchain.json').is_file():
        validate_go_qualification(policy, root)
    validate_architecture_policy_boundary(root, actual)
    review_history(root, policy)
    reject_unless([e.get('value') for e in ET.parse(root / 'NuGet.config').findall('./packageSources/add')]
                  == [policy['publisher']['nuget']['feed']], 'Untrusted NuGet feed')
    # Source manifests may use * only for an exact owner-local producer workspace;
    # packing already substitutes the immutable first-party candidate identity.
    from package_catalog import packages
    workspace = {row['id'] for row in packages('npm', root)}
    for path in input_paths(root):
        if path.endswith('package.json'):
            doc = json.loads((root / path).read_text())
            for kind in ['dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies']:
                for name, version in doc.get(kind, {}).items():
                    if name in workspace and version == '*':
                        continue
                    pinned(version)
        if path.endswith(('.csproj', '.props', '.targets')):
            for element in ET.parse(root / path).iter():
                if element.tag.split('}')[-1] == 'PackageVersion' and element.get('Include'):
                    pinned(element.get('Version'))
    return {'result': 'passed', 'repository': 'Contracts', 'dependencies': len(actual), 'stable': stable,
            'inputs': len(policy['inputHashes']), 'composedGates': ['source provenance', 'contract access',
                                                                 'runtime SBOM/licences', 'locked restore']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stable', action='store_true')
    options = parser.parse_args()
    print(json.dumps(audit(stable=options.stable), indent=2))
