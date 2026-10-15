# ArcForges.Contracts.PublicApi

Public protobuf bindings and declared HTTP exception records.

Apache-2.0. This WP03.00 candidate contains the selected complete record slices; full service and semantic coverage remains in later WP03 substeps. Public accessibility does not authorize importing internal protocols.

## Operation metadata

The package carries `operations/operation-metadata.v1.json` at its root. The file
is an `operation-metadata.v1` document (`schemaVersion` and `operations`) holding
every operation row whose `surface` is `public`, whose `kind` is `proto` and whose
`binding` names a method of a service in this package's descriptor closure
(Foundation and PublicApi). Each row is value-identical to its gated row in the
Contracts `eng/operations` exports, with the same fields in the same order. Rows
for private-helper, in-process, internal or operator surfaces, and public rows
whose service lives outside this closure, are not included.

Rows are ordered by `operationId` in ordinal (byte) order. The file is UTF-8 JSON
with LF line endings and is identical for every build of the same source revision.
The retained `arcforges.hello.v1.HelloService/SayHello` migration example has no
row.

The adopted flagship design service `arcforges.publicapi.v1.SupportAccessService`
(`support_access.proto`, AF-CON-01) has no row either: its methods are classified by
the design annotation block on each RPC (`auth`, `idempotency`, `deadline`, `stream`,
`errors`, `locality`), which `eng/check_operation_scope.py` validates against
`eng/flagship-contracts.json` and the flagship error catalogue.
