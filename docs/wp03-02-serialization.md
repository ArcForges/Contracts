# WP03.02 serialization posture: implementation and evidence

Accepted: the Design [WP03.02 completion receipt](https://github.com/ArcForges/ArcForges-Design/blob/7e56614ced01a12c84eb2047071d14399249ee90/docs/assurance/wp03-02-implementation-evidence.md)
records the merged source, required CI and normal publication. The pre-merge status below is historical.

Status: pre-merge implementation record. Source and targeted local validation are
complete. Applicable PR CI, merge and normal publication remain required acceptance
gates; this record does not establish a released WP03.02 candidate.

Authority: the [WP03.02 serialization posture profile](https://github.com/ArcForges/ArcForges-Design/blob/212825003ed712200e585445301473233404f597/docs/assurance/wp03-02-serialization-posture-profile.md),
registry04 §8 and P2-017. The accepted upstream Contracts source is
`4b8134eaf8a4174922d6378da003ed390b85a94a` (NuGet/npm `1.0.0-ci.89.1`, Maven
`1.0.0-SNAPSHOT`). No package identity, downstream pin or third-party runtime
dependency changes.

## Implemented source boundary

| Deliverable                 | Source and meaning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bounded binary codec        | [`ContractSerialization.cs`](../src/public/dotnet/ArcForges.Contracts.Foundation/ContractSerialization.cs) and [`wire.ts`](../src/public/ts/proto/src/wire.ts): registry size classes, the root plus 100 nested message levels, typed `tooLarge`/`tooDeep`/`malformed` refusals, oversize encode refusal and retained unknown fields. C# uses Google.Protobuf span parsing, which checks the end-of-stream tag, and fails closed if the runtime nesting default ever differs from 100; TypeScript uses protobuf-es `recursionLimit` 101, which admits the same inputs. |
| Strict HTTP-exception JSON  | [`generate_shapes.py`](../eng/generate_shapes.py) emits the strict `JsonSourceGenerationOptions`, C# `<Schema>Json.Parse`/`TryParse`/`Serialize` and TypeScript `parse`/`tryParse`/`serialize<Schema>Json` codecs for `PartReceipt`, `CommitReceipt` and `PackageInventory`. Each schema declares `x-arcforges-max-bytes`.                                                                                                                                                                                                                                             |
| Explicit service catalogues | [`contracts.py`](../eng/contracts.py) generates C# `ContractServices.All` for PublicApi and Sdk.Contracts and TypeScript `contractServices` for `@arcforges/proto` from the authored services. Hosts bind generated `BindService` methods explicitly.                                                                                                                                                                                                                                                                                                                  |
| Public transport            | `createPublicGrpcWebTransport` in `@arcforges/api-client` fixes binary gRPC-Web with the shared read options and refuses codec overrides; the Hello example uses it.                                                                                                                                                                                                                                                                                                                                                                                                   |
| Build posture               | Every project sets `JsonSerializerIsReflectionEnabledByDefault=false`; every packed library remains AOT-compatible with analyzer diagnostics as errors.                                                                                                                                                                                                                                                                                                                                                                                                                |
| Policy gate                 | [`check_serialization.py`](../eng/check_serialization.py) rejects reflection serializer/discovery packages in NuGet, npm and Gradle locks, runtime-selected well-known proto types, reflection/discovery APIs in production source, handwritten wire records outside generated owners, missing strict JSON options and stale catalogues.                                                                                                                                                                                                                               |
| Independent vectors         | [`wp03-02.json`](../fixtures/public/wp03-02.json) was committed before the implementation: 31 binary and 51 JSON cases plus expected catalogues and bound methods. Multi-megabyte boundary inputs are described by construction rules rather than committed bytes.                                                                                                                                                                                                                                                                                                     |
| Native AOT probe            | [`SerializationProbe`](../tests/public/SerializationProbe/Program.cs) roots all 13 C# libraries, publishes with Native AOT for `linux-x64` (CI) or `win-x64` (local) and runs every vector, every generated message parser, the catalogues and explicit binding into a recording binder. It is test-only and never packed.                                                                                                                                                                                                                                             |

The ILCompiler build-test tooling (`Microsoft.DotNet.ILCompiler` and its `linux-x64`/
`win-x64` runtime packages, 10.0.11) is admitted in dependency receipt `wp03-02-r1`
with the evidence already reviewed in DesktopPlatform. It is not a runtime
dependency of any package. Changed generated outputs are bound by the immutable
`contract-bindings-r5` successor.

## Validation record

| Evidence                                                          | Current observation                                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Generation                                                        | Deterministic C#/TS/Java/Kotlin regeneration passed with the new catalogues and codecs.                                                                                                                                                                                                                                                          |
| C# compilation                                                    | Release solution build passed with zero warnings/errors. Local execution used existing SDK `10.0.401` through a local adapter that selects the committed 10.0.11 linker/compiler/runtime packs; committed `global.json` and CI retain `10.0.400`.                                                                                                |
| Native AOT probe (Windows x64, local)                             | Publish passed with zero trim/AOT diagnostics with every library rooted. The native binary passed 31/31 binary and 51/51 JSON vectors, round-tripped all 162 generated messages, matched both catalogues and recorded both explicitly bound methods; dynamic code was unsupported (Native AOT).                                                  |
| TypeScript                                                        | All five workspaces compiled. The seven serialization tests passed the same 31 binary and 51 JSON vectors, catalogue, codec-refusal and transport-override cases.                                                                                                                                                                                |
| Policy gate                                                       | The gate passed on the tree, and its nine offline tests passed, including negative cases for every rule.                                                                                                                                                                                                                                         |
| Retained suites and receipts                                      | The existing C# foundation suite (476 cases), TypeScript `npm test` (13 tests), 314-case C#/TS exchange, build-identity inspection, contract access (531 files, 14 access tests), licence boundary (31 projects), provenance, dependency admission and naming passed. Ten tooling tests need a packed candidate or SDK `10.0.400` and run in CI. |
| Linux Native AOT probe and applicable PR CI/security              | Pending. The existing candidate job runs the gate, AOT publish and probe once.                                                                                                                                                                                                                                                                   |
| Expected merge, normal publication and clean primary fast-forward | Pending.                                                                                                                                                                                                                                                                                                                                         |

The independent vectors found one cross-language divergence during implementation:
Google.Protobuf's stream parser silently accepted a top-level unmatched end-group tag
that protobuf-es refuses. The C# codec now uses the span parser, which refuses it; the
vector remains in the suite.

## Coverage limits and later gates

This is the WP03.02 contribution to F-026: generated-only clients, reflection-package
absence and build-breaking AOT diagnostics over the contract closure. F-026 stays open
until WP06.02 proves a real generated-client call in the published host/client AOT
artifacts. Transport frame enforcement belongs to the WP23/WP24/WP30 transport owners;
the Kotlin/Connect posture, native-auth and browser exceptions and complete operation
catalogues remain WP03.05. WP03.03/.04/.06/.07/.90 retain their gates.

No live RPC, browser/device, installed-package consumer, macOS or commercial result is
claimed. The Windows AOT result is a local observation; Linux AOT evidence comes from
the configured CI candidate job.
