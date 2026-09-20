# Contract and package boundaries

## Authored source and generated output

`public/proto` is the authority for the public wire format. The current example
is `arcforges.hello.v1.HelloService/SayHello`, with a string name and string reply.
The demo server returns `Hello, <name>!` and rejects an empty name with
`INVALID_ARGUMENT`; all other strings, including whitespace and Unicode, are
preserved. This deliberately small rule belongs to the example, not a product.

`eng/Codegen` restores the pinned Grpc.Tools package. Its protoc generates C# (with the matching gRPC C# plugin), TypeScript
(with protoc-gen-es), and Java/Kotlin lite messages with Java/Kotlin gRPC and
Connect-Kotlin service plugins. Connect-Kotlin 0.9.0's executable generator JAR
is resolved from Maven Central with the other checksum-verified codegen tools.
The Java package options do not change protobuf wire names or existing C#/TS APIs.
Generated C# lives in `src/public/dotnet/ArcForges.Contracts.PublicApi/Generated`;
TS lives in `src/public/ts/proto/src/gen`; Java/Kotlin lives in each Maven
module's `generated` directory under `src/public/kotlin`. Generated sources are committed so a PR
can review both schema and API changes. CI regenerates into a temporary directory
and fails if the committed files differ. The binary descriptor is built alongside
the bindings and distributed in the NuGet, npm proto and Maven proto packages.

The .slnx contains the public library, code generation tool restore project and
two small test applications. The test host is an ordinary ASP.NET Core process
with explicit service registration and loopback gRPC/gRPC-Web listeners. It is
never packaged as a product/server deliverable.

## Public consumers

Public business clients use binary gRPC-Web under the [current runtime authority](https://github.com/ArcForges/ArcForges-Design/blob/e2dd78058ce2d4bd1a8434a34d049bbc1158eacb/docs/architecture/30-runtime-and-source-ownership-policy.md).
C# uses `ArcForges.Contracts.PublicApi` with a gRPC-Web channel in the consuming
application. The retained Hello fixture also tests native gRPC for compatibility;
that fixture does not select the public business transport. The package has no native binaries, service
implementation, UI, persistence or build-time compiler dependency.

`@arcforges/proto` contains messages and service descriptors. Its TypeScript
compile has only the ES library, so it cannot accidentally require DOM or Node
types. The runtime dependency is protobuf-es. Web uses these generated types; browser runtime and transport behavior still
require application integration tests.

`@arcforges/api-client` is a small gRPC-Web transport factory using the generated
service descriptor. The caller supplies the endpoint/fetch options and owns
authentication. Android consumes the Kotlin artifacts and explicitly selects
binary gRPC-Web for public business ingress. Native gRPC remains an explicitly
labelled Hello compatibility fixture, not an alternative product configuration.

`contracts-proto` contains Java/Kotlin lite messages, `contracts-client` contains
Java-lite service bindings and coroutine stubs, `contracts-connect-client`
contains Connect-Kotlin service interfaces and coroutine clients, and `contract-fixtures` contains
the same JSON wire cases used by C#/TS plus a resource accessor. All use group
`io.github.arcforges`. The caller owns channel/transport configuration; the client
does not impose OkHttp on a JVM server or create a global channel. The Connect
client uses the same proto classes and depends on Connect-Kotlin core. The caller
adds OkHttp and the Google Java lite serialization strategy and explicitly selects
`NetworkProtocol.GRPC_WEB` for the public product. The Hello fixtures also test
`GRPC`; the Connect protocol default is not supported
by the ASP.NET fixture. This extension covers unary Hello only.

The seven package identities are listed in the repository README. Their Hello
namespaces are examples, not completed PublicApi business
contracts. Do not add production rules by treating this demo as their design.

## Dependency and package discipline

The root npm workspace has one lock. Every .NET project has a committed lock and
uses central versions. Gradle uses a pinned wrapper/version catalog, strict
locks for every resolvable configuration and checksum verification for plugins,
generators and dependencies. Generator/runtime upgrades update pins and locks together,
regenerate sources and pass both consumer platforms. Generated code is never
edited manually. No submodules or cross-repository source references are allowed.

Packing builds one immutable candidate set. npm first-party dependency versions
are rewritten only in a temporary staging directory; source manifests and their
lock stay unchanged. The API client pins the exact proto candidate version.
NuGet contains generated .NET assemblies and runtime dependency references, not
Grpc.Tools or an embedded compiler. Hash verification checks identity, contents,
metadata, licences and the expected runtime dependency set.

The independent consumer copies only the demo application's source, configuration
and candidate archives into an OS temporary directory. It replaces the demo's
producer ProjectReference with a package reference. Fresh NuGet/npm/Gradle caches and a
source-mapped local NuGet feed force use of the candidate package. npm installs
both candidate tarballs. Each consumer first resolves its ephemeral dependency
lock, then restores in locked mode; these consumer locks are retained as evidence.
Two independent Kotlin applications restore the four Maven publications from an
exclusive local repository for `io.github.arcforges`, then run against the same
C# host. The Connect consumer has no grpc-kotlin client dependency and exercises
HTTP/1.1 gRPC-Web with an `/api` prefix and native HTTP/2 gRPC. Their committed
third-party locks/checksums are reused; only the exact, independently
hash-verified first-party candidate is excluded from static locks/checksums. No
producer classes or Gradle caches are copied into that consumer.

Maven Central requires main/source/documentation JARs, POM metadata and detached
PGP signatures. Gradle prepares the unsigned repository and API documentation in
the candidate. After Verify, a separate signing-only Gradle build signs those
files in memory; it has no source sets or dependencies and cannot rebuild them.
The Portal upload uses automatic publication and retains an identity-bound
deployment receipt for recovery. Public JAR/POM/module byte comparison closes
publication; search indexing is not the gate.

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
Build tools are not shipped in public packages. The gRPC Kotlin dependency
includes `javax.annotation-api` under its offered CDDL-1.1 option; that dependency
is referenced rather than copied. Gradle wrapper code retains its upstream
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

Keep existing v1 field numbers/types and RPC identities stable; reserve removed
field numbers/names and introduce a reviewed versioned API for incompatible
behavior. All current releases are prerelease candidates. A normal main merge
increments the package build version, not the protobuf wire namespace.

This bootstrap checks regeneration, a fixed field-number fixture, actual binary
RPC success/error behavior and the package dependency/metadata closure. It does
not implement the future production descriptor compatibility gate, full business
validation catalogues, Android app/device behavior, authentication, browser CORS integration,
Cloud deployment or production AOT server acceptance. Those remain governed by
the accepted design and implementation work packages.
