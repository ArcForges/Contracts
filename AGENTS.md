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
  to the change while iterating; the full CI-equivalent profile runs on the Linux host after the push
  ([Verification after the push](#verification-after-the-push-ad-0020)). Package consumer execution is optional local diagnostics,
  never a CI or hook gate.
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
- Delegated workers and reviewers work locally. Only the coordinator pushes, verifies the pushed head on the Linux host, opens pull requests, merges at the reviewed head and publishes. The merge gate is the required `arcforges/linux` status at the head for every PR, plus full hosted CI for external PRs ([Verification after the push](#verification-after-the-push-ad-0020), [Hosted CI](#hosted-ci)).
- Title pull requests `[<TASK-ID>] <summary>`.
- Shared files: the package inventory, foundation inventory and constraint aggregate are append-only; generated sources and descriptor baselines are regenerated after rebase, never hand-edited or hand-merged. Each merge to main publishes all active packages (NuGet and `@arcforges/ai-internal`) at one candidate version.
- Dated `docs/wp03-*` and `docs/implementation/*` records (`wp00-*`, `wp01-01`, `wp02-04` and `wp02-05`), `docs/bootstrap-plan.md`, the `docs/con-*` task records, `docs/validation.md` and the retired `docs/maven-central.md`, `docs/kotlin-artifacts-plan.md` and `docs/kotlin-grpc-web-plan.md` describe their original scope; they are evidence, not execution instructions. Their TypeScript, Kotlin and Maven statements predate CON.40. Where older documents prefix a command with `delivery.py build-slot run … --` or assign a step to an integration owner, that is historical: run the wrapped command directly, and leave pushing and merging to the coordinator.

## Validation policy (P2-017)

The historical [CI and local validation policy](https://github.com/ArcForges/ArcForges-Design-Parallel/blob/64173614f2c41543bfff8f6df8d5a9e41207eb0a/docs/assurance/ci-and-local-validation-policy.md) (ArcForges-Design-Parallel at `64173614`) stays in force for this repository, except its rule 9 (parallel delivery), which AD-0014 supersedes. Where it differs from the Plan execution policy, the Plan governs.

- Never add or execute macOS CI, installed-package consumers, live transport/service tests, GUI/browser/device tests or public-release installation/upgrade tests in any CI trigger or nested build script.
- Keep necessary Windows/Linux compilation, packaging, targeted offline unit/static tests, locks, required signatures, licence/provenance and non-duplicated security scans. Runtime diagnostics (installed-package consumers, `contracts.py consume`) are explicit local opt-in for affected behavior with existing tools; the host verification runs only the CI-equivalent offline checks.
- Validate candidate contents once during production and identity/integrity at the actual publication handoff. Do not repeatedly download public artifacts, rescan archives, compare hashes or rerun consumers after publishing. Registry status/coordinate metadata establishes completion.
- Preserve deliberate-tag formal releases. The Maven main SNAPSHOT and Maven Central channels are retired (CON.40). Never create tags, republish or re-sign solely for verification. Diagnose failed jobs before rerun; ambiguous existing immutable releases require investigation, not silent skipping.
- Do not reinstall vcpkg, SDKs, emulators or toolchains to expand validation. Use the normal network and never change proxy or network configuration (no port 7890). Diagnose a failure before any rerun, retry transient failures with bounded backoff, inspect remote state before retrying a write, and report the exact operation when a failure persists. Linux checks run on the Linux MCP host, through the Linux MCP server, never through local WSL, not even as a fallback ([AD-0018](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0018-native-platforms-without-wsl-integration.md), [AD-0019](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0019-mcp-first-verification.md)); installs there are the user's, and there is no SSH.
- Every pull request gets an independent review of its complete latest head and passes its merge gate ([Hosted CI](#hosted-ci)); the coordinator merges only at the reviewed head. Post-merge work ends after expected commit, required build/publication status and clean primary fast-forward. Keep branches/worktrees and report untested coverage accurately.
- Documentation-only changes run the full profile too (the naming, provenance, formatting and packaging checks read documentation) and need no additional ad-hoc product builds or runtime tests. Do not suppress configured workflows with skip directives or bypass branch protection.

## Verification after the push (AD-0020)

Every PR into `main` is verified after the push, on the verification host, and gated by GitHub ([AD-0016](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0016-local-first-verification.md) as amended by [AD-0020](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0020-post-push-verification-and-required-checks.md)). The flow: Push → Fetch → Local verification → Report status → Required checks → Review → Merge. The cross-repository rules are the Plan [AGENTS.md](https://github.com/ArcForges/Plan/blob/main/AGENTS.md) rules 6 and 7.

- **Push** the branch to GitHub; nothing is verified before a push and there is no pre-push hook. `python eng/verify.py install`, once per clone from the main checkout on `main`, removes the retired pre-push hook (and any `core.hooksPath`).
- **One leg, on Linux** ([AD-0019](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0019-mcp-first-verification.md)). Hosted CI ran on Ubuntu only, so every step is on the `linux` host, and the `main` ruleset requires only the commit status `arcforges/linux` (plus the hosted `Verify` check, which is skipped for the owner's PRs). The leg runs natively on the Linux MCP host, reached through the Linux MCP server (a standard MCP server that Claude Code and Codex share), never through WSL or a remote shell; local WSL is never a venue, not even as a fallback.
- **Fetch and verify.** In the Linux host's clone (`origin` must be this GitHub repository), fetch the pushed commit from GitHub and run the command in a worktree at it:

  ```
  git fetch origin <branch>
  git worktree add --detach .worktree/verify-<sha> <sha>
  cd .worktree/verify-<sha>
  python eng/verify.py run-and-report
  cd ../..
  git worktree remove --force .worktree/verify-<sha>
  ```

  It reports `arcforges/linux` on that exact commit: `pending` when it starts, `success` only when every step ran and passed, `failure` when a step failed, `error` when the leg could not complete. It exits 0 after success, 1 when a step failed and 2 when the leg could not complete or be reported. Every new push needs verifying again. The host reports with `ARCFORGES_STATUS_TOKEN` when set (a token limited to commit statuses), otherwise with its own `gh` login; steps never see either, and they are never printed. For a pull request from a fork, read the diff first, then fetch `refs/pull/<n>/head`.

- **Stop rule** (AD-0019 §5). If the Linux MCP server is unavailable, unreachable or its host lacks a prerequisite, stop and report the exact failure: the status stays missing and the PR cannot merge. Never skip, mock or weaken a step, or run the leg on another host (local WSL or an agent's own sandbox included).
- `python eng/verify.py list` shows the profile and the steps. `python eng/verify.py run` runs the leg of `HEAD` on the host without reporting.
- **What runs.** The commit, never the working tree, in the Linux-native clone `~/.cache/arcforges-verify/Contracts`, as listed in `eng/verify_steps.py`. Every change runs the full profile.
  - Lane `linux`, in order:
    - `clone-identity`: the clone's `origin` URL is this GitHub repository, which the naming check requires, and its `origin/main` is the merge base, which the base-reading scripts compare against;
    - `restore`: `python eng/contracts.py restore`;
    - `dependency-admission`, `naming`, `provenance` (`--base` the merge base) and `contract-access-test`;
    - `format-audit`: `npm run format:check`, `npm audit --audit-level=high` and `git diff --check`;
    - `pack`: `python eng/contracts.py pack --version 1.0.0-ci.0.0`, which runs the generation check, the policy checks, the Release build, the architecture and structure tests, the `@arcforges/ai-internal` build and tests, the compatibility exchanges, the Native AOT serialization probe and the candidate archives;
    - `tooling-tests` and `clean-tree`;
    - then the Security job's `security-build`, `security-naming` and `architecture-gate` (`--local-gate`: the hosted gate's policy stages over the full project graph, bound to the verified commit instead of the hosted job identity).
  - Lane `scan`: the pinned gitleaks image over the commits since the merge base with `.gitleaks.toml`, without network.
  - `actionlint` when `.github/workflows/**` changed.
  - `CI` is not set (with it, the build requires a GitHub run identity), so local builds carry the `local` build identity.
- **Prerequisites** (installs are the user's): a Linux machine with:
  - the .NET SDK selected by `global.json`;
  - Node and npm as pinned in `.node-version` and `eng/contracts.py`;
  - Python (`python` on PATH);
  - Docker with the pinned gitleaks image;
  - `gh` with a credential that can write commit statuses;
  - network access to GitHub and to the NuGet and npm registries.
- **Failures.** A failed, timed-out or unrunnable step reports `failure` and prints the step, the last log lines and the log path (`<git common dir>/arcforges-verify/logs/`). Read the log, fix the cause, push, verify again.
- **Statuses and rulesets.** A status is reported only by `python eng/verify.py run-and-report` on the host it names, at the commit it verified. Never post, edit or copy an `arcforges/*` status by hand, and never change the ruleset or required checks to get a PR merged.
- AI agents must never use `git push --no-verify` to bypass required validation.
- They must also never disable, remove, modify, or otherwise circumvent the hooks or required checks merely to get a change through.
- If validation fails, investigate and fix the underlying issue.
- If a required local test cannot run, do not silently skip it or claim successful verification.
- Changing `eng/verify*.py`, `.githooks/` or the ruleset as reviewed engineering work is allowed; changing them to get a change through is not.

## Efficient execution

The Plan's rule 7 applies. In this repository:

- Restore once (`python eng/contracts.py restore`), then build incrementally: `dotnet build ArcForges.Contracts.slnx -c Release --no-restore`.
- While iterating, run only the affected checks: `python eng/contracts.py generate --check`, the `eng/check_*.py` script of the changed policy, `node --test tests/tooling/contract_access.test.mjs`, `python -m unittest tests.tooling.<module>`, the built suites (`dotnet tests/StructureTests/bin/Release/net10.0/StructureTests.dll .` and `dotnet tests/ArchitectureTests/bin/Release/net10.0/ArcForges.Contracts.ArchitectureTests.dll`) and `npx prettier --check <changed files>`.
- `python eng/contracts.py pack` is the full candidate. It runs once per pushed head, in the host verification; `python eng/verify.py run` on the Linux host checks it before handover without reporting.

## Hosted CI

- **Owner PRs:** no hosted validation or security analysis; `Build candidate`, `Security` and `Verify` show as skipped.
- **External PRs** (Dependabot included), the merge queue and manual `CI` runs: `Build candidate`, `Security` (the called `security.yml`: dependency review on PRs, the full-history secret scan with the hosted architecture gate, CodeQL for C#, JavaScript/TypeScript and Python) and `Verify`, which requires both. `Verify` is the required check. `Verify` guards jobs, not code scanning's separate `CodeQL` alert check (owner PRs never produce it, so it cannot be required): an external PR merges only when that check is not failing.
- **Main and `v*` pushes:** delivery only, `Build candidate` and the publish jobs, which depend on the candidate. `security.yml` also runs weekly and on manual dispatch.

## Dependency admission (WP02.05)

- Keep `eng/policy/dependency-policy.json` bound to the complete actual dependency inputs. A dependency or framework change requires a reviewed replacement receipt, closure/licence and maintenance review and every upgrade checklist item. Hash refresh alone is insufficient.
- Preserve existing source/native provenance and public/internal import gates. Stable closures cannot import prerelease dependencies; only recorded exact foundation candidates are permitted in development.
- Framework major upgrades require explicit runtime/AOT/trim and affected Android consumer assessment under VG-08. Record conditional local coverage honestly without adding forbidden CI or provisioning tools.
