# AFV2-API-01 — explicit V2 contract adoption

The three adopted specifications are pinned to ArcForges-Design
`493022fbf643b484665b2713c9eb8670f2fb2234`. Their exact source paths/digests and
new owner packages are in `eng/afv2-contracts.json`. Foundation v1, every published
v1 field number/meaning, ContentSandbox (`arcforges.local.sandbox.v1`), retired
package rows and historical descriptor/provenance evidence are preserved.

## Kept, adapted and added

- Keep every current v1 contract and exact compatible runtime/generator dependency.
- Adapt the existing inventory, C#/Go generators, access/provenance inventories,
  explicit descriptor lists, codec exchange and AOT probe for the new owners.
- Add two public C# packages and two packages inside the existing internal Go
  module. Blazor/browser-compatible clients use the same generated C# types;
  there is no new TypeScript SDK or HTTP JSON projection.
- Remove no schema, package version, independent product dependency or runtime.

The Design snapshot has no additional normative internal V2 proto. Local-only
CenterControl remains in the adopted sandbox.v2 namespace; a type's public
contract access does not widen its runtime locality. It is classified explicitly
alongside durable Node mutations, Center revocation, pure reads and transient
terminal acknowledgments. This is a closed inventory, not a dynamic dispatcher.

## Contract validation and boundaries

The authored V2 constraint shards preserve optional scalar presence and require
current mutation identity, owner epoch, CAS revisions and bounded typed input.
The generated helpers check live lease identity/epoch/generation/expiry and the
next unconsumed sequence. Consumed input never becomes a fresh write merely
because an acknowledgment was evicted. The 30 s/256 record/1 MiB volatile window
is explicit; no acknowledgment store, input transcript or durable terminal
GetOperation history is implemented here.

Safe path syntax, exact HTTPS origin syntax and complete known effect/retry
pairs are checked structurally. Authorization, actual OS path/root identity,
OS-specific environment comparison, grant narrowing, HMAC canonicalization,
durable deduplication, native effects and datastore recovery remain runtime
obligations of their owning tasks. Contract tests do not fake those outcomes.
UNKNOWN cannot become AFTER_TIME or a blind new-ID retry. Configure repair and
Delete recovery intent remain distinct; recovery IDs cannot silently become
fresh deletion plans. InspectTransfer is a read and never resubmits BeginExport.
COMPLETE materialization and `closed_at` remain separate fields and meanings.

V2 typed C#/Go codecs impose 1 MiB unary/metadata and 2 MiB chunk-carrier ceilings
before decode; single chunks cap at 1 MiB and output payloads at 64 KiB. Old v1
codec limits are unchanged. Unknown fields and enum values remain available on
compatible reads; strict current-profile validation does not authorize replay.

## Consumer retention

Use the committed `eng/v2-consumers/observed-20261116.json` inventory from BASE-01;
this task does not repeat or reinterpret a deployment/installed-package scan.
AI retains its published old npm pin; ArcNotes/ArcSlate/Web use PublicApi;
ArcScope uses Foundation/LocalRpc.Scope/PublicApi; Mobile uses Events/PublicApi/
Validation; DesktopPlatform uses Foundation/Events/PublicApi/LocalRpc and SDK
contracts. Current ArcForges still uses Node/Fleet/Relay/Foundation until its
explicit later cutover, and Cloud retains PublicApi/CloudInternal/Validation,
internal npm and the Go module until its migration. These flagship dependencies
are temporary migration consumers, not evidence that every old API is used only
by an independent product. Nothing here authorizes deletion of their contracts.

## Reproducible checks and delivery evidence

Use `python eng/contracts.py generate` and `generate --check`; never edit generated
outputs. The fixture `fixtures/public/afv2-api-01.json` contains independent binary
vectors, shared by `StructureTests` (`--afv2-api-01`), its linked Native AOT probe,
and Go `TestV2ContractVectors`. Explicit compiled descriptor lists and the existing
C#/Go/reference-codec exchange cover all fields, enums and oneof arms. The AOT
probe roots both new libraries and binds all seven new services explicitly.

Author diagnostics and required exact-head Linux verification/publication are
separate. The coordinator records their actual SHAs, receipts, review, merge and
normal common-version publication in Plan. Earlier author snapshots are not
relabelled as final-head or live product/runtime evidence. This repository change
applies no SQL, backup/restore, cutover, deployment or public activation.
