# ArcForges.Contracts.Fleet

Generated public ArcForges fleet contracts (`arcforges.fleet.v1`): the cloud fleet API for nodes (node credential), web and Android (account session) and the unauthenticated sign-in flow endpoints, carried as binary gRPC-Web through the Worker ingress.

`public/proto/arcforges/fleet/v1/fleet.proto` is a byte-identical adoption of the ArcForges-Design specification (recorded in `eng/flagship-contracts.json`). It imports `arcforges.node.v1`, so this package depends on `ArcForges.Contracts.Node`. `ContractServices.All` lists the three generated service descriptors; `ArcForges.Contracts.Fleet.Shapes.ContractShapeValidation` checks the declared wire shape of the package's messages and their field closure.

This package contains generated contracts only: no listener, transport, authorization or implementation.

Apache-2.0. Public accessibility does not authorize importing internal protocols.
