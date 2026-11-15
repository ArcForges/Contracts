<!-- SPDX-License-Identifier: Apache-2.0 -->

# Contracts Go qualification evidence

This describes the bounded AD-0023 admission mechanism. It is an implementation
draft, not a qualification receipt. No dependency, generated provenance record or
host result is activated by this document.

The reviewed `review.goQualification` object belongs to the normal immutable
dependency review receipt. Its schema is
`arcforges.contracts.go-qualification.v1`; its authority is Design commit
`2296e2fe37ad9ad1f7b65be871fea1f0b39ce7ad`. The only eligible metadata names are
the nine candidates in that decision. Both untagged implementation dependencies
must be the two explicitly named modules. A module used by any applicable tool,
owned test or existing Linux race configuration immediately loses metadata
eligibility, regardless of which selected version was used.

Prepare evidence in this order:

1. Commit and independently review the implementation, tool selections, owned Go
   sources/tests, module locks and invocation configuration. Keep the active
   qualification absent until actual measurements exist. Preserve the separate
   pending generated-provenance records and historical receipts.
2. On each designated host, independently fetch that common source commit and run
   the existing dependency collector. Each host retains its own complete selected
   graphs, upstream requirement edges, all four tool closures, owned package/test
   closure and Linux race closure where applicable. Failed, dirty or drifting
   source measurements do not qualify. Nothing is copied to another host as a
   replacement for native execution.
3. Record the common `sourceCommit`,
   `dependency_admission.go_qualification_inputs(root)` result and two platform
   references under `platforms.windows` and `platforms.linux`. Each reference has
   `sourceCommit`, UTC `measuredAtUtc`, a host-local `report.location` and its
   `report.sha256`, plus the portable `go_report_summary(report)` result. The
   summary contains native/default configuration, normalized selected-graph,
   complete requirement-edge and package-closure hashes, and recomputed
   classifications. References identify reviewed evidence; they are not stored
   native success statuses.
4. Compute `metadataOnly` as the sorted selected `go:<module>@<version>` identities
   among the nine named candidates whose module path is absent from every
   platform's actual closures. Keep all selected entries and checksums, including
   metadata entries. Unknown unused modules receive no qualification. The
   complete input fingerprint includes all `go/**` source, tests, embeds, nested
   module files and checked-in invocation/workflow controls, so changing owned
   code or a build configuration requires fresh review even if the five module
   input files did not change.
5. For each entry of `untaggedDependencies`, record exact `version`, full
   `sourceCommit`, admitted `checksum`, UTC `queriedAtUtc`, upstream `repository`,
   ordinary `defaultBranch`, and exact official `versionQuery` and `commitQuery`
   source URLs and response SHA256 values. Retain the downloaded official
   responses in the dated source inventory for independent review. The proxy
   response must establish the selected pseudo-version/commit identity; the
   ordinary default-branch response must establish that this is the latest
   upstream commit at lock time. Include the explicit `maturity` disclosure and
   concrete compatibility, security and licence assessments. A source URL/hash
   field alone is not a review of its contents or a latest-version observation.
6. Add that reviewed object to the successor dependency receipt and active policy
   through the normal complete admission change. Their source baseline must be
   an ancestor of the candidate with identical complete Go/control input
   membership and LF hashes. This narrow identity check avoids embedding a
   self-referential final commit in its own policy document; it grants no general
   ancestry or older-dependency exception.
7. Push the complete candidate. Run the required full profile and final actual
   measurements on both applicable native hosts at the same final source SHA.
   `go static` runs its unchanged checks, then the existing collector once, and
   immediately validates that new host-local result against the reviewed
   reference. It requires the current clean HEAD, index, full source-tree
   identity, exact module/lock bytes, all expected queries/configurations and
   matching graph/closure/classification summaries. A pre-existing report does
   not replace this execution. The coordinator independently reviews the final
   pair of results before acceptance; the formal Contracts merge status remains
   its existing Linux profile.

The two retained maturity strings are `experimental; no compatibility promise`
for `golang.org/x/exp/typeparams` and `no API compatibility promise` for
`golang.org/x/telemetry`. These are disclosed upstream limitations, not stable API
claims. All prior locked resolution, checksum, tidy, analyzer, test,
vulnerability, Native AOT, source/provenance and publication gates remain in
force.
