# Contract and package boundaries

## Authored source and generated output

`public/proto` is the authority for the public wire format. The current example
is `arcforges.hello.v1.HelloService/SayHello`, with a string name and string reply.
The demo server returns `Hello, <name>!` and rejects an empty name with
`INVALID_ARGUMENT`; all other strings, including whitespace and Unicode, are
preserved. This deliberately small rule belongs to the example, not a product.

`eng/Codegen` restores the pinned Grpc.Tools package. Its protoc generates both
C# (with the matching gRPC C# plugin) and TypeScript (with protoc-gen-es).
Generated C# lives in `src/public/dotnet/ArcForges.Contracts.PublicApi/Generated`;
TS lives in `src/public/ts/proto/src/gen`. Generated sources are committed so a PR
can review both schema and API changes. CI regenerates into a temporary directory
and fails if the committed files differ. The binary descriptor is built alongside
the bindings and distributed in both schema packages.

The .slnx contains the public library, code generation tool restore project and
two small test applications. The test host is an ordinary ASP.NET Core process
with explicit service registration and loopback gRPC/gRPC-Web listeners. It is
never packaged as a product/server deliverable.

## Public consumers

C# uses `ArcForges.Contracts.PublicApi` and selects its normal gRPC channel in
the consuming application. The package has no native binaries, service
implementation, UI, persistence or build-time compiler dependency.

`@arcforges/proto` contains messages and service descriptors. Its TypeScript
compile has only the ES library, so it cannot accidentally require DOM or Node
types. The runtime dependency is protobuf-es. The same generated public types
are intended for Web and RN; runtime/polyfill/transport behavior must still be
verified in each environment.

`@arcforges/api-client` is a small gRPC-Web transport factory using the generated
service descriptor. The caller supplies the endpoint/fetch options and owns
authentication. RN will consume the shared descriptors through its selected
Hermes transport; that adapter is intentionally outside this bootstrap.

The initial three package identities follow the accepted ArcForges package
registry. Their Hello namespaces are examples, not completed PublicApi business
contracts. Do not add production rules by treating this demo as their design.

## Dependency and package discipline

The root npm workspace has one lock. Every .NET project has a committed lock and
uses central versions. Generator/runtime upgrades update pins and locks together,
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
producer ProjectReference with a package reference. Fresh NuGet/npm caches and a
source-mapped local NuGet feed force use of the candidate package. npm installs
both candidate tarballs. Each consumer first resolves its ephemeral dependency
lock, then restores in locked mode; these consumer locks are retained as evidence.
This does not substitute an application source reference for an artifact test.

## Licensing

| Boundary                                            | Licence                             |
| --------------------------------------------------- | ----------------------------------- |
| Root tooling/configuration and `eng/`               | AGPL-3.0-only, root LICENSE         |
| `public/` authored schema                           | Apache-2.0, public/LICENSE          |
| `src/public/` generated code and client entry point | Apache-2.0, src/public/LICENSE      |
| `tests/public/` reusable example applications/tests | Apache-2.0, tests/public/LICENSE    |
| `fixtures/public/` reusable wire examples           | Apache-2.0, fixtures/public/LICENSE |

The original root LICENSE remains intact. Generation does not relicense authored
schemas; generated bindings follow the public source boundary. Package metadata,
embedded LICENSE/NOTICE and SBOM must agree. The SBOM inventories the resolved
runtime closure for each deliverable; source metadata identifies the dependency
locks used to produce it. Build tools are not shipped in public packages.

## Compatibility and limits

Keep existing v1 field numbers/types and RPC identities stable; reserve removed
field numbers/names and introduce a reviewed versioned API for incompatible
behavior. All current releases are prerelease candidates. A normal main merge
increments the package build version, not the protobuf wire namespace.

This bootstrap checks regeneration, a fixed field-number fixture, actual binary
RPC success/error behavior and the package dependency/metadata closure. It does
not implement the future production descriptor compatibility gate, full business
validation catalogues, RN transport, authentication, browser CORS integration,
Cloud deployment or production AOT server acceptance. Those remain governed by
the accepted design and implementation work packages.
