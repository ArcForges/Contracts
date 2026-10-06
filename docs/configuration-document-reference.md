# Bounded immutable configuration document references

CON.28 adds compatible message fields to the existing internal operator protocol:

| Message                                    | Field            | Meaning                                                                    |
| ------------------------------------------ | ---------------- | -------------------------------------------------------------------------- |
| `OperatorServiceStageConfigurationRequest` | 13 `documentRef` | Existing Foundation `BlobRef` for the complete immutable document envelope |
| `OperatorServiceGetConfigurationValue`     | 12 `documentRef` | The same exact immutable envelope identity for an approved stored document |

The existing inline `document` fields, metadata, parent version, context and validation fields retain their numbers and meanings. Generated C# and TypeScript shape validators require exactly one inline document or reference. Both alternatives absent or present refuse. A reference requires the existing nonzero Foundation blob identity, canonical lowercase SHA256 content hash and explicitly present size, with an owner-specific size bound of 1 through 2097152 bytes. Global Foundation BlobRef rules are unchanged.

Referenced bytes are the complete generated `ConfigurationDocument` protobuf message. The reference hash and size bind those exact outer bytes; the document's independent `documentHash` binds its canonicalJson body. The existing canonicalJson maximum remains 1048576 bytes, and every existing document shape constraint still applies after parsing. This is not a canonical-protobuf encoding claim and adds no URL, latest alias, JSON sentinel or enlarged RPC transport budget. The production owner must authorize the exact realm/object reference, read with bounded size, verify the complete hash, parse the generated envelope and apply generated and semantic document validation before use.

Older consumers retain unknown protobuf fields according to the existing compatible-read posture. A new reference is usable only by a consumer pinned to the actual published CON.28 producer; an older validator that requires inline document cannot authorize it. Existing valid inline requests remain valid.

The actual producer tests exercise both generated validators and binary serializers. The owned fixture includes inline compatibility, minimum/maximum references, missing/both alternatives, zero/oversized/missing size, invalid/missing hash, empty/missing identity and invalid inline documents for both Stage and Get. Complete-envelope tests preserve the legal one-MiB canonicalJson boundary and reject an oversized inner body. These are schema and serialization component checks; they do not prove an object upload, operator authorization, activation, provider readiness or deployment.

The first hosted candidate and Verify passed at `1168f071ff2af7666b36efc3fc36702c8db6b5b7`, while SecretScan reported six occurrences of four verified public input SHA256 rows. The merged Design/Plan repair admits two appended `generic-api-key` allowlists with exact paths, full key/digest lines and AND conditions. Their fixture binds the actual frozen rows and refuses changed digests, keys, paths and adjacent credential content. Existing allowlists and immutable producer/admission history remain unchanged. The amended head still requires its own passing hosted scanner and all applicable CI; the earlier candidate does not establish final approval.

Independent exact-head review, applicable CI, normal immutable package publication and the exact consumer pin remain delivery requirements. CON.26 metadata work and all historical package identities, records and receipts remain separate and unchanged.
