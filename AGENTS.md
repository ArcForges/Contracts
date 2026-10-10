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

## Delivery model (P2-018)

Work is scheduled as delivery tasks in the [delivery graph](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/planning/delivery/README.md) and executed through the [Plan execution entry](https://github.com/ArcForges/Plan/blob/main/arcforges-implementation.md). There is no Current task, numbered substep order or single main context.

- Baseline: WP03.00–WP03.02 are accepted and WP03.03 has not started. Its closures and every later contract area are open tasks in the [contracts lane](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/planning/delivery/lanes/contracts.md); this repository also owns tasks in the extensions, governance and release lanes.
- Start only a task that Plan's `python tools/delivery.py ready` lists and whose claim you hold (`python tools/delivery.py claim <TASK-ID> --worker <name>`, recorded as `claims/<key>`, the ID in lower case with dots replaced by hyphens, such as `claims/con-02`); continue interrupted work from its handoff record (`python tools/delivery.py show <TASK-ID>`) rather than restarting it. No task here is ready until its adoption slice (`ADOPT.03.contracts`, `ADOPT.03.extensions`, `ADOPT.03.governance` or `ADOPT.03.release`) is recorded.
- Several workers may work here at once, each on a different claimed task in its own retained worktree and `task/<key>` branch, inside the task's write scope. Closures are authored concurrently in their own domain proto or HTTP-schema, constraint and fixture files.
- Shared files follow their [declared protocols](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/planning/delivery/shared-resources.md): the package inventory, foundation inventory and constraint aggregate are append-only per closure; a proto file with several contributing tasks has one designated author task; generated sources and descriptor baselines are regenerated after rebase, never hand-edited or hand-merged. The Contracts integration owner merges closure pull requests one at a time, and each merge to main publishes all active packages (NuGet and `@arcforges/ai-internal`) at one candidate version.
- Title pull requests `[<TASK-ID>] <summary>`; a bundle of compatible ready tasks lists each ID, and planning alignment uses `[P2-018]`. The integration owner (the holder of `roles/integration-contracts`) merges only at the head commit reviewed for the claimant at the current claim epoch, keeping the task IDs in the merge title.
- Dated `docs/wp03-*` and `docs/implementation/*` records (`wp00-*`, `wp01-01`, `wp02-04` and `wp02-05`), `docs/bootstrap-plan.md`, the `docs/con-*` task records, `docs/validation.md` and the retired `docs/maven-central.md`, `docs/kotlin-artifacts-plan.md` and `docs/kotlin-grpc-web-plan.md` describe their original scope; they are evidence, not execution instructions. Their TypeScript, Kotlin and Maven statements predate CON.40.

## Validation policy (P2-017)

Follow the [current CI/local authority](https://github.com/ArcForges/ArcForges-Design/blob/47db6670a727317939b91245e8c0b288834acf99/docs/assurance/ci-and-local-validation-policy.md).

- Never add or execute macOS CI, installed-package consumers, live transport/service tests, GUI/browser/device tests or public-release installation/upgrade tests in any CI trigger or nested build script.
- Keep necessary Windows/Linux compilation, packaging, targeted offline unit/static tests, locks, required signatures, licence/provenance and non-duplicated security scans. Runtime diagnostics are explicit local opt-in for affected behavior with existing tools; hooks must not silently rebuild/test.
- Validate candidate contents once during production and identity/integrity at the actual publication handoff. Do not repeatedly download public artifacts, rescan archives, compare hashes or rerun consumers after publishing. Registry status/coordinate metadata establishes completion.
- Preserve deliberate-tag formal releases. The Maven main SNAPSHOT and Maven Central channels are retired (CON.40). Never create tags, republish or re-sign solely for verification. Diagnose failed jobs before rerun; ambiguous existing immutable releases require investigation, not silent skipping.
- Do not reinstall vcpkg, SDKs, emulators or toolchains to expand validation. Stop on local network failure and report the exact operation; diagnose and repair CI failures before a targeted retry; no proxy configuration, port 7890, wsl.exe or WSL wrappers.
- Review the full latest PR and wait for applicable checks before merging. Post-merge work ends after expected commit, required build/publication status and clean primary fast-forward. Keep branches/worktrees and report untested coverage accurately.
- This repository has configured CI/security checks; they remain required for documentation-only PRs. Direct merge after review without CI applies only to documentation repositories with no configured CI. Do not suppress configured workflows with skip directives or bypass branch protection. Documentation changes require no additional ad-hoc local product builds or runtime tests.

## Dependency admission (WP02.05)

- Keep `eng/policy/dependency-policy.json` bound to the complete actual dependency inputs. A dependency or framework change requires a reviewed replacement receipt, closure/licence and maintenance review and every upgrade checklist item. Hash refresh alone is insufficient.
- Preserve existing source/native provenance and public/internal import gates. Stable closures cannot import prerelease dependencies; only recorded exact foundation candidates are permitted in development.
- Framework major upgrades require explicit runtime/AOT/trim and affected Android consumer assessment under VG-08. Record conditional local coverage honestly without adding forbidden CI or provisioning tools.
