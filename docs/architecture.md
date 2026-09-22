# Contract and package boundaries

## Authored source and generated output

The authored proto trees, JSON schemas and constraint sidecars own the wire and
validation shapes. `eng/contract-packages.json` defines all 22 current outputs:
14 NuGet, five npm and three Maven packages. The initial source slices are fixed by the
[WP03.00 structure profile](https://github.com/ArcForges/ArcForges-Design/blob/26f15ebf6278e8cd42c2b2396e82c326513e1078/docs/assurance/wp03-00-contract-structure-profile.md).
The [WP03.01 foundation profile](https://github.com/ArcForges/ArcForges-Design/blob/5e202ff10f3c218d9e159029579ca535c641169b/docs/assurance/wp03-01-foundation-contract-profile.md)
adds the complete selected foundation, Notes query, Scope measurement and recursive
owner-body message closure. [This step's evidence record](wp03-01-foundation.md)
separates implemented source from validation and publication status. The
[WP03.02 serialization posture profile](https://github.com/ArcForges/ArcForges-Design/blob/212825003ed712200e585445301473233404f597/docs/assurance/wp03-02-serialization-posture-profile.md)
fixes the codec, limit, registration and AOT rules below. The remaining
production operation catalogue and later semantic gates are not complete.

Each NuGet project owns real generated contracts or validation/client/tool code.
Foundation and Events are reusable public contracts. The six LocalRpc owners
(Platform, Sandbox, Chat, Notes, Scope and Slate) and CloudInternal have explicit
internal access boundaries. All authored packages remain Apache-2.0; access and
licensing are independent properties. The compiled-descriptor/access gate checks
actual project, npm and Gradle dependencies against the catalog and rejects public
references to internal contracts.

The pinned Grpc.Tools protoc and gRPC C# plugin generate per-owner C# bindings.
Protobuf-es generates public foundation/content/Hello/events and the internal operator module;
the operator module reuses public Foundation types. Java/Kotlin lite and
Connect-Kotlin generate the public foundation/content/Hello/events messages and the
retained Hello service. The new content schema contains no services. Extension IPC is C# only. Generated sources are committed and regenerated
into temporary directories for comparison. JSON schema and constraint generators
emit concrete models, AOT-compatible C# validation and TypeScript unknown-input
validation. Public and internal offline fixtures exercise the selected boundaries.

`ArcForges.Contracts.slnx` includes every C# producer project and targeted offline
tests. The CLI validates the declared inventory.v1 JSON shape; it does not inspect
archive payload bytes or decide signatures, trust or authorization. The SDK client
composes a caller-owned CallInvoker for RenewLease and validates its request. The
caller owns transport, session, authentication and lifecycle.

## Foundation values and profile validation

`eng/foundation-inventory.json` binds the selected seeds and complete recursive
closure to authored fields, tags, presence, oneofs, enums and owners. The current
closure has 148 messages: 32 in Foundation and 116 in PublicApi, including all 16
`AggregateBody` branches. Completeness is checked from field dependencies rather
than inferred from these counts. Stable common values, errors, origin and resource
references stay in `arcforges.foundation.v1`; domain projections live in
`arcforges.publicapi.v1` from `public/proto/arcforges/publicapi/v1/content.proto`.
Foundation does not import those domain projections.

Generated `ContractShapeValidation.IsValid` overloads and TypeScript `is<Type>`
functions validate current wire/profile shape. They check required presence,
oneofs, exact scalar bounds and self-contained Notes, content-origin and measurement
relationships. Measurement thresholds carry their selected channel identity;
result levels/fractions cannot be confused across channels. Rich text keeps exact
UTF-16 boundaries and stable run/atom identities. These checks do not issue cursors,
authorize a resource, retrieve bytes, query a database, evaluate Notes filters or
compute measurements. A valid reference does not establish ownership or availability.

`public/proto/value-boundaries.json` defines 69 separate ID domains. Generated C#
record structs under `ArcForges.Contracts.Foundation.Values` and
`ArcForges.Contracts.PublicApi.Values`, and exported TypeScript ID brands, prevent
accidental domain interchange. Shared value adapters preserve canonical UUID byte
order, int64/uint64 precision, distinct Cloud/native/local tokens, opaque cursor
bounds, exact decimal coefficient/scale and checked rational time conversion.
The generated protobuf messages remain the sole wire representation. Shared decimals
preserve declared scale; `ExactDecimal.FromNotes` / `notesDecimal` additionally
reject trailing fractional zeroes. No adapter grants permission or implements an owner.

Compatible reads can retain unknown protobuf fields and unsupported profile keys.
C# `ReadProjection<T>` and TypeScript `readProjection` report whether current-profile
validation passed while preserving the original generated message. That observation
does not authorize mutation; consumers must validate the actual message again before
using it as a current mutation input. Unsupported read values remain inert.

## Serialization posture

Generated Google.Protobuf (C#) and protobuf-es (TypeScript) code is the only business
wire implementation. `ContractWire` (C#, `ArcForges.Contracts.Foundation.Serialization`)
and `decodeContract`/`encodeContract` (`@arcforges/proto`) apply the registry limits:
4 MiB unary/helper messages, 256 KiB inline pages, 32 KiB stream frames and 64 MiB
large read projections, with the root plus at most 100 nested message levels.
Oversized, too deep and malformed input are distinct typed refusals; unknown fields
are retained and re-emitted. The public TypeScript transport factory
`createPublicGrpcWebTransport` fixes binary gRPC-Web and the same read options.

Each package with services exports a generated catalogue: C# `ContractServices.All`
lists the generated `ServiceDescriptor` values beside the plugin's explicit
`BindService` methods, and TypeScript exports `contractServices`. No server reflection
service, assembly scanning or runtime schema registry is used.

Only the declared HTTP-exception schemas generate JSON records. Their
`JsonSerializerContext` classes disallow unmapped and duplicate properties, use strict
numbers and respect required/nullable annotations. Generated `<Schema>Json.Parse`/
`TryParse`/`Serialize` (C#) and `parse<Schema>Json`/`tryParse<Schema>Json`/
`serialize<Schema>Json` (TypeScript) check the schema's `x-arcforges-max-bytes`, UTF-8
without BOM, JSON depth 32, duplicate properties and integer lexemes before the closed
schema. Every project disables reflection-based System.Text.Json.

`eng/check_serialization.py` rejects reflection serializers and discovery packages in
all locks, runtime-selected well-known proto types, reflection/discovery APIs in
production source, handwritten wire records outside generated owners, missing strict
JSON options and stale service catalogues. The test-only
`tests/public/SerializationProbe` roots all 13 C# libraries, publishes with Native AOT
(analysis warnings are errors) and runs the independent
[`wp03-02.json`](../fixtures/public/wp03-02.json) vectors; the TypeScript suite runs the
same vectors. See the [WP03.02 record](wp03-02-serialization.md).

## Public consumers

Public business clients use binary gRPC-Web. The retained Hello example and its
native transport diagnostic are migration fixtures, not production behavior.
`@arcforges/proto` exports generated messages/descriptors, shape/profile checks and
safe value adapters through its public entry point;
`@arcforges/api-client` supplies the transport factory and public HTTP types/checks.
`@arcforges/contract-fixtures` exports offline public cases. `@arcforges/ai-internal`
and `@arcforges/operator-client` expose internal HTTP and operator contracts without
introducing them into a public consumer closure.

Maven group `io.github.arcforges` publishes `contracts-proto`,
`contracts-connect-client` and `contract-fixtures`. The native-only
`contracts-client` is retired from new candidates before business-schema expansion;
previous immutable publications and consumer pins remain untouched. Connect callers
supply transport and serialization configuration and explicitly choose binary
gRPC-Web for public business ingress. No package creates global channels, product
storage, endpoint dispatch or authentication policy.

## Dependency and package discipline

The root npm workspace has one lock. Every .NET project has a committed lock and
uses central versions. Gradle uses a pinned wrapper/version catalog, strict
locks for every resolvable configuration and checksum verification for plugins,
generators and dependencies. Generator/runtime upgrades update pins and locks together,
regenerate sources and pass the retained build/offline checks; relevant runtime diagnostics remain local opt-in. Generated code is never
edited manually. No submodules or cross-repository source references are allowed.

Packing builds one immutable candidate set. npm first-party dependency versions
are rewritten only in a temporary staging directory; source manifests and their
lock stay unchanged. The API client pins the exact proto candidate version.
NuGet libraries contain their own assemblies and runtime dependency references.
The framework-dependent CLI tool carries its managed dependency closure and terms.
No package embeds Grpc.Tools or a compiler. Per-package descriptors and authored
schema sources follow the selected dependency closure; public packages exclude
internal sources and extension IPC is excluded from public TS/Maven. Hash verification checks identity, contents,
metadata, licences and the expected runtime dependency set.

The retained Hello installed-package diagnostics are local opt-in only. They use
C#, TypeScript and the Connect-Kotlin fixture, and are not required by build, pack,
publish or CI. Their results cover that example only. No public-package downloads
or consumer executions are part of ordinary post-merge verification.

Formal Maven Central releases require main/source/documentation JARs, POM metadata and detached
PGP signatures. Gradle prepares the unsigned repository and API documentation in
the candidate. After Verify, a separate source-free Gradle build signs those
files in memory; it has no source sets or dependencies and cannot rebuild them.
The Portal upload uses automatic publication and retains an identity-bound
deployment receipt for recovery. Portal `PUBLISHED`, matching deployment ID/name and expected
package coordinates complete publication; public byte downloads and search indexing are not gates.

Main builds instead use the Sonatype SNAPSHOT repository and no signing key. The same source-free Gradle project transports tested files and creates timestamped metadata. The serialized publisher checks GitHub main-ref metadata and skips an older queued commit, then stops after successful upload. Isolated Kotlin transport diagnostics are local opt-in only. The manifest separates `version` (cross-language CI identity) from `mavenVersion`; the JAR retains the CI identity and Git SHA. Canonical formal tags share their version across ecosystems. See [publication channels and recovery](maven-central.md).

## Licensing

ArcForges-authored schemas, generated bindings, client code, examples, tooling,
tests, configuration and documentation use [Apache-2.0](../LICENSE). The root
LICENSE applies throughout this repository. The LICENSE files in `public/`,
`src/public/`, `tests/public/` and `fixtures/public/` are copies of that same
licence retained for source exports and package distribution.

Generation preserves the schema's Apache-2.0 declaration. Package metadata,
embedded LICENSE/NOTICE and SBOM must agree. Dependencies retain their own licences
and notices. The SBOM inventories the resolved runtime closure for each
deliverable; source metadata identifies the dependency locks used to produce it.
Build tools are not shipped in packages. Retired native-only Maven dependencies
remain in historical review receipts; they are not new publication outputs. Gradle wrapper code retains its upstream
Apache-2.0 notices. The explicit Maven runtime licence catalog rejects an unknown
new dependency until its upstream licence is reviewed.

The closed inventory in `eng/policy/licence-boundary.json` assigns every current
build scope to Apache-2.0 / Apache. Source checks cover tooling and independent
consumer/signing builds as well as public libraries. Locked transitive first-party
packages cannot introduce another owner's AGPL code or an unknown package family.
MSBuild and Gradle separately check evaluated declarations and local references;
changing the inventory alone cannot change the repository's permitted boundary.
These first-party checks complement the existing distributable dependency notices
and SBOM checks; they do not relicense third-party material.

## Compatibility and limits

The [WP02.04 support identity profile](implementation/wp02-04-build-identity.md)
separates contract, dependency and artifact versions and defines package-only
runtime retrieval of compiled build identity in C#, TypeScript and Kotlin.

Keep existing v1 field numbers/types and RPC identities stable; reserve removed
field numbers/names and introduce a reviewed versioned API for incompatible
behavior. All current releases are prerelease candidates. A normal main merge
increments the package build version, not the protobuf wire namespace.

The retained CI checks regeneration, selected offline shape/wire cases, compilation
and the package dependency/metadata closure. The foundation suite uses independent
positive/negative records, fixed binary oracles and C#/TS exchange; profile scenario
inputs/results are fixture data, not executed numerical/query/transaction engines.
It does not run live RPC fixtures. The Linux candidate build also runs the
serialization gate and the Native AOT probe once. The real generated-client call in a
published host/client AOT artifact remains WP06.02; .03 retains resource/descriptor/Sync admission semantics; .05
retains complete operations, scope/stream/history and three-language client
conformance; .06/.07/.90 retain their full compatibility/signing/stage gates.
Android device behavior, authentication, browser CORS, live Cloud/provider behavior
and commercial acceptance remain with their designated owners.
