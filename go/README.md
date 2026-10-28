# ArcForges Contracts: Go bindings

`github.com/ArcForges/Contracts/go` holds the Go bindings of the ArcForges contracts for the ArcForges
center ([AD-0021](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0021-central-access-go-center.md)
§8). Every package is generated from the `.proto` files of this repository by `protoc-gen-go` and
`protoc-gen-connect-go`; nothing is written by hand.

| Go package                                                  | Proto package             | Contract access |
| ----------------------------------------------------------- | ------------------------- | --------------- |
| `arcforges/foundation/v1` (`foundationv1`)                  | `arcforges.foundation.v1` | public          |
| `arcforges/hello/v1` (`hellov1`, `hellov1connect`)          | `arcforges.hello.v1`      | public          |
| `arcforges/publicapi/v1` (`publicapiv1`, `…connect`)        | `arcforges.publicapi.v1`  | public          |
| `arcforges/catalog/v1` (`catalogv1`, `catalogv1connect`)    | `arcforges.catalog.v1`    | public          |
| `arcforges/node/v1` (`nodev1`, `nodev1connect`)             | `arcforges.node.v1`       | public          |
| `arcforges/fleet/v1` (`fleetv1`, `fleetv1connect`)          | `arcforges.fleet.v1`      | public          |
| `arcforges/relay/v1` (`relayv1`)                            | `arcforges.relay.v1`      | internal        |
| `arcforges/operator/v1` (`operatorv1`, `operatorv1connect`) | `arcforges.operator.v1`   | internal        |

The module's contract access is **internal**: it is published for first-party ArcForges services (the
center), not as a business-client SDK. C# NuGet stays the only first-party SDK channel for business
clients (CON.40). `relayv1` and `operatorv1` hold internal contracts; Go's `internal/` directory rule
is not used for them because the center is another module, so their boundary is the contract-access
policy recorded in `eng/contract-packages.json`.

## Versions

Each publication of the C# packages at `1.0.0-ci.<run>.<attempt>` (and each canonical `vX.Y.Z`
release) tags this module `go/v<same version>` on the same commit after the NuGet packages are
published. Pin the exact version and commit `go.sum`:

```text
go get github.com/ArcForges/Contracts/go@v1.0.0-ci.12.1
```

The version above is illustrative. See [docs/consuming.md](../docs/consuming.md#go-center-bindings) for
the protocol and serialization rules a Go consumer applies (binary protobuf only, the WP03.02 limits).

## Development

Never edit the generated packages. Change the `.proto` files and run, from the repository root:

```text
python eng/contracts.py generate
python eng/contracts.py go check
```

`go/tools` is a separate, never published module that pins the generators and analysers. Both modules
are resolved read-only (`GOFLAGS=-mod=readonly`) with the Go release pinned in `toolchain.json`
(`GOTOOLCHAIN=local`). See [docs/engineering-controls.md](../docs/engineering-controls.md).
