# Contributing

1. Create a branch or independent Git worktree from main.
2. Install the pinned toolchains and follow the README quick start.
3. Edit authored schemas and regenerate bindings. Keep changes bounded and retain
   field numbers, names and service identities unless an approved breaking
   contract change requires a new version.
4. Run local verification. For packaging changes, pack and run isolated consumers.
5. Submit a PR with behavior/compatibility impact and actual validation evidence.

Use LF/UTF-8 and the repository formatting rules. Do not hand-edit generated code
or publish from a contributor branch. Dependency updates include the affected
lock files; CI restores them in locked mode.

Contributions under `public/`, `src/public/`, `tests/public/` and
`fixtures/public/` are Apache-2.0; repository tooling otherwise uses the root
AGPL-3.0 licence. Add SPDX headers to authored code. Do not copy reference code or
introduce a licence-incompatible dependency into a public package.

Use the proposal template for schema changes and the private reporting route in
SECURITY.md for vulnerabilities. Discuss changes respectfully and focus review
on reproducible behavior, compatibility and maintainability.
