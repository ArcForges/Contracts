# Repository instructions

- Plan before implementing. Keep work within the requested bootstrap or contract change.
- Handwritten proto/HTTP schemas and constraint sidecars own their wire/shape definitions.
  Keep the complete `eng/contract-packages.json` inventory and actual access boundaries synchronized. Never edit
  generated C#, TypeScript, Java or Kotlin files directly; use `python eng/contracts.py generate`.
- Read `docs/architecture.md` and `docs/releasing.md` before changing generation,
  package identities, licensing or CI publication.
- ArcForges-authored source, generated code, tooling, tests, configuration and
  documentation use Apache-2.0 under the root LICENSE. Preserve all third-party
  licences and notices.
- Consumers use exact NuGet/npm/Maven versions. No submodules, sibling source builds or
  cross-repository project references. Local references in producer tests are
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

## Delivery model (P2-018)

Work is scheduled as delivery tasks in the [delivery graph](https://github.com/ArcForges/ArcForges-Design-B/blob/fd16c5f285de0bda2d0320cdff4d52c34c9098ed/docs/planning/delivery/README.md) and executed through the [Plan execution entry](https://github.com/ArcForges/Plan-B/blob/0cb637d1bfbf64d7db22a96a2b7370a409a25d8e/arcforges-implementation.md). There is no Current task, numbered substep order or single main context.

- Baseline: WP03.00–WP03.02 are accepted and WP03.03 has not started. Its closures and every later contract area are open tasks in the [contracts lane](https://github.com/ArcForges/ArcForges-Design-B/blob/fd16c5f285de0bda2d0320cdff4d52c34c9098ed/docs/planning/delivery/lanes/contracts.md); this repository also owns tasks in the extensions, governance and release lanes.
- Start only a task that Plan-B's `python tools/delivery.py ready --claims` lists and whose `claims/<task-id>` branch you hold. No task here is ready until its adoption slice (`ADOPT.03.contracts`, `ADOPT.03.extensions`, `ADOPT.03.governance` or `ADOPT.03.release`) is recorded.
- Several workers may work here at once, each on a different claimed task in its own retained worktree and `task/<task-id>` branch, inside the task's write scope. Closures are authored concurrently in their own domain proto or HTTP-schema, constraint and fixture files.
- Shared files follow their [declared protocols](https://github.com/ArcForges/ArcForges-Design-B/blob/fd16c5f285de0bda2d0320cdff4d52c34c9098ed/docs/planning/delivery/shared-resources.md): the package inventory, foundation inventory and constraint aggregate are append-only per closure; a proto file with several contributing tasks has one designated author task; generated sources and descriptor baselines are regenerated after rebase, never hand-edited or hand-merged. The Contracts integration owner merges closure pull requests one at a time, and each merge to main publishes all packages at one candidate version.
- Title pull requests `[<TASK-ID>] <summary>`; a bundle of compatible ready tasks lists each ID, and planning alignment uses `[P2-018]`. The integration owner merges only pull requests of the claimant at the current claim epoch.
- Dated `docs/wp03-*` and `docs/implementation/wp00-*` records describe their original scope; they are evidence, not execution instructions.

## Validation policy (P2-017)

Follow the [current CI/local authority](https://github.com/ArcForges/ArcForges-Design/blob/47db6670a727317939b91245e8c0b288834acf99/docs/assurance/ci-and-local-validation-policy.md).

- Never add or execute macOS CI, installed-package consumers, live transport/service tests, GUI/browser/device tests or public-release installation/upgrade tests in any CI trigger or nested build script.
- Keep necessary Windows/Linux compilation, packaging, targeted offline unit/static tests, locks, required signatures, licence/provenance and non-duplicated security scans. Runtime diagnostics are explicit local opt-in for affected behavior with existing tools; hooks must not silently rebuild/test.
- Validate candidate contents once during production and identity/integrity at the actual publication handoff. Do not repeatedly download public artifacts, rescan archives, compare hashes or rerun consumers after publishing. Registry status/coordinate metadata establishes completion.
- Preserve Maven main SNAPSHOT and deliberate-tag formal releases. Never create tags, republish or re-sign solely for verification. Diagnose failed jobs before rerun; ambiguous existing immutable releases require investigation, not silent skipping.
- Do not reinstall vcpkg, SDKs, emulators or toolchains to expand validation. Stop on local network failure and report the exact operation; diagnose and repair CI failures before a targeted retry; no proxy configuration, port 7890, wsl.exe or WSL wrappers.
- Review the full latest PR and wait for applicable checks before merging. Post-merge work ends after expected commit, required build/publication status and clean primary fast-forward. Keep branches/worktrees and report untested coverage accurately.
- This repository has configured CI/security checks; they remain required for documentation-only PRs. Direct merge after review without CI applies only to documentation repositories with no configured CI. Do not suppress configured workflows with skip directives or bypass branch protection. Documentation changes require no additional ad-hoc local product builds or runtime tests.

## Dependency admission (WP02.05)

- Keep `eng/policy/dependency-policy.json` bound to the complete actual dependency inputs. A dependency or framework change requires a reviewed replacement receipt, closure/licence and maintenance review and every upgrade checklist item. Hash refresh alone is insufficient.
- Preserve existing source/native provenance and public/internal import gates. Stable closures cannot import prerelease dependencies; only recorded exact foundation candidates are permitted in development.
- Framework major upgrades require explicit runtime/AOT/trim and affected Android Kotlin/JVM/ART/R8 assessment under VG-08. Record conditional local coverage honestly without adding forbidden CI or provisioning tools.
