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
lock files; CI restores them in locked mode (`npm ci` and `dotnet restore --locked-mode`).
For an intentional update, use `python eng/contracts.py restore --update-locks`,
regenerate and review both the dependency versions and the lock diff; ordinary CI
must never generate or accept a missing lock entry. The Gradle build, Kotlin
generators and Maven channel are retired (CON.40), so no Gradle lock, wrapper or
verification metadata is maintained here.

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

Dependabot updates the NuGet, npm and GitHub Actions dependencies. The Gradle
ecosystem and the npm `protobuf` and `connect` groups of the retired TypeScript
generators left the Dependabot configuration with CON.40, and the Java/Kotlin CodeQL job and its
pinned prerelease CodeQL bundle were removed; CodeQL analyses C#,
JavaScript/TypeScript and Python. Never reintroduce a source, generator or new
version for a retired package identity.

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
