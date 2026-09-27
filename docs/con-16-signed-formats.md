<!-- SPDX-License-Identifier: Apache-2.0 -->

# Signed distribution format contracts

CON.16 authors four closed JSON documents in `public/http/v1/signed-formats.schema.json`:

| Document                 | Payload                                                     | Maximum canonical document | Freshness ceiling |
| ------------------------ | ----------------------------------------------------------- | -------------------------- | ----------------- |
| `catalog-index.v1`       | Package entries or immutable shard references               | 1 MiB                      | 24 hours          |
| `catalog-revocations.v1` | Revocation entries or immutable shard references            | 1 MiB                      | 24 hours          |
| `android-update.v1`      | Direct-channel APK update metadata                          | 1 MiB                      | 7 days            |
| `realm.v1`               | Deployment origins, supported contracts and advertised keys | 32 KiB                     | 7 days            |

The root schema is a bundle of alternatives, not an extra wire envelope. Index and revocation bodies use exactly one of `entries` or `shards`; no additional discriminator is introduced. Revisions, APK version codes, byte sizes and realm generations are canonical uint64 decimal strings. Consumers must compare them as exact integers, including values above JavaScript's safe integer range.

Signing uses Ed25519 over the canonical document with only `signature` omitted. Catalog and Android envelopes also carry the SHA-256 of their canonical body. The independent vectors use an RFC 8785-compatible restricted profile: ordinal ASCII property names, UTF-8, no insignificant whitespace, and no floating-point fields. `canonicalUnsigned`, `canonicalDocument`, `canonicalBody` and `documentSha256` are literal cross-implementation expectations, not outputs produced by the contract code generator.

Shape validation does not establish authority. A consuming distribution implementation must validate signature and body hash against previously pinned trust, enforce key validity and revocation, pin realm and origins explicitly, validate actual calendar instants and freshness, retain monotonic state, and bind every shard to the signed root's realm/channel/revision/key and declared count/hash. Revocation sets cannot lose previously accepted entries. Android additionally retains the highest version code and verifies the installed signing-certificate lineage. HTTPS hostname and port shape bounds do not replace the consuming download policy.

`fixtures/public/con-16-signed-formats.json` contains synthetic signed documents and acceptance/refusal cases, with public reproducible seed material labelled **fixture only, never production**. The Python test independently canonicalizes and hashes the documents and uses Node's built-in WebCrypto Ed25519 verifier. It exercises malformed JSON, unknown fields, exact integer bounds, tampering, expired/unknown/revoked/not-yet-valid trust, rollback, mismatched shards, pinned origins and certificate mismatch. The oversized-document case describes a deterministic repetition of the independent entry (1,000 copies with a 1,500-character URL suffix), avoiding a multi-megabyte checked-in vector while exceeding the full UTF-8 document limit. Its small schema oracle and state evaluator are test helpers, not a production validator or trust service.

The fixtures assume explicitly pinned trust. They do not implement first-use user confirmation, production key custody, rollover ceremonies, distribution hosting, or installed-consumer behavior. Production trust is supplied by UPD.07; REL.11 removes fixture trust from release composition. Advertising a key inside a signed realm document does not independently authorize that key.

Run the offline vectors with `python -m unittest discover -s tests/tooling -p test_signed_formats.py -v`.
