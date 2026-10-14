# ArcForges.Contracts.Relay

Internal ArcForges relay contracts (`arcforges.relay.v1`): the protobuf frames that nodes, viewers, the `FleetHub` Durable Object adapter and the C# host exchange over the relay WebSockets. The package declares messages only, no gRPC service.

`internal/proto/arcforges/relay/v1/relay.proto` is a byte-identical adoption of the ArcForges-Design specification (recorded in `eng/flagship-contracts.json`). It imports `arcforges.fleet.v1` and `arcforges.node.v1`, so this internal package depends on the public `ArcForges.Contracts.Fleet` and `ArcForges.Contracts.Node`; no public package may reference it. `ArcForges.Contracts.Relay.Shapes.ContractShapeValidation` checks the declared wire shape.

This package contains generated contracts only: no WebSocket handling, token validation or implementation.

Apache-2.0. Public accessibility does not authorize importing internal protocols.
