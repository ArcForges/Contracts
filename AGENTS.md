# Repository instructions

- Plan before implementing. Keep work within the requested bootstrap or contract change.
- Handwritten `public/proto` schemas own the public wire definition. Never edit
  generated C# or TypeScript files directly; use `python eng/contracts.py generate`.
- Read `docs/architecture.md` and `docs/releasing.md` before changing generation,
  package identities, licensing or CI publication.
- ArcForges-authored source, generated code, tooling, tests, configuration and
  documentation use Apache-2.0 under the root LICENSE. Preserve all third-party
  licences and notices.
- Consumers use exact NuGet/npm versions. No submodules, sibling source builds or
  cross-repository project references. Local references in producer tests are
  replaced by package references in the isolated artifact tests.
- Use the pinned toolchain and commit every lock file. Run the checks relevant
  to the change; packaging changes require the actual package consumer gate.
- Never put account tokens or keys in files, commands, examples or PR bodies.
  Registry setup belongs in GitHub environments/variables and trusted publishers.
- Write repository documentation in English. Keep examples explicitly separate
  from production product contracts and from evidence of RN/Hermes operation.
