# Kotlin Hello over gRPC-Web

## Scope and findings

The current Android/JVM client contains grpc-kotlin stubs for native HTTP/2 gRPC.
It cannot call the current Cloudflare Worker gRPC-Web ingress. The Hello proto,
messages and RPC identity already fit both transports; no schema change is needed.
The consumer gate covers native Kotlin gRPC only, and publication/signing still
assumes three Maven modules.

This change is confined to Contracts and unary Hello. Cloud routing, the Android
application, authentication, streaming RPCs and the formal product design are
separate steps. PR validation does not publish or establish device/deployment
compatibility.

## Implementation plan

1. Add `io.github.arcforges:contracts-connect-client`, containing the generated
   coroutine service interface and implementation. Reuse `contracts-proto` at the
   exact candidate version. Preserve `contracts-client` and all existing APIs.
2. Pin Connect-Kotlin runtime and generator to 0.9.0 in the Gradle catalog. Resolve
   its executable generator JAR from Maven Central through existing dependency
   locks and checksum verification; use the same protoc and schema. Do not add a
   remote generation service or require protoc in consuming applications.
3. Keep endpoint, protocol, transport lifetime, TLS, timeouts and credentials in
   the caller. Document explicit `NetworkProtocol.GRPC_WEB` with OkHttp and the
   Google Java lite strategy. The library's default Connect protocol is not an
   ASP.NET gRPC endpoint. Also test explicit `GRPC` against native HTTP/2.
4. Extend the candidate, metadata, licence inventory, archive validation and
   signing path to four Maven publications / seven package identities. Use the
   existing main-only publishing job and credentials. Sign the tested files;
   never rebuild during publication.
5. Add a separate isolated Kotlin archive consumer without grpc-kotlin stubs.
   Install the candidate from the exclusive local Maven feed with strict
   third-party locks and checksums. Call the real C# fixture over HTTP/1.1
   gRPC-Web (including an `/api` base path) and HTTP/2 gRPC. Verify fixed Hello
   fixtures, Unicode/whitespace, protobuf types, RPC path/content type, and
   `INVALID_ARGUMENT`. Retain the original C#/TS/Kotlin/AOT checks.
6. Update active installation/release documentation and dependency grouping.
   Review the diff, commit, push and open a PR. Do not merge or publish in this
   step; inspect Windows/Linux consumer and security results on that PR.

## Closure conditions

- Regenerated files match committed output on CI and preserve the original proto.
- The new JAR has generated clients, sources, API documentation, correct exact
  dependencies and Apache-2.0 metadata; it contains no duplicate message classes
  or bundled third-party implementations.
- Candidate verification and real detached-signature tests cover all four Maven
  modules. Negative tests reject missing files and wrong first-party versions.
- Independent consumers pass both protocols against C#, with evidence recording
  the transport and explicitly excluding Android device and Cloud deployment.
- PR checks pass; existing main checkout, Cloud and Mobile remain untouched.

Upstream references: [Connect-Kotlin 0.9.0](https://github.com/connectrpc/connect-kotlin/releases/tag/v0.9.0),
[generation](https://connectrpc.com/docs/kotlin/generating-code/),
[client configuration](https://connectrpc.com/docs/kotlin/using-clients/).
