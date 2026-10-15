# ArcForges.Contracts.Peer

Internal ArcForges peer contracts (`arcforges.peer.v1`): the node-to-node protocol over mutually authenticated TLS and the host-guest `GuestLinkService` over the WSL bridge.

`internal/proto/arcforges/peer/v1/peer.proto` is a byte-identical adoption of the ArcForges-Design specification (recorded in `eng/flagship-contracts.json`). It imports `arcforges.node.v1`, so this internal package depends on the public `ArcForges.Contracts.Node`; no public package may reference it. `ContractServices.All` lists the six generated service descriptors; `ArcForges.Contracts.Peer.Shapes.ContractShapeValidation` checks the declared wire shape.

This package contains generated contracts only: no listener, certificate handling, pairing, authorization or implementation.

Apache-2.0. Public accessibility does not authorize importing internal protocols.
