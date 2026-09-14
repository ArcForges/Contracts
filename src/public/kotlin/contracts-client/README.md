# ArcForges contracts-client

`io.github.arcforges:contracts-client` supplies generated Java-lite gRPC bindings
and the Kotlin coroutine client/server base for the Hello World example. It
depends on the exact same release of `contracts-proto`. Apache-2.0.

Supply an `io.grpc.Channel` to
`io.github.arcforges.contracts.hello.v1.HelloServiceGrpcKt.HelloServiceCoroutineStub`.
Android callers normally use `io.grpc:grpc-okhttp`. The application owns channel
creation, TLS, authentication, deadlines, coroutine lifecycle and shutdown.
No global channel, insecure production endpoint or authentication policy is
installed by the generated library. This is native gRPC over HTTP/2.

Use Java 17 and Kotlin 2.4.20 or a compatible newer compiler. See
[installation and a complete call example](https://github.com/ArcForges/Contracts/blob/main/docs/consuming.md).
