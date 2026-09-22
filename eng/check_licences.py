# SPDX-License-Identifier: Apache-2.0
"""Check the Contracts Apache project inventory and first-party dependency closure.

MSBuild and Gradle also enforce the effective properties during their own builds.
This Apache-owned tool does not import another repository's implementation.
"""

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'eng/policy/licence-boundary.json'
PROJECT_SUFFIXES = {'.csproj', '.fsproj', '.vbproj', '.vcxproj', '.esproj'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'duplicate JSON key: {key}')
        result[key] = value
    return result


def project_kind(path):
    if path.suffix in PROJECT_SUFFIXES:
        return 'msbuild'
    return {'package.json': 'npm', 'build.gradle.kts': 'gradle',
            'build.gradle': 'gradle', 'CMakeLists.txt': 'cmake'}.get(path.name)


def check_package(name):
    lower = name.lower()
    if lower.startswith('arcforges.'):
        require(lower.startswith(('arcforges.contracts.', 'arcforges.sdk.')) or lower == 'arcforges.cli',
                f'Non-Apache or unknown first-party NuGet dependency: {name}')
    if lower.startswith('@arcforges/'):
        require(lower in {'@arcforges/proto', '@arcforges/api-client', '@arcforges/contract-fixtures',
                          '@arcforges/ai-internal', '@arcforges/operator-client'}, f'Non-Apache or unknown first-party npm dependency: {name}')
    if lower.startswith('io.github.arcforges:'):
        require(lower in {'io.github.arcforges:' + module for module in
                         ('contracts-proto', 'contracts-connect-client', 'contract-fixtures')},
                f'Non-Apache or unknown first-party Maven dependency: {name}')


def audit(root=ROOT):
    root = root.resolve()
    files = set(subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--cached',
                                        '--others', '--exclude-standard'], text=True, encoding='utf-8').split('\0')) - {''}

    def read(name):
        path = root / name
        require(path.is_file() and path.resolve().is_relative_to(root), f'Missing or escaped input: {name}')
        require(not any(p.is_symlink() or p.is_junction() for p in [path, *path.parents] if p.is_relative_to(root)),
                f'Linked input: {name}')
        return path.read_text(encoding='utf-8-sig')

    def document(name):
        return json.loads(read(name), object_pairs_hook=unique)

    policy = document(POLICY)
    require(set(policy) == {'schemaVersion', 'repository', 'spdxLicense', 'licenceBoundary', 'projects'}, 'Invalid licence policy fields')
    require(type(policy['schemaVersion']) is int and policy['schemaVersion'] == 1 and policy['repository'] == 'Contracts'
            and policy['spdxLicense'] == 'Apache-2.0' and policy['licenceBoundary'] == 'Apache', 'Incorrect repository assignment')
    actual = {p: project_kind(PurePosixPath(p)) for p in files if project_kind(PurePosixPath(p))}
    registered = {}
    for entry in policy['projects']:
        require(set(entry) == {'path', 'kind'} and entry['path'] not in registered, 'Invalid/duplicate project registration')
        registered[entry['path']] = entry['kind']
    require(actual and registered == actual, 'Project inventory drift; register every project, including tests and tooling')
    local_managed = {PurePosixPath(p).stem.lower() for p, kind in actual.items() if kind == 'msbuild'}
    local_npm = {document(p)['name'] for p, kind in actual.items() if kind == 'npm'}
    for name, kind in actual.items():
        text = read(name)
        if kind == 'msbuild':
            tree = ET.fromstring(text)
            for prop, expected in [('PackageLicenseExpression', 'Apache-2.0'), ('LicenceBoundary', 'Apache')]:
                require([e.text for e in tree.iter() if e.tag.split('}')[-1] == prop] == [expected], f'Missing/incorrect declaration: {name}: {prop}')
            for element in tree.iter():
                if element.tag.split('}')[-1] in {'AssemblyName', 'PackageId'} and element.text:
                    local_managed.add(element.text.lower())
        elif kind == 'npm':
            package = document(name)
            require(package.get('license') == 'Apache-2.0' and package.get('arcforges', {}).get('licenceBoundary') == 'Apache' and set(package.get('arcforges', {})) <= {'licenceBoundary', 'contractAccess'},
                    f'Missing/incorrect npm declaration: {name}')
        elif kind == 'gradle':
            for prop, expected in [('spdxLicense', 'Apache-2.0'), ('licenceBoundary', 'Apache')]:
                require(re.findall(r'extra\["' + prop + r'"\]\s*=\s*"([^"\n]+)"', text) == [expected],
                        f'Missing/incorrect Gradle declaration: {name}: {prop}')
        else:
            raise ValueError(f'Unreviewed build system in Apache owner: {name}')

    references = []
    for name in sorted(files):
        path = PurePosixPath(name)
        if path.suffix in PROJECT_SUFFIXES | {'.props', '.targets'}:
            for element in ET.fromstring(read(name)).iter():
                tag = element.tag.split('}')[-1]
                if tag in {'LicenceBoundary', 'PackageLicenseExpression'}:
                    require(element.text == ('Apache' if tag == 'LicenceBoundary' else 'Apache-2.0'), f'Property override: {name}: {tag}')
                if tag == 'ProjectReference':
                    value = element.get('Include', '')
                    require(value and not any(c in value for c in '$@*?;'), f'Unreviewed project reference: {name}')
                    target = (root / path.parent / value.replace('\\', '/')).resolve()
                    require(target.is_relative_to(root), f'Project reference escapes owner: {name}')
                    require(actual.get(target.relative_to(root).as_posix()) == 'msbuild', f'Unregistered project reference: {name}')
                if tag in {'PackageVersion', 'PackageReference'}:
                    package = element.get('Include') or element.get('Update') or ''
                    check_package(package)
                    references.append(package)
        elif path.name == 'package.json':
            package = document(name)
            for section in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'):
                for dependency, version in package.get(section, {}).items():
                    require(not version.startswith(('file:', 'link:', 'git+', './', '../')), f'Unpublished npm dependency: {name}')
                    if dependency not in local_npm:
                        check_package(dependency)
                    if version.startswith('npm:'):
                        alias = version[4:]
                        end = alias.find('@', 1)
                        check_package(alias if end < 0 else alias[:end])
        elif path.name == 'packages.lock.json':
            for framework in document(name)['dependencies'].values():
                for dependency, entry in framework.items():
                    if entry['type'].lower() == 'project':
                        require(dependency.lower() in local_managed, f'Unknown locked project: {dependency}')
                    else:
                        check_package(dependency)
                        references.append(dependency)
        elif path.name == 'package-lock.json':
            for dependency, entry in document(name).get('packages', {}).items():
                dependency = entry.get('name') or dependency.rsplit('node_modules/', 1)[-1]
                if dependency not in local_npm:
                    check_package(dependency)
        elif path.name.endswith('.lockfile'):
            for line in read(name).splitlines():
                if not line.startswith('#') and ':' in line:
                    check_package(':'.join(line.split(':')[:2]))
        elif path.name in {'build.gradle.kts', 'settings.gradle.kts', 'build.gradle', 'settings.gradle'}:
            text = read(name)
            require('includeBuild(' not in text and 'mavenLocal(' not in text, f'Unpublished Gradle source: {name}')
            for dependency in re.findall(r'io\.github\.arcforges:[A-Za-z0-9_.-]+', text):
                check_package(dependency)
    return {'result': 'passed', 'repository': 'Contracts', 'spdxLicense': 'Apache-2.0', 'licenceBoundary': 'Apache',
            'projects': [{'path': p, 'kind': actual[p]} for p in sorted(actual)],
            'lockedAndDeclaredManagedPackages': sorted(set(references)),
            'evidenceClass': 'source-project-inventory-and-first-party-reference-audit'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'artifacts/evidence/licence-boundary.json')
    args = parser.parse_args()
    result = audit()
    result['evaluatedMSBuild'] = []
    for project in result['projects']:
        if project['kind'] == 'msbuild':
            output = subprocess.check_output(['dotnet', 'msbuild', project['path'],
                '-t:ArcForgesVerifyLicenceBoundary', '-getProperty:PackageLicenseExpression,LicenceBoundary',
                '-getItem:ProjectReference', '-verbosity:quiet'], cwd=ROOT, text=True, encoding='utf-8')
            evaluated = json.loads(output)
            result['evaluatedMSBuild'].append({'path': project['path'], 'properties': evaluated['Properties'],
                'projectReferences': [Path(item['FullPath']).relative_to(ROOT).as_posix()
                                      for item in evaluated['Items']['ProjectReference']]})
    result['commit'] = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    result['dirty'] = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f"Verified {len(result['projects'])} Apache project declarations and first-party references.")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
