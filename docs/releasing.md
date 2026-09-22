# Registry setup and automatic releases

The workflow is `.github/workflows/ci.yml`. Main pushes automatically build,
validate and publish NuGet/npm `1.0.0-ci.<run-number>.<run-attempt>` and Maven `1.0.0-SNAPSHOT`. Canonical `vX.Y.Z` tags on main ancestry publish `X.Y.Z` across all three registries. PR,
merge-group and manual diagnostic events validate only. Setting a variable by
itself does not trigger a run; finish setup before the next main merge.

The GitHub repository is [ArcForges/Contracts](https://github.com/ArcForges/Contracts).
GitHub organisation membership does not create a corresponding npm organisation.

## 1. GitHub configuration

In repository Settings, create environments **nuget**, **npm** and **maven-central**. In each,
restrict deployment to branch **main** and tags **v***. Leave required reviewers and wait timers
off for unattended publication. Actions default permissions should be read-only;
NuGet/npm jobs request OIDC only after the build/offline candidate gate. Maven Central uses
its own environment secrets and requests no OIDC token.

Under Settings → Secrets and variables → Actions → Variables:

| Variable                | Initial setup                                                     | Normal operation                       |
| ----------------------- | ----------------------------------------------------------------- | -------------------------------------- |
| `NUGET_USER`            | Your nuget.org username, currently `dekueon`                      | Same username; not an API key or email |
| `NUGET_PUBLISH_ENABLED` | Unset or `false` until the policy below exists                    | `true`                                 |
| `NPM_PUBLISH_MODE`      | Unset/`disabled`, then `bootstrap` for the first creation         | `oidc`                                 |
| `MAVEN_PUBLISH_ENABLED` | `false` until Central namespace, token and PGP key are configured | `true`                                 |

No normal NuGet or npm publishing secret is required. npm's **first creation**
uses the temporary environment secret described below. Repository variables are
not secrets; never put a token in a variable.

Enable dependency graph/Dependabot alerts and security updates, private
vulnerability reporting, secret scanning and push protection. The repository
files add Dependabot updates, CodeQL, secret scanning in CI and PR dependency
review. CodeQL and the security workflow are separate PR checks; package upload
is directly gated by the CI `Verify` job. Require successful CI/security checks
in branch protection before merging.

These GitHub-side settings are configured for this repository, including the
CI/security checks (including Java/Kotlin CodeQL) and PR requirement on main (zero required review
approvals). Normal operation uses `NUGET_PUBLISH_ENABLED=true` and
`NPM_PUBLISH_MODE=oidc`; the WP03.00 first publication temporarily used bootstrap
mode for new npm identities. See the [accepted publication and OIDC transition](#wp0300-accepted-publication)
for the recorded state, and check current repository variables before diagnosing
a skipped publication.

## 2. NuGet: authorize every registered package family

Sign in to [nuget.org](https://www.nuget.org/) with the existing verified account.
Open the username menu → Trusted Publishing and create a policy:

| Field            | Value                                                                |
| ---------------- | -------------------------------------------------------------------- |
| Policy name      | `ArcForges-Contracts`                                                |
| Package owner    | `dekueon` (or the account/organisation that will own these packages) |
| Provider         | GitHub Actions                                                       |
| Repository owner | `ArcForges`                                                          |
| Repository       | `Contracts`                                                          |
| Workflow file    | `ci.yml` (filename only)                                             |
| Environment      | `nuget`                                                              |
| Permission       | Push new packages and versions                                       |
| Package pattern  | `ArcForges.Contracts.*`                                              |

The same trusted workflow/environment must also authorize `ArcForges.Sdk.*` and
`ArcForges.Cli` through matching additional policies. Confirm all three scopes
before merging the first complete split-package candidate. An existing
`ArcForges.Contracts.*` policy alone is insufficient.

The DesktopPlatform policy does not authorise this repository. The wildcard
allows future matching package IDs without creating a policy per version. It
does not reserve a namespace or confer ownership of someone else's package.

Set `NUGET_USER` to the username and `NUGET_PUBLISH_ENABLED=true` after saving
the policy. The workflow exchanges its GitHub identity for a short-lived key.
You do not create or paste a long-lived NuGet API key.

Official reference: [NuGet trusted publishing](https://learn.microsoft.com/en-us/nuget/nuget-org/trusted-publishing).

## 3. npm: account, scope and first creation through CI

Create/sign in to [npm](https://www.npmjs.com/), verify the email address and
enable account 2FA. Create the **arcforges** organisation (public packages can use
the free plan), or obtain publication rights from its existing owner. You must
be able to publish under `@arcforges`; do not silently rename the package scope.

npm currently requires a package to exist before its trusted publisher can be
configured. Every new package identity needs one first real candidate publication.
The initial proto/API packages already existed; WP03.00 introduced
`@arcforges/contract-fixtures`, `@arcforges/ai-internal` and
`@arcforges/operator-client`. All five now exist; the completed bootstrap and
remaining OIDC evidence are recorded below. A future new identity follows the
same first-creation sequence with a temporary granular token:

1. In the npm account menu, open Access Tokens and create a granular token named
   `Contracts-initial-publish`.
2. Permit direct publication in its package permissions and select the
   `@arcforges` scope. Scope access covers the new package identities. Organisation
   administration permissions are unnecessary.
3. Enable bypass of publishing 2FA for this temporary CI token. Choose a short
   expiry, such as one day. Hosted runners do not have one fixed outbound IP.
4. Copy the token directly into GitHub Settings → Environments → **npm** →
   Environment secrets, named **NPM_BOOTSTRAP_TOKEN**. Do not send it in chat,
   put it in source or store it as a repository variable.
5. Set the repository variable **NPM_PUBLISH_MODE=bootstrap**.
6. Merge the bootstrap PR, or the next accepted PR if the scaffold is already on
   main. CI publishes all registered npm packages after the
   build/offline candidate gate, in dependency order. Use a token authorized for
   existing packages and new identities; secret-name presence does not prove validity.

There is no manual `npm publish` command or version input in this sequence.
Bootstrap mode deliberately uses the temporary token instead of OIDC, because
package trust is not configured yet.

Official references: [token setup](https://docs.npmjs.com/creating-and-viewing-access-tokens/),
[npm trusted-publisher prerequisites](https://docs.npmjs.com/cli/v11/commands/npm-trust/).

## 4. npm: configure OIDC for every package after first creation

Open each package's Settings → Trusted publishing. Add GitHub Actions:

| Field                | Value                |
| -------------------- | -------------------- |
| Organisation or user | `ArcForges`          |
| Repository           | `Contracts`          |
| Workflow filename    | `ci.yml`             |
| Environment          | `npm`                |
| Allowed operation    | Direct `npm publish` |

Configure this **for every package in the producer catalog**. npm trust is per package; there is no
NuGet-style package glob policy. The relationship is reused for every future
version. A genuinely new npm package needs its own initial setup once.

Set **NPM_PUBLISH_MODE=oidc** before the next main merge. That run uses GitHub
OIDC and automatically supplies provenance on npm. Confirm every required npm package
was accepted, then delete the **NPM_BOOTSTRAP_TOKEN** GitHub environment secret,
revoke the token on npm, and disallow token publishing in the packages' publishing
settings. Keep account 2FA enabled. Daily main merges now need no credentials,
version entry or publish button.

The pinned Node/npm satisfy the current OIDC prerequisites. This is a public
GitHub-hosted workflow with repository metadata matching
`https://github.com/ArcForges/Contracts`. Renaming the workflow, repo or environment
requires updating its registry trust relationships.

Official reference: [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/).

The historical [main run publishing 1.0.0-ci.6.1](https://github.com/ArcForges/Contracts/actions/runs/34697244586)
completed its NuGet/npm registry jobs. Its npm log records
`NPM_PUBLISH_MODE=oidc`, and the proto/API versions identify GitHub Actions as
their trusted publisher with provenance. This proves OIDC only for those two
package identities; it does not authorize later packages or establish their
OIDC publication. Follow the all-package confirmation above before removing a
temporary credential used for a later expansion. Deleting the GitHub environment
secret removes that stored copy; revoking the token in npm Account → Access
Tokens invalidates the credential itself. Keep the package trusted-publisher
connections and the GitHub `npm` environment. Registry publication does not
establish product or Android device acceptance.

## Maven Central setup

Follow [the complete Maven Central account, signing and recovery guide](maven-central.md).
The group is `io.github.arcforges`, with `contracts-proto`,
`contracts-connect-client` and `contract-fixtures`. The native-only
`contracts-client` is retired from new candidates; historical releases remain available. Formal releases share the NuGet/npm version; development Maven snapshots retain the CI build identity in JAR metadata. Enable SNAPSHOTs for the existing namespace; keep its credentials and publication switch.
For a new repository installation, leave Maven disabled until that setup is ready.

## 5. Understand the result

- **Build candidate / Verify passed:** generation, code, archive contents and
  targeted offline checks passed; runtime consumers were not run. This alone is not registry publication.
- **Publish job skipped:** its registry is disabled, or this event was not a main or formal-tag
  push. Check the variables and workflow event.
- **Publish job passed:** the provider accepted the candidate or an identity-bound recovery completed.
  A SNAPSHOT receipt with phase `superseded` explicitly means no upload because a newer main commit owns the channel. Registry scanning/indexing can finish
  after upload. Check the registry job for each ecosystem separately.
- **npm latest:** the highest published `1.0.0-ci.<run-number>.<run-attempt>`
  version in that package, compared numerically by run number and then attempt.
  New main releases explicitly publish with `--tag latest`. npm's default package
  page and a fresh install without a version use this tag, even though these
  builds remain prereleases. Consumers still pin the exact verified version.
- **npm ci / old next:** an older delayed run publishes using `ci` when a newer
  `latest` already exists; it cannot move the default version backwards. `ci` is
  only a non-default tag for such uploads, not a newest-version channel. The old
  `next` tag is retained for existing users but is no longer advanced. Existing
  consumer manifests and locks do not update themselves when a tag moves.
- **Candidate artifacts:** the exact bytes retained for publication,
  retained for 30 days with hashes, source commit and descriptors. npm provenance
  is generated during OIDC upload, not by the local pack command.

The source manifests retain the development version. CI substitutes a shared
release version only in staging/output, so it does not push version-bump commits
or recursively trigger itself. Main builds retain their own source/version allocation; hosted consumer gates are removed.
The npm publication job serializes its registry read and upload with a shared
concurrency group and `queue: max` (up to GitHub's 100 pending-job limit), without
canceling an active publication. Because jobs can reach the queue out of source
order, the numeric version check also prevents an older run or retry from
replacing a newer `latest`. Superseded PR runs may be cancelled.

After the first stable release, main builds use npm `ci` and cannot replace stable
`latest`. A newer stable version advances `latest`; an older stable release uses
`release`. Before the first stable version, the existing numeric CI latest policy
above continues. These mutable tags do not alter consumer locks.

## 6. Failure and retry

Registries do not provide an atomic transaction spanning all 22 packages.
Treat the common version as usable only after all required packages are present.
Do not promote a partially published set by changing a client's dependency to an
unrelated version.

Inspect the exact failure before retrying a publication job. Stop on local network failure; do not
change proxies or retry blindly. Diagnose CI failures and fix their concrete cause before recovery. A diagnosed retry uses the original retained candidate/version,
without rebuilding. Existing npm versions are compared through registry integrity metadata.
An existing NuGet version fails for investigation of its publication receipt; it is not downloaded
or silently skipped. Maven formal recovery resumes the retained deployment ID and checks provider
status/coordinates. SNAPSHOT upload checks the latest main identity and completes at transport
success. No registry uses a routine public archive download/byte-comparison cycle.

Re-running all jobs on a main run creates a new candidate with an increased CI attempt suffix. Formal tags keep their immutable version, so retry failed publication jobs using the retained original candidate. Missing/expired artifacts also require a new validated
run; do not reconstruct an old version from another source revision.

To stop future uploads, disable the relevant variable. To recover consumers,
pin their last verified version and merge a fix that publishes a new immutable
version. Immutable releases are never overwritten, automatically unlisted or deleted. Maven development snapshots are the explicit mutable exception. Formal tag publication does not establish product readiness or production compatibility.

## WP03.00 first publication readiness

Before source merge, confirm NuGet policy coverage for Contracts, SDK and CLI,
and a valid scope-authorized temporary npm bootstrap credential for the three new
package identities. Existing OIDC for proto/API does not authorize packages that
do not yet exist. Publish only the reviewed actual candidate; do not create empty
placeholder packages or allocate verification-only versions. Configure each new
package's trusted publisher after its first accepted publication, then return the
repository to OIDC mode. npm trust administration requires an authenticated account
with 2FA; a publishing token that bypasses 2FA does not authorize trust management.

After merge, inspect the expected commit and required publication job results,
then fast-forward the clean primary checkout. Do not run another package download,
hash-audit, install or runtime cycle. Report partial publication and pending account
setup explicitly; neither a secret name nor green compilation proves publisher readiness.

### WP03.00 first-publish correction

Run 35702693766 published NuGet and Maven successfully and npm proto/API
`1.0.0-ci.82.1`, but stopped before the three new npm uploads. The dist-tag
management endpoint returned HTTP 401 for the unpublished fixture package.
Tag selection now reads `dist-tags` from the public package metadata document;
a missing package (404) starts at `latest`, while 401/403 and other failures
still stop publication. Stable and newer CI tags retain their existing protection.

The old run is a partial release and is not an accepted complete package set.
Re-running its unchanged job would execute the same defective source. The reviewed
source correction used the normal main publication channel to produce the
complete corrected release below; it did not overwrite or republish the old
immutable versions.

### WP03.00 accepted publication

[Contracts PR #34](https://github.com/ArcForges/Contracts/pull/34) merged as
`84c89054b119bb0afa595c85ad85c24638501b65`. Its
[main run 35704055306](https://github.com/ArcForges/Contracts/actions/runs/35704055306)
passed Build candidate, Verify and all three publication jobs; the
[matching Security run](https://github.com/ArcForges/Contracts/actions/runs/35704055307)
also passed. It published the
complete registered set of 22 outputs: 14 NuGet and five npm packages at
`1.0.0-ci.84.1`, plus the three Maven modules at `1.0.0-SNAPSHOT` with that source
and CI build identity. This is the accepted WP03.00 package set; the earlier
partial `1.0.0-ci.82.1` set remains historical.

The npm job used bootstrap authorization. On 2026-09-22, the account owner
confirmed that all three new packages have their GitHub Actions trusted
publisher saved for `ArcForges/Contracts`, workflow `ci.yml`, environment `npm`,
with direct `npm publish` allowed. `NPM_PUBLISH_MODE` was then set to `oidc` and
read back. The first normal OIDC publication covering all five packages has
not yet been observed. The temporary `NPM_BOOTSTRAP_TOKEN` environment secret
is retained until that publication succeeds; OIDC mode does not pass it to the
publisher. Afterwards, remove the stored secret and revoke the npm token as
described above. No verification-only publication, replacement version or tag
is required to record this transition.

Acceptance uses the expected source identity and successful build/publication
job results. No post-publication archive download, installation or runtime test
was performed. The selected structure, generated slices and offline checks do
not establish the later WP03 business-schema, compatibility, product integration
or device acceptance gates.
