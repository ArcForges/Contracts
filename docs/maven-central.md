# Maven Central setup and recovery

Kotlin artifacts use the Sonatype Central Portal. The Maven group is
`io.github.arcforges`; module names are `contracts-proto`, `contracts-client` and
`contract-fixtures`. New versions require no new package registration.

## One-time account and signing setup

1. Register/sign in at [Central Portal](https://central.sonatype.com/) and verify
   the account email. Claim `io.github.arcforges`. Follow the Portal's current
   GitHub ownership-verification instructions for the `ArcForges` organisation;
   owning a different personal namespace is insufficient. Complete this before
   enabling publication. See [namespace verification](https://central.sonatype.org/register/namespace/).
2. On the [user-token page](https://central.sonatype.com/usertoken), generate a
   publishing user token. Its generated username and password/token are the API
   credential pair, not the website login password.
3. Create or select a dedicated PGP signing key and retain a secure backup in
   your normal key manager. Publish its public key to a supported key server:
   Central must retrieve it before validating signatures. Export the ASCII-armored
   private signing key directly to the protected secret input; do not put it in
   source, repository variables or chat. Follow [Central's PGP guide](https://central.sonatype.org/publish/requirements/gpg/).
4. In GitHub repository Settings → Environments → **maven-central**, add these
   **environment secrets**:

   | Secret                   | Value                                                                |
   | ------------------------ | -------------------------------------------------------------------- |
   | `MAVEN_CENTRAL_USERNAME` | Username generated with the Portal user token                        |
   | `MAVEN_CENTRAL_TOKEN`    | Password/token generated with the same user token                    |
   | `MAVEN_SIGNING_KEY`      | Complete ASCII-armored private signing key, including boundary lines |
   | `MAVEN_SIGNING_PASSWORD` | Passphrase for that signing key                                      |

5. Set repository variable **MAVEN_PUBLISH_ENABLED=true** after namespace
   verification and the secrets are ready. The environment accepts main only;
   no reviewer or timer is needed for unattended releases.
6. Merge the accepted PR. CI allocates a version, builds all six packages, tests
   them on Windows/Linux, then runs the registry jobs. Maven signing adds detached
   signatures and checksums to tested files. The Portal request selects
   `AUTOMATIC`; no manual publish button, version entry or local Gradle publish is
   part of the normal release flow.
7. Confirm **Publish Maven Central** reports that all three modules match the
   tested candidate in the public repository. A disabled job skips visibly;
   an enabled job with missing credentials fails. Keep the environment, Portal
   token and signing key for future releases and rotate credentials when needed.

This Portal integration uses a stored token and signing key; deleting them stops
future Maven releases. Existing NuGet/npm OIDC configuration is independent.
The initial GitHub setup leaves Maven disabled and contains no dummy secrets.
Account ownership and private credential values must come from a maintainer.

See [Portal tokens](https://central.sonatype.org/publish/generate-portal-token/),
[publication requirements](https://central.sonatype.org/publish/requirements/) and
[Publisher API](https://central.sonatype.org/publish/publish-portal-api/).

## Failed-job recovery

The `maven-deployment-<run-id>-<attempt>` artifact contains a non-secret receipt
tied to the candidate version, source commit and unsigned bundle hash. A failed
job retry downloads matching receipts from the same workflow run and resumes
the accepted deployment ID. It does not rebuild or repeat the upload. Validation
failure, an unexpected manual-publication state, a mismatching public version
or an unknown state fails visibly. Retain the receipt for investigation.

A timeout after sending an upload but before receiving its ID is ambiguous.
The retry refuses another upload. Inspect Central, set **environment variable**
`MAVEN_CENTRAL_DEPLOYMENT_ID` to the confirmed deployment ID and re-run the failed
job. Remove that variable afterwards; it is not a normal release setting. If
Central confirms there was no accepted upload, use a new validated main run and
version. Do not delete or overwrite an existing release to make a retry succeed.

`PUBLISHED` can precede CDN visibility. After Central completes, the job allows
15 minutes for public files to appear. A later retry compares existing bytes
again. Partial visibility causes a retryable failure, never an overwrite of the
visible subset. A completely matching public release succeeds without another
upload. Search-page indexing is not the acceptance gate.

Candidates are retained for 30 days and receipts for 90 days. An expired
candidate requires a new version even if its receipt remains. Use **Re-run failed
jobs** to retain an existing candidate; **Re-run all jobs** builds a new version.
Each registry has separate results, so a green Verify or NuGet/npm publication
does not establish Maven publication.
