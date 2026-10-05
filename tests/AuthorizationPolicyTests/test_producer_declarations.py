# SPDX-License-Identifier: Apache-2.0
"""Pinned producer declarations: extraction, pin consistency and stale-pin refusal."""
import copy
import json
import unittest

import producer_declarations as pd

MANIFEST = {
    'identity': {'schemaVersion': 'x', 'owner': 'identity', 'tables': [
        {'name': 'identity_user', 'columns': [{'name': 'user_id'}, {'name': 'realm_id'}]},
        {'name': 'identity_session', 'columns': [{'name': 'session_id'}, {'name': 'user_id'}],
         'foreignKeys': [{'columns': ['user_id'], 'references': {'table': 'identity_user', 'columns': ['user_id']}}]}]},
    'device': {'schemaVersion': 'x', 'owner': 'device', 'tables': [
        {'name': 'device_device', 'columns': [{'name': 'device_id'}]}]},
    'workspace': {'schemaVersion': 'x', 'owner': 'workspace', 'tables': [
        {'name': 'workspace_workspace', 'columns': [{'name': 'owner_user_id'}],
         'foreignKeys': [{'columns': ['owner_user_id'], 'references': {'table': 'identity_user', 'columns': ['user_id']}}],
         'indexes': [{'columns': ['realm_id', 'owner_user_id'], 'unique': True}]}]},
}
MODEL = """
public enum EnforcementPoint
{
    None = 0,
    CallerPreCheck = 1,
    ServiceDecision = 2,
}
public enum DecisionStep
{
    None = 0,
    ActorIdentity = 1,
    OwnerValidation = 2,
}
public static class DecisionProfiles
{
    private static readonly DecisionStep[] PreCheck =
    [
        DecisionStep.ActorIdentity,
    ];
    private static readonly DecisionStep[] Service = [DecisionStep.ActorIdentity, DecisionStep.OwnerValidation];
    public static X StepsFor(EnforcementPoint point) => point switch
    {
        EnforcementPoint.CallerPreCheck => Array.AsReadOnly(PreCheck),
        EnforcementPoint.ServiceDecision => Array.AsReadOnly(Service),
    };
}
"""


def synthetic_sources() -> dict:
    files = {path: f'-- plan: p.{i}\n-- version: 1\n-- access: {"read" if i % 2 else "write"}\n-- tail: v1 events=1\nSELECT 1;\n'
             for i, path in enumerate(pd.CLOUD_PLAN_PATHS)}
    files['storage/plans/families.json'] = json.dumps({'families': [{'family': 'account-enrollment', 'participants': [
        {'module': 'identity', 'requirement': 'required'}, {'module': 'device', 'requirement': 'conditional'}]}]})
    files[pd.CLOUD_IDENTIFIERS] = ''.join(f'internal readonly record struct {n}Id\n{{\n}}\n' for n in ('Realm', 'User', 'AuthIdentity', 'Workspace'))
    for path, name in zip(pd.CLOUD_MANIFEST_PATHS, ('identity', 'device', 'workspace')):
        files[path] = json.dumps(MANIFEST[name])
    files[pd.PLATFORM_SOURCES[0]] = MODEL
    return {path: text.encode('utf-8') for path, text in files.items()}


def reader(files: dict):
    return lambda path: files[path]


def snapshot_from(files: dict) -> dict:
    snapshot = {'schemaVersion': 'producer-declarations.v1', 'producers': {}}
    for name, spec in pd.PRODUCERS.items():
        snapshot['producers'][name] = {'repository': spec['repository'], 'task': spec['task'], 'commit': 'a' * 40,
                                       **pd.derive(name, reader(files))}
    return snapshot


class ProducerDeclarations(unittest.TestCase):
    def test_extraction_reads_declared_plans_relations_and_pipeline_profiles(self):
        files = synthetic_sources()
        cloud = pd.extract_cloud(reader(files))
        self.assertEqual(cloud['identifierTypes'], ['AuthIdentityId', 'RealmId', 'UserId', 'WorkspaceId'])
        self.assertEqual(cloud['tables']['identity_session']['references'], ['user_id>identity_user'])
        self.assertEqual(cloud['tables']['workspace_workspace']['unique'], ['realm_id+owner_user_id'])
        self.assertEqual(cloud['family']['participants'], {'identity': 'required', 'device': 'conditional'})
        self.assertEqual({p['access'] for p in cloud['plans']}, {'read', 'write'})
        platform = pd.extract_platform(reader(files))
        self.assertEqual(platform['pointSteps'], {'CallerPreCheck': [1], 'ServiceDecision': [1, 2]})
        self.assertNotIn('None', platform['steps'])

    def test_plan_header_without_access_is_refused(self):
        with self.assertRaises(ValueError):
            pd.cloud_plan('-- plan: x\n-- version: 1\nSELECT 1;\n')
        with self.assertRaises(ValueError):
            pd.cloud_plan('-- plan: x\n-- version: 1\n-- access: maybe\n')

    def test_point_without_a_step_profile_is_refused(self):
        files = synthetic_sources()
        files[pd.PLATFORM_SOURCES[0]] = MODEL.replace('EnforcementPoint.ServiceDecision => Array.AsReadOnly(Service),', '').encode()
        with self.assertRaises(ValueError):
            pd.extract_platform(reader(files))

    def test_fresh_pin_verifies_and_every_moved_source_is_stale(self):
        files = synthetic_sources()
        snapshot = snapshot_from(files)
        pd.validate_snapshot(snapshot)
        for name in pd.PRODUCERS:
            pd.verify_against(snapshot, name, reader(files))
        for path in pd.CLOUD_SOURCES + pd.PLATFORM_SOURCES:
            moved = dict(files)
            moved[path] = files[path] + b'\n'
            producer = 'cloud' if path in pd.CLOUD_SOURCES else 'platform'
            with self.subTest(path=path), self.assertRaises(pd.StalePin):
                pd.verify_against(snapshot, producer, reader(moved))

    def test_changed_declaration_with_unchanged_digest_is_stale(self):
        files = synthetic_sources()
        snapshot = snapshot_from(files)
        snapshot['producers']['cloud']['declared']['plans'][0]['access'] = 'read'
        with self.assertRaises(pd.StalePin):
            pd.verify_against(snapshot, 'cloud', reader(files))

    def test_hand_edited_facts_break_the_pin_offline(self):
        snapshot = snapshot_from(synthetic_sources())
        edited = copy.deepcopy(snapshot)
        edited['producers']['cloud']['declared']['identifierTypes'].append('MembershipId')
        with self.assertRaises(ValueError):
            pd.validate_snapshot(edited)

    def test_pin_must_be_exact_complete_and_sanctioned(self):
        snapshot = snapshot_from(synthetic_sources())
        cases = {
            'branch pin': lambda s: s['producers']['cloud'].update(commit='main'),
            'short commit': lambda s: s['producers']['platform'].update(commit='2ffeba3'),
            'extra producer': lambda s: s['producers'].update(web=copy.deepcopy(s['producers']['cloud'])),
            'missing producer': lambda s: s['producers'].pop('platform'),
            'other repository': lambda s: s['producers']['cloud'].update(repository='ArcForges/Web'),
            'dropped source': lambda s: s['producers']['cloud']['sources'].pop(),
            'bad digest': lambda s: s['producers']['cloud']['sources'][0].update(sha256='0' * 63),
            'version': lambda s: s.update(schemaVersion='producer-declarations.v2'),
        }
        for label, mutate in cases.items():
            value = copy.deepcopy(snapshot)
            mutate(value)
            with self.subTest(label), self.assertRaises(ValueError):
                pd.validate_snapshot(value)

    def test_duplicate_keys_in_the_snapshot_file_are_refused(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 's.json'
            path.write_text('{"schemaVersion": "a", "schemaVersion": "b"}')
            with self.assertRaises(ValueError):
                pd.load(path)

    def test_committed_snapshot_is_consistent(self):
        snapshot = pd.load()
        pd.validate_snapshot(snapshot)
        self.assertEqual(snapshot['producers']['cloud']['task'], 'CLOUD.11')
        self.assertEqual(snapshot['producers']['platform']['task'], 'PLT.38')


if __name__ == '__main__':
    unittest.main()
