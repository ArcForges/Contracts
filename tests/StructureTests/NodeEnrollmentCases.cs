// SPDX-License-Identifier: Apache-2.0
using Google.Protobuf;
using ArcForges.Contracts.Fleet.V1;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.Node.V1;
using FleetShapes = ArcForges.Contracts.Fleet.Shapes.ContractShapeValidation;
using NodeShapes = ArcForges.Contracts.Node.Shapes.ContractShapeValidation;

// AF-CTR-04 part C0: presence vectors of the five new required request fields through the generated validators,
// binary round trips of every added field and the SignOutNode method of NodeEnrollmentService. The expected values
// are the C0 decisions (field numbers, presence), not values read from the generated code.
internal static class NodeEnrollmentCases
{
    private static readonly Id NodeId = new() { Value = ByteString.CopyFrom(Convert.FromHexString("0192f7a0c3e47b1a8d2e5f6a7b8c9d0e")) };
    private static readonly ByteString Key = ByteString.CopyFrom(new byte[91]);
    private static readonly ByteString Proof = ByteString.CopyFrom(new byte[64]);

    public static void Run()
    {
        var node = new EnrollingNodeInfo { NodeId = NodeId, Name = "build-01", Os = OsFamily.Linux, Arch = CpuArchitecture.X64, Version = "0.1.0-dev" };

        var begin = new NodeEnrollmentServiceBeginNodeSignInRequest
        {
            CodeChallenge = new string('A', 43), RedirectUri = "http://127.0.0.1:49152/callback", Node = node,
            State = new string('s', 32), NodePublicKey = Key,
        };
        Require(FleetShapes.IsValid(begin), "Begin with state and node_public_key is valid");
        Require(!FleetShapes.IsValid(Without(begin, b => b.ClearState())), "Begin without state is refused");
        Require(!FleetShapes.IsValid(Without(begin, b => b.ClearNodePublicKey())), "Begin without node_public_key is refused");
        // Presence only: length, pattern and key shape stay specification text, enforced by the center and the node.
        Require(FleetShapes.IsValid(Without(begin, b => b.State = "")), "Begin with an empty, present state passes the presence check");

        var start = new NodeEnrollmentServiceStartDeviceAuthorizationRequest { Node = node, NodePublicKey = Key };
        Require(FleetShapes.IsValid(start), "Start with node_public_key is valid");
        Require(!FleetShapes.IsValid(Without(start, s => s.ClearNodePublicKey())), "Start without node_public_key is refused");

        var complete = new NodeEnrollmentServiceCompleteNodeSignInRequest
        {
            FlowId = NodeId, Code = new string('c', 43), CodeVerifier = new string('v', 64), NodeKeyProof = Proof,
        };
        Require(FleetShapes.IsValid(complete), "Complete with node_key_proof is valid");
        Require(!FleetShapes.IsValid(Without(complete, c => c.ClearNodeKeyProof())), "Complete without node_key_proof is refused");

        var poll = new NodeEnrollmentServicePollDeviceAuthorizationRequest { DeviceCode = new string('d', 43), NodeKeyProof = Proof };
        Require(FleetShapes.IsValid(poll), "Poll with node_key_proof is valid");
        Require(!FleetShapes.IsValid(Without(poll, p => p.ClearNodeKeyProof())), "Poll without node_key_proof is refused");

        // Every added field survives the binary codec, at its decided number.
        var expires = new Instant { UnixSeconds = 1_830_000_000 };
        var publicKey = new PublicKey { Kid = "cmd-2026-11", Algorithm = "ES256", Key = Key, NotBefore = expires, NotAfter = expires };
        var refreshed = new NodeEnrollmentServiceRefreshNodeSessionValue
        {
            RefreshToken = "afr1.x", AccessToken = "afa1.x", AccessExpiresAt = expires, CommandKeys = { publicKey },
            EntitlementKeys = { publicKey }, SessionExpiresAt = expires, AccessLifetimeMs = 3_600_000,
        };
        RoundTrip(refreshed, ("command_keys", 13), ("entitlement_keys", 14), ("session_expires_at", 15), ("access_lifetime_ms", 16));
        RoundTrip(new NodeCredentials { SessionExpiresAt = expires, AccessLifetimeMs = 900_000 },
            ("session_expires_at", 10), ("access_lifetime_ms", 11));
        RoundTrip(new FleetNode { NodeId = NodeId, CredentialExpiresAt = expires }, ("credential_expires_at", 14));
        RoundTrip(begin, ("state", 13), ("node_public_key", 14));
        RoundTrip(start, ("node_public_key", 11));
        RoundTrip(complete, ("node_key_proof", 14));
        RoundTrip(poll, ("node_key_proof", 12));
        RoundTrip(new NodeSettings { CenterUrl = "https://arcforges.com/api" }, ("center_url", 6));
        RoundTrip(new NodeServiceUpdateNodeSettingsRequest { CenterUrl = "http://127.0.0.1:8080" }, ("center_url", 12));
        RoundTrip(new AccountStatus { CenterUrl = "https://arcforges.com/api", NodeKeyFingerprint = "AAAA-BBBB-CCCC-DDDD-EEEE", CredentialExpiresAt = expires },
            ("center_url", 14), ("node_key_fingerprint", 15), ("credential_expires_at", 16));
        RoundTrip(new SignInFlow { NodeKeyFingerprint = "AAAA-BBBB-CCCC-DDDD-EEEE" }, ("node_key_fingerprint", 13));
        Require(NodeShapes.IsValid(new NodeServiceUpdateNodeSettingsRequest { CenterUrl = "" }), "center_url is optional on UpdateNodeSettings");

        // SignOutNode: the 23rd method of NodeEnrollmentService, after ReportNodeInfo, a unary node-credential command.
        var service = FleetReflection.Descriptor.Services.Single(s => s.Name == "NodeEnrollmentService");
        Require(service.Methods.Count == 23, "NodeEnrollmentService has 23 methods");
        var names = service.Methods.Select(m => m.Name).ToList();
        Require(names.IndexOf("SignOutNode") == names.IndexOf("ReportNodeInfo") + 1, "SignOutNode follows ReportNodeInfo");
        var signOut = service.FindMethodByName("SignOutNode");
        Require(signOut.InputType.FullName == "arcforges.fleet.v1.NodeEnrollmentServiceSignOutNodeRequest"
            && signOut.OutputType.FullName == "arcforges.fleet.v1.NodeEnrollmentServiceSignOutNodeResponse"
            && !signOut.IsClientStreaming && !signOut.IsServerStreaming, "SignOutNode is unary with its own messages");
        Require(signOut.InputType.Fields.InFieldNumberOrder().Select(f => f.FieldNumber).SequenceEqual(new[] { 1 }), "SignOutNode request has only meta");
        Require(NodeEnrollmentServiceSignOutNodeValue.Descriptor.FindFieldByName("receipt").FieldNumber == 10, "SignOutNode value carries the receipt at 10");
        var reply = new NodeEnrollmentServiceSignOutNodeResponse { Value = new NodeEnrollmentServiceSignOutNodeValue { Receipt = new Receipt { CommandId = NodeId } } };
        Require(NodeEnrollmentServiceSignOutNodeResponse.Parser.ParseFrom(reply.ToByteArray()).Equals(reply), "SignOutNode reply round-trips");
        Require(FleetShapes.IsValid(new NodeEnrollmentServiceSignOutNodeRequest()), "SignOutNode request has no required field");
        Require(EnrollingNodeInfo.Descriptor.FindFieldByNumber(8) is null, "EnrollingNodeInfo has no key_fingerprint");
        Require(NodeEnrollmentServiceRefreshNodeSessionRequest.Descriptor.FindFieldByNumber(11) is null, "RefreshNodeSession carries no key proof");
        Console.WriteLine("Validated the AF-CTR-04 C0 presence vectors, round trips and SignOutNode.");
    }

    private static T Without<T>(T value, Action<T> change) where T : IMessage<T>
    {
        var copy = value.Clone();
        change(copy);
        return copy;
    }

    private static void RoundTrip<T>(T value, params (string Name, int Number)[] fields) where T : IMessage<T>, new()
    {
        // The value sets every listed field, so equality after the binary round trip shows that each one survives.
        var parsed = new MessageParser<T>(() => new T()).ParseFrom(value.ToByteArray());
        Require(parsed.Equals(value), typeof(T).Name + " round-trips");
        foreach (var (name, number) in fields)
        {
            var field = value.Descriptor.FindFieldByName(name);
            Require(field is not null && field.FieldNumber == number, $"{typeof(T).Name}.{name} = {number}");
        }
    }

    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("AF-CTR-04 C0 case failed: " + name);
    }
}
