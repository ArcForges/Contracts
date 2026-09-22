# @arcforges/api-client

A typed gRPC-Web client entry point using the generated `@arcforges/proto`
service descriptor. This first prerelease implements only the Hello World
packaging example; it contains no business logic or production authentication.

```ts
import { createHelloClient } from "@arcforges/api-client";

const client = createHelloClient({ baseUrl: "http://localhost:50052" });
const reply = await client.sayHello({ name: "World" }, { timeoutMs: 5000 });
console.log(reply.message);
```

`createPublicGrpcWebTransport` is the public business transport: binary gRPC-Web
only, unknown fields retained and the shared 100-level nesting bound. It refuses
`useBinaryFormat`, `jsonOptions` and `binaryOptions` overrides. The declared HTTP
exception records have strict codecs such as `tryParsePartReceiptJson` and
`serializePartReceiptJson`; they enforce the schema byte limit, UTF-8, JSON depth 32,
duplicate-property and integer-lexeme rules before the closed schema check.

The endpoint must serve gRPC-Web. Browser cross-origin access also requires
server CORS configuration. The demo host binds to loopback for tests.

Android uses the separately published Kotlin artifacts with binary gRPC-Web.
This package is the TypeScript Web client; it does not provide a mobile runtime.

Apache-2.0. [Source and full setup](https://github.com/ArcForges/Contracts).
