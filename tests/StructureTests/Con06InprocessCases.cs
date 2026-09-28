// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using F = ArcForges.Contracts.Foundation.V1;
using U = ArcForges.Contracts.PublicApi.V1;
using P = ArcForges.Contracts.LocalRpc.Platform.V1;
using C = ArcForges.Contracts.LocalRpc.Chat.V1;
using S = ArcForges.Contracts.LocalRpc.Scope.V1;
using PublicShape = ArcForges.Contracts.Validation.ContractShapeValidation;
using PlatformShape = ArcForges.Contracts.LocalRpc.Platform.Shapes.ContractShapeValidation;
using ChatShape = ArcForges.Contracts.LocalRpc.Chat.Shapes.ContractShapeValidation;
using ScopeShape = ArcForges.Contracts.LocalRpc.Scope.Shapes.ContractShapeValidation;

internal static class Con06InprocessCases
{
    public static void Run(string root)
    {
        using var fixture = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/internal/con-06-product-ports.json")));
        var count = 0;
        foreach (var row in fixture.RootElement.GetProperty("cases").EnumerateArray())
        {
            var name = row.GetProperty("case").GetString()!;
            var actual = row.GetProperty("domain").GetString() switch
            {
                "decoder" => ScopeShape.IsValid(Decoder(name)),
                "turn" => PublicShape.IsValid(Turn(name)),
                "consent" => PublicShape.IsValid(Consent(name)),
                "hint" => PlatformShape.IsValid(Hint(name)),
                "chunk" => PlatformShape.IsValid(Chunk(name)),
                _ => throw new InvalidOperationException("Unknown independent fixture domain."),
            };
            Require(actual == row.GetProperty("valid").GetBoolean(), "CON06 fixture " + row.GetProperty("id").GetString());
            count++;
        }
        Envelopes();
        TurnContext();
        VerifyEnvelope(S.ScopeOperationsServiceListSessionsRequest.Descriptor, S.ScopeOperationsServiceListSessionsResponse.Descriptor);
        VerifyEnvelope(C.ChatOperationsServiceListConversationsRequest.Descriptor, C.ChatOperationsServiceListConversationsResponse.Descriptor);
        Require(S.ScopeOperationsServiceListSessionsRequest.Descriptor.File.Services.Count == 0, "Scope records must not declare a gRPC service.");
        Require(C.ChatOperationsServiceListConversationsRequest.Descriptor.File.Services.Count == 0, "Chat records must not declare a gRPC service.");
        Require(P.LocalHint.Descriptor.File.Services.Count == 0, "Infrastructure ports must not declare a gRPC service.");
        Console.WriteLine($"CON.06 {count} independent shape fixtures and Scope/Chat envelope/context round trips passed; no runtime authority evidence.");
    }

    private static S.DecoderOptions Decoder(string name)
    {
        var kind = name.StartsWith("i2c", StringComparison.Ordinal) ? "i2c" : name.StartsWith("spi", StringComparison.Ordinal) ? "spi" : "uart";
        var value = new S.DecoderOptions { Kind = kind, Bits = 8, Parity = "none", StopBits = 1, Mode = 0, MsbFirst = true, ActiveLow = true, AddressBits = 7, IdleHigh = true, Timeout = new U.ScopeTime { Ticks = 1, Rate = new F.Rational { Numerator = 1000, Denominator = 1 } } };
        for (var i = 0; i < (kind == "uart" ? 1 : kind == "i2c" ? 2 : 3); i++) value.Channels.Add(Id((byte)(i + 1)));
        if (kind == "uart") value.Baud = 115200;
        switch (name)
        {
            case "uart": case "i2c": case "spi": break;
            case "uart-boundaries": value.Bits = 9; value.Parity = "odd"; value.StopBits = 2; value.IdleHigh = false; break;
            case "i2c-ten-bit": value.AddressBits = 10; break;
            case "spi-miso": value.Channels.Add(Id(4)); break;
            case "spi-active-options": value.Bits = 32; value.Mode = 3; value.MsbFirst = false; value.ActiveLow = false; break;
            case "wrong-case": value.Kind = "UART"; break;
            case "unknown": value.Kind = "future"; break;
            case "uart-no-baud": value.ClearBaud(); break;
            case "uart-four-bits": value.Bits = 4; break;
            case "uart-ten-bits": value.Bits = 10; break;
            case "uart-two-channels": value.Channels.Add(Id(2)); break;
            case "i2c-baud": value.Baud = 115200; break;
            case "i2c-one-channel": value.Channels.RemoveAt(1); break;
            case "spi-two-channels": value.Channels.RemoveAt(2); break;
            case "spi-five-channels": value.Channels.Add(Id(4)); value.Channels.Add(Id(5)); break;
            case "spi-inactive-parity": value.Parity = "even"; break;
            case "spi-inactive-stop": value.StopBits = 2; break;
            case "i2c-inactive-bit": value.Bits = 9; break;
            case "uart-inactive-mode": value.Mode = 1; break;
            case "uart-inactive-order": value.MsbFirst = false; break;
            case "uart-inactive-cs": value.ActiveLow = false; break;
            case "spi-inactive-address": value.AddressBits = 10; break;
            case "i2c-inactive-idle": value.IdleHigh = false; break;
            case "zero-timeout": value.Timeout.Ticks = 0; break;
            case "negative-timeout": value.Timeout.Ticks = -1; break;
            case "missing-timeout": value.Timeout = null; break;
            case "missing-active-bit": value.ClearBits(); break;
            case "unknown-parity": value.Parity = "None"; break;
            case "invalid-channel": value.Channels[0] = new F.Id(); break;
            default: throw new InvalidOperationException("Unknown decoder fixture: " + name);
        }
        return value;
    }

    private static U.TurnOptions Turn(string name)
    {
        var value = new U.TurnOptions { Mode = U.ChatMode.Agent, TaskId = Id(), ProfileId = Id(2), AllowWebSearch = false, CompactionRequested = false };
        if (name.StartsWith("ordinary", StringComparison.Ordinal) || name == "temporary")
        { value.Mode = name == "temporary" ? U.ChatMode.Temporary : U.ChatMode.Ordinary; value.TaskId = null; value.TurnId = Id(3); }
        switch (name)
        {
            case "agent": case "ordinary": case "temporary": break;
            case "agent-no-task": value.TaskId = null; break;
            case "agent-with-turn": value.TurnId = Id(3); break;
            case "ordinary-with-task": value.TaskId = Id(); break;
            case "ordinary-no-turn": value.TurnId = null; break;
            case "unknown-mode": value.Mode = (U.ChatMode)99; break;
            case "missing-profile": value.ProfileId = null; break;
            case "missing-search-selection": value.ClearAllowWebSearch(); break;
            default: throw new InvalidOperationException("Unknown turn fixture: " + name);
        }
        return value;
    }

    private static U.SourceConsentSpec Consent(string name)
    {
        var value = new U.SourceConsentSpec { OperationId = Id(), Purpose = "turnContext", MaxBytes = 1, PolicyRevision = new F.Revision { Value = 1 } };
        switch (name)
        {
            case "turnContext": break;
            case "webSearch": value.Purpose = "webSearch"; value.QueryHash = new string('a', 64); break;
            case "attachment": value.Purpose = "attachment"; break;
            case "temporary-false": value.Override = new U.KnowledgePolicyPatch { AiRetrievalAllowed = false, ManagedAiProcessingAllowed = false }; break;
            case "temporary-true": value.Override = new U.KnowledgePolicyPatch { AiRetrievalAllowed = true, ManagedAiProcessingAllowed = true }; break;
            case "64-sources": case "65-sources":
                for (var i = 0; i < (name == "64-sources" ? 64 : 65); i++) value.Sources.Add(new F.VersionedRef { Root = new F.AggregateRef { Kind = "report", Id = Id((byte)(i + 1)) }, Revision = new F.Revision { Value = 1 } });
                break;
            case "webSearch-no-hash": value.Purpose = "webSearch"; break;
            case "wrong-case": value.Purpose = "TurnContext"; break;
            case "transcription": value.Purpose = "transcription"; break;
            case "zero-budget": value.MaxBytes = 0; break;
            case "missing-policy": value.PolicyRevision = null; break;
            case "searchable-false": value.Override = new U.KnowledgePolicyPatch { Searchable = false }; break;
            case "cloud-index-false": value.Override = new U.KnowledgePolicyPatch { CloudIndexAllowed = false }; break;
            case "bad-hash": value.QueryHash = new string('A', 64); break;
            default: throw new InvalidOperationException("Unknown consent fixture: " + name);
        }
        return value;
    }

    private static P.LocalHint Hint(string name)
    {
        var value = new P.LocalHint { Sequence = 0, Kind = "contextChanged", InstanceId = Id() };
        if (name.StartsWith("resource", StringComparison.Ordinal)) { value.Kind = "resourceChanged"; value.ResourceId = Id(2); }
        if (name.StartsWith("job", StringComparison.Ordinal)) { value.Kind = "jobChanged"; value.JobId = Id(3); }
        switch (name)
        {
            case "resource": case "job": case "context": break;
            case "health": value.Kind = "healthChanged"; break;
            case "capabilities": value.Kind = "capabilitiesChanged"; break;
            case "resource-missing": value.ResourceId = null; break;
            case "resource-with-job": value.JobId = Id(3); break;
            case "job-missing": value.JobId = null; break;
            case "context-with-resource": value.ResourceId = Id(2); break;
            case "unknown-kind": value.Kind = "futureChanged"; break;
            case "missing-sequence": value.ClearSequence(); break;
            default: throw new InvalidOperationException("Unknown hint fixture: " + name);
        }
        return value;
    }

    private static P.ResourceAccessServiceReadChunkRequest Chunk(string name)
    {
        var value = new P.ResourceAccessServiceReadChunkRequest { Meta = Meta(), TransferId = Id(), Offset = 0, Length = 1 };
        switch (name)
        {
            case "one-byte": break;
            case "64-kib": value.Length = 65536; break;
            case "last-address": value.Offset = ulong.MaxValue - 1; break;
            case "zero-length": value.Length = 0; break;
            case "oversize": value.Length = 65537; break;
            case "overflow": value.Offset = ulong.MaxValue; break;
            case "missing-transfer": value.TransferId = null; break;
            case "missing-offset": value.ClearOffset(); break;
            default: throw new InvalidOperationException("Unknown chunk fixture: " + name);
        }
        return value;
    }

    private static void Envelopes()
    {
        var scope = new S.ScopeOperationsServiceListSessionsRequest { Meta = Meta(), Page = new F.PageRequest { Limit = 1 } };
        Require(ScopeShape.IsValid(scope), "Scope paged request.");
        Require(scope.Equals(S.ScopeOperationsServiceListSessionsRequest.Parser.ParseFrom(scope.ToByteArray())), "Scope binary roundtrip.");
        scope.Page.Limit = 0; Require(!ScopeShape.IsValid(scope), "Explicit zero page budget refused.");
        scope.Page.Limit = 1; scope.Meta = null; Require(!ScopeShape.IsValid(scope), "Scope missing envelope meta refused.");
        var chat = new C.ChatOperationsServiceListConversationsRequest { Meta = Meta(), Page = new F.PageRequest { Limit = 1 } };
        Require(ChatShape.IsValid(chat), "Chat paged request.");
        Require(chat.Equals(C.ChatOperationsServiceListConversationsRequest.Parser.ParseFrom(chat.ToByteArray())), "Chat binary roundtrip.");
        chat.Page = null; Require(!ChatShape.IsValid(chat), "Chat missing page refused.");
        var scopeReply = new S.ScopeOperationsServiceListSessionsResponse { Meta = ReplyMeta(), Value = new S.ScopeOperationsServiceListSessionsValue { Page = new F.PageState { HasMore = false } } };
        Require(ScopeShape.IsValid(scopeReply), "Empty terminal Scope page is a typed success.");
        Require(scopeReply.Equals(S.ScopeOperationsServiceListSessionsResponse.Parser.ParseFrom(scopeReply.ToByteArray())), "Scope response roundtrip.");
        scopeReply.ClearOutcome(); Require(!ScopeShape.IsValid(scopeReply), "Scope absent outcome refused.");
        var chatReply = new C.ChatOperationsServiceListConversationsResponse { Meta = ReplyMeta(), Value = new C.ChatOperationsServiceListConversationsValue { Page = new F.PageState { HasMore = false } } };
        Require(ChatShape.IsValid(chatReply), "Empty terminal Chat page is a typed success.");
        chatReply.Value.Page.HasMore = true; Require(!ChatShape.IsValid(chatReply), "Continuation cannot omit cursor.");
        chatReply.ClearOutcome(); Require(!ChatShape.IsValid(chatReply), "Chat absent outcome refused.");
        var start = new C.ChatOperationsServiceStartAgentTurnRequest { Meta = Meta(), TaskId = Id(), ConversationId = Id(2), Input = new U.TurnInput(), Options = Turn("agent") };
        Require(ChatShape.IsValid(start), "Matching agent task identity accepted structurally.");
        start.TaskId = Id(9); Require(!ChatShape.IsValid(start), "Envelope cannot disagree with selected task identity.");
        start.TaskId = Id(); start.Options = Turn("ordinary"); Require(!ChatShape.IsValid(start), "Agent entry cannot silently select ordinary mode.");
    }

    private static void TurnContext()
    {
        var context = new U.ContextRef { Source = new F.AggregateRef { Kind = "report", Id = Id() }, Revision = new F.Revision { Value = 1 }, Lifetime = U.ContextLifetime.Pinned };
        var input = new U.TurnInput(); input.Context.Add(context);
        Require(PublicShape.IsValid(input), "Frozen persistent context is structurally valid.");
        Require(input.Equals(U.TurnInput.Parser.ParseFrom(input.ToByteArray())), "Turn context generated binary roundtrip.");
        context.Revision.Value = 0; Require(!PublicShape.IsValid(input), "A provided turn context revision must identify a committed revision.");
        context.Revision = new F.Revision { Value = 1 }; context.Source.Id = new F.Id();
        Require(!PublicShape.IsValid(input), "Nested malformed context ID is rejected.");
        var patch = new U.KnowledgePolicyPatch { AiRetrievalAllowed = false };
        var decoded = U.KnowledgePolicyPatch.Parser.ParseFrom(patch.ToByteArray());
        Require(decoded.HasAiRetrievalAllowed && !decoded.AiRetrievalAllowed && !decoded.HasSearchable, "Explicit deny survives wire roundtrip without converting absence into consent.");
    }

    private static void VerifyEnvelope(MessageDescriptor request, MessageDescriptor response)
    {
        Require(request.FindFieldByNumber(1).MessageType.FullName == "arcforges.foundation.v1.RequestMeta", "RequestMeta tag1.");
        Require(response.FindFieldByNumber(1).MessageType.FullName == "arcforges.foundation.v1.ResponseMeta", "ResponseMeta tag1.");
        for (var tag = 2; tag <= 9; tag++) Require(request.FindFieldByNumber(tag) is null, "Reserved request envelope gap.");
        Require(response.FindFieldByNumber(2).ContainingOneof.Name == "outcome" && response.FindFieldByNumber(3).ContainingOneof.Name == "outcome", "Success/error exclusive outcome.");
        Require(response.FindFieldByNumber(3).MessageType.FullName == "arcforges.foundation.v1.ArcError", "Error is typed.");
        Require(response.FindFieldByNumber(4).ContainingOneof.Name == "outcome", "Eligible paged projections use EncodedBodyRef outcome4.");
    }

    private static F.Id Id(byte suffix = 1) { var bytes = Convert.FromHexString("00112233445566778899aabbccddee00"); bytes[15] = suffix; return new F.Id { Value = ByteString.CopyFrom(bytes) }; }
    private static F.RequestMeta Meta() => new() { CorrelationId = Id() };
    private static F.ResponseMeta ReplyMeta() => new() { CorrelationId = Id() };
    private static void Require(bool valid, string message) { if (!valid) throw new InvalidOperationException(message); }
}

