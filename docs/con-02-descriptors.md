# Descriptor records and immutable large projections

CON.02 implements the field assignments in registry04 sections 3 and 4. Shared
capability/action, contract compatibility, health/readiness and `EncodedBodyRef`
types belong to Foundation. PublicApi owns `ContextProvider` and
`ContextDescriptor`, which reuse its existing `ContextRef`. Foundation never
imports PublicApi. Application presence remains a separate contract obligation.

Generated C#/TypeScript shape checks enforce field presence, registered enum
values, bounds, unique descriptor sets, canonical SemVer2 and directional
minimum-version ordering. SemVer fields retain exact build metadata while
precedence ignores it; only the explicitly designated version fields accept `+`.
Integer components are compared without machine-number rounding. The general
Key vocabulary stays unchanged. Shape validation cannot resolve a registered
operation or provider, enforce owner-specific compiled limits, authorize access
or infer availability, trust, compatibility or health from another dimension.

`EncodedBodyReader.Read` and `readEncodedBody` accept already acquired bytes and
a caller-bound expected generated message type, descriptor digest and snapshot.
They validate reference shape, canonical time and expiry, exact byte length,
the shared 64 MiB limit and `ResourceVersionRef.contentHash` before invoking a
fixed generated parser. The byte snapshot is copied before hashing; asynchronous
TypeScript hashing cannot admit subsequent caller mutations. No reflection
serializer or runtime type registry is introduced. Callers remain responsible
for resource/revision admission, authorization, revocation and decoded semantic
validation. These helpers neither fetch content nor grant a new resource right.

Each domain operation owns its response tag4 `EncodedBodyRef` alternative.
`ResponseMeta` remains metadata and has no result payload. The immutable
published Foundation baseline and existing content schema output names remain
unchanged; the current descriptor inventory is extended explicitly.

Independent fixtures cover fixed wire tags and enum values, positive and
negative SemVer and descriptor cases, predecode refusal and exact64MiB admission.
The large projection uses the Hello packaging message solely as an offline codec
fixture, not as production service acceptance. No live transport, object storage,
device, installation or product authorization behavior is claimed.
