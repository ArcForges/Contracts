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
lock files; CI restores them in locked mode. For Gradle changes, use
`python eng/contracts.py restore --update-locks`, regenerate and pack, then
`python eng/contracts.py consume --update-kotlin-locks` to refresh the separate
consumer locks/checksums. Review both dependency versions and new checksums;
ordinary CI must never generate or accept missing verification metadata.

A Dependabot Gradle PR can update the version catalog without refreshing the
producer or isolated consumer locks and checksums. Complete the same update
sequence in that PR before merging; rebasing alone does not regenerate them.

The Java/Kotlin CodeQL job temporarily pins the SHA-256-verified upstream
`codeql-bundle-20260913` nightly because stable CLI 2.27.0 cannot extract Kotlin
2.4.20. This is an unsupported prerelease scanner, used only in that analysis job;
it is not a package or build dependency. See the
[upstream compatibility issue](https://github.com/github/codeql/issues/22381#issuecomment-5620711447).
Once the action's recommended stable CLI includes the fix in 2.27.1 or later,
remove the bundle download and `tools` override and verify Java/Kotlin extraction
with the pinned compiler. Do not downgrade Kotlin to work around the scanner:
older Gradle plugins are affected by
[GHSA-r937-wjx7-w2jp](https://github.com/advisories/GHSA-r937-wjx7-w2jp).

Contributions to ArcForges-authored source, generated bindings, examples, tooling,
configuration and documentation use Apache-2.0 under the root LICENSE. Add SPDX
headers to authored code and preserve third-party licences and notices. Do not
copy reference code or introduce a licence-incompatible dependency into a package.

Use the proposal template for schema changes and the private reporting route in
SECURITY.md for vulnerabilities. Discuss changes respectfully and focus review
on reproducible behavior, compatibility and maintainability.
