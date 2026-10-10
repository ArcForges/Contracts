# SPDX-License-Identifier: Apache-2.0
"""Check reviewed Contracts dependency inputs without restoring or contacting feeds."""
import argparse
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
BUILD_POLICY_KEY = 'nuget:arcforges.build.policy@1.0.0-ci.94.1'
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
                     'gradle/wrapper/gradle-wrapper.properties', 'eng/toolchain.json', 'eng/contract-packages.json', 'eng/policy/contract-access.json'}
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
        elif path.endswith('.lockfile'):
            for line in (root / path).read_text().splitlines():
                if not line.startswith('#') and ':' in line:
                    coordinate = line.split('=')[0]
                    pinned(coordinate.rsplit(':', 1)[1])
                    reject_unless(coordinate in verification, 'Unverified Maven coordinate: ' + coordinate)
                    admit('maven:' + coordinate, verification[coordinate])
    return result


def validate(policy, actual, stable=False):
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
        if stable:
            reject_unless(stable_dependency(key), 'Stable closure contains prerelease: ' + key)
    review = policy['review']
    reject_unless(review['owner'] and review['reviewer'] and review['maintenanceAssessment'], 'Missing review')
    reject_unless(re.fullmatch('[0-9a-f]{40}', review['baselineCommit']), 'Floating source tag')
    reject_unless(review['inputHashes'] == policy['inputHashes'], 'Upgrade receipt does not bind inputs')
    reject_unless(set(review['checks']) == CHECKS and all(review['checks'].values()), 'Missing upgrade evidence')
    reject_unless(policy['publisher'] == {'repository': 'ArcForges/Contracts', 'workflow': 'ci.yml',
                  'nuget': {'feed': 'https://api.nuget.org/v3/index.json', 'environment': 'nuget', 'credential': 'github-oidc'},
                  'npm': {'feed': 'https://registry.npmjs.org/', 'environment': 'npm', 'credential': 'github-oidc'},
                  'maven': {'environment': 'maven-central', 'credential': 'central-token-and-formal-pgp'}},
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
                  'Only ArcForges.Build.Policy 1.0.0-ci.94.1 is admitted')
    pin_path = root / 'Directory.Packages.props'
    reject_unless(pin_path.is_file(), 'Build.Policy exact central version pin is missing')
    pins = [item for item in ET.parse(pin_path).getroot().iter()
            if item.tag.split('}')[-1] == 'PackageVersion'
            and (item.get('Include') or '').casefold() == 'arcforges.build.policy']
    reject_unless(len(pins) == 1 and pins[0].get('Include') == 'ArcForges.Build.Policy'
                  and pins[0].get('Version') == '1.0.0-ci.94.1',
                  'Build.Policy must have exactly one exact central pin')

    project = ET.parse(host).getroot()
    def values(name):
        return [element.text or '' for element in project.iter() if element.tag.split('}')[-1] == name]
    reject_unless(values('TargetFramework') == ['net10.0'] and values('OutputType') == ['Exe']
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
                  and locks[0][3].get('resolved') == '1.0.0-ci.94.1'
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
    return {'dotnetSdk': json.loads((root / 'global.json').read_text())['sdk']['version'],
            'node': (root / '.node-version').read_text().strip()}


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
    validate(policy, actual, stable)
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
