# Contributing

1. Create a branch or independent Git worktree from main.
2. Reuse the existing toolchains and follow the relevant README commands.
3. Edit authored schemas and regenerate bindings. Keep changes bounded and retain
   field numbers, names and service identities unless an approved breaking
   contract change requires a new version.
4. Run relevant offline checks once. Runtime consumers are explicit local opt-in only when affected;
   do not install tools or require hosted consumers. Follow [AGENTS.md](AGENTS.md).
5. Submit a PR with behavior/compatibility impact and actual validation evidence.

Use LF/UTF-8 and the repository formatting rules. Do not hand-edit generated code
or publish from a contributor branch. Dependency updates include the affected
lock files; CI restores them in locked mode. For Gradle changes, use
`python eng/contracts.py restore --update-locks`, regenerate and pack, then
`python eng/contracts.py consume --update-kotlin-locks` to refresh the separate
consumer locks/checksums. Review both dependency versions and new checksums;
ordinary CI must never generate or accept missing verification metadata.

## Concurrent contract closures

Author constraints in domain files under `public/proto/constraints/` or
`internal/proto/constraints/`, with the `proto-constraints.v1` envelope, Apache-2.0
license and a `messages` object keyed by fully qualified protobuf message name.
Each message has one authoring shard. Preserve existing `*-baseline.json` entries;
coordinate edits to a shared domain with its task owner. New domain shards must
not duplicate existing messages or JSON keys. `eng/contracts.py generate` merges
shards in filename order into the derived `proto/constraints.json` compatibility
snapshots; `generate --check` rejects stale snapshots without writing them.
Edit shards, never author the aggregate snapshots directly. A layout-only split
preserves their effective content and bytes.

The current holder of Plan's `roles/integration-contracts` is the single Contracts
integration owner. Authors append only their domain entries to
`eng/contract-packages.json` and `eng/foundation-inventory.json`; preserve existing
identities, ownership, wire reservations and historical baselines. Request shared
source changes through its designated author. The integration owner serially
merges independently reviewed CON.* heads after applicable checks pass and waits
for normal main publication before the next merge. The next author rebases onto
that main, regenerates bindings and inventories with pinned tools, and obtains
review of the updated head. Never hand-merge generated output or create a second
publication solely for validation.

A Dependabot Gradle PR can update the version catalog or wrapper without
refreshing the producer or isolated consumer locks and checksums. Wrapper
upgrades can also change embedded Kotlin dependencies. Complete the same update
sequence in that PR before merging; rebasing alone does not regenerate them.
Keep the wrapper JAR, scripts and properties together, verify the upstream JAR
and distribution checksums, and preserve the `.gitattributes` line-ending rules.

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

Before reusing source, tests, assets, wrappers or generated material, complete the
[ten-field provenance process](docs/implementation/wp00-03-provenance.md). The
Licensing and Provenance Owner reviews the exact files and disposition. Preserve
used records; source/target changes require a superseding record. Register a
licence/origin conflict and block that material until its formal resolution.
Run `python eng/check_provenance.py --owner Contracts` and the tooling tests.
Contributions use DCO with inbound-equals-outbound Apache-2.0; sign off commits.
No CLA, dual licensing or special distribution exception is introduced.

Use the proposal template for schema changes and the private reporting route in
SECURITY.md for vulnerabilities. Discuss changes respectfully and focus review
on reproducible behavior, compatibility and maintainability.
