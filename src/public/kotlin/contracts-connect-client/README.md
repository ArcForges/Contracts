# ArcForges Connect-Kotlin client

Generated Hello service interface and coroutine client for Android/JVM. This
Apache-2.0 package shares the exact matching `contracts-proto` messages and uses
Connect-Kotlin 0.9.0. It adds no server implementation or duplicate message types.

The application supplies a `ProtocolClientInterface` to `HelloServiceClient` and
owns its HTTP transport, endpoint, TLS, authentication, timeouts and lifetime.
For the Cloudflare Worker ingress, explicitly select `NetworkProtocol.GRPC_WEB`
with OkHttp and `GoogleJavaLiteProtobufStrategy`. Native HTTP/2 gRPC endpoints
can use `NetworkProtocol.GRPC`. The default Connect protocol does not target an
ASP.NET gRPC service.

See [installation and configuration](https://github.com/ArcForges/Contracts/blob/main/docs/consuming.md#kotlin--android)
for a complete example. The existing `contracts-client` provides the separate
grpc-kotlin channel API and remains available. The current Hello contract is
unary; these JVM package checks do not certify Android devices or Cloud deployment.
