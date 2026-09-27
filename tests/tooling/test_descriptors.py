# SPDX-License-Identifier: Apache-2.0
"""Independent source ownership and wire assignment checks for CON.02."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'eng'))
from check_foundation import FOUNDATION, CONTENT, DESCRIPTORS, parse_schema, check_model


class DescriptorSourceTests(unittest.TestCase):
    def setUp(self):
        self.schemas = {p: parse_schema((ROOT / p).read_text(), p) for p in [FOUNDATION, CONTENT, DESCRIPTORS]}
        self.inventory = json.loads((ROOT / 'eng/foundation-inventory.json').read_text())
        self.baseline = json.loads((ROOT / 'eng/foundation-baseline.json').read_text())
        self.values = json.loads((ROOT / 'public/proto/value-boundaries.json').read_text())
        self.constraints = json.loads((ROOT / 'public/proto/constraints.json').read_text())

    def check(self, schemas=None, inventory=None):
        return check_model(inventory or self.inventory, schemas or self.schemas, self.constraints, self.values, self.baseline)

    def test_complete_owned_closure(self):
        self.check()
        self.assertEqual(set(self.schemas[DESCRIPTORS]['messages']), {'ContextProvider', 'ContextDescriptor'})
        self.assertFalse(self.schemas[FOUNDATION]['imports'])

    def test_exact_encoded_reference_and_binding_tags(self):
        encoded = self.schemas[FOUNDATION]['messages']['EncodedBodyRef']['fields']
        self.assertEqual([(x['tag'], x['jsonName']) for x in encoded],
                         [(1, 'resource'), (2, 'messageType'), (3, 'descriptorHash'), (4, 'byteLength'), (5, 'snapshotToken'), (6, 'expiresAt')])
        self.assertEqual(self.schemas[FOUNDATION]['enums']['BindingProtocol'][-1], {'name': 'BINDING_PROTOCOL_IN_PROCESS', 'number': 6})
        self.assertNotIn('InstancePresence', self.schemas[FOUNDATION]['messages'])
        self.assertNotIn('InstancePresence', self.schemas[DESCRIPTORS]['messages'])

    def test_wrong_public_import_and_owner_are_refused(self):
        changed = deepcopy(self.schemas)
        changed[DESCRIPTORS]['imports'].append('arcforges/local/platform/v1/platform.proto')
        with self.assertRaises(ValueError): self.check(changed)
        changed = deepcopy(self.inventory)
        next(x for x in changed['records'] if x['name'] == 'ContextDescriptor')['owner'] = 'ArcForges.Contracts.Foundation'
        with self.assertRaises(ValueError): self.check(inventory=changed)

    def test_wrong_generated_stem_and_published_tag_are_refused(self):
        changed = deepcopy(self.inventory)
        row = next(x for x in changed['records'] if x['name'] == 'ContextDescriptor')
        row['outputs']['csharp'] = row['outputs']['csharp'].replace('Descriptors.cs', 'Content.cs')
        with self.assertRaises(ValueError): self.check(inventory=changed)
        changed = deepcopy(self.schemas)
        changed[FOUNDATION]['messages']['Id']['fields'][0]['tag'] = 99
        with self.assertRaises(ValueError): self.check(changed)

    def test_unregistered_descriptor_source_and_presence_are_refused(self):
        changed = deepcopy(self.schemas)
        changed['public/proto/extra.proto'] = changed[DESCRIPTORS]
        with self.assertRaises(ValueError): self.check(changed)
        changed = deepcopy(self.schemas)
        changed[FOUNDATION]['messages']['EncodedBodyRef']['fields'][3]['label'] = ''
        with self.assertRaises(ValueError): self.check(changed)


if __name__ == '__main__':
    unittest.main()
