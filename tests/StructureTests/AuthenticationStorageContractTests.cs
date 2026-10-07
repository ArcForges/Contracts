// SPDX-License-Identifier: Apache-2.0
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Google.Protobuf;
using S = ArcForges.Contracts.CloudInternal.Identity.Storage.V1;
using V = ArcForges.Contracts.CloudInternal.Shapes.ContractShapeValidation;
using Policy = ArcForges.Contracts.CloudInternal.Identity.Http.V1.OperatorProviderPolicyJson;

internal static class AuthenticationStorageContractTests
{
    public static void Run(string root)
    {
        using var fixture = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/internal/con-31-authentication-storage.json")));
        var vectors = fixture.RootElement.GetProperty("vectors").EnumerateArray().ToArray();
        Require(vectors.Length == 44, "closed independent vector inventory");
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var vector in vectors)
        {
            var name = vector.GetProperty("id").GetString()!;
            Require(seen.Add(name), "vector consumed once: " + name);
            var bytes = Convert.FromHexString(vector.GetProperty("wireHex").GetString()!);
            var parsed = Parse(vector.GetProperty("message").GetString()!, bytes);
            Require(Valid(parsed) == vector.GetProperty("valid").GetBoolean(), name);
            Require(parsed.ToByteArray().AsSpan().SequenceEqual(bytes), "real wire roundtrip: " + name);
        }
        var original = Convert.FromHexString(vectors.Single(v => v.GetProperty("id").GetString() == "actual-step-up-original-passkey").GetProperty("wireHex").GetString()!);
        var snapshot = S.StepUpMethodProofSnapshot.Parser.ParseFrom(original);
        var credential = snapshot.Credentials[0];
        snapshot.Credentials.Clear();
        for (var i = 0; i < 64; i++)
        {
            var row = credential.Clone();
            var identity = new byte[16]; identity[0] = (byte)(i + 1);
            var subject = new byte[32]; subject[0] = (byte)(i + 1);
            row.IdentityId.Value = ByteString.CopyFrom(identity); row.SubjectSha256 = ByteString.CopyFrom(subject);
            snapshot.Credentials.Add(row);
        }
        Require(V.IsValid(snapshot) && V.IsValid(S.StepUpMethodProofSnapshot.Parser.ParseFrom(snapshot.ToByteArray())), "all64 original passkeys survive actual storage roundtrip");
        var overflow = snapshot.Clone(); overflow.Credentials.Add(credential.Clone()); Require(!V.IsValid(overflow), "65 credentials refuse");
        var unsorted = snapshot.Clone(); (unsorted.Credentials[0], unsorted.Credentials[1]) = (unsorted.Credentials[1], unsorted.Credentials[0]); Require(!V.IsValid(unsorted), "original inventory must remain sorted");
        var duplicateSubject = snapshot.Clone(); duplicateSubject.Credentials[1].SubjectSha256 = duplicateSubject.Credentials[0].SubjectSha256; Require(!V.IsValid(duplicateSubject), "duplicate provider subject refuses");
        var flowBytes = Convert.FromHexString(vectors[0].GetProperty("wireHex").GetString()!);
        var future = flowBytes.Concat(Convert.FromHexString("ca3e03aabbcc")).ToArray();
        var flow = S.AuthenticationFlowPayload.Parser.ParseFrom(future);
        Require(V.IsValid(flow) && flow.ToByteArray().AsSpan().SequenceEqual(future), "future unknown field is retained");
        using (var stream = new MemoryStream())
        {
            stream.Write(flowBytes);
            using (var output = new CodedOutputStream(stream, true)) { output.WriteTag(1001, WireFormat.WireType.LengthDelimited); output.WriteBytes(ByteString.CopyFrom(new byte[131073])); }
            Require(!V.IsValid(S.AuthenticationFlowPayload.Parser.ParseFrom(stream.ToArray())), "unknown data counts toward131072 encoded custody bound");
        }
        var policyBytes = File.ReadAllBytes(Path.Combine(root, "fixtures/internal/operator-provider-policy.json"));
        Require(Policy.TryParse(policyBytes, out var policy, out _), "independent signed-profile body shape");
        Require(policy!.NotAfter == "2026-10-07T00:00:00.123456790Z", "full original nanoseconds preserved");
        var node = JsonNode.Parse(policyBytes)!.AsObject();
        var equal = node.DeepClone().AsObject(); equal["notAfter"] = node["capturedAt"]!.DeepClone(); Refuse(equal, "equal timestamp");
        var date = node.DeepClone().AsObject(); date["capturedAt"] = "2026-02-30T00:00:00Z"; Refuse(date, "invalid calendar date");
        var zero = node.DeepClone().AsObject(); zero["realmId"] = "00000000-0000-0000-0000-000000000000"; Refuse(zero, "zero configured realm");
        var duplicate = node.DeepClone().AsObject(); var ids = duplicate["policyIds"]!.AsArray(); ids.Add(ids[0]!.DeepClone()); Refuse(duplicate, "duplicate policy");
        var arbitrary = node.DeepClone().AsObject(); arbitrary["verified"] = true; Refuse(arbitrary, "no verified authority flag");
        var duplicateText = node.ToJsonString().Replace("\"version\":\"v1\"", "\"version\":\"v1\",\"version\":\"v1\"", StringComparison.Ordinal);
        Require(!Policy.TryParse(Encoding.UTF8.GetBytes(duplicateText), out _, out _), "duplicate input field refusal");
        Console.WriteLine("CON.31:44 binary vectors plus actual64 inventory, presence, encoded-bound, unknown-retention and trust-profile cases passed.");
    }
    private static void Refuse(JsonObject node, string label) => Require(!Policy.TryParse(Encoding.UTF8.GetBytes(node.ToJsonString()), out _, out _), label);
    private static IMessage Parse(string type, byte[] bytes) => type switch
    {
        "AuthenticationFlowPayload" => S.AuthenticationFlowPayload.Parser.ParseFrom(bytes),
        "StepUpMethodProofSnapshot" => S.StepUpMethodProofSnapshot.Parser.ParseFrom(bytes),
        "OperatorAuthenticationEvidence" => S.OperatorAuthenticationEvidence.Parser.ParseFrom(bytes),
        "CustomerProviderAuthenticationEvidence" => S.CustomerProviderAuthenticationEvidence.Parser.ParseFrom(bytes),
        "PasskeyFlowBinding" => S.PasskeyFlowBinding.Parser.ParseFrom(bytes),
        "AuthenticationCredentialReference" => S.AuthenticationCredentialReference.Parser.ParseFrom(bytes),
        "OperatorPolicyObservation" => S.OperatorPolicyObservation.Parser.ParseFrom(bytes),
        "OperatorPolicyProjection" => S.OperatorPolicyProjection.Parser.ParseFrom(bytes),
        _ => throw new InvalidOperationException("Unknown closed fixture type"),
    };
    private static bool Valid(IMessage message) => message switch
    {
        S.AuthenticationFlowPayload v => V.IsValid(v),
        S.StepUpMethodProofSnapshot v => V.IsValid(v),
        S.OperatorAuthenticationEvidence v => V.IsValid(v),
        S.CustomerProviderAuthenticationEvidence v => V.IsValid(v),
        S.PasskeyFlowBinding v => V.IsValid(v),
        S.AuthenticationCredentialReference v => V.IsValid(v),
        S.OperatorPolicyObservation v => V.IsValid(v),
        S.OperatorPolicyProjection v => V.IsValid(v),
        _ => false,
    };
    private static void Require(bool condition, string label) { if (!condition) throw new InvalidOperationException("CON.31 fixture failed: " + label); }
}
