# ArcForges.Contracts.PublicApi

Generated C# protobuf messages and gRPC client/server bindings for the initial
`arcforges.hello.v1.HelloService` example. Targets .NET 10 and contains no service
implementation or native binary. This prerelease does not implement ArcForges
product APIs.

Install an exact published version, then use
`ArcForges.Contracts.Hello.V1.HelloService.HelloServiceClient` with
`Grpc.Net.Client`. A server derives from `HelloService.HelloServiceBase` and
registers it explicitly. An empty name returns gRPC `InvalidArgument` in the
example server.

Authored schemas and generated bindings are Apache-2.0.
Source, examples and release instructions:
[ArcForges/Contracts](https://github.com/ArcForges/Contracts).
