# Registry setup and automatic releases

The workflow is `.github/workflows/ci.yml`. Main pushes automatically build,
validate and publish a version `1.0.0-ci.<run-number>.<run-attempt>`. PR,
merge-group and manual diagnostic events validate only. Setting a variable by
itself does not trigger a run; finish setup before the next main merge.

The GitHub repository is [ArcForges/Contracts](https://github.com/ArcForges/Contracts).
GitHub organisation membership does not create a corresponding npm organisation.

## 1. GitHub configuration

In repository Settings, create environments **nuget**, **npm** and **maven-central**. In each,
restrict deployment branches to **main**. Leave required reviewers and wait timers
off for unattended publication. Actions default permissions should be read-only;
NuGet/npm jobs request OIDC only after the consumer gate. Maven Central uses
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
approvals). Initial setup used disabled publisher switches. Normal operation now
uses `NUGET_PUBLISH_ENABLED=true` and `NPM_PUBLISH_MODE=oidc`; check the current
repository variables before diagnosing a skipped publication.

## 2. NuGet: use the existing account and add a Contracts policy

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
configured. The two initial package identities therefore need one bootstrap
publication. The workflow performs that publication automatically with a
temporary granular token:

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
   main. CI creates both `@arcforges/proto` and `@arcforges/api-client` after the
   Windows/Linux consumer gate. The proto package is uploaded first.

There is no manual `npm publish` command or version input in this sequence.
Bootstrap mode deliberately uses the temporary token instead of OIDC, because
package trust is not configured yet.

Official references: [token setup](https://docs.npmjs.com/creating-and-viewing-access-tokens/),
[npm trusted-publisher prerequisites](https://docs.npmjs.com/cli/v11/commands/npm-trust/).

## 4. npm: switch to OIDC after the first two packages exist

Open each package's Settings → Trusted publishing. Add GitHub Actions:

| Field                | Value                |
| -------------------- | -------------------- |
| Organisation or user | `ArcForges`          |
| Repository           | `Contracts`          |
| Workflow filename    | `ci.yml`             |
| Environment          | `npm`                |
| Allowed operation    | Direct `npm publish` |

Configure this **for both packages**. npm trust is per package; there is no
NuGet-style package glob policy. The relationship is reused for every future
version. A genuinely new npm package needs its own initial setup once.

Set **NPM_PUBLISH_MODE=oidc** before the next main merge. That run uses GitHub
OIDC and automatically supplies provenance on npm. Confirm both npm packages
were accepted, then delete the **NPM_BOOTSTRAP_TOKEN** GitHub environment secret,
revoke the token on npm, and disallow token publishing in the packages' publishing
settings. Keep account 2FA enabled. Daily main merges now need no credentials,
version entry or publish button.

The pinned Node/npm satisfy the current OIDC prerequisites. This is a public
GitHub-hosted workflow with repository metadata matching
`https://github.com/ArcForges/Contracts`. Renaming the workflow, repo or environment
requires updating its registry trust relationships.

Official reference: [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/).

The [main run publishing 1.0.0-ci.6.1](https://github.com/ArcForges/Contracts/actions/runs/34697244586)
completed both registry jobs. Its npm log records `NPM_PUBLISH_MODE=oidc`, and
both npm versions identify GitHub Actions as their trusted publisher with
provenance. The initial token is no longer needed for these two packages.
Deleting the GitHub environment secret removes that stored copy; revoke
`Contracts-initial-publish` in npm Account → Access Tokens to invalidate the
credential itself. Keep the package trusted-publisher connections and the GitHub
`npm` environment. This evidence concerns registry publication, not product or
Android device acceptance.

## Maven Central setup

Follow [the complete Maven Central account, signing and recovery guide](maven-central.md).
The group is `io.github.arcforges`, with `contracts-proto`, `contracts-client`
and `contract-fixtures`. They use the same candidate version as NuGet/npm.
Maven publication remains disabled until its separate account and secrets are ready.

## 5. Understand the result

- **Build candidate / Verify passed:** generation, code, archive contents and
  independent consumers passed. This alone is not registry publication.
- **Publish job skipped:** its registry is disabled, or this event was not a main
  push. Check the variables and workflow event.
- **Publish job passed:** that registry accepted the candidate, or an identical
  previously accepted version was verified. Registry scanning/indexing can finish
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
- **Candidate artifacts:** the exact bytes used for consumption and publication,
  retained for 30 days with hashes, source commit and descriptors. npm provenance
  is generated during OIDC upload, not by the local pack command.

The source manifests retain the development version. CI substitutes a shared
release version only in staging/output, so it does not push version-bump commits
or recursively trigger itself. Main builds and consumer gates remain independent.
The npm publication job serializes its registry read and upload with a shared
concurrency group and `queue: max` (up to GitHub's 100 pending-job limit), without
canceling an active publication. Because jobs can reach the queue out of source
order, the numeric version check also prevents an older run or retry from
replacing a newer `latest`. Superseded PR runs may be cancelled.

On the first main merge containing this change, the new version advances both
packages' `latest` tags from their old bootstrap version. No manual tag command,
long-lived token or re-upload of `1.0.0-ci.6.1` is needed. A `latest` value outside
the supported CI version series fails publication for review; stable-release
policy must be designed before introducing a different version series.

## 6. Failure and retry

Registries do not provide an atomic transaction spanning all six packages.
Treat the common version as usable only after all required packages are present.
Do not promote a partially published set by changing a client's dependency to an
unrelated version.

After correcting credentials or a transient registry failure, **re-run failed
jobs** on the same main run. They download the original successful candidate and
retain its version; no rebuild occurs. An already published npm version must
match tarball integrity. An existing NuGet version must match the original ZIP
contents, allowing only nuget.org's added repository signature. Maven compares
every tested JAR, POM and Gradle module metadata file byte for byte. A mismatch fails
instead of silently skipping it. A registry indexing delay may require retrying
after the existing version becomes visible.

Re-running all jobs creates a new candidate with an increased attempt suffix,
which is a new version. Missing/expired artifacts also require a new validated
run; do not reconstruct an old version from another source revision.

To stop future uploads, disable the relevant variable. To recover consumers,
pin their last verified version and merge a fix that publishes a new immutable
version. Existing packages are never overwritten, automatically unlisted or
deleted. Stable release promotion and production compatibility baselines are
outside this Hello World bootstrap.
