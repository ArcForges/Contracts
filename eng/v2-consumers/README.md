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

## AFV2-MIG-01 cutover inventory

The committed source review used these `origin/main` snapshots at cutover
start. The six independent worktrees were clean and matched their listed
revisions.

| Repository | Source revision |
| --- | --- |
| ArcForges | `237e5cccbbdc8d01eff4579b29d2882214cbdad9` |
| Cloud | `9b8796eac760982d9814f371b820b736ddd945c4` |
| Web | `d517bc45fc50e3143a25c7987726f37a24a4999b` |
| Contracts | `0cd178ac8bec8c32f06366dcb30fea6dd6566bf3` |
| DesktopPlatform | `6e109ef5d01855158c7ae3a63cd42c98db2647f3` |
| Mobile | `072ee675e8ea67e779922082dbf65dbc02ed6916` |
| AI | `70f8b22d56d67abd2a983f8b448846731ee22902` |
| ArcScope | `485c8d6d9a84825eb5bc737c9808b8bc4b616643` |
| ArcSlate | `569785a050c97a8022fe264f6af986285766bf87` |
| ArcNotes | `2839da696cf3d6cc8ab3c241212eea8403c5a0a1` |

This review supplements the package-declaration scanner with selected committed
locks and authored source. The six independent snapshots showed no direct
TaskService, FleetService or Node v1 file/workspace call in the checked source.
Their observed shared edges are below. Version suffixes in this table use the
`1.0.0-ci.` prefix.

| Consumer | Protected lock and source edge |
| --- | --- |
| DesktopPlatform | ContentSandbox Contracts/Broker lock Foundation, LocalRpc.Platform and LocalRpc.Sandbox at `216.1`. The ContentSandbox contract uses the independent `arcforges.local.sandbox.v1` descriptor. The separate Realtime AOT probe locks Foundation, PublicApi and Events at `270.1`. [ContentSandbox call site](https://github.com/ArcForges/DesktopPlatform/blob/6e109ef5d01855158c7ae3a63cd42c98db2647f3/src/DesktopHelpers/ArcForges.ContentSandbox.Contracts/ContentSandboxContract.cs), [ContentSandbox lock](https://github.com/ArcForges/DesktopPlatform/blob/6e109ef5d01855158c7ae3a63cd42c98db2647f3/src/DesktopHelpers/ArcForges.ContentSandbox.Contracts/packages.lock.json), [Realtime lock](https://github.com/ArcForges/DesktopPlatform/blob/6e109ef5d01855158c7ae3a63cd42c98db2647f3/tests/ReleaseArtifactTests/Realtime/packages.lock.json) |
| Mobile | The Network project locks PublicApi and Events at `324.1`. Its actual client calls the shared Hello RPC. [Hello client](https://github.com/ArcForges/Mobile/blob/072ee675e8ea67e779922082dbf65dbc02ed6916/src/core/ArcForges.Mobile.Network/CloudHelloClient.cs), [Network lock](https://github.com/ArcForges/Mobile/blob/072ee675e8ea67e779922082dbf65dbc02ed6916/src/core/ArcForges.Mobile.Network/packages.lock.json) |
| AI | The Hello implementation imports schemas from the retired npm output `@arcforges/proto@1.0.0-ci.287.1`. Preserve that published version and the producer's retirement record. [Hello source](https://github.com/ArcForges/AI/blob/70f8b22d56d67abd2a983f8b448846731ee22902/src/hello.ts), [npm lock](https://github.com/ArcForges/AI/blob/70f8b22d56d67abd2a983f8b448846731ee22902/package-lock.json), [Pinned publication](https://github.com/ArcForges/Contracts/actions/runs/36966686225) |
| ArcScope | Core and the desktop executable lock Hello-bearing PublicApi `36.1`. The executable also locks Foundation and LocalRpc.Scope at `113.1`, and the annotation Application/Infrastructure lock Foundation `216.1`. [Hello client](https://github.com/ArcForges/ArcScope/blob/485c8d6d9a84825eb5bc737c9808b8bc4b616643/src/ArcForges.ArcScope.Core/CloudHelloClient.cs), [Executable lock](https://github.com/ArcForges/ArcScope/blob/485c8d6d9a84825eb5bc737c9808b8bc4b616643/src/ArcForges.ArcScope/packages.lock.json), [Annotation lock](https://github.com/ArcForges/ArcScope/blob/485c8d6d9a84825eb5bc737c9808b8bc4b616643/src/ArcForges.ArcScope.Infrastructure/packages.lock.json) |
| ArcSlate | Core locks PublicApi `36.1` and calls Hello. [Hello client](https://github.com/ArcForges/ArcSlate/blob/569785a050c97a8022fe264f6af986285766bf87/src/ArcForges.ArcSlate.Core/CloudHelloClient.cs), [Core lock](https://github.com/ArcForges/ArcSlate/blob/569785a050c97a8022fe264f6af986285766bf87/src/ArcForges.ArcSlate.Core/packages.lock.json) |
| ArcNotes | Core locks PublicApi `36.1` and calls Hello. [Hello client](https://github.com/ArcForges/ArcNotes/blob/2839da696cf3d6cc8ab3c241212eea8403c5a0a1/src/ArcForges.ArcNotes.Core/CloudHelloClient.cs), [Core lock](https://github.com/ArcForges/ArcNotes/blob/2839da696cf3d6cc8ab3c241212eea8403c5a0a1/src/ArcForges.ArcNotes.Core/packages.lock.json) |

Keep the shared Go Hello registration and its Worker forwarding route when
retiring the old C# Center. The current V2 CenterControl adapter also uses
Fleet v1 `NodeEnrollmentService` for sign-in, device-code enrollment, refresh,
reporting and sign-out. Its Go routes and consent/activation pages are separate
from the legacy FleetService registry, Task and host file/workspace routes.
CloudLink's V2 channel still imports shared Node and Relay bindings. [Go Hello
registration](https://github.com/ArcForges/Cloud/blob/9b8796eac760982d9814f371b820b736ddd945c4/center/internal/server/server.go#L239),
[Worker routes](https://github.com/ArcForges/Cloud/blob/9b8796eac760982d9814f371b820b736ddd945c4/worker/tables/center-tables.generated.ts),
[Node enrollment client](https://github.com/ArcForges/ArcForges/blob/237e5cccbbdc8d01eff4579b29d2882214cbdad9/src/ArcForges.Node.CloudLink/CenterClient.cs),
[Browser and device-code sign-in](https://github.com/ArcForges/ArcForges/blob/237e5cccbbdc8d01eff4579b29d2882214cbdad9/src/ArcForges.Node.CloudLink/SignInOrchestrator.cs),
[Go enrollment routes](https://github.com/ArcForges/Cloud/blob/9b8796eac760982d9814f371b820b736ddd945c4/center/internal/routes/fleet.go),
[Legacy operation list](https://github.com/ArcForges/Cloud/blob/9b8796eac760982d9814f371b820b736ddd945c4/center/internal/routes/nodes.go),
[V2 channel](https://github.com/ArcForges/ArcForges/blob/237e5cccbbdc8d01eff4579b29d2882214cbdad9/src/ArcForges.Node.CloudLink/ChannelLoop.V2.cs)

The active Contracts change records this inventory and retains the tracked
schemas, generated bindings and package definitions. The cutover targets
obsolete runtime registrations. It requires no edit to the six independent
repositories. Published artifacts and applied migration history retain their
original bytes. This source audit reports committed locks and call sites and
does not establish installation, deployment, package re-resolution or native
acceptance. Keep the [historical scanner report](observed-20261116.json) at its
original scope. [Package inventory](../contract-packages.json),
[Publication policy](../../docs/releasing.md#retired-channels-con40)
