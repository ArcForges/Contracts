# Installing and using the packages

Choose a version whose main CI candidate and relevant registry job both passed.
The release manifest supplies the exact common version. An Actions artifact named
candidate is a tested archive; it becomes a registry package only after upload.
Versions such as `1.0.0-ci.12.1` below are illustrative, not an assertion that
this version exists.

## C#

A repository using central package management adds these entries to
`Directory.Packages.props`:

```xml
<Project>
  <PropertyGroup>
    <ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <PackageVersion Include="ArcForges.Contracts.PublicApi" Version="1.0.0-ci.12.1" />
    <PackageVersion Include="Grpc.Net.Client" Version="2.83.0" />
  </ItemGroup>
</Project>
```

The application's project references them without inline versions:

```xml
<ItemGroup>
  <PackageReference Include="ArcForges.Contracts.PublicApi" />
  <PackageReference Include="Grpc.Net.Client" />
</ItemGroup>
```

Enable `RestorePackagesWithLockFile`, commit `packages.lock.json`, and use
`dotnet restore --locked-mode` in CI. nuget.org is the public source; no publishing
credentials are required for a consumer.

```csharp
using ArcForges.Contracts.Hello.V1;
using Grpc.Net.Client;

using var channel = GrpcChannel.ForAddress("http://localhost:50051");
var client = new HelloService.HelloServiceClient(channel);
var reply = await client.SayHelloAsync(
    new SayHelloRequest { Name = "World" },
    deadline: DateTime.UtcNow.AddSeconds(5));
Console.WriteLine(reply.Message);
```

The local example server can be run from the Contracts checkout after restore:

```text
dotnet run --project tests/public/HelloHost -- --grpc-port 50051 --web-port 50052
```

That server is a loopback test fixture. A real application supplies its own
service implementation, TLS endpoint and authentication.

## TypeScript / Web

The default npm package page and a fresh install without a version follow
`latest`, which CI advances to the newest published main build. Check that both
npm publication results passed and use their common version; registry uploads
are not an atomic operation across packages. Moving `latest` does not rewrite an
existing application's dependency version or lock file.

Install exact package versions and commit the application's lock:

```text
npm install --save-exact @arcforges/proto@1.0.0-ci.12.1 @arcforges/api-client@1.0.0-ci.12.1
```

```ts
import { createHelloClient } from "@arcforges/api-client";

const client = createHelloClient({ baseUrl: "http://localhost:50052" });
const reply = await client.sayHello({ name: "World" }, { timeoutMs: 5000 });
console.log(reply.message);
```

The endpoint serves gRPC-Web. For a browser on another origin, the application
must configure CORS; the bootstrap test uses Node fetch against loopback and
does not claim a browser integration test.

For serialization alone, use `@arcforges/proto` with `@bufbuild/protobuf`.
Generated service descriptors also work with the caller's compatible transport.

## React Native / Mobile

Install the same `@arcforges/proto` version. C# and RN do not share a compiled
assembly; they share the source schema, with generated bindings for each language.
Web and RN share the actual TS message/service-descriptor package.

Do not add a second Mobile proto tree. The future `@arcforges/rn-transport` owns
the Hermes gRPC-Web framing/fetch adaptation. This bootstrap has neither a mobile
app nor a device test; installing the types alone does not prove RN networking.

## Updating a dependency

Select an accepted new version, update the explicit manifest/central version and
lock, then run the consuming application's tests before merging. Dependabot can
open these update PRs in each consuming repository; the producer cannot configure
an unrelated repository's update policy. Do not use floating `*` versions or a
moving dist-tag as a committed production dependency.

No consumer needs protoc, Git submodules, a checkout of Contracts or access to
DesktopPlatform. NuGet/npm download the published dependencies normally.
