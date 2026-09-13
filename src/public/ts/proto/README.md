# @arcforges/proto

Generated public Protocol Buffers messages and service descriptors, shared by
TypeScript Web and React Native consumers. This first prerelease contains only
the `arcforges.hello.v1` packaging example. There are no Node or DOM imports in
this package and it does not implement networking.

Use `create(SayHelloRequestSchema, { name: "World" })`, `toBinary` and
`fromBinary` from `@bufbuild/protobuf`. Use the exported `HelloService`
descriptor with a compatible gRPC/gRPC-Web client transport.

The package ships ESM JavaScript, TypeScript declarations, the authored proto and
its descriptor set. Pin the exact version in your dependency manifest and lock
file. React Native transport/Hermes validation is a separate delivery; using the
same generated types does not by itself verify a mobile runtime.

Apache-2.0. See [the repository](https://github.com/ArcForges/Contracts) for
examples, licensing and release setup.
