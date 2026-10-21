# ArcForges.Contracts.Node

Generated public ArcForges node contracts (`arcforges.node.v1`): the local node API that the CLI, Desktop, MCP adapter, hook handler and probe call over the node's local gRPC endpoint.

The 20 schema files under `public/proto/arcforges/node/v1` are byte-identical adoptions of the ArcForges-Design specification (`docs/contracts/proto`, recorded with their digests in `eng/flagship-contracts.json`). Each RPC carries its design annotation block (`auth`, `idempotency`, `deadline`, `stream`, `errors`, `locality`, optional `state`); error codes come from the design error catalogue, mirrored in `fixtures/public/af-con-01-error-catalogue.json`. `ContractServices.All` lists the generated service descriptors; `ArcForges.Contracts.Node.Shapes.ContractShapeValidation` checks the declared wire shape (field presence of `validate: required` fields and the nested Foundation rules). The remaining `validate:` comments are specification text that the service implementations enforce.

This package contains generated contracts only: no listener, transport, authorization or implementation. Service simple names such as `TaskService` repeat in `arcforges.publicapi.v1`, but the fully qualified gRPC names and C# namespaces differ (`ArcForges.Contracts.Node.V1`).

The WSL guest-link surfaces of `v1` (for example `ResourceService.ListGuestLinks`, `SetGuestLink`, `GetHostLink`, `TrustHost` and `NODE_ROLE_GUEST`) are retired by ArcForges-Design AD-0018 and kept only because `v1` is additive: new callers must not use them. The repository's `docs/consuming.md` lists them.

Apache-2.0. Public accessibility does not authorize importing internal protocols.
