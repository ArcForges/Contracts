# Contracts bootstrap plan

This records the original C#/TS bootstrap. The [Kotlin extension plan](kotlin-artifacts-plan.md)
and current architecture/consuming documentation supersede its former RN direction.
This is revision-bound historical evidence, reviewed on 2026-09-20 against the
[current runtime authority](https://github.com/ArcForges/ArcForges-Design/blob/e2dd78058ce2d4bd1a8434a34d049bbc1158eacb/docs/architecture/30-runtime-and-source-ownership-policy.md); its original results are not current product requirements.

## Scope and decisions

Start from `b68633c6ef0a378cf82d0fb6e3d8716fc7ca7c73` in the independent
`codex/contracts-bootstrap` worktree. The primary checkout and other repositories
remain unchanged. This delivery establishes a runnable packaging foundation, not
the product contract catalogue or a production service.

- Author one Apache-2.0 `arcforges.hello.v1.HelloService` demo proto.
- Publish `ArcForges.Contracts.PublicApi`, `@arcforges/proto` and
  `@arcforges/api-client`. Consumers install packages; no submodules or sibling
  source references. The client package uses gRPC-Web; the C# binding supports
  native gRPC. No RN transport or product business rules are introduced.
- Use Apache-2.0 for ArcForges-authored repository source, generated bindings,
  examples, tooling, configuration and documentation, as well as package contents.
  Dependencies retain their own licences and notices.
- Pin .NET, Node, protobuf generators and dependencies. Both generators use the
  protoc supplied by the locked Grpc.Tools dependency. Commit dependency locks;
  regenerate, build and verify before packing.
- Build one candidate set, then restore/install its actual archives in isolated
  C# and TypeScript consumers on Windows and Linux. Exercise Hello over real
  gRPC and gRPC-Web, including a server error; include an AOT C# consumer proof.
- PRs validate only. Main pushes automatically assign
  `1.0.0-ci.<run-number>.<run-attempt>`. Registry jobs publish the tested archives
  after all required checks, using OIDC and separately enabled registry settings.
  npm uses `latest` for the newest published CI version, as updated in the release
  runbook. Stable releases are outside this demo bootstrap.
  A one-time npm bootstrap mode uses a temporary token to create the two package
  identities in CI, because npm requires existing packages before OIDC setup.
  Switch to OIDC and revoke that token after establishing package trust.

## Execution order

1. Add repository hygiene, contribution/security guidance, ownership, dependency
   updates and the solution/workspace structure.
2. Implement the proto, deterministic generation, package metadata and scripts.
3. Implement fixture and real package-consumer checks, then the ordered CI and
   registry jobs. Include hashes, descriptors, dependency notices and SBOMs.
4. Document local use, consumer setup, registry account/policy setup, npm's first
   publication, automatic subsequent releases and partial-release recovery.
5. Run local checks, inspect actual archives, open a PR and run GitHub CI. Record
   observed evidence separately from registry or product validation not performed.

## Acceptance and limits

The three archives contain generated code, licence/notices and correct exact
first-party dependencies. Generation is repeatable; independent consumers use no
producer source. A failed build or consumer gate cannot reach registry upload.
Missing registry setup is visibly skipped and never reported as publication.
No credentials enter Git. The primary checkout remains at its original commit.

This is not WP03 completion: production schemas, compatibility against a first
released product descriptor, validation projections, RN/Hermes, Cloud and business
acceptance remain in their existing implementation work packages.

## Completion

All five execution stages are complete. The actual three-package candidate,
Windows/Linux gRPC and gRPC-Web consumers, Native AOT C# consumers and security
checks passed. See [validation evidence](validation.md) for immutable run links
and the distinction between CI validation and registry/product operation.
The remaining user setup is registry account/policy authorisation, documented in
[the release runbook](releasing.md). No registry publication was performed.
