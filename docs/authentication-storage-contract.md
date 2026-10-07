# Authentication storage contracts

CON.31 adds storage-only `arcforges.identity.storage.v1` messages to the existing
CloudInternal and operator-client owners. It adds no public authentication service,
Kotlin private package or authority flag. The authored protobuf and constraint shard
own the fields; normal generation emits the concrete C# and TypeScript codecs and
validators. The independently configured `operator.provider-policy.v1` JSON body
uses the existing strict JSON generators. Parsing its body does not verify its
signature, configured trust key or provider policy.

All scalar fields preserve explicit protobuf presence. Recovery generation zero
is valid when present; missing is refused. Revisions are positive. The original
flow and StepUp proof snapshot are bounded to 131072 encoded bytes; Operator and
customer provider evidence are bounded to 65536 bytes. Unknown protobuf fields
remain available for compatible reads and count toward encoded limits. Callers
must bound input bytes before parsing through the actual contract codec.

The original credential inventory contains sorted, distinct credential IDs and
their captured revision, provider and digest facts. Passkey inventories support
1-64 entries; other methods require one. Anonymous discovery and new enrollment
have no fabricated identity. Existing enrollment may retain a different original
actor method; its replacement method and registration arm must agree. Recovery
requires a known User, an empty replacement inventory and a genuine, separate
RecoveryMethod authorization reference. Its shape does not verify that reference.

NativeAuthorization binds the actual original PKCE/code row. NativeAuthentication
is a direct flow with no invented code row. Browser origin, preauthentication and
CSRF bindings are jointly present. Installation key/proof fields are jointly
present and the key digest binds the captured bytes. Public native possession
transcripts belong to CON.34; these storage messages do not sign or verify them.

Completion captures the actual verified credential and current owner revisions
without replacing original flow facts. StepUp snapshots retain the original
inventory and actual passkey challenge digest. Operator evidence captures exact
configured issuer/client/tenant, signed authentication time, immutable policy
observations and the original session/evidence association for step-up. It has
no `MfaAt` field. Customer evidence preserves absence of authentication time when
the actual provider did not attest it. Neither a signed assertion digest nor a
parsed policy creates identity or authorization.

CLOUD.12/13/15/19 must verify current signatures, configured origins and providers,
protected one-use custody, original subject/key/handle bytes, full original
inventory currentness, current realm/User/session/credential revisions and actual
method effects. Final registered family guards compare actual original protobuf
BLOB bytes and execute atomically with owner records. A generated shape or a
newly read inventory cannot replace those proofs. No token, authorization code,
password, recipient, private key or protected custody envelope is stored here.

Cross-field credential, Id and revision relationships compare their known facts
in both SDKs. Future nested protobuf unknown fields remain preserved; they do
not alter a known revision or identity. The owner's separate final original
protobuf BLOB guard still binds all original bytes, including those unknown fields.

Component evidence uses independent numbered binary fixtures and the actual
generated C#/TypeScript parsers and serializers. It covers presence, phases,
method arms, recovery, inventory membership/order, unknown-field retention,
encoded limits and strict policy JSON with full nanosecond precision. It is not
evidence of provider deployment, login, account activation or whole-system acceptance.
