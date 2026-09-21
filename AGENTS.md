# Repository instructions

- Plan before implementing. Keep work within the requested bootstrap or contract change.
- Handwritten `public/proto` schemas own the public wire definition. Never edit
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

## Validation policy (P2-017)

Follow the [current CI/local authority](https://github.com/ArcForges/ArcForges-Design/blob/47db6670a727317939b91245e8c0b288834acf99/docs/assurance/ci-and-local-validation-policy.md).

- Never add or execute macOS CI, installed-package consumers, live transport/service tests, GUI/browser/device tests or public-release installation/upgrade tests in any CI trigger or nested build script.
- Keep necessary Windows/Linux compilation, packaging, targeted offline unit/static tests, locks, required signatures, licence/provenance and non-duplicated security scans. Runtime diagnostics are explicit local opt-in for affected behavior with existing tools; hooks must not silently rebuild/test.
- Validate candidate contents once during production and identity/integrity at the actual publication handoff. Do not repeatedly download public artifacts, rescan archives, compare hashes or rerun consumers after publishing. Registry status/coordinate metadata establishes completion.
- Preserve Maven main SNAPSHOT and deliberate-tag formal releases. Never create tags, republish or re-sign solely for verification. Diagnose failed jobs before rerun; ambiguous existing immutable releases require investigation, not silent skipping.
- Do not reinstall vcpkg, SDKs, emulators or toolchains to expand validation. Stop on network failure and report the exact operation; no proxy configuration, port 7890, wsl.exe or WSL wrappers.
- Review the full latest PR and wait for applicable checks before merging. Post-merge work ends after expected commit, required build/publication status and clean primary fast-forward. Keep branches/worktrees and report untested coverage accurately.
