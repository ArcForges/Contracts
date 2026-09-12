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

Main branch protection requires a PR, up-to-date checks and resolved review
conversations. Required checks are Verify, Dependency review, Secret scan, CodeQL
and the three language-specific CodeQL jobs. The required approval count is zero;
registry environments have no manual release approval gate.

[PR 1](https://github.com/ArcForges/Contracts/pull/1) validated implementation commit
`0de04b3d579a71d70d9541cddb1ed326a6100b66`:

- [CI run 34692732413](https://github.com/ArcForges/Contracts/actions/runs/34692732413)
  passed generation, compilation, archive/guard tests, both Windows/Linux JIT and
  Native AOT consumers, actual gRPC/gRPC-Web success/error calls and the Verify
  gate. Publication jobs were correctly skipped for the PR.
- [Security run 34692732422](https://github.com/ArcForges/Contracts/actions/runs/34692732422)
  passed dependency review, secret scanning and CodeQL for C#, TypeScript/JavaScript
  and Python.
- The immutable CI candidate is `1.0.0-ci.1.1`, built from GitHub's clean PR merge
  revision `da0bdb641d67192026c4c6de14313b96fc3002fc`. Its manifest and both consumer
  evidence archives were downloaded and inspected. This is CI artifact evidence,
  not a claim that version exists on a registry.

The evidence record itself was added after these runs; the implementation and
workflow files did not change when recording these results.

No registry upload, registry restore, browser rendering, Hermes/device operation,
production service AOT build or ArcForges business behavior has been verified by
the local results above. Registry identity setup and first publication require
the account configuration documented in releasing.md.
