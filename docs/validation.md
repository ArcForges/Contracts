# Bootstrap validation evidence

## Observed locally

On Windows x64, the bootstrap has passed:

- Locked .NET/npm dependency restoration with the pinned toolchain.
- Generation of C# and TypeScript from the same Grpc.Tools protoc.
- Regeneration comparison, .NET and strict TS builds, and ASCII/Unicode/wire
  field/malformed-payload tests.
- Creation and inspection of the actual NuGet and two npm archives, including
  public licences, runtime dependencies, source metadata, descriptor and hashes.
- Installation into an independent temporary directory with fresh caches.
- Real C# gRPC and TS gRPC-Web calls, including the server's InvalidArgument error.
- Native AOT publication and execution of the C# package consumer.

The initial local candidate was built from the bootstrap worktree and is marked
dirty/development; it is not eligible for registry upload. The generated evidence
lives in ignored `artifacts/evidence/win-x64`.

## CI and external evidence

GitHub repository setup was verified: the nuget/npm environments accept only
main and have no approval timer/reviewer gate; Actions defaults to read-only.
Private vulnerability reporting, Dependabot security updates, secret scanning
and push protection are enabled. NUGET_USER is set to the existing username;
NuGet publication and npm publication remain disabled pending registry setup.

The PR CI matrix will execute the same archive consumer on Windows and Linux.
Run links and final results are recorded after that execution. CodeQL, dependency
review and secret scanning are separate checks.

No registry upload, registry restore, browser rendering, Hermes/device operation,
production service AOT build or ArcForges business behavior has been verified by
the local results above. Registry identity setup and first publication require
the account configuration documented in releasing.md.
