# SPDX-License-Identifier: Apache-2.0
"""Validate the single naming authority and scan real Git inventories (WP00.00)."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / 'eng/policy/product-names.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected.split()),
            f'{label}: unexpected or missing fields')


def strings(value, label, *, empty=False):
    require(isinstance(value, list) and (empty or value), f'{label}: expected array')
    require(all(isinstance(s, str) and s.strip() == s and s for s in value),
            f'{label}: expected nonempty strings')
    require(len({s.casefold() for s in value}) == len(value), f'{label}: duplicate values')


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'duplicate JSON key: {key}')
        result[key] = value
    return result


def occurrences(data, names):
    """Scan raw bytes, including binary/UTF-16 resources, without discarding errors."""
    for encoding in ('utf-8', 'utf-16-le', 'utf-16-be'):
        tokens = {name.encode(encoding).lower(): name for name in names}
        pattern = re.compile(b'|'.join(re.escape(t) for t in sorted(tokens, key=len, reverse=True)),
                             re.IGNORECASE)
        for match in pattern.finditer(data):
            yield {'name': tokens[match[0].lower()], 'encoding': encoding,
                   'offset': match.start(), 'end': match.end()}


def validate_policy(policy):
    fields(policy, 'schemaVersion license design repositories products features webOutputs '
           'retiredProductIds providers forbiddenNames referenceRepositoryNames provenanceExceptions', 'policy')
    require(type(policy['schemaVersion']) is int and policy['schemaVersion'] == 1, 'unsupported schema')
    require(policy['license'] == 'Apache-2.0', 'incorrect policy license')
    fields(policy['design'], 'repository commit rule', 'design')
    require(policy['design']['repository'] == 'ArcForges/ArcForges-Design', 'incorrect Design owner')
    require(re.fullmatch('[0-9a-f]{40}', policy['design']['commit']) is not None, 'invalid Design commit')
    require(re.fullmatch(r'P2-\d{3}', policy['design']['rule']) is not None, 'invalid Design rule')
    strings(policy['repositories'], 'repositories')
    require(set(policy['repositories']) == {'DesktopPlatform', 'Contracts', 'ArcNotes', 'ArcScope',
            'ArcSlate', 'Cloud', 'AI', 'Web', 'Mobile'}, 'incorrect repository set')
    require(isinstance(policy['products'], list) and len(policy['products']) == 4, 'four wire identities required')
    product_ids, installed, associations, namespaces = [], [], [], []
    for product in policy['products']:
        fields(product, 'id displayName kind owners namespaces applicationIds legacyApplicationIds fileAssociations', 'product')
        product_ids.append(product['id'])
        expected_display = {'arcnotes': 'ArcNotes', 'arcscope': 'ArcScope', 'arcslate': 'ArcSlate', 'companion': 'ArcChat'}
        require(isinstance(product['id'], str) and product['id'] in expected_display, 'unknown ProductId')
        require(product['displayName'] == expected_display[product['id']], 'incorrect canonical display name')
        require(isinstance(product['displayName'], str) and product['displayName'], 'missing display name')
        require(product['kind'] == ('companion' if product['id'] == 'companion' else 'desktop'), 'incorrect product kind')
        strings(product['owners'], 'owners'); strings(product['namespaces'], 'namespaces')
        require(product['owners'] == (['Mobile', 'Web'] if product['id'] == 'companion' else [product['displayName']]), 'incorrect product owner')
        expected_namespaces = (['com.arcforges.mobile'] if product['id'] == 'companion'
                               else [product['displayName'], 'ArcForges.' + product['displayName']])
        require(product['namespaces'] == expected_namespaces, 'incomplete reserved namespaces')
        strings(product['applicationIds'], 'applicationIds')
        require(product['applicationIds'] == ['com.arcforges.' + ('mobile' if product['id'] == 'companion' else product['id'])], 'incorrect installed identity')
        namespaces.extend(product['namespaces'])
        for value in product['applicationIds']:
            require(re.fullmatch(r'[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+', value), 'invalid application ID')
        installed.extend(product['applicationIds'])
        require(isinstance(product['legacyApplicationIds'], list)
                and len(product['legacyApplicationIds']) == (1 if product['id'] == 'companion' else 0),
                'invalid legacy identities')
        for legacy in product['legacyApplicationIds']:
            fields(legacy, 'id disposition owner', 'legacy application')
            require(product['id'] == 'companion' and legacy == {
                'id': 'io.github.arcforges.mobile', 'disposition': 'development-prerelease-reinstall',
                'owner': 'WP30'}, 'unsupported identity migration')
        require(isinstance(product['fileAssociations'], list), 'invalid file associations')
        require(len(product['fileAssociations']) == (1 if product['id'] in {'arcscope', 'arcslate'} else 0),
                'native association ownership mismatch')
        for association in product['fileAssociations']:
            fields(association, 'extension windowsProgId appleTypeId state formatOwner registrationOwner', 'association')
            require(association['state'] == 'reserved' and association['registrationOwner'] == 'WP53', 'unproven association')
            require(association['extension'] == '.' + product['id'], 'invalid native extension')
            require(association['windowsProgId'] == 'ArcForges.' + product['displayName'] + '.Project', 'invalid ProgID')
            require(association['appleTypeId'] == 'com.arcforges.' + product['id'] + '.project', 'invalid type ID')
            require(association['formatOwner'] == ('WP33/WP35' if product['id'] == 'arcscope' else 'WP36/WP39'), 'invalid format owner')
            associations.append(association['extension'])
    require(set(product_ids) == {'arcnotes', 'arcscope', 'arcslate', 'companion'}, 'incorrect ProductId set')
    strings(installed, 'installed identities'); strings(associations, 'association identities')
    strings(namespaces, 'reserved namespaces')
    require(policy['features'] == [{'id': 'assistant', 'displayName': 'ArcChat', 'owner': 'DesktopPlatform',
            'namespaces': ['ArcForges.Assistant'], 'fileAssociations': []}], 'invalid embedded feature')
    require(policy['webOutputs'] == ['site', 'account', 'chat', 'operations'], 'invalid Web outputs')
    require(policy['retiredProductIds'] == ['arcchat', 'arcchat-mobile', 'mobile', 'web'], 'invalid retired IDs')
    require(policy['providers'] == [{'name': 'Paddle', 'role': 'merchant-of-record'},
            {'name': 'Payoneer', 'role': 'payout-only'}], 'incorrect provider roles')
    require(isinstance(policy['forbiddenNames'], list) and len(policy['forbiddenNames']) == 6, 'incomplete forbidden set')
    names = []
    # Components make the guard's expected vocabulary testable without exempting its source.
    dispositions = {'Arc' + suffix: ('excluded', None) for suffix in ('Canvas', 'Music', 'Image')}
    dispositions.update({'Arc' + 'Video': ('direction-only', 'arcslate'),
                         'Arc' + 'VideoFoundation': ('reference-only', None),
                         'Waf' + 'fo': ('provider-replaced', 'Paddle')})
    for item in policy['forbiddenNames']:
        fields(item, 'name disposition target note', 'forbidden declaration')
        require(item['name'] in dispositions and (item['disposition'], item['target']) == dispositions[item['name']],
                'invalid legacy disposition')
        require(isinstance(item['note'], str) and item['note'].strip(), 'missing disposition rationale')
        names.append(item['name'])
    strings(names, 'forbidden names')
    require(set(names) == set(dispositions), 'incorrect forbidden names')
    references = ['Arc' + suffix for suffix in ('Video', 'VideoFoundation')]
    require(policy['referenceRepositoryNames'] == references, 'incorrect reference exception names')
    require(isinstance(policy['provenanceExceptions'], list), 'invalid exceptions')
    seen = set()
    for item in policy['provenanceExceptions']:
        fields(item, 'repository path sha256 names reason', 'exception')
        require(item['repository'] in policy['repositories'], 'invalid exception repository')
        path = item['path']
        legacy_trace = (item['repository'] == 'DesktopPlatform'
                        and path == 'artifacts/evidence/traceability/feature-trace-bridge.json'
                        and item['sha256'] == 'f4a8f47549a96e529af5af9582f07a81dd97af73f006ba3c4436c624210a0976')
        normal_provenance = (isinstance(path, str)
                             and re.fullmatch(r'(?:docs|eng)/provenance/[A-Za-z0-9_.\-/]+\.(?:md|json)', path)
                             and '\\' not in path and '..' not in PurePosixPath(path).parts
                             and str(PurePosixPath(path)) == path)
        require(legacy_trace or normal_provenance, 'exception must name an exact provenance file')
        require(re.fullmatch('[0-9a-f]{64}', item['sha256']) is not None, 'invalid exception digest')
        strings(item['names'], 'exception names')
        require(set(item['names']) <= set(references), 'only reference names may be excepted')
        require(isinstance(item['reason'], str) and item['reason'].strip(), 'missing exception reason')
        key = (item['repository'], path)
        require(key not in seen, 'duplicate exception'); seen.add(key)
    sanitized = deepcopy(policy)
    for item in sanitized['forbiddenNames']:
        item['name'] = ''
    sanitized['referenceRepositoryNames'] = []
    for item in sanitized['provenanceExceptions']:
        item['names'] = []
    require(not list(occurrences(json.dumps(sanitized).encode(), names)),
            'forbidden name outside designated policy fields')
    return policy


def load_policy(path=POLICY_PATH):
    return validate_policy(json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=no_duplicate_keys))


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout


def scan_repository(root, repository, policy, policy_path=POLICY_PATH):
    root = root.resolve()
    require(repository in policy['repositories'], 'unknown repository')
    require(Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == root,
            'scan target must be a Git root')
    remote = git(root, 'remote', 'get-url', 'origin').decode().strip()
    if '://' in remote:
        parsed = urlsplit(remote)
        require(parsed.hostname == 'github.com' and parsed.scheme in {'https', 'ssh'}, 'unexpected repository host')
        remote_path = parsed.path
    else:
        require(remote.startswith('git@github.com:'), 'unexpected repository host')
        remote_path = remote.split(':', 1)[1]
    require(remote_path.removesuffix('.git').strip('/') == 'ArcForges/' + repository,
            'repository origin does not match requested owner')
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    state = git(root, 'status', '--porcelain=v1', '-z')
    tracked = git(root, 'ls-files', '--stage', '-z').split(b'\0')
    paths = set()
    findings = []
    for entry in filter(None, tracked):
        metadata, raw_path = entry.split(b'\t', 1)
        mode, _, stage = metadata.split()
        path = raw_path.decode('utf-8')
        paths.add(path)
        if mode not in {b'100644', b'100755'} or stage != b'0':
            findings.append({'path': path, 'kind': 'unsupported Git entry'})
    paths.update(p.decode('utf-8') for p in git(root, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if p)
    require(paths, 'empty source inventory')
    exceptions = {item['path']: item for item in policy['provenanceExceptions'] if item['repository'] == repository}
    used = set()
    names = [item['name'] for item in policy['forbiddenNames']]
    inventory_hash = hashlib.sha256()
    for path in sorted(paths):
        for match in occurrences(path.encode(), names):
            findings.append({'path': path, 'kind': 'forbidden path', **match})
        target = root / path
        if not target.resolve().is_relative_to(root) or any(p.is_symlink() or p.is_junction() for p in [target, *target.parents] if p != root):
            findings.append({'path': path, 'kind': 'unsupported symbolic path'}); continue
        try:
            data = target.read_bytes()
        except OSError:
            findings.append({'path': path, 'kind': 'unreadable inventory file'}); continue
        inventory_hash.update(path.encode() + b'\0' + hashlib.sha256(data).digest())
        if target.resolve() == policy_path.resolve():
            # Reparse these exact bytes: the policy itself never receives a blanket exemption.
            validate_policy(json.loads(data.decode('utf-8'), object_pairs_hook=no_duplicate_keys))
            continue
        exception = exceptions.get(path)
        if exception and hashlib.sha256(data).hexdigest() != exception['sha256']:
            findings.append({'path': path, 'kind': 'stale provenance exception'}); exception = None
        admitted = set()
        for match in occurrences(data, names):
            # Only standalone UTF-8 repository names in the reviewed record may be admitted.
            prefix, suffix = data[max(0, match['offset'] - 1):match['offset']], data[match['end']:match['end'] + 1]
            standalone = not re.search(rb'[A-Za-z0-9_]', prefix + suffix)
            if exception and match['encoding'] == 'utf-8' and match['name'] in exception['names'] and standalone:
                admitted.add(match['name']); continue
            findings.append({'path': path, 'kind': 'forbidden content', **match})
        if exception and admitted == set(exception['names']):
            used.add(path)
    for path in exceptions.keys() - used:
        findings.append({'path': path, 'kind': 'unused or invalid provenance exception'})
    require(head == git(root, 'rev-parse', 'HEAD').decode().strip() and state == git(root, 'status', '--porcelain=v1', '-z'),
            'repository changed during scan; retry against a stable snapshot')
    return {'repository': repository, 'commit': head, 'dirty': bool(state), 'filesScanned': len(paths),
            'inventorySha256': inventory_hash.hexdigest(), 'exceptionsUsed': sorted(used),
            'status': 'fail' if findings else 'pass', 'findings': findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', action='append', metavar='OWNER=PATH', help='repeat for each actual Git root')
    parser.add_argument('--report', type=Path, help='write evidence outside source or under ignored artifacts/')
    args = parser.parse_args()
    try:
        policy = load_policy()
        results = []
        for value in args.repository or [f'Contracts={ROOT}']:
            owner, separator, path = value.partition('=')
            require(separator and path, 'repository must be OWNER=PATH')
            results.append(scan_repository(Path(path), owner, policy))
        require(len({r['repository'] for r in results}) == len(results), 'duplicate repository target')
        report = {'substep': 'WP00.00', 'checkedAt': datetime.now(timezone.utc).isoformat(),
                  'designCommit': policy['design']['commit'], 'policySha256': hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest(),
                  'evidenceClass': 'source-policy-scan', 'repositories': results}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        for result in results:
            print(f"{result['repository']}: {result['status']}; {result['filesScanned']} files; "
                  f"{len(result['exceptionsUsed'])} exceptions; {len(result['findings'])} findings")
            for finding in result['findings']:
                print(json.dumps(finding))
        return int(any(r['status'] != 'pass' for r in results))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        # Do not echo command output, file contents, remotes or credentials.
        print(f'Naming verification failed: {type(error).__name__}: ' +
              (str(error) if isinstance(error, ValueError) else 'Git or file access failed'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
