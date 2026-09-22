# @arcforges/proto

Generated public Protocol Buffers messages, shape validators and exact value
adapters, shared by TypeScript Web consumers. The selected public closure includes
Foundation, Notes scalar/query, Scope measurement, all owner-body variants and
events, alongside the retained `arcforges.hello.v1` packaging example. There are
no Node or DOM imports in this package and it does not implement networking.

Use `create(SayHelloRequestSchema, { name: "World" })`, `toBinary` and
`fromBinary` from `@bufbuild/protobuf`. Use the exported `HelloService`
descriptor with a compatible gRPC/gRPC-Web client transport.

`decodeContract(schema, bytes, limit)` and `encodeContract` apply the registry size
classes in `wireLimits` (4 MiB unary/helper, 256 KiB inline page, 32 KiB stream frame,
64 MiB large projection) and the root-plus-100 nesting bound, retaining unknown fields.
Refusals are `ContractSerializationError` values with `tooLarge`, `tooDeep` or
`malformed`. `contractServices` lists the generated services; nothing is discovered
at runtime.

Use `parseId` and `idToWire` to preserve an explicit identifier domain, bigint for
exact 64-bit values, and `notesDecimal`/`decimalParts` for Notes decimal boundaries.
The generated `is<Type>` functions check the current supported mutation profile.
`readProjection` and `preserveProjection` retain compatible unknown read data;
revalidate the actual message before a mutation. These checks do not authorize
access, query product state or execute numerical engines. See the
[Foundation API and coverage profile](https://github.com/ArcForges/Contracts/blob/main/docs/wp03-01-foundation.md).

The package ships ESM JavaScript, TypeScript declarations, the authored proto and
its descriptor set. Pin the exact version in your dependency manifest and lock
file. Android uses separately generated Kotlin artifacts from the same authored
proto; TypeScript codec validation does not establish Android runtime behavior.

Apache-2.0. See [the repository](https://github.com/ArcForges/Contracts) for
examples, licensing and release setup.
