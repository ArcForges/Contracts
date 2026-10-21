# ArcForges.Contracts.Peer

Internal ArcForges peer contracts (`arcforges.peer.v1`): the node-to-node protocol over mutually authenticated TLS.

**Retired: `GuestLinkService`** (the former host–guest link over a WSL bridge) and its messages `GuestHello`, `GrantRequest`, `GrantRelease`, `GuestUsageReport` and `GrantDecision`. ArcForges has no dedicated Windows–WSL integration ([AD-0018](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0018-native-platforms-without-wsl-integration.md)). The service stays declared and generated unchanged, so descriptors and field numbers remain compatible with the published `v1`, but no node serves or calls it and no new consumer may use it (see `docs/consuming.md` in the Contracts repository).

`internal/proto/arcforges/peer/v1/peer.proto` is a byte-identical adoption of the ArcForges-Design specification (recorded in `eng/flagship-contracts.json`). It imports `arcforges.node.v1`, so this internal package depends on the public `ArcForges.Contracts.Node`; no public package may reference it. `ContractServices.All` lists the six generated service descriptors; `ArcForges.Contracts.Peer.Shapes.ContractShapeValidation` checks the declared wire shape.

This package contains generated contracts only: no listener, certificate handling, pairing, authorization or implementation.

Apache-2.0. Public accessibility does not authorize importing internal protocols.
