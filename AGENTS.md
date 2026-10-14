# Repository instructions

- Plan before implementing. Keep work within the requested bootstrap or contract change.
- Handwritten proto/HTTP schemas and constraint sidecars own their wire/shape definitions.
  Keep the complete `eng/contract-packages.json` inventory and actual access boundaries synchronized. Never edit
  generated C# or `@arcforges/ai-internal` TypeScript files directly; use `python eng/contracts.py generate`.
- Read `docs/architecture.md` and `docs/releasing.md` before changing generation,
  package identities, licensing or CI publication.
- ArcForges-authored source, generated code, tooling, tests, configuration and
  documentation use Apache-2.0 under the root LICENSE. Preserve all third-party
  licences and notices.
- Consumers use exact NuGet versions; the Cloudflare thin adapters use exact `@arcforges/ai-internal`
  npm versions. No submodules, sibling source builds or cross-repository project references. Local references in producer tests are
  replaced by package references in the isolated artifact tests.
- Use the pinned toolchain and commit every lock file. Run the checks relevant
  to the change; package consumer execution is optional local diagnostics, never a CI gate.
- Never put account tokens or keys in files, commands, examples or PR bodies.
  Registry setup belongs in GitHub environments/variables and trusted publishers.
- Write repository documentation in English. Keep examples explicitly separate
  from production product contracts and from evidence of Android device operation.
- Serialization (WP03.02): generated protobuf code is the only business wire format; declared
  HTTP exceptions use the generated strict JSON codecs. Never add reflection serializers, protobuf
  JSON mapping, `Any`/`Struct`, runtime registries or server reflection, and never enable
  reflection-based System.Text.Json. `eng/check_serialization.py` and the Native AOT
  `tests/public/SerializationProbe` enforce this in the build.
- C#-only SDK channels (CON.40, P2-021 Decision 4): C# NuGet is the only first-party SDK channel for
  business clients, and `@arcforges/ai-internal` is the one retained npm package, published to the
  public registry with an internal contract-access boundary. Never add a source, generator, workflow
  step, Dependabot group or new version for the retired identities (npm `@arcforges/proto`,
  `@arcforges/api-client`, `@arcforges/contract-fixtures`, `@arcforges/operator-client`; Maven
  `io.github.arcforges:contracts-proto`, `contracts-connect-client`, `contract-fixtures`), and never
  unpublish, deprecate or delete any of their published versions; existing consumer pins stay resolvable.
- Retired rows are kept and marked, never deleted. A retired identity stays in
  `eng/contract-packages.json` with a `retired` marking; its `eng/policy/contract-access.json` rows stay
  byte-identical and are marked retired through the owner row, so a new row for it or the removal of a
  historical row fails `eng/check_contract_access.mjs`. `eng/foundation-inventory.json` keeps its
  TypeScript and Java/Kotlin output rows and marks them retired through the appended, closed
  `outputRetirement` entry (CON.40). That marking is an append under the append-only protocol, not an
  exception to it: regeneration under `RES-contracts-generated-baseline` preserves it, and
  `eng/check_foundation.py --generated` refuses a retired output that reappears. A first-party artifact
  leaves the provenance inventory only through a reviewed receipt under `eng/provenance/retirements/`.

## Flagship role

Contracts is an **active** repository of the ArcForges flagship ([AD-0001](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0001-flagship-pivot.md)); the design authority is [ArcForges-Design](https://github.com/ArcForges/ArcForges-Design). Per [architecture 01 §5](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/architecture/01-system-overview.md#5-repository-and-project-map) and the [reuse classification](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/reuse/inventory-and-classification.md#1-contracts), it adds the `node.v1`, `fleet.v1`, `peer.v1`, `relay.v1` and `operator_read` contracts with their packages, makes additive `publicapi.v1` changes listed in the [reuse map](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/contracts/reuse-map.md), and renames the `ArcForges.Cli` tool command (conflict C-03). It reuses `arcforges.foundation.v1` and the identity, entitlement, commerce, support, notification, data, device and operator contracts unchanged. The other contracts of the earlier product family are retained for future products and are not scheduled.

## Delivery (serial, ArcForges/Plan)

Tasks for this repository come from the [Plan delivery graph](https://github.com/ArcForges/Plan/blob/main/delivery-graph.json) and are delivered under the Plan [execution policy](https://github.com/ArcForges/Plan/blob/main/execution-policy.md) and [delivery procedure](https://github.com/ArcForges/Plan/blob/main/delivery-procedure.md) ([AD-0014](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0014-delivery-method.md)). They are binding. The historical P2-018 model (delivery lanes, adoption slices, `delivery.py` claims and handoffs, parallel workers, integration-owner roles, the build slot and the launcher) is retired and never resumed.

- One task is active at a time. Work only inside its write scope, in a worktree `.worktree/<task-id-lower>` on branch `task/<task-id-lower>`, never in the primary checkout.
- Delegated workers and reviewers work locally. Only the coordinator pushes, opens pull requests, merges (at the reviewed head, after hosted CI passes) and publishes.
- Title pull requests `[<TASK-ID>] <summary>`.
- Shared files: the package inventory, foundation inventory and constraint aggregate are append-only; generated sources and descriptor baselines are regenerated after rebase, never hand-edited or hand-merged. Each merge to main publishes all active packages (NuGet and `@arcforges/ai-internal`) at one candidate version.
- Dated `docs/wp03-*` and `docs/implementation/*` records (`wp00-*`, `wp01-01`, `wp02-04` and `wp02-05`), `docs/bootstrap-plan.md`, the `docs/con-*` task records, `docs/validation.md` and the retired `docs/maven-central.md`, `docs/kotlin-artifacts-plan.md` and `docs/kotlin-grpc-web-plan.md` describe their original scope; they are evidence, not execution instructions. Their TypeScript, Kotlin and Maven statements predate CON.40. Where older documents prefix a command with `delivery.py build-slot run … --` or assign a step to an integration owner, that is historical: run the wrapped command directly, and leave pushing and merging to the coordinator.

## Validation policy (P2-017)

The historical [CI and local validation policy](https://github.com/ArcForges/ArcForges-Design-Parallel/blob/64173614f2c41543bfff8f6df8d5a9e41207eb0a/docs/assurance/ci-and-local-validation-policy.md) (ArcForges-Design-Parallel at `64173614`) stays in force for this repository, except its rule 9 (parallel delivery), which AD-0014 supersedes. Where it differs from the Plan execution policy, the Plan governs.

- Never add or execute macOS CI, installed-package consumers, live transport/service tests, GUI/browser/device tests or public-release installation/upgrade tests in any CI trigger or nested build script.
- Keep necessary Windows/Linux compilation, packaging, targeted offline unit/static tests, locks, required signatures, licence/provenance and non-duplicated security scans. Runtime diagnostics are explicit local opt-in for affected behavior with existing tools; hooks must not silently rebuild/test.
- Validate candidate contents once during production and identity/integrity at the actual publication handoff. Do not repeatedly download public artifacts, rescan archives, compare hashes or rerun consumers after publishing. Registry status/coordinate metadata establishes completion.
- Preserve deliberate-tag formal releases. The Maven main SNAPSHOT and Maven Central channels are retired (CON.40). Never create tags, republish or re-sign solely for verification. Diagnose failed jobs before rerun; ambiguous existing immutable releases require investigation, not silent skipping.
- Do not reinstall vcpkg, SDKs, emulators or toolchains to expand validation. Use the normal network and never change proxy or network configuration (no port 7890). Diagnose a failure before any rerun, retry transient failures with bounded backoff, inspect remote state before retrying a write, and report the exact operation when a failure persists. Linux opt-in checks run in the local WSL2 Debian distribution (P2-024); installs inside it are the user's, and there is no SSH.
- Every pull request gets an independent review of its complete latest head and waits for its applicable checks; the coordinator merges only at the reviewed head. Post-merge work ends after expected commit, required build/publication status and clean primary fast-forward. Keep branches/worktrees and report untested coverage accurately.
- This repository has configured CI/security checks; they remain required for documentation-only PRs. Direct merge after review without CI applies only to documentation repositories with no configured CI. Do not suppress configured workflows with skip directives or bypass branch protection. Documentation changes require no additional ad-hoc local product builds or runtime tests.

## Dependency admission (WP02.05)

- Keep `eng/policy/dependency-policy.json` bound to the complete actual dependency inputs. A dependency or framework change requires a reviewed replacement receipt, closure/licence and maintenance review and every upgrade checklist item. Hash refresh alone is insufficient.
- Preserve existing source/native provenance and public/internal import gates. Stable closures cannot import prerelease dependencies; only recorded exact foundation candidates are permitted in development.
- Framework major upgrades require explicit runtime/AOT/trim and affected Android consumer assessment under VG-08. Record conditional local coverage honestly without adding forbidden CI or provisioning tools.
