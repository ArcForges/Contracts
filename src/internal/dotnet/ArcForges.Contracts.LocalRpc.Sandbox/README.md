# ArcForges.Contracts.LocalRpc.Sandbox

Internal, parent-to-child ContentSandbox gRPC contracts for bounded image and PDF parsing. The service has exactly 15 operations; retired media and OTIO operations are excluded. All requests and results use Foundation envelopes, with business payloads at tag 10 and above.

**Retired PDF operations (P2-022, CON.40).** `OpenPdf`, `GetPdfPage`, `ExtractPdfText`, `RenderPdfTile` and `ClosePdf` are retired: native in-app PDF preview and local PDF parsing are retired, never completed. The five RPCs and their PDF-named messages stay in the published `arcforges.local.sandbox.v1` schema and in this generated package unchanged, so field numbers, names and descriptors remain compatible, but no new consumer may call them. `eng/policy/contract-access.json` records the marking under `retiredOperations`, and the access check refuses its removal and any marking of an undeclared operation.

`ContentSandboxPolicy` checks generated descriptor identity and endpoint-role metadata. It is an offline policy check, not authentication or operating-system containment. The LocalRpc/runtime owner must verify launch identity, connection credentials, current grants, actor and invocation, and enforce parent-death cleanup.

`SandboxProfile` supplements generated shape validation with image bounds, finite PDF geometry, UTF16 pagination/box boundaries and slot/region geometry checks. Runtime owners additionally bind invocation, lease and generation, track sequence and coverage, copy shared bytes into private memory and verify their digest before use. This package performs no process launch, allocation, file access or listener registration.

Apache-2.0. Public accessibility does not authorize importing internal protocols.
