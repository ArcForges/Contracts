// SPDX-License-Identifier: Apache-2.0
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.PublicApi;
using ArcForges.Contracts.PublicApi.V1;
using ArcForges.Contracts.PublicApi.Http.V1.NativeAuth;
using ArcForges.Contracts.Validation;
using Google.Protobuf;

internal static class InstallationPossessionContractTests
{
    internal static void Run(string root)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-34-installation-possession.json")));
        var fixture = document.RootElement;
        var command = FromHexId(Text(fixture.GetProperty("ids"), "command"));
        var challenge = Hex(fixture, "challengeHex"); var binding = Hex(fixture, "bindingHex");
        foreach (var vector in fixture.GetProperty("initial").EnumerateArray())
        {
            Require(InstallationPossession.TryInitialSigningData((InstallationInitialOperation)vector.GetProperty("operation").GetInt32(), command,
                challenge, binding, out var data), "initial-positive");
            Equal(data, vector, "dataHex");
            Require(Convert.ToHexStringLower(SHA256.HashData(data!)) == Text(vector, "sha256"), "initial-hash");
        }
        var refresh = fixture.GetProperty("refresh"); var context = Hex(fixture, "contextHex"); var token = Text(refresh, "canonicalToken");
        Require(InstallationPossession.TryRefreshSigningData(command, context, token, out var refreshData), "refresh-positive");
        Equal(refreshData, refresh, "dataHex");
        foreach (var vector in fixture.GetProperty("flowBindings").EnumerateArray())
        {
            Require(Flow(vector, out var hash), "flow-positive"); Equal(hash, vector, "sha256");
        }
        var current = fixture.GetProperty("refreshContext");
        Require(Context(current, out var currentHash), "context-positive"); Equal(currentHash, current, "sha256");
        foreach (var operation in new[] { 0, 5, -1, int.MaxValue })
            Require(!InstallationPossession.TryInitialSigningData((InstallationInitialOperation)operation, command, challenge, binding, out var refused) && refused is null, "unknown-operation");
        foreach (var id in new Id?[] { null, new(), FromHexId(new string('0', 32)), FromHexId(new string('1', 30)), FromHexId(new string('1', 34)) })
            Require(!InstallationPossession.TryInitialSigningData(InstallationInitialOperation.NativeToken, id, challenge, binding, out var refused) && refused is null, "invalid-id");
        Require(!InstallationPossession.TryInitialSigningData(InstallationInitialOperation.NativeToken, command, challenge.AsSpan(1), binding, out var shortData) && shortData is null, "short-challenge");
        const string alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
        var alias = token[..^1] + alphabet[alphabet.IndexOf(token[^1], StringComparison.Ordinal) + 1];
        foreach (var invalid in new[] { string.Empty, token + "=", token + "\n", token[1..], "+" + token[1..], alias })
            Require(!InstallationPossession.TryRefreshSigningData(command, context, invalid, out var refused) && refused is null, "invalid-token");
        var native = fixture.GetProperty("flowBindings")[0];
        foreach (var revision in new[] { 0L, -1L }) Require(!Flow(native, out _, recoveryRevision: revision), "invalid-recovery-revision");
        Require(!Flow(native, out _, platform: "windows\n"), "invalid-platform");
        Require(!Flow(native, out _, redirectUri: "arcscope://\ud800"), "invalid-utf16");
        Require(!Flow(native, out _, expires: 253402300800000000L), "invalid-expiry");
        Require(!Flow(native, out _, keyVersion: 0), "invalid-key-version");
        Require(!Flow(native, out _, purpose: AuthPurpose.Unspecified), "invalid-purpose");
        var direct = fixture.GetProperty("flowBindings")[1];
        Require(!Flow(direct, out _, pkce: challenge), "direct-pkce-not-zero");
        Require(!Flow(direct, out _, state: binding), "direct-state-not-zero");
        Require(!Context(current, out _, revision: 0), "invalid-session-revision");
        Require(!Context(current, out _, product: "other"), "invalid-product");
        Require(!Context(current, out _, generation: -1), "invalid-generation");
        // Result bytes are owned, not an alias of any mutable request input.
        Require(InstallationPossession.TryInitialSigningData(InstallationInitialOperation.CompleteAuthentication, command, challenge, binding, out var captured), "capture-positive");
        command.Value = ByteString.Empty; challenge.AsSpan().Clear(); binding.AsSpan().Clear();
        Equal(captured, fixture.GetProperty("initial")[0], "dataHex");
        Adjuncts(root);
    }

    private static void Adjuncts(string root)
    {
        using var original = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-07-identity.json")));
        string Positive(string target) => original.RootElement.GetProperty("cases").EnumerateArray()
            .First(value => Text(value, "target") == target && value.GetProperty("valid").GetBoolean()).GetProperty("value").GetRawText();
        var publicKey = Convert.FromHexString("3059301306072a8648ce3d020106082a8648ce3d03010703420004" +
            "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296" +
            "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5");
        var claim = JsonParser.Default.Parse<InstallationClaim>(Positive("InstallationClaim"));
        Require(ContractShapeValidation.IsValid(claim), "unbound-browser-claim-shape");
        claim.PublicKey = ByteString.CopyFrom(publicKey); claim.KeyVersion = long.MaxValue;
        Require(ContractShapeValidation.IsValid(InstallationClaim.Parser.ParseFrom(claim.ToByteArray())), "bound-claim-wire");
        var badClaim = claim.Clone(); badClaim.ClearKeyVersion(); Require(!ContractShapeValidation.IsValid(badClaim), "missing-key-version");
        badClaim = claim.Clone(); badClaim.ClearPublicKey(); Require(!ContractShapeValidation.IsValid(badClaim), "missing-key");
        badClaim = claim.Clone(); badClaim.KeyVersion = (ulong)long.MaxValue + 1; Require(!ContractShapeValidation.IsValid(badClaim), "key-version-overflow");
        var offCurve = publicKey.ToArray(); offCurve[^1] ^= 1;
        badClaim = claim.Clone(); badClaim.PublicKey = ByteString.CopyFrom(offCurve); Require(!ContractShapeValidation.IsValid(badClaim), "off-curve-spki");
        badClaim = claim.Clone(); badClaim.PublicKey = ByteString.CopyFrom([.. publicKey, 0]); Require(!ContractShapeValidation.IsValid(badClaim), "noncanonical-spki");
        var challenge = JsonParser.Default.Parse<AuthChallenge>(Positive("AuthChallenge"));
        Require(ContractShapeValidation.IsValid(challenge), "unbound-challenge-shape");
        challenge.InstallationProofChallenge = ByteString.CopyFrom(new byte[32]);
        challenge.InstallationProofBinding = ByteString.CopyFrom(new byte[32]); challenge.InstallationKeyVersion = 1;
        Require(ContractShapeValidation.IsValid(AuthChallenge.Parser.ParseFrom(challenge.ToByteArray())), "bound-challenge-wire");
        var badChallenge = challenge.Clone(); badChallenge.ClearInstallationProofBinding(); Require(!ContractShapeValidation.IsValid(badChallenge), "missing-binding");
        badChallenge = challenge.Clone(); badChallenge.ClearInstallationProofChallenge(); Require(!ContractShapeValidation.IsValid(badChallenge), "missing-challenge");
        badChallenge = challenge.Clone(); badChallenge.ClearInstallationKeyVersion(); Require(!ContractShapeValidation.IsValid(badChallenge), "missing-challenge-version");
        var proof = new InstallationPossessionProof { KeyVersion = 1, Signature = ByteString.CopyFrom(new byte[64]) };
        Require(ContractShapeValidation.IsValid(InstallationPossessionProof.Parser.ParseFrom(proof.ToByteArray())), "p1363-wire-shape-only");
        var badProof = proof.Clone(); badProof.Signature = ByteString.CopyFrom(new byte[70]); Require(!ContractShapeValidation.IsValid(badProof), "der-is-not-p1363");
        badProof = proof.Clone(); badProof.ClearKeyVersion(); Require(!ContractShapeValidation.IsValid(badProof), "proof-version-absent");
        var session = JsonParser.Default.Parse<NativeSession>(Positive("NativeSession"));
        Require(!ContractShapeValidation.IsValid(session), "old-session-no-possession-context");
        session.RecoveryGeneration = 0; session.InstallationProofContext = ByteString.CopyFrom(new byte[32]); session.InstallationKeyVersion = 1;
        Require(ContractShapeValidation.IsValid(NativeSession.Parser.ParseFrom(session.ToByteArray())), "native-session-generation-zero-wire");
        var badSession = session.Clone(); badSession.InstallationProofContext = ByteString.CopyFrom(new byte[31]); Require(!ContractShapeValidation.IsValid(badSession), "context-short");
        badSession = session.Clone(); badSession.InstallationKeyVersion = 0; Require(!ContractShapeValidation.IsValid(badSession), "session-key-version-zero");
        static string Url(byte[] value) => Convert.ToBase64String(value).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        var authorize = new NativeAuthorizeRequest
        {
            ClientId = "arcscope.desktop",
            RedirectUri = "com.arcforges.arcscope:/auth/callback",
            ResponseType = "code",
            CodeChallenge = Url(new byte[32]),
            CodeChallengeMethod = "S256",
            State = "original-state",
            InstallationId = "11223344-5566-4788-99aa-bbccddeeff00",
            PublicKey = Url(publicKey),
            KeyVersion = "9223372036854775807"
        };
        var authorizeWire = NativeAuthorizeRequestForm.Serialize(authorize);
        Require(NativeAuthorizeRequestForm.Parse(authorizeWire) == authorize, "authorize-form-roundtrip");
        Require(!NativeAuthorizeRequestForm.TryParse(System.Text.Encoding.UTF8.GetBytes(System.Text.Encoding.UTF8.GetString(authorizeWire) + "&keyVersion=1"), out _, out _), "duplicate-form-version");
        foreach (var version in new[] { "0", "01", "9223372036854775808" })
            Require(!NativeAuthorizeRequestForm.TryParse(System.Text.Encoding.UTF8.GetBytes(System.Text.Encoding.UTF8.GetString(authorizeWire).Replace("keyVersion=9223372036854775807", "keyVersion=" + version, StringComparison.Ordinal)), out _, out _), "form-version-bound");
        var callback = new NativeAuthorizeCallbackSuccess { Code = new string('x', 43), State = authorize.State, InstallationProofChallenge = Url(new byte[32]), InstallationProofBinding = Url(new byte[32]), InstallationKeyVersion = "1" };
        var callbackWire = NativeAuthorizeCallbackSuccessForm.Serialize(callback);
        Require(NativeAuthorizeCallbackSuccessForm.Parse(callbackWire) == callback, "callback-form-roundtrip");
        Require(!NativeAuthorizeCallbackSuccessForm.TryParse(System.Text.Encoding.UTF8.GetBytes(System.Text.Encoding.UTF8.GetString(callbackWire) + "&unknown=1"), out _, out _), "callback-unknown");
        var token = new NativeTokenRequest
        {
            GrantType = "authorization_code",
            Code = callback.Code,
            CodeVerifier = new string('v', 43),
            ClientId = authorize.ClientId,
            RedirectUri = authorize.RedirectUri,
            InstallationId = authorize.InstallationId,
            CommandId = "21223344-5566-4788-99aa-bbccddeeff00",
            InstallationKeyVersion = "1",
            InstallationProofSignature = Url(new byte[64])
        };
        var tokenWire = NativeTokenRequestForm.Serialize(token);
        Require(NativeTokenRequestForm.Parse(tokenWire) == token, "token-form-roundtrip");
        Require(!NativeTokenRequestForm.TryParse(System.Text.Encoding.UTF8.GetBytes(System.Text.Encoding.UTF8.GetString(tokenWire) + "&installationProofSignature=x"), out _, out _), "token-proof-duplicate");
        Require(!NativeTokenRequestForm.TryParse(System.Text.Encoding.UTF8.GetBytes(System.Text.Encoding.UTF8.GetString(tokenWire).Replace(token.InstallationProofSignature, Url(new byte[70]), StringComparison.Ordinal)), out _, out _), "token-der-refused");
    }

    private static bool Flow(JsonElement value, out byte[]? hash, string? platform = null, string? redirectUri = null,
        long? recoveryRevision = null, long? keyVersion = null, AuthPurpose? purpose = null, byte[]? pkce = null, byte[]? state = null, long? expires = null)
        => InstallationPossession.TryFlowBindingHash(FromHexId(Text(value, "realmId")), FromHexId(Text(value, "flowId")), FromHexId(Text(value, "installationId")),
            Text(value, "productId"), platform ?? Text(value, "platform"), Hex(value, "publicKeySha256Hex"), keyVersion ?? Number(value, "keyVersion"),
            purpose ?? (AuthPurpose)value.GetProperty("purpose").GetInt32(), Number(value, "authEpoch"), Number(value, "recoveryGeneration"),
            recoveryRevision ?? Number(value, "recoveryRevision"), Text(value, "clientId"), redirectUri ?? Text(value, "redirectUri"),
            pkce ?? Hex(value, "pkceChallengeHex"), state ?? Hex(value, "stateSha256Hex"), expires ?? Number(value, "expiresAtMicros"), out hash);
    private static bool Context(JsonElement value, out byte[]? hash, long? revision = null, string? product = null, long? generation = null)
        => InstallationPossession.TryRefreshContextHash(FromHexId(Text(value, "realmId")), FromHexId(Text(value, "userId")), FromHexId(Text(value, "deviceId")),
            FromHexId(Text(value, "installationId")), FromHexId(Text(value, "sessionId")), FromHexId(Text(value, "familyId")), product ?? Text(value, "productId"),
            Hex(value, "publicKeySha256Hex"), Number(value, "keyVersion"), (AuthPurpose)value.GetProperty("purpose").GetInt32(), Number(value, "authEpoch"),
            generation ?? Number(value, "recoveryGeneration"), revision ?? Number(value, "sessionRevision"), Number(value, "familyExpiresAtMicros"), out hash);
    private static string Text(JsonElement value, string key) => value.GetProperty(key).GetString()!;
    private static byte[] Hex(JsonElement value, string key) => Convert.FromHexString(Text(value, key));
    private static long Number(JsonElement value, string key) => long.Parse(Text(value, key), CultureInfo.InvariantCulture);
    private static Id FromHexId(string value) => new() { Value = ByteString.CopyFrom(Convert.FromHexString(value)) };
    private static void Equal(byte[]? actual, JsonElement value, string key) => Require(actual is not null && Convert.ToHexStringLower(actual) == Text(value, key), key);
    private static void Require(bool value, string key) { if (!value) throw new InvalidOperationException("CON34 canonical helper case failed: " + key); }
}
