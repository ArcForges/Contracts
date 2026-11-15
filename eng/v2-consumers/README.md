# V2 consumer inventory

Run the read-only source inventory from the Contracts repository:

```sh
python eng/v2-consumers/inventory.py --workspace /explicit/path/containing/repositories > consumer-inventory.json
python -m unittest discover -s eng/v2-consumers -p "test_*.py" -v
```

On Windows the workspace can be `C:/MyFile/Projects/ArcForges`. The command
checks `origin` identity for ArcForges, Cloud, Web, DesktopPlatform, Mobile, AI,
ArcScope, ArcSlate, ArcNotes and Contracts. It performs no fetch, build, package
resolution, migration or deletion. Credentials, local configuration and lockfiles
are not inspected. Repository errors use fixed diagnostics; remote URLs and Git
stderr are never included in the JSON.

Each repository is scanned at one exact committed HEAD. The report records that
revision, selected input hashes and whether tracked or untracked changes exist.
Uncommitted inputs are excluded. Missing, mismatched, unreadable or malformed
repositories are `unknown`; exit code 2 means the inventory is incomplete, not
that absent consumers have been established. Exit code 0 means all known source
repositories were observed. Neither result establishes an installed/deployed
cohort, package provenance or runtime compatibility.

The scanner reads tracked project XML, Directory.Build.props/targets,
Directory.Packages.props, package.json and go.mod from Git. It records declared
Contracts/DesktopPlatform package and project references separately from central
version declarations. DesktopPlatform package IDs come from its committed
projects. Conditional MSBuild inputs are marked conservatively and are not
evaluated; version expressions are declarations rather than resolved versions.
Generated language bindings, source call sites and arbitrary imported build files
are outside this bounded inventory. New dependency input formats require an
explicit scanner update before source retirement can rely on them.

All observed consumer edges remain protected. Independent Mobile, AI, ArcScope,
ArcSlate and ArcNotes are outside deletion scope. Shared
`arcforges.local.sandbox.v1` remains DesktopPlatform ContentSandbox and must not
be repurposed as V2 CLI Sandbox. This preparation command never authorizes source
or package deletion. Published artifacts and applied migrations remain immutable.

The tests create local temporary Git repositories and check parsing, revision
binding, dirty/missing/mismatched states and output redaction. They are input
tests, not native runtime or migration acceptance.
