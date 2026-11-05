// SPDX-License-Identifier: Apache-2.0
using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Google.Protobuf;
using ArcForges.Contracts.Fleet.V1;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.Node.V1;
using ArcForges.Contracts.Relay.V1;
using FleetShapes = ArcForges.Contracts.Fleet.Shapes.ContractShapeValidation;
using NodeShapes = ArcForges.Contracts.Node.Shapes.ContractShapeValidation;
using RelayShapes = ArcForges.Contracts.Relay.Shapes.ContractShapeValidation;

// AF-CTR-05 part C2: the node channel, the relay assertion and the routed fleet methods. The golden vectors of
// fixtures/internal/af-ctr-05-relay-vectors.json are decoded with the generated C# codecs, each signing input is rebuilt from
// the decoded fields (the domain string of its kind first) and each ES256 signature is verified; go/internal/compat checks the
// same bytes with the generated Go codecs. The validator vectors exercise every new field's presence, bounds and
// relationships through the generated validators. The expected values are the C2 decisions, not values read from generated code.
internal static class NodeChannelCases
{
    // Design 11 section 3, "Signature domain strings" (Plan decision PB-3): one per signature kind.
    private static readonly byte[] CallDomain = "ArcForges relay-call v1\n"u8.ToArray();
    private static readonly byte[] ResultDomain = "ArcForges relay-result v1\n"u8.ToArray();
    private static readonly byte[] HelloDomain = "ArcForges relay-hello v1\n"u8.ToArray();
    private static readonly byte[] OriginDomain = "ArcForges relay-origin v1\n"u8.ToArray();
    private static readonly byte[][] Domains = [CallDomain, ResultDomain, HelloDomain, OriginDomain];
    private static readonly System.Numerics.BigInteger Order =
        System.Numerics.BigInteger.Parse("0FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", System.Globalization.NumberStyles.HexNumber);

    public static void Run(string root)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/internal/af-ctr-05-relay-vectors.json")));
        var fixture = document.RootElement;
        DomainStrings(fixture);
        var assertions = RelayAssertions(fixture);
        RoutedCall(fixture, assertions[0]);
        RoutedResult(fixture);
        Hello(fixture);
        RelayNonces(fixture);
        RelayCloses(fixture);
        FieldNumbers();
        Validators(fixture);
        Console.WriteLine("Validated the AF-CTR-05 C2 golden vectors, signatures, field numbers and validator vectors.");
    }

    private static void DomainStrings(JsonElement fixture)
    {
        var domains = fixture.GetProperty("domains");
        Require(Encoding.ASCII.GetBytes(domains.GetProperty("call").GetString()!).SequenceEqual(CallDomain), "the routed-call domain string");
        Require(Encoding.ASCII.GetBytes(domains.GetProperty("result").GetString()!).SequenceEqual(ResultDomain), "the routed-result domain string");
        Require(Encoding.ASCII.GetBytes(domains.GetProperty("hello").GetString()!).SequenceEqual(HelloDomain), "the hello domain string");
        Require(Encoding.ASCII.GetBytes(domains.GetProperty("origin").GetString()!).SequenceEqual(OriginDomain), "the relay-origin domain string");
        Require(CallDomain.Length == 24 && ResultDomain.Length == 26 && HelloDomain.Length == 25 && OriginDomain.Length == 26, "domain string lengths");
        for (var i = 0; i < Domains.Length; i++)
            for (var j = 0; j < Domains.Length; j++)
                if (i != j) Require(!Domains[i].AsSpan().StartsWith(Domains[j]), "no domain string is a prefix of another");
        Require(!Domains.Any(d => d.AsSpan().StartsWith("ArcForges node-key-proof v1\n"u8)), "the node key proof keeps its own domain string");
    }

    private static List<RelayAssertion> RelayAssertions(JsonElement fixture)
    {
        var audience = Hex(fixture, "audienceSha256");
        Require(audience.SequenceEqual(SHA256.HashData(Encoding.UTF8.GetBytes(fixture.GetProperty("audience").GetString()!))), "the audience digest");
        var node = Key(fixture, "node");
        var ids = fixture.GetProperty("ids");
        var result = new List<RelayAssertion>();
        foreach (var vector in fixture.GetProperty("relayAssertions").EnumerateArray())
        {
            var id = vector.GetProperty("id").GetString()!;
            var bytes = Hex(vector, "assertion");
            var assertion = RelayAssertion.Parser.ParseFrom(bytes);
            Require(assertion.ToByteArray().SequenceEqual(bytes), id + ": the assertion re-encodes byte for byte");
            Require(RelayShapes.IsValid(assertion), id + ": the assertion is valid");
            Require(Id(assertion.RelayingNodeId) == ids.GetProperty("node").GetString() && Id(assertion.RelayingInstallationId) == ids.GetProperty("installation").GetString()
                && Id(assertion.LocalSessionId) == ids.GetProperty("localSession").GetString(), id + ": relaying node, installation and local session");
            Require((int)assertion.Method == vector.GetProperty("method").GetInt32() && (int)assertion.LocalOrigin == vector.GetProperty("localOrigin").GetInt32(), id + ": method and origin");
            Require(OptionalId(assertion.TargetNodeId) == OptionalText(vector, "targetNodeId") && OptionalId(assertion.CommandId) == OptionalText(vector, "commandId"), id + ": target and command");
            Require(assertion.RequestSha256.ToByteArray().SequenceEqual(Hex(vector, "requestSha256")) && assertion.RelayNonce.ToByteArray().SequenceEqual(Hex(vector, "relayNonce")), id + ": digest and nonce");
            Require(Same(assertion.IssuedAt, vector.GetProperty("issuedAt")) && Same(assertion.ExpiresAt, vector.GetProperty("expiresAt")), id + ": issue and expiry");
            var signing = OriginSigningInput(audience, assertion);
            Require(signing.Length == 228 && signing.SequenceEqual(Hex(vector, "signingInput")), id + ": the canonical relay-origin bytes");
            var signature = assertion.Signature.ToByteArray();
            Require(signature.SequenceEqual(Hex(vector, "signature")), id + ": the carried signature");
            Require(Verify(node, signing, signature), id + ": the relay assertion signature verifies");
            Require(!Verify(node, signing[OriginDomain.Length..], signature), id + ": a signature over the bare fields is refused");
            Require(!Verify(node, [.. CallDomain, .. signing[OriginDomain.Length..]], signature), id + ": the signature is not valid under another domain string");
            Require(!Verify(node, Hex(vector, "signingInput"), Hex(vector, "highSSignature")), id + ": a high-S signature is refused");
            Require(!Verify(Key(fixture, "otherInstallation"), signing, signature), id + ": another installation's key does not verify the assertion");
            if (vector.TryGetProperty("listNodesRequest", out var listed))
            {
                var request = FleetServiceListNodesRequest.Parser.ParseFrom(Convert.FromHexString(listed.GetString()!));
                Require(request.RelayAssertion.ToByteArray().SequenceEqual(bytes) && FleetShapes.IsValid(request), id + ": the ListNodes request carries it");
                var kept = WithoutField(Convert.FromHexString(listed.GetString()!), 11);
                Require(kept.SequenceEqual(Hex(vector, "listNodesRequestWithoutAssertion")), id + ": the request without its relay_assertion field");
                Require(SHA256.HashData(kept).SequenceEqual(assertion.RequestSha256.ToByteArray()), id + ": request_sha256 of a ListNodes request");
                Require(request.Caller.Kind == CallerKind.NodeRelay && request.Caller.LocalOrigin == assertion.LocalOrigin
                    && request.Caller.RelayingNodeId.Equals(assertion.RelayingNodeId), id + ": the caller equals the assertion's");
            }
            if (vector.TryGetProperty("getNodeRequest", out var got))
            {
                var full = Convert.FromHexString(got.GetString()!);
                var request = FleetServiceGetNodeRequest.Parser.ParseFrom(full);
                Require(request.RelayAssertion.ToByteArray().SequenceEqual(bytes) && FleetShapes.IsValid(request), id + ": the GetNode request carries it");
                var kept = WithoutField(full, 12);
                Require(kept.SequenceEqual(Hex(vector, "getNodeRequestWithoutAssertion")), id + ": the GetNode request without its relay_assertion field (12)");
                Require(SHA256.HashData(kept).SequenceEqual(assertion.RequestSha256.ToByteArray()), id + ": request_sha256 of a GetNode request");
                Require(request.NodeId.Equals(assertion.TargetNodeId) && request.Caller.LocalOrigin == assertion.LocalOrigin
                    && request.Caller.RelayingNodeId.Equals(assertion.RelayingNodeId), id + ": node_id and caller equal the assertion's");
            }
            result.Add(assertion);
        }
        Require(result.Count == 3 && result[1].TargetNodeId is null && result[1].CommandId is null, "the ListNodes assertion names no target and no command");
        Require(result[2].Method == RoutedMethod.GetNode && result[2].TargetNodeId is not null && result[2].CommandId is null, "the GetNode assertion names its target and no command");
        return result;
    }

    private static void RoutedCall(JsonElement fixture, RelayAssertion submit)
    {
        var vector = fixture.GetProperty("routedCall");
        var ids = fixture.GetProperty("ids");
        var bytes = Hex(vector, "frame");
        var frame = RelayFrame.Parser.ParseFrom(bytes);
        Require(frame.FrameCase == RelayFrame.FrameOneofCase.Call && frame.FrameVersion == 1 && frame.FrameSeq == 7, "the call frame is RelayFrame member 23");
        Require(frame.ToByteArray().SequenceEqual(bytes) && RelayShapes.IsValid(frame), "the call frame re-encodes and is valid");
        var call = frame.Call;
        var header = call.Header.Header.ToByteArray();
        Require(header.SequenceEqual(Hex(vector, "callHeader")), "the exact call header bytes");
        byte[] signing = [.. CallDomain, .. header];
        Require(signing.SequenceEqual(Hex(vector, "signingInput")), "the routed-call signing input is the domain string and the exact header");
        var center = Key(fixture, "center");
        var signature = call.Header.Signature.ToByteArray();
        Require(Verify(center, signing, signature), "the routed-call signature verifies");
        Require(!Verify(center, header, signature), "a call signature over the bare header is refused (Design 11 section 3)");
        foreach (var other in new[] { ResultDomain, HelloDomain, OriginDomain })
            Require(!Verify(center, [.. other, .. header], signature), "a call signature is not valid under another domain string");
        Require(!Verify(center, signing, Hex(vector, "highSSignature")), "a high-S call signature is refused");
        Require(!Verify(Key(fixture, "otherCenter"), signing, signature), "another center's command key does not verify the call");
        var flipped = (byte[])header.Clone();
        flipped[^1] ^= 1;
        Require(!Verify(center, [.. CallDomain, .. flipped], signature), "a flipped header byte is refused");
        Require(call.Header.Kid == vector.GetProperty("kid").GetString() && call.Header.Algorithm == "ES256", "kid and algorithm");
        var decoded = CallHeader.Parser.ParseFrom(header);
        Require(decoded.ToByteArray().SequenceEqual(header) && RelayShapes.IsValid(decoded), "the call header re-encodes and is valid");
        Require(Id(decoded.CallId) == ids.GetProperty("call").GetString() && decoded.CallId.Equals(call.CallId), "call_id");
        Require(decoded.Kid == call.Header.Kid, "the header kid equals the signed header's (PN-9)");
        Require(decoded.CenterUrlSha256.ToByteArray().SequenceEqual(Hex(fixture, "audienceSha256")), "center_url_sha256");
        Require(Id(decoded.AccountId) == ids.GetProperty("account").GetString() && Id(decoded.TargetNodeId) == ids.GetProperty("node").GetString(), "account and target");
        Require(decoded.Caller.Kind == CenterCallerKind.NodeRelay && decoded.Caller.LocalOrigin == Origin.Human
            && decoded.Caller.RelayingNodeId.Equals(submit.RelayingNodeId) && decoded.Caller.LocalSessionId.Equals(submit.LocalSessionId)
            && decoded.Caller.AccountId.Equals(decoded.AccountId), "the center caller is the verified assertion's");
        Require(decoded.CommandId.Equals(submit.CommandId) && decoded.Method == RoutedMethod.SubmitNodeTask, "command and method");
        var payload = call.Payload.ToByteArray();
        Require(decoded.RequestSha256.ToByteArray().SequenceEqual(SHA256.HashData(payload)) && decoded.RequestSha256.Equals(submit.RequestSha256), "request_sha256 is the payload's and the assertion's");
        Require(decoded.RequestSize == payload.Length && decoded.RequestSize == vector.GetProperty("requestSize").GetUInt32(), "request_size");
        Require(Same(decoded.IssuedAt, vector.GetProperty("issuedAt")) && Same(decoded.ExpiresAt, vector.GetProperty("expiresAt")) && Same(decoded.Deadline, vector.GetProperty("deadline")), "issued, expires, deadline");
        Require(decoded.RelayAssertionSha256.ToByteArray().SequenceEqual(SHA256.HashData(submit.ToByteArray())), "relay_assertion_sha256");
        var request = TaskServiceSubmitTaskRequest.Parser.ParseFrom(payload);
        Require(request.Meta.CommandId.Equals(decoded.CommandId) && request.Spec.WorkingDirectory == "/srv/build", "the payload is the node.v1 request");
    }

    private static void RoutedResult(JsonElement fixture)
    {
        var vector = fixture.GetProperty("routedResult");
        var ids = fixture.GetProperty("ids");
        var bytes = Hex(vector, "frame");
        var frame = RelayFrame.Parser.ParseFrom(bytes);
        Require(frame.FrameCase == RelayFrame.FrameOneofCase.CallResult && frame.ToByteArray().SequenceEqual(bytes) && RelayShapes.IsValid(frame), "the result frame is RelayFrame member 24");
        var result = frame.CallResult;
        var header = result.Header.Header.ToByteArray();
        byte[] signing = [.. ResultDomain, .. header];
        Require(signing.SequenceEqual(Hex(vector, "signingInput")), "the routed-result signing input");
        var node = Key(fixture, "node");
        var signature = result.Header.Signature.ToByteArray();
        Require(Verify(node, signing, signature), "the routed-result signature verifies");
        Require(!Verify(node, header, signature), "a result signature over the bare header is refused (PB-3)");
        Require(!Verify(node, [.. CallDomain, .. header], signature), "a result signature is not valid under the call domain");
        Require(!Verify(Key(fixture, "otherInstallation"), signing, signature), "another installation's key does not verify the result");
        Require(!Verify(node, signing, Hex(vector, "highSSignature")), "a high-S result signature is refused");
        Require(!result.Header.HasKid, "a result names no kid");
        var decoded = ResultHeader.Parser.ParseFrom(header);
        Require(decoded.ToByteArray().SequenceEqual(header) && RelayShapes.IsValid(decoded), "the result header re-encodes and is valid");
        Require(Id(decoded.CallId) == ids.GetProperty("call").GetString() && Id(decoded.CommandId) == ids.GetProperty("command").GetString()
            && Id(decoded.NodeId) == ids.GetProperty("node").GetString(), "call, command and node");
        Require(decoded.Outcome == RoutedOutcome.Executed && decoded.Method == RoutedMethod.SubmitNodeTask && decoded.Error is null, "an executed submit");
        var payload = result.Payload.ToByteArray();
        Require(decoded.ResponseSha256.ToByteArray().SequenceEqual(SHA256.HashData(payload)) && decoded.ResponseSize == payload.Length, "the response digest and size");
        Require(decoded.RequestSha256.ToByteArray().SequenceEqual(Hex(fixture.GetProperty("routedCall"), "payloadSha256")), "the echoed request digest");
        Require(Same(decoded.ExecutedAt, vector.GetProperty("executedAt")), "executed_at");
        var response = TaskServiceSubmitTaskResponse.Parser.ParseFrom(payload);
        Require(Id(response.Value.TaskId) == ids.GetProperty("task").GetString(), "the payload is the node.v1 response");
    }

    private static void Hello(JsonElement fixture)
    {
        var vector = fixture.GetProperty("hello");
        var ids = fixture.GetProperty("ids");
        var challengeFrame = RelayFrame.Parser.ParseFrom(Hex(vector, "challengeFrame"));
        Require(challengeFrame.FrameCase == RelayFrame.FrameOneofCase.Challenge && RelayShapes.IsValid(challengeFrame), "the challenge is RelayFrame member 27");
        var challenge = challengeFrame.Challenge;
        Require(challenge.Nonce.ToByteArray().SequenceEqual(Hex(vector, "nonce")) && Id(challenge.ConnectionId) == ids.GetProperty("connection").GetString()
            && Same(challenge.HelloDeadline, vector.GetProperty("helloDeadline")), "the challenge fields");
        var helloBytes = Hex(vector, "helloFrame");
        var helloFrame = RelayFrame.Parser.ParseFrom(helloBytes);
        Require(helloFrame.FrameCase == RelayFrame.FrameOneofCase.NodeHello && helloFrame.ToByteArray().SequenceEqual(helloBytes) && RelayShapes.IsValid(helloFrame), "the hello frame");
        var hello = helloFrame.NodeHello;
        Require(hello.Version == vector.GetProperty("version").GetString() && hello.ContractVersion == vector.GetProperty("contractVersion").GetString()
            && hello.Capabilities.SequenceEqual(vector.GetProperty("capabilities").EnumerateArray().Select(e => e.GetString())), "version, contract version and capabilities");
        Require(Id(hello.NodeId) == ids.GetProperty("node").GetString() && Id(hello.InstallationId) == ids.GetProperty("installation").GetString(), "node and installation");
        byte[] signing = [.. HelloDomain, .. challenge.Nonce.ToByteArray(), .. challenge.ConnectionId.Value.ToByteArray(), .. Hex(fixture, "audienceSha256"),
            .. hello.NodeId.Value.ToByteArray(), .. hello.InstallationId.Value.ToByteArray()];
        Require(signing.Length == 137 && signing.SequenceEqual(Hex(vector, "signingInput")), "the canonical hello bytes");
        var signature = hello.HelloSignature.ToByteArray();
        Require(signature.SequenceEqual(Hex(vector, "signature")) && Verify(Key(fixture, "node"), signing, signature), "the hello proof verifies");
        Require(!Verify(Key(fixture, "otherInstallation"), signing, signature), "the key of another installation proves nothing (D0-B2)");
        Require(!Verify(Key(fixture, "node"), signing[HelloDomain.Length..], signature), "a hello proof over the bare bytes is refused");
        Require(!Verify(Key(fixture, "node"), [.. ResultDomain, .. signing[HelloDomain.Length..]], signature), "a hello proof is not a result signature");
        var otherNonce = (byte[])signing.Clone();
        otherNonce[HelloDomain.Length] ^= 1;
        Require(!Verify(Key(fixture, "node"), otherNonce, signature), "a proof over another connection's nonce fails");
        Require(!Verify(Key(fixture, "node"), signing, Hex(vector, "highSSignature")), "a high-S hello proof is refused");
    }

    private static void RelayNonces(JsonElement fixture)
    {
        var vector = fixture.GetProperty("relayNonce");
        var request = RelayFrame.Parser.ParseFrom(Hex(vector, "requestFrame"));
        var nonce = RelayFrame.Parser.ParseFrom(Hex(vector, "frame"));
        Require(request.FrameCase == RelayFrame.FrameOneofCase.RelayNonceRequest && nonce.FrameCase == RelayFrame.FrameOneofCase.RelayNonce
            && RelayShapes.IsValid(request) && RelayShapes.IsValid(nonce), "the relay nonce frames are members 28 and 29");
        Require(nonce.RelayNonce.RequestId.Equals(request.RelayNonceRequest.RequestId) && nonce.RelayNonce.Nonce.ToByteArray().SequenceEqual(Hex(vector, "nonce")), "the nonce answers its request");
    }

    private static void RelayCloses(JsonElement fixture)
    {
        // A graceful shutdown (CTR5-HUB-11): close code 4500 with the reconnect hint, RelayFrame member 20.
        var vector = fixture.GetProperty("relayClose");
        var bytes = Hex(vector, "frame");
        var frame = RelayFrame.Parser.ParseFrom(bytes);
        Require(frame.FrameCase == RelayFrame.FrameOneofCase.Close && frame.ToByteArray().SequenceEqual(bytes) && RelayShapes.IsValid(frame), "the close frame");
        Require(frame.Close.Code == vector.GetProperty("code").GetUInt32() && frame.Close.Reason == vector.GetProperty("reason").GetString()
            && frame.Close.ReconnectAfterMs == vector.GetProperty("reconnectAfterMs").GetUInt32(), "code 4500, reason and reconnect_after_ms");
        Require(RelayShapes.IsValid(Change(frame.Close, c => c.ReconnectAfterMs = 300_000)) && RelayShapes.IsValid(Change(frame.Close, c => c.ReconnectAfterMs = 0))
            && !RelayShapes.IsValid(Change(frame.Close, c => c.ReconnectAfterMs = 300_001)) && RelayShapes.IsValid(Change(frame.Close, c => c.ClearReconnectAfterMs())),
            "reconnect_after_ms is optional, 0..300,000");
    }

    private static void FieldNumbers()
    {
        Number(RelayFrame.Descriptor, ("call", 23), ("call_result", 24), ("heartbeat", 25), ("accepted", 26), ("challenge", 27), ("relay_nonce_request", 28), ("relay_nonce", 29),
            ("command", 15), ("command_result", 16), ("node_hello", 10));
        Number(RelayClose.Descriptor, ("code", 1), ("reason", 2), ("reconnect_after_ms", 3));
        Number(NodeHello.Descriptor, ("contract_version", 5), ("capabilities", 6), ("installation_id", 7), ("hello_signature", 8));
        Number(CallHeader.Descriptor, ("call_id", 1), ("kid", 2), ("center_url_sha256", 3), ("account_id", 4), ("target_node_id", 5), ("caller", 6), ("command_id", 7),
            ("method", 8), ("request_sha256", 9), ("request_size", 10), ("issued_at", 11), ("expires_at", 12), ("deadline", 13), ("relay_assertion_sha256", 14));
        Number(ResultHeader.Descriptor, ("call_id", 1), ("command_id", 2), ("node_id", 3), ("method", 4), ("request_sha256", 5), ("response_sha256", 6), ("response_size", 7),
            ("executed_at", 8), ("outcome", 9), ("error", 10));
        Number(RelayAssertion.Descriptor, ("relaying_node_id", 1), ("relaying_installation_id", 2), ("local_origin", 3), ("local_session_id", 4), ("method", 5),
            ("request_sha256", 6), ("target_node_id", 7), ("command_id", 8), ("relay_nonce", 9), ("issued_at", 10), ("expires_at", 11), ("signature", 12));
        Number(SignedHeader.Descriptor, ("header", 1), ("signature", 2), ("kid", 3), ("algorithm", 4));
        Number(ChannelCall.Descriptor, ("call_id", 1), ("header", 2), ("payload", 3));
        Number(ChannelResult.Descriptor, ("call_id", 1), ("header", 2), ("payload", 3));
        Number(ChannelChallenge.Descriptor, ("nonce", 1), ("connection_id", 2), ("hello_deadline", 3));
        Number(ChannelAccepted.Descriptor, ("connection_id", 1), ("limits", 2), ("signing_kids", 3), ("node_name", 4));
        Number(ChannelLimits.Descriptor, ("max_frame_bytes", 1), ("max_in_flight_calls", 2), ("heartbeat_interval_ms", 3), ("heartbeat_deadline_ms", 4), ("max_relay_nonces", 5));
        Number(ChannelHeartbeat.Descriptor, ("sent_at", 1), ("seq", 2));
        Number(RelayNonceRequest.Descriptor, ("request_id", 1));
        Number(RelayNonce.Descriptor, ("request_id", 1), ("nonce", 2), ("expires_at", 3));
        Number(FleetServiceListNodesRequest.Descriptor, ("meta", 1), ("caller", 10), ("relay_assertion", 11));
        Number(FleetServiceGetNodeRequest.Descriptor, ("meta", 1), ("node_id", 10), ("caller", 11), ("relay_assertion", 12));
        Number(FleetNode.Descriptor, ("credential_expires_at", 14), ("reported_name", 15));
        Number(RoutedCaller.Descriptor, ("kind", 1), ("relaying_node_id", 2), ("local_origin", 3));
        foreach (var descriptor in RoutedRequests())
            Number(descriptor, ("meta", 1), ("node_id", 10), ("caller", 11), ("request", 12), ("relay_assertion", 13));
        Number(ActorRef.Descriptor, ("client_name", 8), ("center_caller", 9));
        Number(CenterCaller.Descriptor, ("kind", 1), ("account_id", 2), ("user_id", 3), ("session_id", 4), ("relaying_node_id", 5), ("local_origin", 6), ("local_session_id", 7));
        Number(ManagedTask.Descriptor, ("shared_keys", 26), ("local_diagnostic", 27));
        Number(TaskServiceReadTaskOutputRequest.Descriptor, ("max_bytes", 13), ("wait_ms", 14));
        Number(PolicyDocument.Descriptor, ("retry_safety", 17), ("center_routed", 18));
        Number(CenterRoutedPolicy.Descriptor, ("enabled", 1), ("relayed_from", 2));
        Require((int)RoutedMethod.SubmitNodeTask == 1 && (int)RoutedMethod.CancelNodeTask == 6 && (int)RoutedMethod.ListNodes == 7 && (int)RoutedMethod.GetNode == 8, "the routed method numbers");
        Require((int)RoutedOutcome.Executed == 1 && (int)RoutedOutcome.RefusedByPolicy == 2 && (int)RoutedOutcome.RefusedVerification == 3 && (int)RoutedOutcome.Expired == 4,
            "the outcome numbers are routed_call_log.decision 1..4");
        Require((int)RelayedFrom.OwnNode == 1 && (int)RelayedFrom.Account == 2 && new CenterRoutedPolicy().RelayedFrom == RelayedFrom.Unspecified,
            "relayed_from: OWN_NODE is 1, ACCOUNT the opt-in, absent reads as OWN_NODE");
        var service = FleetReflection.Descriptor.Services.Single(s => s.Name == "FleetService");
        var names = service.Methods.Select(m => m.Name).ToList();
        Require(names.Count == 19 && names.Skip(13).SequenceEqual(["SubmitNodeTask", "GetNodeTask", "ListNodeTasks", "WaitNodeTask", "ReadNodeTaskOutput", "CancelNodeTask"]),
            "the six routed methods follow the 13 earlier FleetService methods");
        foreach (var method in service.Methods.Skip(13))
            Require(!method.IsClientStreaming && !method.IsServerStreaming && method.InputType.Name == $"FleetService{method.Name}Request"
                && method.OutputType.Name == $"FleetService{method.Name}Response", method.Name + " is unary with its own messages");
    }

    private static void Validators(JsonElement fixture)
    {
        var call = CallHeader.Parser.ParseFrom(Hex(fixture.GetProperty("routedCall"), "callHeader"));
        Require(RelayShapes.IsValid(call), "the vector call header is valid");
        Invalid(call, c => c.ClearKid(), "call without kid");
        Invalid(call, c => c.Kid = "short", "call kid shorter than 8");
        Invalid(call, c => c.CenterUrlSha256 = ByteString.CopyFrom(new byte[31]), "center_url_sha256 of 31 bytes");
        Invalid(call, c => c.CallId = null, "call without call_id");
        Invalid(call, c => c.AccountId = null, "call without account");
        Invalid(call, c => c.TargetNodeId = null, "call without target");
        Invalid(call, c => c.Caller = null, "call without caller");
        Invalid(call, c => c.Method = RoutedMethod.ListNodes, "a call never names LIST_NODES");
        Invalid(call, c => c.ClearRequestSha256(), "call without request digest");
        Invalid(call, c => c.RequestSize = 0, "request_size 0");
        Invalid(call, c => c.RequestSize = 253_953, "request_size above 253,952");
        Valid(call, c => c.RequestSize = 253_952, "request_size 253,952");
        Invalid(call, c => c.CommandId = null, "a submit call without command_id");
        Invalid(call, c => c.Method = RoutedMethod.GetNodeTask, "a read call with command_id");
        Valid(call, c => { c.Method = RoutedMethod.GetNodeTask; c.CommandId = null; }, "a read call without command_id");
        Valid(call, c => c.ExpiresAt = At(c.IssuedAt, 300, 0), "expires_at = issued_at + 300 s");
        Invalid(call, c => c.ExpiresAt = At(c.IssuedAt, 300, 1), "expires_at one nanosecond past issued_at + 300 s");
        Invalid(call, c => c.ExpiresAt = At(c.IssuedAt, 0, 0), "expires_at = issued_at");
        Invalid(call, c => c.Deadline = At(c.ExpiresAt, 0, 1), "a deadline after expires_at");
        Invalid(call, c => c.Deadline = At(c.IssuedAt, 0, 0), "a deadline at issued_at");
        Invalid(call, c => c.ClearRelayAssertionSha256(), "a NODE_RELAY call without the assertion digest");
        Invalid(call, c => c.Caller.AccountId = c.TargetNodeId, "a caller of another account than the header's");
        var session = new CenterCaller { Kind = CenterCallerKind.AccountSession, AccountId = call.AccountId, UserId = call.CallId, SessionId = call.TargetNodeId };
        Require(NodeShapes.IsValid(session), "an account-session caller");
        Valid(call, c => { c.Caller = session; c.ClearRelayAssertionSha256(); }, "an account-session call without an assertion digest");
        Invalid(call, c => c.Caller = session, "an account-session call with an assertion digest");
        var relayed = call.Caller;
        Require(!NodeShapes.IsValid(Change(session, s => s.RelayingNodeId = relayed.RelayingNodeId)), "an account session naming a relaying node");
        Require(!NodeShapes.IsValid(Change(session, s => s.UserId = null)), "an account session without user");
        Require(!NodeShapes.IsValid(Change(relayed, s => s.LocalSessionId = null)), "a node relay without local session");
        Require(!NodeShapes.IsValid(Change(relayed, s => s.ClearLocalOrigin())), "a node relay without local origin");
        Require(!NodeShapes.IsValid(Change(relayed, s => s.LocalOrigin = Origin.Remote)), "a node relay with origin REMOTE");
        Require(!NodeShapes.IsValid(Change(relayed, s => s.SessionId = relayed.LocalSessionId)), "a node relay naming a center session");
        Require(!NodeShapes.IsValid(Change(relayed, s => s.Kind = CenterCallerKind.AgentGrant)), "AGENT_GRANT is reserved");
        Require(!NodeShapes.IsValid(Change(relayed, s => s.AccountId = null)), "a caller without account");
        Require(NodeShapes.IsValid(new ActorRef { Origin = Origin.Remote, CenterCaller = relayed }) && !NodeShapes.IsValid(new ActorRef { CenterCaller = new CenterCaller() }), "ActorRef.center_caller");

        var result = ResultHeader.Parser.ParseFrom(Hex(fixture.GetProperty("routedResult"), "resultHeader"));
        Require(RelayShapes.IsValid(result), "the vector result header is valid");
        var refusal = new ArcError
        {
            Code = "permission_denied", Category = ErrorCategory.Authorization, MessageKey = "error.authorization.permission_denied",
            Retry = new RetryAdvice { Mode = RetryMode.Never }, Effect = EffectCertainty.DidNotHappen, CorrelationId = call.CallId,
        };
        Invalid(result, r => r.ClearResponseSha256(), "an executed result without a response digest");
        Invalid(result, r => r.ClearResponseSize(), "an executed result without a response size");
        Invalid(result, r => r.Error = refusal, "an executed result with an error");
        Invalid(result, r => r.ResponseSize = 1_040_385, "a response above 1,040,384 bytes");
        Invalid(result, r => r.ClearOutcome(), "a result without outcome");
        Invalid(result, r => r.NodeId = null, "a result without node");
        Invalid(result, r => r.ExecutedAt = null, "a result without executed_at");
        Valid(result, r => { r.Outcome = RoutedOutcome.RefusedByPolicy; r.ClearResponseSha256(); r.ClearResponseSize(); r.Error = refusal; }, "a policy refusal");
        Invalid(result, r => { r.Outcome = RoutedOutcome.RefusedByPolicy; r.ClearResponseSha256(); r.ClearResponseSize(); }, "a policy refusal without its error");
        Valid(result, r => { r.Outcome = RoutedOutcome.RefusedVerification; r.ClearResponseSha256(); r.ClearResponseSize(); r.Error = refusal; r.ClearMethod(); r.ClearRequestSha256(); r.CommandId = null; },
            "a verification refusal echoes nothing it could not verify");
        Invalid(result, r => { r.Outcome = RoutedOutcome.RefusedVerification; r.ClearResponseSha256(); r.ClearResponseSize(); r.Error = refusal; }, "a verification refusal echoing the method");
        Invalid(result, r => { r.Outcome = RoutedOutcome.Expired; r.ClearResponseSha256(); r.ClearResponseSize(); r.Error = refusal; r.ClearMethod(); }, "an expired result without method");
        RoutedRefusals(result, refusal);

        var frame = RelayFrame.Parser.ParseFrom(Hex(fixture.GetProperty("routedCall"), "frame")).Call;
        Invalid(frame, c => c.Header.ClearKid(), "a call without kid");
        Invalid(frame, c => c.Payload = ByteString.Empty, "a call with an empty payload");
        Invalid(frame, c => c.Payload = ByteString.CopyFrom(new byte[253_953]), "a call payload above 253,952 bytes");
        Invalid(frame, c => c.Header.Signature = ByteString.CopyFrom(new byte[63]), "a signature of 63 bytes");
        Invalid(frame, c => c.Header.Algorithm = "ES384", "another algorithm");
        Invalid(frame, c => c.Header.Header = ByteString.CopyFrom(new byte[2049]), "a header above 2,048 bytes");
        Invalid(frame, c => c.Header.Header = ByteString.Empty, "an empty header");
        Invalid(frame, c => c.CallId = null, "a call frame without call_id");
        var answer = RelayFrame.Parser.ParseFrom(Hex(fixture.GetProperty("routedResult"), "frame")).CallResult;
        Invalid(answer, r => r.Header.Kid = "cmd-test-2026-11", "a result naming a kid");
        Invalid(answer, r => r.Payload = ByteString.CopyFrom(new byte[1_040_385]), "a result payload above 1,040,384 bytes");
        Valid(answer, r => r.Payload = ByteString.Empty, "an empty result payload (a refusal)");

        var challenge = RelayFrame.Parser.ParseFrom(Hex(fixture.GetProperty("hello"), "challengeFrame")).Challenge;
        Invalid(challenge, c => c.Nonce = ByteString.CopyFrom(new byte[16]), "a challenge nonce of 16 bytes");
        Invalid(challenge, c => c.ConnectionId = null, "a challenge without connection");
        Invalid(challenge, c => c.HelloDeadline = null, "a challenge without deadline");
        var hello = RelayFrame.Parser.ParseFrom(Hex(fixture.GetProperty("hello"), "helloFrame")).NodeHello;
        Invalid(hello, h => h.InstallationId = null, "a hello without installation");
        Invalid(hello, h => h.ClearHelloSignature(), "a hello without proof");
        Invalid(hello, h => h.HelloSignature = ByteString.CopyFrom(new byte[65]), "a hello proof of 65 bytes");
        Invalid(hello, h => h.Capabilities.Add("Routed.v2"), "a capability outside the pattern");
        Invalid(hello, h => h.Capabilities.Add("routed.v1"), "a repeated capability");
        Invalid(hello, h => h.Capabilities.AddRange(Enumerable.Range(0, 16).Select(i => $"cap{i}")), "17 capabilities");
        Invalid(hello, h => h.ContractVersion = new string('1', 65), "a contract version of 65 chars");
        Valid(hello, h => h.ClearContractVersion(), "a hello without contract version");

        var limits = new ChannelLimits { MaxFrameBytes = 1_048_576, MaxInFlightCalls = 8, HeartbeatIntervalMs = 25_000, HeartbeatDeadlineMs = 60_000, MaxRelayNonces = 8 };
        var accepted = new ChannelAccepted { ConnectionId = challenge.ConnectionId, Limits = limits, SigningKids = { "cmd-test-2026-11" }, NodeName = "build-01" };
        Require(RelayShapes.IsValid(accepted), "a channel acceptance with the default limits");
        Invalid(accepted, a => a.Limits.MaxFrameBytes = 1_048_577, "a frame bound above 1 MiB");
        Invalid(accepted, a => a.Limits.MaxFrameBytes = 65_535, "a frame bound below 64 KiB");
        Invalid(accepted, a => a.Limits.MaxFrameBytes = 1_048_575, "a frame bound below 1 MiB (the bound is pinned)");
        Invalid(accepted, a => a.Limits.MaxFrameBytes = 65_536, "a frame bound of 64 KiB (the bound is pinned)");
        Invalid(accepted, a => a.Limits.HeartbeatDeadlineMs = 25_000, "a heartbeat deadline not above the interval");
        Invalid(accepted, a => a.Limits.MaxInFlightCalls = 0, "no in-flight call");
        Invalid(accepted, a => a.Limits.MaxRelayNonces = 65, "65 relay nonces");
        Invalid(accepted, a => a.Limits.ClearHeartbeatIntervalMs(), "limits without heartbeat interval");
        Invalid(accepted, a => a.SigningKids.Clear(), "no signing kid");
        Invalid(accepted, a => a.SigningKids.Add("cmd-test-2026-11"), "a repeated signing kid");
        Invalid(accepted, a => a.SigningKids.AddRange(Enumerable.Range(0, 8).Select(i => $"cmd-test-{i:D4}")), "nine signing kids");
        Invalid(accepted, a => a.NodeName = new string('n', 65), "a node name of 65 chars");
        Invalid(accepted, a => a.Limits = null, "an acceptance without limits");
        Require(!RelayShapes.IsValid(new ChannelHeartbeat { SentAt = challenge.HelloDeadline }), "a heartbeat without seq");
        Require(RelayShapes.IsValid(new ChannelHeartbeat { SentAt = challenge.HelloDeadline, Seq = 1 }), "a heartbeat");
        var nonce = RelayFrame.Parser.ParseFrom(Hex(fixture.GetProperty("relayNonce"), "frame")).RelayNonce;
        Invalid(nonce, n => n.Nonce = ByteString.CopyFrom(new byte[31]), "a relay nonce of 31 bytes");
        Invalid(nonce, n => n.ExpiresAt = null, "a relay nonce without expiry");
        Require(!RelayShapes.IsValid(new RelayNonceRequest()), "a nonce request without request_id");

        var assertion = RelayAssertion.Parser.ParseFrom(Hex(fixture.GetProperty("relayAssertions")[0], "assertion"));
        Valid(assertion, a => a.ExpiresAt = At(a.IssuedAt, 120, 0), "an assertion expiring 120 s after issue");
        Invalid(assertion, a => a.ExpiresAt = At(a.IssuedAt, 120, 1), "an assertion expiring past 120 s");
        Invalid(assertion, a => a.ExpiresAt = At(a.IssuedAt, 0, 0), "an assertion expiring at issue");
        Invalid(assertion, a => a.Method = RoutedMethod.ListNodes, "a LIST_NODES assertion naming a target");
        Valid(assertion, a => { a.Method = RoutedMethod.ListNodes; a.TargetNodeId = null; a.CommandId = null; }, "a LIST_NODES assertion");
        Invalid(assertion, a => { a.Method = RoutedMethod.GetNode; a.TargetNodeId = null; a.CommandId = null; }, "a GET_NODE assertion without target");
        Invalid(assertion, a => a.Method = RoutedMethod.GetNodeTask, "a read assertion naming a command");
        Invalid(assertion, a => a.CommandId = null, "a submit assertion without command");
        Invalid(assertion, a => a.LocalOrigin = Origin.Remote, "an assertion with origin REMOTE");
        Invalid(assertion, a => a.ClearMethod(), "an assertion without method");
        Invalid(assertion, a => a.ClearRelayNonce(), "an assertion without nonce");
        Invalid(assertion, a => a.ClearSignature(), "an assertion without signature");
        Invalid(assertion, a => a.RelayingInstallationId = null, "an assertion without installation");
        Invalid(assertion, a => a.LocalSessionId = null, "an assertion without local session");

        // Every routed request, the reads ListNodes and GetNode included, carries caller and relay_assertion together (Plan
        // addendum C-N6): a node-relayed call without its assertion is invalid, an account session sends neither.
        var id = call.TargetNodeId;
        var caller = new RoutedCaller { Kind = CallerKind.NodeRelay, RelayingNodeId = id, LocalOrigin = Origin.Script };
        var meta = new RequestMeta { CorrelationId = call.CallId };
        var bytes = ByteString.CopyFrom(new byte[] { 1 });
        Relayed(new FleetServiceListNodesRequest { Meta = meta, Caller = caller, RelayAssertion = bytes }, r => r.Caller = null, r => r.ClearRelayAssertion(), "ListNodes");
        Relayed(new FleetServiceGetNodeRequest { Meta = meta, NodeId = id, Caller = caller, RelayAssertion = bytes }, r => r.Caller = null, r => r.ClearRelayAssertion(), "GetNode");
        Routed(new FleetServiceSubmitNodeTaskRequest { Meta = meta, NodeId = id, Caller = caller, Request = bytes, RelayAssertion = bytes }, 253_952, "SubmitNodeTask");
        Routed(new FleetServiceGetNodeTaskRequest { Meta = meta, NodeId = id, Caller = caller, Request = bytes, RelayAssertion = bytes }, 3_072, "GetNodeTask");
        Routed(new FleetServiceListNodeTasksRequest { Meta = meta, NodeId = id, Caller = caller, Request = bytes, RelayAssertion = bytes }, 3_072, "ListNodeTasks");
        Routed(new FleetServiceWaitNodeTaskRequest { Meta = meta, NodeId = id, Caller = caller, Request = bytes, RelayAssertion = bytes }, 3_072, "WaitNodeTask");
        Routed(new FleetServiceReadNodeTaskOutputRequest { Meta = meta, NodeId = id, Caller = caller, Request = bytes, RelayAssertion = bytes }, 3_072, "ReadNodeTaskOutput");
        Routed(new FleetServiceCancelNodeTaskRequest { Meta = meta, NodeId = id, Caller = caller, Request = bytes, RelayAssertion = bytes }, 3_072, "CancelNodeTask");
        Require(!FleetShapes.IsValid(new FleetServiceGetNodeRequest { Meta = meta, NodeId = id, Caller = Change(caller, c => c.Kind = CallerKind.AccountSession), RelayAssertion = bytes }), "a caller of kind ACCOUNT_SESSION");
        Require(!FleetShapes.IsValid(new FleetServiceGetNodeRequest { Meta = meta, NodeId = id, Caller = Change(caller, c => c.LocalOrigin = Origin.Remote), RelayAssertion = bytes }), "a caller of origin REMOTE");
        Require(!FleetShapes.IsValid(new FleetServiceGetNodeRequest { Meta = meta, NodeId = id, Caller = Change(caller, c => c.RelayingNodeId = null), RelayAssertion = bytes }), "a caller without relaying node");
        Require(!FleetShapes.IsValid(new FleetServiceGetNodeRequest { Meta = meta, NodeId = id, Caller = caller, RelayAssertion = ByteString.CopyFrom(new byte[513]) }), "an assertion above 512 bytes");
        var value = new FleetServiceSubmitNodeTaskValue { Response = bytes, NodeId = id };
        Require(FleetShapes.IsValid(value), "a routed value");
        Require(!FleetShapes.IsValid(Change(value, v => v.ClearResponse())) && !FleetShapes.IsValid(Change(value, v => v.NodeId = null))
            && !FleetShapes.IsValid(Change(value, v => v.Response = ByteString.CopyFrom(new byte[1_040_385])))
            && FleetShapes.IsValid(Change(value, v => v.Response = ByteString.CopyFrom(new byte[1_040_384]))), "the routed value bounds");
        Require(FleetShapes.IsValid(new FleetNode { NodeId = id, ReportedName = new string('n', 64) }) && !FleetShapes.IsValid(new FleetNode { NodeId = id, ReportedName = new string('n', 65) })
            && !FleetShapes.IsValid(new FleetNode { NodeId = id, ReportedName = "" }), "reported_name 1..64");
        Require(NodeShapes.IsValid(new TaskServiceReadTaskOutputRequest { AttemptId = id, WaitMs = 20_000 }) && !NodeShapes.IsValid(new TaskServiceReadTaskOutputRequest { AttemptId = id, WaitMs = 20_001 }),
            "wait_ms 0..20,000");
        Require(NodeShapes.IsValid(new CenterRoutedPolicy()) && NodeShapes.IsValid(new CenterRoutedPolicy { Enabled = false, RelayedFrom = RelayedFrom.Account })
            && !NodeShapes.IsValid(new CenterRoutedPolicy { RelayedFrom = (RelayedFrom)3 }), "the center-routed policy");
        Require(NodeShapes.IsValid(new PolicyDocument { CenterRouted = new CenterRoutedPolicy { RelayedFrom = RelayedFrom.OwnNode } }), "PolicyDocument.center_routed");
        Require(NodeShapes.IsValid(new ManagedTask { LocalDiagnostic = true }), "ManagedTask.local_diagnostic");
    }

    // ResultHeader.error holds closed fields only (rule routedRefusal; Plan PN-6; review A B-1): free text, other details, a
    // resource other than an approval of approval_required and a message key other than the catalogue's are refused.
    private static void RoutedRefusals(ResultHeader result, ArcError refusal)
    {
        var policy = Change(result, r => { r.Outcome = RoutedOutcome.RefusedByPolicy; r.ClearResponseSha256(); r.ClearResponseSize(); r.Error = refusal; });
        StateFailure State(string state, string reason) => new() { State = state, Reason = reason };
        void Refusal(Action<ArcError> change, bool valid, string name) =>
            Require(RelayShapes.IsValid(Change(policy, r => change(r.Error))) == valid, name + (valid ? " is valid" : " is refused"));
        Refusal(e => { }, true, "a refusal without details");
        Refusal(e => e.Details = new ErrorDetails { State = State("task.submit", "relay_own_node_only") }, true, "a refusal with a closed state");
        Refusal(e => e.Details = new ErrorDetails { State = State("task.submit", "/home/u/.ssh/id_ed25519: permission denied") }, false, "a path-like reason");
        Refusal(e => e.Details = new ErrorDetails { State = State("task.submit", "Relay_own_node_only") }, false, "a reason outside the closed pattern");
        Refusal(e => e.Details = new ErrorDetails { State = State("task submit", "relay_own_node_only") }, false, "a state outside the closed pattern");
        Refusal(e => e.Details = new ErrorDetails { State = State("task.submit", new string('a', 65)) }, false, "a reason of 65 characters");
        Refusal(e => e.Details = new ErrorDetails { Limit = new LimitFailure { LimitName = "routed_calls_per_account" } }, false, "details.limit");
        Refusal(e => e.Details = new ErrorDetails { Revision = new RevisionConflict() }, false, "details.revision");
        Refusal(e => e.Details = new ErrorDetails { Upgrade = new VersionFailure { MinReadable = "1.0.0", MinWritable = "1.0.0", Received = "0.9.0" } }, false, "details.upgrade");
        Refusal(e => { var s = State("task.submit", "relay_own_node_only"); s.Resource = new AggregateRef { Kind = "task", Id = refusal.CorrelationId }; e.Details = new ErrorDetails { State = s }; },
            false, "state.resource on a permission refusal");
        Refusal(e => { var s = State("task.submit", "relay_own_node_only"); s.Native = new NativeContentRev { Value = 1 }; e.Details = new ErrorDetails { State = s }; }, false, "state.native");
        Refusal(e => e.Code = "Permission denied", false, "a free-text code");
        Refusal(e => e.Code = "authorization.permission_denied", false, "a dotted code");
        Refusal(e => e.MessageKey = "error.authorization.something_else", false, "a message key that is not the code's");
        Refusal(e => e.MessageKey = "/srv/build", false, "a path as message key");
        var approval = new ArcError
        {
            Code = "approval_required", Category = ErrorCategory.Authorization, MessageKey = "error.authorization.approval_required",
            Retry = new RetryAdvice { Mode = RetryMode.Reconcile, ReconciliationOperation = "arcforges.node.v1.ApprovalService/GetApproval" },
            Effect = EffectCertainty.DidNotHappen, CorrelationId = refusal.CorrelationId,
            Details = new ErrorDetails { State = new StateFailure { State = "task.cancel_others", Reason = "approval_required", Resource = new AggregateRef { Kind = "approval", Id = refusal.CorrelationId } } },
        };
        Refusal(e => e.MergeFrom(approval), true, "approval_required with its approval resource and GetApproval");
        Refusal(e => { e.MergeFrom(approval); e.Details.State.Resource.Kind = "task"; }, false, "approval_required with another resource kind");
        Refusal(e => { e.MergeFrom(approval); e.Retry.ReconciliationOperation = "arcforges.node.v1.TaskService/GetTask"; }, false, "another reconciliation operation");
    }

    private static void Routed<T>(T request, int bound, string name) where T : class, IMessage<T>
    {
        var requestField = request.Descriptor.FindFieldByName("request");
        Relayed(request, r => r.Descriptor.FindFieldByName("caller").Accessor.Clear(r), r => r.Descriptor.FindFieldByName("relay_assertion").Accessor.Clear(r), name);
        Require(!IsValid(Change(request, r => requestField.Accessor.Clear(r))), name + ": request is required");
        Require(!IsValid(Change(request, r => requestField.Accessor.SetValue(r, ByteString.Empty))), name + ": an empty request");
        Require(IsValid(Change(request, r => requestField.Accessor.SetValue(r, ByteString.CopyFrom(new byte[bound])))), $"{name}: a request of {bound} bytes");
        Require(!IsValid(Change(request, r => requestField.Accessor.SetValue(r, ByteString.CopyFrom(new byte[bound + 1])))), $"{name}: a request of {bound + 1} bytes");
        Require(!IsValid(Change(request, r => r.Descriptor.FindFieldByName("node_id").Accessor.Clear(r))), name + ": node_id is required");
    }

    private static void Relayed<T>(T request, Action<T> clearCaller, Action<T> clearAssertion, string name) where T : class, IMessage<T>
    {
        Require(IsValid(request), name + ": a node-relayed caller with its assertion");
        Require(!IsValid(Change(request, clearAssertion)), name + ": a node-relayed caller without its relay assertion is refused");
        Require(!IsValid(Change(request, clearCaller)), name + ": a relay assertion without its caller is refused");
        Require(IsValid(Change(Change(request, clearCaller), clearAssertion)), name + ": an account session sends neither");
    }

    private static Google.Protobuf.Reflection.MessageDescriptor[] RoutedRequests() =>
    [
        FleetServiceSubmitNodeTaskRequest.Descriptor, FleetServiceGetNodeTaskRequest.Descriptor, FleetServiceListNodeTasksRequest.Descriptor,
        FleetServiceWaitNodeTaskRequest.Descriptor, FleetServiceReadNodeTaskOutputRequest.Descriptor, FleetServiceCancelNodeTaskRequest.Descriptor,
    ];

    private static void Number(Google.Protobuf.Reflection.MessageDescriptor descriptor, params (string Name, int Number)[] fields)
    {
        foreach (var (name, number) in fields)
        {
            var field = descriptor.FindFieldByName(name);
            Require(field is not null && field.FieldNumber == number, $"{descriptor.Name}.{name} = {number}");
        }
    }

    private static byte[] OriginSigningInput(byte[] audience, RelayAssertion value)
    {
        var output = new List<byte>(228);
        output.AddRange(OriginDomain);
        output.AddRange(audience);
        output.AddRange(value.RelayingNodeId.Value.ToByteArray());
        output.AddRange(value.RelayingInstallationId.Value.ToByteArray());
        output.Add((byte)value.LocalOrigin);
        output.AddRange(value.LocalSessionId.Value.ToByteArray());
        output.Add((byte)value.Method);
        output.AddRange(value.RequestSha256.ToByteArray());
        output.AddRange(value.TargetNodeId is null ? new byte[16] : value.TargetNodeId.Value.ToByteArray());
        output.AddRange(value.CommandId is null ? new byte[16] : value.CommandId.Value.ToByteArray());
        output.AddRange(value.RelayNonce.ToByteArray());
        output.AddRange(Canonical(value.IssuedAt));
        output.AddRange(Canonical(value.ExpiresAt));
        return [.. output];
    }

    private static byte[] Canonical(Instant value)
    {
        var bytes = new byte[12];
        BinaryPrimitives.WriteInt64BigEndian(bytes, value.UnixSeconds);
        BinaryPrimitives.WriteUInt32BigEndian(bytes.AsSpan(8), value.Nanos);
        return bytes;
    }

    // The top-level fields of a message as transmitted, in wire order and byte for byte, without every occurrence of one field.
    private static byte[] WithoutField(byte[] message, int number)
    {
        var output = new List<byte>(message.Length);
        var input = new CodedInputStream(message);
        while (!input.IsAtEnd)
        {
            var start = (int)input.Position;
            var tag = input.ReadTag();
            input.SkipLastField();
            if (Google.Protobuf.WireFormat.GetTagFieldNumber(tag) != number)
                output.AddRange(message.AsSpan(start, (int)input.Position - start).ToArray());
        }
        return [.. output];
    }

    private static bool Verify(ECDsa key, byte[] data, byte[] signature)
    {
        // ES256 in IEEE P1363 form, 64 bytes, low-S (Design 11 section 3): a high-S signature is refused before verification.
        if (signature.Length != 64) return false;
        var s = new System.Numerics.BigInteger(signature.AsSpan(32), isUnsigned: true, isBigEndian: true);
        if (s.IsZero || s > Order / 2) return false;
        return key.VerifyData(data, signature, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation);
    }

    private static ECDsa Key(JsonElement fixture, string name)
    {
        var key = ECDsa.Create();
        key.ImportSubjectPublicKeyInfo(Convert.FromHexString(fixture.GetProperty("keys").GetProperty(name).GetProperty("spki").GetString()!), out _);
        return key;
    }

    private static Instant At(Instant from, long seconds, uint nanos)
    {
        var total = (System.Int128)from.UnixSeconds * 1_000_000_000 + from.Nanos + (System.Int128)seconds * 1_000_000_000 + nanos;
        return new Instant { UnixSeconds = (long)(total / 1_000_000_000), Nanos = (uint)(total % 1_000_000_000) };
    }

    private static bool Same(Instant value, JsonElement expected) =>
        value.UnixSeconds == expected[0].GetInt64() && value.Nanos == expected[1].GetUInt32();

    private static byte[] Hex(JsonElement element, string name) => Convert.FromHexString(element.GetProperty(name).GetString()!);

    private static string Id(ArcForges.Contracts.Foundation.V1.Id value) => Convert.ToHexStringLower(value.Value.ToByteArray());

    private static string? OptionalId(ArcForges.Contracts.Foundation.V1.Id? value) => value is null ? null : Id(value);

    private static string? OptionalText(JsonElement element, string name) =>
        element.GetProperty(name).ValueKind == JsonValueKind.Null ? null : element.GetProperty(name).GetString();

    private static void Valid<T>(T value, Action<T> change, string name) where T : class, IMessage<T> =>
        Require(IsValid(Change(value, change)), name + " is valid");

    private static void Invalid<T>(T value, Action<T> change, string name) where T : class, IMessage<T> =>
        Require(!IsValid(Change(value, change)), name + " is refused");

    private static bool IsValid<T>(T value) where T : class, IMessage<T> => value switch
    {
        CallHeader v => RelayShapes.IsValid(v),
        ResultHeader v => RelayShapes.IsValid(v),
        ChannelCall v => RelayShapes.IsValid(v),
        ChannelResult v => RelayShapes.IsValid(v),
        ChannelChallenge v => RelayShapes.IsValid(v),
        ChannelAccepted v => RelayShapes.IsValid(v),
        NodeHello v => RelayShapes.IsValid(v),
        RelayNonce v => RelayShapes.IsValid(v),
        RelayAssertion v => RelayShapes.IsValid(v),
        FleetServiceListNodesRequest v => FleetShapes.IsValid(v),
        FleetServiceGetNodeRequest v => FleetShapes.IsValid(v),
        FleetServiceSubmitNodeTaskRequest v => FleetShapes.IsValid(v),
        FleetServiceGetNodeTaskRequest v => FleetShapes.IsValid(v),
        FleetServiceListNodeTasksRequest v => FleetShapes.IsValid(v),
        FleetServiceWaitNodeTaskRequest v => FleetShapes.IsValid(v),
        FleetServiceReadNodeTaskOutputRequest v => FleetShapes.IsValid(v),
        FleetServiceCancelNodeTaskRequest v => FleetShapes.IsValid(v),
        _ => throw new InvalidOperationException("no validator for " + typeof(T).Name),
    };

    private static T Change<T>(T value, Action<T> change) where T : IMessage<T>
    {
        var copy = value.Clone();
        change(copy);
        return copy;
    }

    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("AF-CTR-05 C2 case failed: " + name);
    }
}
