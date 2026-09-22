# Contract and package boundaries

## Authored source and generated output

The authored proto trees, JSON schemas and constraint sidecars own the wire and
validation shapes. `eng/contract-packages.json` defines all 22 current outputs:
14 NuGet, five npm and three Maven packages. The complete selected source slices
and later-substep exclusions are fixed by the
[WP03.00 structure profile](https://github.com/ArcForges/ArcForges-Design/blob/26f15ebf6278e8cd42c2b2396e82c326513e1078/docs/assurance/wp03-00-contract-structure-profile.md).
These selected slices do not claim the remaining production schema catalog is complete.

Each NuGet project owns real generated contracts or validation/client/tool code.
Foundation and Events are reusable public contracts. The six LocalRpc owners
(Platform, Sandbox, Chat, Notes, Scope and Slate) and CloudInternal have explicit
internal access boundaries. All authored packages remain Apache-2.0; access and
licensing are independent properties. The compiled-descriptor/access gate checks
actual project, npm and Gradle dependencies against the catalog and rejects public
references to internal contracts.

The pinned Grpc.Tools protoc and gRPC C# plugin generate per-owner C# bindings.
Protobuf-es generates public core/Hello/events and the internal operator module;
the operator module reuses public Foundation types. Java/Kotlin lite and
Connect-Kotlin generate only public core/Hello/events and the retained Hello
service. Extension IPC is C# only. Generated sources are committed and regenerated
into temporary directories for comparison. JSON schema and constraint generators
emit concrete models, AOT-compatible C# validation and TypeScript unknown-input
validation. Public and internal offline fixtures exercise the selected boundaries.

`ArcForges.Contracts.slnx` includes every C# producer project and targeted offline
tests. The CLI validates the declared inventory.v1 JSON shape; it does not inspect
archive payload bytes or decide signatures, trust or authorization. The SDK client
composes a caller-owned CallInvoker for RenewLease and validates its request. The
caller owns transport, session, authentication and lifecycle.

## Public consumers

Public business clients use binary gRPC-Web. The retained Hello example and its
native transport diagnostic are migration fixtures, not production behavior.
`@arcforges/proto` exports generated messages/descriptors and core shape checks;
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
and the package dependency/metadata closure. It does not run live RPC fixtures. It does
not implement the future production descriptor compatibility gate, full business
validation catalogues, Android app/device behavior, authentication, browser CORS integration,
Cloud deployment or production AOT server acceptance. Those remain governed by
the accepted design and implementation work packages.
