# WP03.01 foundation contracts: implementation and evidence

Status: pre-merge implementation record. Source, targeted local validation and
independent provenance review are complete. Applicable PR CI, merge and normal
publication remain required acceptance gates. This record does not establish a
released WP03.01 candidate or acceptance of later product behavior.

Authority: the [WP03.01 implementation profile](https://github.com/ArcForges/ArcForges-Design/blob/5e202ff10f3c218d9e159029579ca535c641169b/docs/assurance/wp03-01-foundation-contract-profile.md),
registry04, annex10 and P2-017. The accepted upstream Contracts source is
`30ddcad2bcb3634e089abb5e29d6c9ce05d38386`; its WP03.00 publication remains
historical evidence. This contribution does not upgrade downstream consumer pins.

## Implemented source boundary

| Deliverable                      | Source and meaning                                                                                                                                                                                                                                                                                                                         |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Complete selected schema closure | [`eng/foundation-inventory.json`](../eng/foundation-inventory.json) binds the fixed seeds and recursive field dependencies: 148 messages, 10 enums, all 16 AggregateBody branches. Counts summarize the inventory; field completeness and ownership are the acceptance rules.                                                              |
| Stable Foundation owner          | [`foundation.proto`](../public/proto/arcforges/foundation/v1/foundation.proto) contains 32 messages, preserving existing names/tags and adding exact values, pagination, ranges, origin and shared references.                                                                                                                             |
| Public domain projection owner   | [`content.proto`](../public/proto/arcforges/publicapi/v1/content.proto) contains 116 public messages. It defines Notes query/measurement and owner-body records without adding service registration or operation envelopes.                                                                                                                |
| Wire/profile validation          | [`constraints.json`](../public/proto/constraints.json), generator rules and semantic helpers produce explicit C#/TS validation. Shape, presence, oneof, bounds, profile keys and self-contained relationships remain separate from owner authorization or execution.                                                                       |
| Safe value boundaries            | [`value-boundaries.json`](../public/proto/value-boundaries.json) selects 69 ID domains. C# typed records and TypeScript brands preserve ID domains, exact numbers, revision/token kinds and opaque cursors; authored adapters handle decimal coefficient/scale and rational time conversion.                                               |
| Independent evidence inputs      | [`wp03-01.json`](../fixtures/public/wp03-01.json) contains 476 cases: 314 positive and 162 negative, covering 148 records, all 82 selected oneof branches, 16 AggregateBody branches, 45 error-category mappings, 10 hand-specified binary vectors and 10 original-profile scenario groups. These are independently authored expectations. |
| Offline suites                   | [`FoundationCases.cs`](../tests/StructureTests/FoundationCases.cs), [`foundation.test.mjs`](../tests/public/foundation.test.mjs) and [`foundation-types.ts`](../tests/public/foundation-types.ts) exercise semantic rejection, binary round trips, C#/TS exchange and domain-assignment compilation failures.                              |

All existing package identities and public/internal access boundaries remain in
place. Public TypeScript and Java/Kotlin generation include the selected public
closure; the .01 required semantic round-trip gate is C#/TS. Helpers use generated
wire types and do not introduce handwritten alternative serializable DTOs.

## Consumer use

Use the generated message at the serialization boundary and the explicit safe
value at an application boundary. For example, C# `DocumentId.FromWire(Id)` and
`DocumentId.ToWire()` use canonical UUID network bytes; a `ResourceId` cannot be
implicitly substituted. TypeScript exposes the equivalent functions from the
public package entry point:

```typescript
import { parseId, idToWire, notesDecimal, decimalParts } from "@arcforges/proto";

const documentId = parseId("DocumentId", "00112233-4455-6677-8899-aabbccddeeff");
const wireId = idToWire("DocumentId", documentId);
const exact = decimalParts(notesDecimal("0.000000001"));
// exact.coefficient === 1n; exact.scale === 9
```

`CloudRevision` accepts positive committed int64 values; its explicit new-root
precondition preserves present zero without calling it a committed revision.
`NativeRevision`, `LocalNotesToken` and `DeliverySequence` remain distinct.
TypeScript uses bigint throughout these paths. Shared exact decimals preserve
declared scale, while C# `ExactDecimal.FromNotes` and TypeScript `notesDecimal`
apply the stricter Notes canonical form. Rational conversion uses wide integer
intermediates and refuses an unrepresentable target tick or overflow.

C# `ContractShapeValidation.IsValid(message)` and TypeScript `is<Type>(message)`
check the current known mutation profile. C# `ReadProjection<T>.Parse` and
TypeScript `readProjection` can preserve compatible unknown response data with an
explicit known-profile observation. That observation belongs to the decoded
snapshot; it is not authority and must not be reused as proof that a subsequently
changed message is valid. Revalidate the actual mutation input before dispatch.

The validators check content-origin ordering/lineage bounds, Notes literal/AST
shape and definition bindings, measurement family/value/unit/threshold/channel
relationships and the selected recursive owner records. They do not establish
current owner permissions, actual resource-byte hashes, remote availability or
committed side effects. Notes queries are not evaluated here; numerical profile
outputs are independent codec fixtures, not recomputed DSP results. Origin
lifecycle examples do not execute save/export/import transactions or live AI.

## Validation and publication record

| Evidence                                                     | Current observation                                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Authored/generated diff review and provenance/import closure | Complete independent source/generated review findings were fixed. Current generated-source/provenance inventory passed and binds repaired source snapshot `af7b6cca5e14a51735512d283b03d3ae9d96d170` through the immutable bindings-r4 successor.                                                                                                                                                                          |
| Generation and selected descriptor inventory                 | Deterministic C#/TS/Java/Kotlin regeneration passed (`artifacts/generate-check.log`). All 8 targeted inventory negative tests passed.                                                                                                                                                                                                                                                                                      |
| C#/TS positive/negative cases and independent binary oracles | Both offline runners passed all 476 cases, covering 148 records, all 82 selected oneof branches, 16 owner-body branches, 45 error categories and 10 binary oracles. Logs: `artifacts/foundation-csharp.log` and `artifacts/foundation-typescript.log`.                                                                                                                                                                     |
| Bidirectional C#/TS exchange                                 | All 314 positive cases passed C# to TypeScript and TypeScript to C# validation. Exchange identity uses current fixture bytes and rejects missing or duplicate case IDs. Return verification: `artifacts/foundation-exchange.log`.                                                                                                                                                                                          |
| TypeScript negative domain/revision compilation cases        | `npm test` passed the existing 4 offline tests and strict `tsc --noEmit` checks, including the expected domain/revision assignment errors. Log: `artifacts/ts-existing-tests.log`.                                                                                                                                                                                                                                         |
| Managed and TypeScript compilation                           | C# solution Release build passed with 0 warnings and 0 errors; TypeScript workspace build passed. Logs: `artifacts/dotnet-build.log` and `artifacts/ts-build.log`. Local C# execution used existing SDK `10.0.401` through a local adapter; committed `global.json` and CI retain `10.0.400`. This is not CI-equivalent SDK evidence.                                                                                      |
| Kotlin compilation and assembly                              | Cached JDK 17 `assemble`/`check` passed for the retained modules (`artifacts/kotlin-build.log`). Test tasks reported `NO-SOURCE`; no Kotlin runtime or third-language semantic conformance result is claimed.                                                                                                                                                                                                              |
| Source-access offline regressions                            | All 14 tests passed (`artifacts/access-tests.log`). The compiled access audit passed for 174 total contract types, 526 distribution files and 22 packages. The Apache source boundary passed for 30 projects; naming checks found no exceptions or findings.                                                                                                                                                               |
| Dokka documentation and provenance successor                 | The r6 repair passed one cached offline regeneration after the CI oracle failure exposed wrong inherited method links. All 14,017 API members and 152 prior API-marker pages remain; 453 protobuf pages changed, with no pages removed. The 481 inputs, 42 fixed resources, 10 excluded fonts and 81 third-party components remain bound. Six focused admission tests passed; Linux candidate validation remains required. |
| Applicable latest-head PR CI/security                        | Pending. Existing configured checks remain required.                                                                                                                                                                                                                                                                                                                                                                       |
| Expected source merge and complete normal publication        | Pending; no WP03.01 candidate coordinate or successful upload is claimed.                                                                                                                                                                                                                                                                                                                                                  |
| Clean primary fast-forward                                   | Pending after accepted merge.                                                                                                                                                                                                                                                                                                                                                                                              |

Independent review corrected mixed-unit common threshold binding, cursor-result
agreement, fixed-binary field/checksum overlap, complete date/link matching and
exchange case uniqueness. The independent fixtures now cover every selected
union branch and explicitly preserve the registry's Unicode boundary oracle;
both language suites exercise exact rational conversion and unknown-read helpers.

The documentation provenance record freezes generated-source inputs and admitted
API output. The expanded schema used r5; the r6 successor repairs the observed
Dokka cross-type inherited-method aliases by suppressing inherited members only
in the protobuf documentation publication. All declared record/field markers,
including `Id.hasValue`, remain. Exact page/resource hashes and the mandatory
`publicApi` marker field still fail closed; no normalization was weakened.
Historical profiles, source records and dependency receipts remain unchanged.
The normal candidate producer still validates packaged documentation before publication.

The first PR run exposed a polynomial URL regex in generated TypeScript. The
authoritative C#/TS helpers now validate schemes, nonempty authority/body and
whitespace with linear scans. Focused tests passed 96 URL expectations in each
language, including a 100,000-character authority and rejected whitespace suffixes;
the targeted C# build passed with no warnings/errors. Logs are
`artifacts/link-fix-ts-tests.log`, `artifacts/link-fix-csharp-build.log` and
`artifacts/link-fix-csharp-tests.log`. The original 476 fixture cases are unchanged.
The configured latest-head suite and CodeQL remain required.

The same PR run's redacted secret scan reported public Dokka SHA256 rows as
generic API keys. Reviewed exceptions bind only the exact public source paths,
field rows and hashes under that rule. Default scanning remains enabled, with
targeted tests guarding the exception boundaries. Bindings-r4, Dokka-r6 and
dependency receipt `wp03-01-r2` bind the reviewed CI repairs without changing any
of the 140 admitted third-party coordinates or package identities.

The coordinated offline exchange executes the full C# suite once with
`--foundation-exchange`, the TypeScript suite once with `--exchange`, then the C#
`--verify-foundation-exchange` mode validates only the returned TypeScript bytes.
The final mode does not repeat the full passing suite. Tests are repeated only
for a relevant source change or a concrete unresolved finding.

Candidate production checks actual package contents once and retains the required
handoff identity, licences, provenance and signatures. Required provider results
establish publication; there is no public-byte polling or post-merge download,
installation, hash-audit or runtime-test cycle. NuGet/npm use the normal allocated
candidate version and Maven retains its separate SNAPSHOT channel.

## Coverage limits and later gates

WP03.02 owns complete serialization/AOT/registration posture. WP03.03 retains the
full capability/descriptor/resource/Sync admission semantics and its negatives,
even where this step generates a required shared record early. WP03.04 retains
helper/in-process closure. WP03.05 retains all operation authorization/scope
fields, stream/history/target schemas and complete three-language conformance;
.06/.07/.90 retain their compatibility, signed-format and stage acceptance gates.
WP04 still owns application foundation value packages.

No macOS, physical-device/emulator, GUI/browser E2E, live service/inference,
installed-package consumer or public-release installation/upgrade result is
claimed. This step does not run Notes query engines, Scope numerical engines,
native/media effects, storage transactions, export/import pipelines or Cloud
authorization. Generation, compilation, fixture validation and registry publication
are distinct evidence classes; none establishes commercial product acceptance.
