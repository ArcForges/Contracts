# SPDX-License-Identifier: Apache-2.0
"""Pinned snapshots of the identity facts that producers declare, and their extraction.

Contracts never builds, references or vendors producer source. The only input is a
reviewed snapshot (`producer-declarations.json`) of *declared facts* with an exact
repository, commit and file digest per source. CI checks the snapshot offline for
internal consistency. An explicit local run re-derives the same facts from the exact
pinned commit of a producer checkout (`git show <commit>:<path>`, never the working
tree) and fails when a producer moved or the snapshot was edited by hand.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Callable

SNAPSHOT = Path(__file__).with_name('producer-declarations.json')
Reader = Callable[[str], bytes]

CLOUD_PLAN_PATHS = [
    'storage/plans/identity/credential-add.sql', 'storage/plans/identity/credential-find.sql',
    'storage/plans/identity/credential-list.sql', 'storage/plans/identity/credential-relabel.sql',
    'storage/plans/identity/credential-revoke.sql', 'storage/plans/identity/credential-touch.sql',
    'storage/plans/identity/user-load.sql', 'storage/plans/identity/user-rename.sql',
    'storage/plans/families/account-enrollment.create-user.sql',
]
CLOUD_MANIFEST_PATHS = [f'src/ArcForges.Cloud.Storage.D1/Physical/manifest/{name}.json'
                        for name in ('identity', 'device', 'workspace')]
CLOUD_IDENTIFIERS = 'src/ArcForges.Cloud.Modules.Identity/Core/Domain/Identifiers.cs'
CLOUD_SOURCES = [*CLOUD_PLAN_PATHS, 'storage/plans/families.json', CLOUD_IDENTIFIERS, *CLOUD_MANIFEST_PATHS]
PLATFORM_SOURCES = ['src/BuildingBlocks/ArcForges.Security/Decisions/DecisionModel.cs']
PRODUCERS = {
    'cloud': {'repository': 'ArcForges/Cloud', 'task': 'CLOUD.11', 'sources': CLOUD_SOURCES},
    'platform': {'repository': 'ArcForges/DesktopPlatform', 'task': 'PLT.38', 'sources': PLATFORM_SOURCES},
}


class StalePin(ValueError):
    """A producer fact differs from its recorded pin."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def facts_digest(declared: dict) -> str:
    return digest(canonical(declared).encode('ascii'))


def git_reader(repository: Path, commit: str) -> Reader:
    def read(path: str) -> bytes:
        result = subprocess.run(['git', '-C', str(repository), 'show', f'{commit}:{path}'], capture_output=True)
        require(result.returncode == 0, f'unreadable pinned source {path} at {commit}')
        return result.stdout
    return read


def directory_reader(root: Path) -> Reader:
    return lambda path: (root / path).read_bytes()


def _text(data: bytes) -> str:
    return data.decode('utf-8').replace('\r\n', '\n')


def cloud_plan(text: str) -> dict:
    header = {}
    for line in text.split('\n'):
        if not line.startswith('--'):
            break
        match = re.match(r'-- (plan|version|access|tail): ?(.*)$', line)
        if match:
            header.setdefault(match.group(1), match.group(2).strip())
    require({'plan', 'version', 'access'} <= set(header), 'plan header incomplete')
    require(header['access'] in {'read', 'write'}, 'plan access is neither read nor write')
    plan = {'name': header['plan'], 'version': int(header['version']), 'access': header['access']}
    if 'tail' in header:
        plan['tail'] = header['tail'].split(' ')[0] if header['tail'].startswith('none') else header['tail']
    return plan


def cloud_tables(manifest: dict) -> dict:
    tables = {}
    for table in manifest['tables']:
        tables[table['name']] = {
            'columns': sorted(column['name'] for column in table['columns']),
            'references': sorted(f"{'+'.join(fk['columns'])}>{fk['references']['table']}" for fk in table.get('foreignKeys', [])),
            'unique': sorted('+'.join(index['columns']) for index in table.get('indexes', []) if index.get('unique')),
        }
    return {'owner': manifest['owner'], 'tables': tables}


def extract_cloud(read: Reader) -> dict:
    plans = sorted((cloud_plan(_text(read(path))) for path in CLOUD_PLAN_PATHS), key=lambda p: p['name'])
    families = json.loads(_text(read('storage/plans/families.json')))['families']
    enrollment = next((f for f in families if f['family'] == 'account-enrollment'), None)
    require(enrollment is not None, 'account-enrollment family missing')
    identifiers = sorted(re.findall(r'^internal readonly record struct (\w+Id)\b', _text(read(CLOUD_IDENTIFIERS)), re.M))
    modules, tables = {}, {}
    for path in CLOUD_MANIFEST_PATHS:
        facts = cloud_tables(json.loads(_text(read(path))))
        modules[facts['owner']] = sorted(facts['tables'])
        tables.update(facts['tables'])
    return {
        'identifierTypes': identifiers,
        'plans': plans,
        'family': {'name': 'account-enrollment',
                   'participants': {p['module']: p['requirement'] for p in enrollment['participants']}},
        'moduleTables': modules,
        'tables': dict(sorted(tables.items())),
    }


def _enum_members(text: str, name: str) -> dict:
    body = re.search(rf'public enum {name}\s*\{{(.*?)\n\}}', text, re.S)
    require(body is not None, f'enum {name} missing')
    return {m[0]: int(m[1]) for m in re.findall(r'^\s*(\w+) = (\d+),', body.group(1), re.M)}


def extract_platform(read: Reader) -> dict:
    text = _text(read(PLATFORM_SOURCES[0]))
    steps = _enum_members(text, 'DecisionStep')
    points = _enum_members(text, 'EnforcementPoint')
    arrays = {name: re.findall(r'DecisionStep\.(\w+)', body)
              for name, body in re.findall(r'private static readonly DecisionStep\[\] (\w+) =\s*\[(.*?)\];', text, re.S)}
    mapping = dict(re.findall(r'EnforcementPoint\.(\w+) => Array\.AsReadOnly\((\w+)\)', text))
    require(set(mapping) == {name for name in points if name != 'None'}, 'enforcement point without a step profile')
    profiles = {}
    for point, array in mapping.items():
        require(array in arrays, f'step profile {array} missing')
        profiles[point] = [steps[name] for name in arrays[array]]
    return {'steps': {name: number for name, number in steps.items() if name != 'None'},
            'enforcementPoints': {name: number for name, number in points.items() if name != 'None'},
            'pointSteps': dict(sorted(profiles.items()))}


EXTRACTORS = {'cloud': extract_cloud, 'platform': extract_platform}


def derive(name: str, read: Reader) -> dict:
    """Fresh snapshot entry body (sources + declared facts) from one producer's pinned files."""
    sources = [{'sha256': digest(read(path)), 'path': path} for path in PRODUCERS[name]['sources']]
    declared = EXTRACTORS[name](read)
    return {'sources': sources, 'declared': declared, 'factsDigest': facts_digest(declared)}


def load(path: Path = SNAPSHOT) -> dict:
    def no_duplicates(pairs):
        keys = [k for k, _ in pairs]
        require(len(keys) == len(set(keys)), 'duplicate key in producer snapshot')
        return dict(pairs)
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)


def validate_snapshot(snapshot: dict) -> None:
    """Offline consistency: complete producer set, exact pins, facts bound to their digest."""
    require(snapshot.get('schemaVersion') == 'producer-declarations.v1', 'unknown producer snapshot version')
    require(set(snapshot.get('producers', {})) == set(PRODUCERS), 'producer set differs from the sanctioned producers')
    for name, expected in PRODUCERS.items():
        entry = snapshot['producers'][name]
        require(entry['repository'] == expected['repository'] and entry['task'] == expected['task'],
                f'{name}: producer identity differs')
        require(re.fullmatch(r'[0-9a-f]{40}', entry['commit']) is not None, f'{name}: pin is not an exact commit')
        require([s['path'] for s in entry['sources']] == expected['sources'], f'{name}: source set differs from the sanctioned set')
        require(all(re.fullmatch(r'[0-9a-f]{64}', s['sha256']) for s in entry['sources']), f'{name}: source digest malformed')
        require(entry['factsDigest'] == facts_digest(entry['declared']), f'{name}: declared facts edited without a new pin')


def verify_against(snapshot: dict, name: str, read: Reader) -> None:
    """Re-derive one producer's facts from its pinned files and require exact equality."""
    entry = snapshot['producers'][name]
    fresh = derive(name, read)
    if fresh['sources'] != entry['sources']:
        changed = [a['path'] for a, b in zip(fresh['sources'], entry['sources']) if a != b]
        raise StalePin(f'{name}: pinned source digest differs: {changed}')
    if fresh['declared'] != entry['declared']:
        raise StalePin(f'{name}: declared facts differ from the pin')


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('write', 'verify'):
        command = sub.add_parser(name)
        for producer in PRODUCERS:
            command.add_argument(f'--{producer}', type=Path, required=name == 'write', help=f'{producer} repository checkout (read through git only)')
        if name == 'write':
            for producer in PRODUCERS:
                command.add_argument(f'--{producer}-commit', required=True)
    options = parser.parse_args()
    if options.command == 'write':
        snapshot = {'schemaVersion': 'producer-declarations.v1', 'producers': {}}
        for name, spec in PRODUCERS.items():
            commit = getattr(options, f'{name}_commit')
            body = derive(name, git_reader(getattr(options, name), commit))
            snapshot['producers'][name] = {'repository': spec['repository'], 'task': spec['task'], 'commit': commit, **body}
        validate_snapshot(snapshot)
        SNAPSHOT.write_text(json.dumps(snapshot, indent=2) + '\n', encoding='utf-8')
        return 0
    snapshot = load()
    validate_snapshot(snapshot)
    for name in PRODUCERS:
        repository = getattr(options, name)
        if repository is not None:
            verify_against(snapshot, name, git_reader(repository, snapshot['producers'][name]['commit']))
            print(f'{name}: pinned facts re-derived from {snapshot["producers"][name]["commit"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
