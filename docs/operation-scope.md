# Operation scope and reachability gate

`eng/check_operation_scope.py` validates the offline producer metadata and writes
the deterministic operation-by-actor matrix. The normal Contracts build runs it
and retains `artifacts/evidence/operation-reachability.json` with the other policy
reports. Tooling unit tests exercise positive retained-source coverage and hostile
metadata. This evidence is not runtime authorization or installed-consumer proof.

The frozen `eng/operation-scope-manifest.json` contains all 310 rows of Design
manifest 11 at the recorded source commit, including pending and reserved future
operations. Pending operations need no invented service. Future operations may
not be registered. The optional `--oracle <manifest11.md>` additionally checks
the normalized UTF-8/LF source digest and exact sorted rows; CI needs no Design
checkout or network access. Scope changes require an explicit reviewed oracle
update, not scraping a moving branch during builds.

Each domain owns a JSON export under `eng/operations/`. Its top-level object has
`schemaVersion: operation-metadata.v1` and an `operations` array. Each row supplies
`operationId`, exact `binding`, `kind` (`proto`, `http`, or `in-process`), repository
relative `source`, `scope`, `surface`, `profile`, anchored Design `sourceRule`,
`idempotency` and all eight `authorization` fields. The initial extension export
is a complete example. Domains append their own files, without rewriting another
domain's entries. Duplicate JSON keys, operations and bindings are rejected.

Authored public and internal proto service methods are discovered independently.
Each must have exactly one export pointing to the exact source and fully qualified
`package.Service/Method`, except for the exact retained Hello migration example
and the single closed CON.11 private RunStream projection below. HTTP and
in-process bindings use explicit domain exports referencing real source files;
the gate does not infer runtime route registrations from arbitrary source
languages. Producers must export those bindings as part of their owned
route/descriptor generation. Report provenance preserves their declared binding
kind, source, profile and authority anchor.

The only private projection exception is
`arcforges.cf.v1.RunStreamService/Run` from
`internal/proto/arcforges/cf/v1/stream.proto`, bound to the exact RPC vector in
`fixtures/internal/con-11-run-stream.json`. The checker discovers the method,
validates that source and fixture identity, and reports it separately as a
private service projection. It is not an operation: it has no operation ID,
export row, authorization profile or operation-matrix/count entry. Every other
public or internal proto method still requires exactly one exact operation
export; no path, package or service wildcard is exempt.

Authorization fields are `capability`, `risk`, `approval`, `stepUp`,
`localPresence`, `egress`, `patEligible`, and `actorKinds`. Boolean fields are
literal booleans, risk is R0–R3, and actors must be classified identities. Exact
source profiles determine approval and egress strings; non-placeholder strings
are syntactically accepted but do not constitute new source authority. Review
must verify their pinned Design rule. Null capability is required outside tool
bindings. Tools require explicit oracle allowlisting; human-only decisions remain
denied even if allowlisted. PATs use the closed catalogue operation set. Operator,
CF service, customer, helper and provider identities are not interchangeable.

Invoke uses the closed `delegated-invocation` profile. All seven non-PAT fields
must use objects of the form `{"from":"admittedCapability.risk"}`; capability
uses `admittedCapability.operationId`. PAT remains false. Its `delegation` object
must set `intersectOriginalActor`, `requireCurrentGrant`, `denyHumanOnly` and
`requireLaunchRole` to true. The runtime must intersect descriptor, original actor
and current grant and check receiver launch direction. The matrix marks these
fields derived rather than claiming static authority. Unknown or partial
expressions fail. Helper parents acting for a human require the `helper-parent`
profile and `launchRoles: ["owning-parent"]`; this does not grant tool access.

Invoke also derives `idempotency` from `admittedCapability.idempotency`, rather
than treating every delegated effect as a retryable write. Bootstrap uses the
separate `launch-bootstrap-only` profile: its actorKinds expression is exactly
`{"from":"verifiedLaunchProfile.actorKinds"}`, launchRoles is exactly
`{"from":"verifiedLaunchProfile.callerRoles"}`, and requireLaunchRole is true.
Only Challenge/Confirm (NI) and Renew (IW) may use that profile, with the
fixed R1/no-approval/no-egress/no-PAT fields. This expresses the verified
listener direction instead of admitting a wildcard parent/child actor list.

Run the narrow checks with:

```powershell
python eng/check_operation_scope.py --report artifacts/evidence/operation-reachability.json
python -m unittest discover -s tests/tooling -p test_operation_scope.py -v
```
