# AF-CTR-06 file and registered-workspace contracts

This producer slice defines additive v1 messages, service methods and static shape
validation. It does not deliver the Node file service, workspace CLI, center routing,
filesystem safety, authorization, persistence or either platform's end-to-end
acceptance. Those remain AF-CTR-06 consumer work. The strict target is
[Design 06a](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/architecture/06a-node-files.md).

## Wire surface

The public Node package adds `files.proto`: ReadFile, WriteFile, EditFile,
SearchFiles, ListDirectory, PlanRemoval, ExecuteRemoval, GetFileOperation and
AcknowledgeFileOperation. The acknowledgment is local HUMAN management only and
has no Fleet counterpart. RegisterWorkspace and UnregisterWorkspace remain fixed
HUMAN-only; ListWorkspaces and GetWorkspace permit policy-authorized queries.

Fleet appends twelve named envelopes for those first eight operations and the
four workspace operations. Relay method values 9 through 20 bind the same exact
operations. Values 7 and 8 remain ListNodes/GetNode assertion-only values, never
routed channel calls. Mutation command IDs bind methods 1, 6, 10, 11, 14, 15, 17
and 18; a command is absent on these new read calls. The six new Fleet mutations
require an outer command ID, while their corresponding node request and the verified
call and result bind that same ID at runtime. New-method result shapes check ID
presence, not cross-message equality. Existing result shapes for methods 1–6 are
not tightened here. A relayed caller and its assertion must appear together. Shape
validation never verifies the assertion's signature or grants authority: the actual
center and node enforce authentication, account and device ownership,
nonce/signature/request binding, step-up, entitlement and policy.

Requests preserve fields 2 through 9 as reserved; new fields take free tags.
Responses retain value/error as one outcome and add bounded metadata-only audit
observations outside that outcome, so a post-read error can still account for the
bytes actually examined. The four existing workspace response shapes require an
outcome and their declared result presence. Registration requires a nonempty,
bounded path and mutation command identity; native absolute-directory resolution
and HUMAN classification remain runtime checks.

## Bounds and meaning

| Operation      | Contract boundary                                                                                                                                       |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Path           | Explicit workspace ID and present portable relative path, at most 4,096 UTF-8 bytes; empty only for list/search                                         |
| Read           | At most 65,536 returned bytes; SHA-256 of those returned bytes; next offset equals offset plus returned count without overflow; EOF and file size agree |
| Write          | At most 196,608 input bytes; exactly one expected whole-file SHA-256 or expected-absent=true                                                            |
| Edit           | Nonempty old text, each text at most 65,536 UTF-8 bytes, 1–1,000 expected non-overlapping occurrences, expected whole-file SHA-256                      |
| Search         | Literal or regex; at most 100 matches, 8 MiB scanned bytes, 10,000 visited entries and 64 bounded problems; truncation names its reason                 |
| Directory      | At most 128 entries per page, bounded opaque cursor and explicit snapshot/truncation metadata                                                           |
| Removal plan   | One workspace path or trusted attempt ID; at most root plus 1,000 descendants and 64 MiB; exact digest and expiry                                       |
| Node payload   | Request at most 245,760 serialized bytes; response at most 1,040,384; search response at most 131,072                                                   |
| Workspace list | Closed unique kinds, at most 500 records and 131,072 serialized response bytes; runtime must provide lossless continuation                             |

## Workspace adoption and legacy compatibility

The four existing workspace methods are being activated for AF-CTR-06. Their
request/response shape checks are tightened for the target: registration and
unregistration require a command ID and their declared path/ID; list and get
reject a read command ID; responses require an outcome and the declared value;
list kinds are closed and unique, at most 500 records and 131,072 encoded bytes.
These are validation/admission changes to existing wire messages, not changes to
their old field numbers or a promise that older unvalidated payloads pass the new
profile. Rollout must coordinate consumers and producers and capability checks.
The lower serialized list limit does not itself implement pagination or prove
that a continuation is lossless.

GitStatusSummary gains optional v1 tag 11 quality. A legacy summary with the tag
absent remains valid in the generic model; missing or UNSPECIFIED is never evidence
of COMPLETE. For Register/Get/List, a present summary must explicitly be COMPLETE,
UNKNOWN or TRUNCATED. COMPLETE requires present dirty, modified_files,
untracked_files and locked fields. UNKNOWN/TRUNCATED omit all old boolean and
count fields and may retain only independently established branch/head. A null
summary is valid only when the node proves the root is non-git; a shape validator
cannot establish that fact or execute the bounded safe Git query. These semantics
do not change the legacy generic Workspace model's validation of a summary with
no quality tag.

The search digest identifies the ordered actual scan transcript, not only matches.
Directory/workspace metadata digests identify their specified metadata transcript,
not file content. Audit observations name their precise digest scope and contain
counts and SHA-256 only. Consumers must enforce value/audit consistency and persist
no file body, search pattern or replacement text in an audit.

File-operation state distinguishes PREPARED, COMPLETED and UNKNOWN. UNKNOWN
remains uncertain after HUMAN acknowledgment; the hold and recorded outcome must
not turn into an invented success or an automatic repeated filesystem effect.
The shape checks reject missing preconditions, inconsistent read ranges/digests,
invalid result/hold combinations and duplicate audit scopes. They do not replace
the node's journal, transactions, approval or recovery behavior.

## Strict native cleanup remains unresolved

The approved target requires protection of the authorized source object and the
entire planned tree before any namespace effect. Linux capture-then-check and
attempted restoration do not supply that guarantee. In the currently measured
unprivileged Linux 6.12/ext4 environment it has not been established. A consumer
must refuse with explicit enforcement-unavailable before effect when it cannot
prove protection; a refusal does not satisfy the required real successful cleanup
or permit CTR06 delivery. No owner-only mock exception changes this rule.

## Validation and admission

C# tests use the generated codecs and validators; Go tests retain exact compiled
schema/descriptor-set equality and independent fixed wire samples. The official
exchange reads every message and oneof arm through the reference reader, generated
C# and generated Go codecs, with both directions checked. These are offline
contract tests, not runtime file or hosted acceptance.

The active package/access inventory, first-party generated-source successors and
dependency receipt are reviewed together. Historical retired identities and
immutable receipts remain intact. No external package, framework/toolchain pin,
runtime wire registry or reflection serializer is introduced. Until independent
review and the exact-head native Linux profile pass, provenance decisions remain
pending. Publication and consumer adoption use the repository's main-push cohort
and exact package versions; sibling source references are prohibited.
