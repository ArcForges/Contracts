// SPDX-License-Identifier: Apache-2.0
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Nodes;
using Google.Protobuf;
using C = ArcForges.Contracts.LocalRpc.Chat.V1;
using D = ArcForges.Contracts.LocalRpc.Dispatch;
using F = ArcForges.Contracts.Foundation.V1;
using P = ArcForges.Contracts.LocalRpc.Platform.V1;
using PlatformShape = ArcForges.Contracts.LocalRpc.Platform.Shapes.ContractShapeValidation;
using S = ArcForges.Contracts.LocalRpc.Scope.V1;
using U = ArcForges.Contracts.PublicApi.V1;

/// <summary>CON.43: every generated local-operation decoder, encoder and the closed tool allowlist against the
/// independent fixture (typed values from the wp03-01 samples, structured forms derived outside the emitter).</summary>
internal static class Con43LocalOperationCases
{
    private delegate bool Decoder<T>(U.CapabilityArguments? arguments, F.RequestMeta? meta, P.LocalCallContext? context, [NotNullWhen(true)] out T? request, [NotNullWhen(false)] out D.LocalOperationFault? fault);
    private delegate bool ResultEncoder<T>(T? value, [NotNullWhen(true)] out U.CapabilityResult? result, [NotNullWhen(false)] out D.LocalOperationFault? fault);
    private delegate bool ResultDecoder<T>(U.CapabilityResult? result, [NotNullWhen(true)] out T? value, [NotNullWhen(false)] out D.LocalOperationFault? fault);
    private delegate bool ArgumentEncoder<T>(T? request, [NotNullWhen(true)] out U.CapabilityArguments? arguments, [NotNullWhen(false)] out D.LocalOperationFault? fault);

    private sealed record Adapter(
        string OperationId, string RequestSchemaId, string ResultSchemaId, bool IsAdmitted, D.LocalOperation Operation,
        Func<string, IMessage> ParseRequest, Func<string, IMessage> ParseValue,
        Func<U.CapabilityArguments?, F.RequestMeta?, P.LocalCallContext?, (IMessage? Request, D.LocalOperationFault? Fault)> Decode,
        Func<IMessage?, (U.CapabilityResult? Result, D.LocalOperationFault? Fault)> EncodeResult,
        Func<U.CapabilityResult?, (IMessage? Value, D.LocalOperationFault? Fault)> DecodeResult,
        Func<IMessage?, (U.CapabilityArguments? Arguments, D.LocalOperationFault? Fault)> EncodeArguments);

    private static Adapter Make<TRequest, TValue>(string operationId, string requestSchemaId, string resultSchemaId, bool admitted,
        D.LocalOperation operation, Decoder<TRequest> decode, ResultEncoder<TValue> encodeResult, ResultDecoder<TValue> decodeResult,
        ArgumentEncoder<TRequest> encodeArguments)
        where TRequest : class, IMessage<TRequest>, new()
        where TValue : class, IMessage<TValue>, new() =>
        new(operationId, requestSchemaId, resultSchemaId, admitted, operation,
            json => JsonParser.Default.Parse<TRequest>(json), json => JsonParser.Default.Parse<TValue>(json),
            (arguments, meta, context) => decode(arguments, meta, context, out var request, out var fault) ? (request, null) : (null, fault),
            value => encodeResult((TValue?)value, out var result, out var fault) ? (result, null) : (null, fault),
            result => decodeResult(result, out var value, out var fault) ? (value, null) : (null, fault),
            request => encodeArguments((TRequest?)request, out var arguments, out var fault) ? (arguments, null) : (null, fault));

    private static readonly Adapter[] Adapters =
    [
        Make<C.ChatOperationsServiceAppendUserMessageRequest, C.ChatOperationsServiceAppendUserMessageValue>(D.ChatAppendUserMessageOperation.OperationId, D.ChatAppendUserMessageOperation.RequestSchemaId, D.ChatAppendUserMessageOperation.ResultSchemaId, D.ChatAppendUserMessageOperation.IsAdmitted, D.ChatAppendUserMessageOperation.Operation, D.ChatAppendUserMessageOperation.TryDecode, D.ChatAppendUserMessageOperation.TryEncodeResult, D.ChatAppendUserMessageOperation.TryDecodeResult, D.ChatAppendUserMessageOperation.TryEncodeArguments),
        Make<C.ChatOperationsServiceCreateConversationRequest, C.ChatOperationsServiceCreateConversationValue>(D.ChatCreateConversationOperation.OperationId, D.ChatCreateConversationOperation.RequestSchemaId, D.ChatCreateConversationOperation.ResultSchemaId, D.ChatCreateConversationOperation.IsAdmitted, D.ChatCreateConversationOperation.Operation, D.ChatCreateConversationOperation.TryDecode, D.ChatCreateConversationOperation.TryEncodeResult, D.ChatCreateConversationOperation.TryDecodeResult, D.ChatCreateConversationOperation.TryEncodeArguments),
        Make<C.ChatOperationsServiceGetConversationRequest, C.ChatOperationsServiceGetConversationValue>(D.ChatGetConversationOperation.OperationId, D.ChatGetConversationOperation.RequestSchemaId, D.ChatGetConversationOperation.ResultSchemaId, D.ChatGetConversationOperation.IsAdmitted, D.ChatGetConversationOperation.Operation, D.ChatGetConversationOperation.TryDecode, D.ChatGetConversationOperation.TryEncodeResult, D.ChatGetConversationOperation.TryDecodeResult, D.ChatGetConversationOperation.TryEncodeArguments),
        Make<C.ChatOperationsServiceListConversationsRequest, C.ChatOperationsServiceListConversationsValue>(D.ChatListConversationsOperation.OperationId, D.ChatListConversationsOperation.RequestSchemaId, D.ChatListConversationsOperation.ResultSchemaId, D.ChatListConversationsOperation.IsAdmitted, D.ChatListConversationsOperation.Operation, D.ChatListConversationsOperation.TryDecode, D.ChatListConversationsOperation.TryEncodeResult, D.ChatListConversationsOperation.TryDecodeResult, D.ChatListConversationsOperation.TryEncodeArguments),
        Make<C.ChatOperationsServiceOpenArtifactRequest, C.ChatOperationsServiceOpenArtifactValue>(D.ChatOpenArtifactOperation.OperationId, D.ChatOpenArtifactOperation.RequestSchemaId, D.ChatOpenArtifactOperation.ResultSchemaId, D.ChatOpenArtifactOperation.IsAdmitted, D.ChatOpenArtifactOperation.Operation, D.ChatOpenArtifactOperation.TryDecode, D.ChatOpenArtifactOperation.TryEncodeResult, D.ChatOpenArtifactOperation.TryDecodeResult, D.ChatOpenArtifactOperation.TryEncodeArguments),
        Make<C.ChatOperationsServiceStartAgentTurnRequest, C.ChatOperationsServiceStartAgentTurnValue>(D.ChatStartAgentTurnOperation.OperationId, D.ChatStartAgentTurnOperation.RequestSchemaId, D.ChatStartAgentTurnOperation.ResultSchemaId, D.ChatStartAgentTurnOperation.IsAdmitted, D.ChatStartAgentTurnOperation.Operation, D.ChatStartAgentTurnOperation.TryDecode, D.ChatStartAgentTurnOperation.TryEncodeResult, D.ChatStartAgentTurnOperation.TryDecodeResult, D.ChatStartAgentTurnOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceCompareSessionsRequest, S.ScopeOperationsServiceCompareSessionsValue>(D.ScopeCompareSessionsOperation.OperationId, D.ScopeCompareSessionsOperation.RequestSchemaId, D.ScopeCompareSessionsOperation.ResultSchemaId, D.ScopeCompareSessionsOperation.IsAdmitted, D.ScopeCompareSessionsOperation.Operation, D.ScopeCompareSessionsOperation.TryDecode, D.ScopeCompareSessionsOperation.TryEncodeResult, D.ScopeCompareSessionsOperation.TryDecodeResult, D.ScopeCompareSessionsOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceCreateAnnotationRequest, S.ScopeOperationsServiceCreateAnnotationValue>(D.ScopeCreateAnnotationOperation.OperationId, D.ScopeCreateAnnotationOperation.RequestSchemaId, D.ScopeCreateAnnotationOperation.ResultSchemaId, D.ScopeCreateAnnotationOperation.IsAdmitted, D.ScopeCreateAnnotationOperation.Operation, D.ScopeCreateAnnotationOperation.TryDecode, D.ScopeCreateAnnotationOperation.TryEncodeResult, D.ScopeCreateAnnotationOperation.TryDecodeResult, D.ScopeCreateAnnotationOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceCreateFindingRequest, S.ScopeOperationsServiceCreateFindingValue>(D.ScopeCreateFindingOperation.OperationId, D.ScopeCreateFindingOperation.RequestSchemaId, D.ScopeCreateFindingOperation.ResultSchemaId, D.ScopeCreateFindingOperation.IsAdmitted, D.ScopeCreateFindingOperation.Operation, D.ScopeCreateFindingOperation.TryDecode, D.ScopeCreateFindingOperation.TryEncodeResult, D.ScopeCreateFindingOperation.TryDecodeResult, D.ScopeCreateFindingOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceGenerateReportRequest, S.ScopeOperationsServiceGenerateReportValue>(D.ScopeGenerateReportOperation.OperationId, D.ScopeGenerateReportOperation.RequestSchemaId, D.ScopeGenerateReportOperation.ResultSchemaId, D.ScopeGenerateReportOperation.IsAdmitted, D.ScopeGenerateReportOperation.Operation, D.ScopeGenerateReportOperation.TryDecode, D.ScopeGenerateReportOperation.TryEncodeResult, D.ScopeGenerateReportOperation.TryDecodeResult, D.ScopeGenerateReportOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceGetConfigurationSnapshotRequest, S.ScopeOperationsServiceGetConfigurationSnapshotValue>(D.ScopeGetConfigurationSnapshotOperation.OperationId, D.ScopeGetConfigurationSnapshotOperation.RequestSchemaId, D.ScopeGetConfigurationSnapshotOperation.ResultSchemaId, D.ScopeGetConfigurationSnapshotOperation.IsAdmitted, D.ScopeGetConfigurationSnapshotOperation.Operation, D.ScopeGetConfigurationSnapshotOperation.TryDecode, D.ScopeGetConfigurationSnapshotOperation.TryEncodeResult, D.ScopeGetConfigurationSnapshotOperation.TryDecodeResult, D.ScopeGetConfigurationSnapshotOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceGetSessionRequest, S.ScopeOperationsServiceGetSessionValue>(D.ScopeGetSessionOperation.OperationId, D.ScopeGetSessionOperation.RequestSchemaId, D.ScopeGetSessionOperation.ResultSchemaId, D.ScopeGetSessionOperation.IsAdmitted, D.ScopeGetSessionOperation.Operation, D.ScopeGetSessionOperation.TryDecode, D.ScopeGetSessionOperation.TryEncodeResult, D.ScopeGetSessionOperation.TryDecodeResult, D.ScopeGetSessionOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceGetStructuredContextRequest, S.ScopeOperationsServiceGetStructuredContextValue>(D.ScopeGetStructuredContextOperation.OperationId, D.ScopeGetStructuredContextOperation.RequestSchemaId, D.ScopeGetStructuredContextOperation.ResultSchemaId, D.ScopeGetStructuredContextOperation.IsAdmitted, D.ScopeGetStructuredContextOperation.Operation, D.ScopeGetStructuredContextOperation.TryDecode, D.ScopeGetStructuredContextOperation.TryEncodeResult, D.ScopeGetStructuredContextOperation.TryDecodeResult, D.ScopeGetStructuredContextOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceListCapturesRequest, S.ScopeOperationsServiceListCapturesValue>(D.ScopeListCapturesOperation.OperationId, D.ScopeListCapturesOperation.RequestSchemaId, D.ScopeListCapturesOperation.ResultSchemaId, D.ScopeListCapturesOperation.IsAdmitted, D.ScopeListCapturesOperation.Operation, D.ScopeListCapturesOperation.TryDecode, D.ScopeListCapturesOperation.TryEncodeResult, D.ScopeListCapturesOperation.TryDecodeResult, D.ScopeListCapturesOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceListSessionsRequest, S.ScopeOperationsServiceListSessionsValue>(D.ScopeListSessionsOperation.OperationId, D.ScopeListSessionsOperation.RequestSchemaId, D.ScopeListSessionsOperation.ResultSchemaId, D.ScopeListSessionsOperation.IsAdmitted, D.ScopeListSessionsOperation.Operation, D.ScopeListSessionsOperation.TryDecode, D.ScopeListSessionsOperation.TryEncodeResult, D.ScopeListSessionsOperation.TryDecodeResult, D.ScopeListSessionsOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceRunAnalysisRequest, S.ScopeOperationsServiceRunAnalysisValue>(D.ScopeRunAnalysisOperation.OperationId, D.ScopeRunAnalysisOperation.RequestSchemaId, D.ScopeRunAnalysisOperation.ResultSchemaId, D.ScopeRunAnalysisOperation.IsAdmitted, D.ScopeRunAnalysisOperation.Operation, D.ScopeRunAnalysisOperation.TryDecode, D.ScopeRunAnalysisOperation.TryEncodeResult, D.ScopeRunAnalysisOperation.TryDecodeResult, D.ScopeRunAnalysisOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceRunMeasurementRequest, S.ScopeOperationsServiceRunMeasurementValue>(D.ScopeRunMeasurementOperation.OperationId, D.ScopeRunMeasurementOperation.RequestSchemaId, D.ScopeRunMeasurementOperation.ResultSchemaId, D.ScopeRunMeasurementOperation.IsAdmitted, D.ScopeRunMeasurementOperation.Operation, D.ScopeRunMeasurementOperation.TryDecode, D.ScopeRunMeasurementOperation.TryEncodeResult, D.ScopeRunMeasurementOperation.TryDecodeResult, D.ScopeRunMeasurementOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceStartCaptureRequest, S.ScopeOperationsServiceStartCaptureValue>(D.ScopeStartCaptureOperation.OperationId, D.ScopeStartCaptureOperation.RequestSchemaId, D.ScopeStartCaptureOperation.ResultSchemaId, D.ScopeStartCaptureOperation.IsAdmitted, D.ScopeStartCaptureOperation.Operation, D.ScopeStartCaptureOperation.TryDecode, D.ScopeStartCaptureOperation.TryEncodeResult, D.ScopeStartCaptureOperation.TryDecodeResult, D.ScopeStartCaptureOperation.TryEncodeArguments),
        Make<S.ScopeOperationsServiceStopCaptureRequest, S.ScopeOperationsServiceStopCaptureValue>(D.ScopeStopCaptureOperation.OperationId, D.ScopeStopCaptureOperation.RequestSchemaId, D.ScopeStopCaptureOperation.ResultSchemaId, D.ScopeStopCaptureOperation.IsAdmitted, D.ScopeStopCaptureOperation.Operation, D.ScopeStopCaptureOperation.TryDecode, D.ScopeStopCaptureOperation.TryEncodeResult, D.ScopeStopCaptureOperation.TryDecodeResult, D.ScopeStopCaptureOperation.TryEncodeArguments),
    ];

    public static void Run(string root)
    {
        using var fixture = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/internal/con-43-local-operations.json")));
        var data = fixture.RootElement;
        Require(data.GetProperty("schemaVersion").GetString() == "con-43-local-operations.v1", "CON.43 fixture version");
        var byId = Adapters.ToDictionary(adapter => adapter.OperationId, StringComparer.Ordinal);
        var meta = JsonParser.Default.Parse<F.RequestMeta>(data.GetProperty("meta").GetRawText());
        var context = JsonParser.Default.Parse<P.LocalCallContext>(data.GetProperty("context").GetRawText());
        Require(PlatformShape.IsValid(meta) && PlatformShape.IsValid(context), "CON.43 fixture meta and context are valid");

        Inventory(data, byId);
        Allowlist(data);
        var decoded = DecodeVectors(data, byId, meta, context);
        var refused = Refusals(data, byId, meta, context);
        var encoded = ResultVectors(data, byId);
        var encodeRefused = EncodeRefusals(data, byId);
        Guards(meta, context);
        Console.WriteLine($"CON.43 {Adapters.Length} generated local operations: {decoded} decode and argument round trips, {refused} typed refusals, "
            + $"{encoded} result encodings and round trips, {encodeRefused} encode refusals; the closed allowlist holds {D.LocalToolAllowlist.Keys.Count} key.");
    }

    private static void Inventory(JsonElement data, Dictionary<string, Adapter> byId)
    {
        var expected = data.GetProperty("operations").EnumerateArray().ToArray();
        Require(expected.Length == 19 && Adapters.Length == 19 && D.LocalOperationCatalog.All.Count == 19, "CON.43: exactly 19 tool-eligible operations");
        for (var i = 0; i < expected.Length; i++)
        {
            var row = expected[i];
            var id = row.GetProperty("operationId").GetString()!;
            var operation = D.LocalOperationCatalog.All[i];
            Require((int)operation == i + 1, id + ": catalog order is the ordinal operation-ID order");
            Require(byId.TryGetValue(id, out var adapter) && adapter.Operation == operation, id + ": one generated adapter");
            Require(D.LocalOperationCatalog.OperationId(operation) == id, id + ": catalog operation ID");
            Require(adapter!.RequestSchemaId == row.GetProperty("requestSchemaId").GetString()
                && D.LocalOperationCatalog.RequestSchemaId(operation) == adapter.RequestSchemaId, id + ": request schema ID");
            Require(adapter.ResultSchemaId == row.GetProperty("resultSchemaId").GetString()
                && D.LocalOperationCatalog.ResultSchemaId(operation) == adapter.ResultSchemaId, id + ": result schema ID");
            Require(adapter.IsAdmitted == row.GetProperty("admitted").GetBoolean() && D.LocalOperationCatalog.IsAdmitted(operation) == adapter.IsAdmitted,
                id + ": admission flag");
            foreach (var (text, schemaId, root) in new[]
            {
                (D.LocalOperationCatalog.RequestSchema(operation), adapter.RequestSchemaId, true),
                (D.LocalOperationCatalog.ResultSchema(operation), adapter.ResultSchemaId, false),
            })
            {
                using var schema = JsonDocument.Parse(text);
                var value = schema.RootElement;
                Require(value.GetProperty("dialect").GetString() == "arcforges.local-operation-schema.v1"
                    && value.GetProperty("schemaId").GetString() == schemaId && value.GetProperty("root").GetString() == schemaId
                    && value.GetProperty("maxDepth").GetInt32() == 16 && value.GetProperty("maxItems").GetInt32() == 200, id + ": schema header");
                var definition = value.GetProperty("definitions").GetProperty(schemaId);
                Require(definition.GetProperty("closed").GetBoolean() && definition.GetProperty("kind").GetString() == "record", id + ": closed root record");
                Require(!root || !definition.GetProperty("fields").TryGetProperty("meta", out _), id + ": the request meta is never an argument");
            }
        }
        Require(Throws(() => D.LocalOperationCatalog.OperationId(D.LocalOperation.Unspecified)), "CON.43: Unspecified has no identity");
        foreach (var key in data.GetProperty("notEligible").EnumerateArray().Select(item => item.GetString()!))
        {
            Require(!byId.ContainsKey(key) && D.LocalOperationCatalog.All.All(op => D.LocalOperationCatalog.OperationId(op) != key),
                key + ": infrastructure ports and human-only decisions get no generated adapter");
        }
    }

    private static void Allowlist(JsonElement data)
    {
        var admitted = Adapters.Where(adapter => adapter.IsAdmitted).Select(adapter => adapter.OperationId).ToArray();
        Require(admitted.SequenceEqual(["IScopeOperations.CreateAnnotation"], StringComparer.Ordinal), "CON.43: exactly the S61(2) admitted operation");
        Require(D.LocalToolAllowlist.Keys.SequenceEqual(admitted, StringComparer.Ordinal), "CON.43: the allowlist holds exactly the admitted keys");
        foreach (var key in D.LocalToolAllowlist.Keys)
        {
            var matches = D.LocalOperationCatalog.All.Count(op => D.LocalToolAllowlist.TryResolve(key, out var resolved) && resolved == op);
            Require(matches == 1 && D.LocalToolAllowlist.TryResolve(key, out var operation)
                && D.LocalOperationCatalog.OperationId(operation) == key && D.LocalOperationCatalog.IsAdmitted(operation), key + ": resolves to exactly one admitted operation");
        }
        var count = 0;
        foreach (var row in data.GetProperty("resolve").EnumerateArray())
        {
            var key = row.GetProperty("key").GetString();
            var expected = row.GetProperty("operation");
            var resolved = D.LocalToolAllowlist.TryResolve(key, out var operation);
            if (expected.ValueKind == JsonValueKind.Null)
                Require(!resolved && operation == D.LocalOperation.Unspecified, "CON.43: '" + key + "' resolves to nothing");
            else
                Require(resolved && D.LocalOperationCatalog.OperationId(operation) == expected.GetString(), "CON.43: '" + key + "' resolves exactly");
            count++;
        }
        Require(!D.LocalToolAllowlist.TryResolve(null, out var none) && none == D.LocalOperation.Unspecified && count > 30, "CON.43: null and the resolve vectors");
    }

    private static int DecodeVectors(JsonElement data, Dictionary<string, Adapter> byId, F.RequestMeta meta, P.LocalCallContext context)
    {
        var count = 0;
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var row in data.GetProperty("decode").EnumerateArray())
        {
            var id = row.GetProperty("id").GetString()!;
            var adapter = byId[row.GetProperty("operation").GetString()!];
            var arguments = new U.CapabilityArguments { SchemaId = adapter.RequestSchemaId, Value = Structured(row.GetProperty("arguments")) };
            var original = arguments.Clone();
            var (request, fault) = adapter.Decode(arguments, meta, context);
            Require(request is not null && fault is null, id + ": decodes (" + fault + ")");
            Require(arguments.Equals(original), id + ": the structured input is not modified");
            var expectedJson = JsonNode.Parse(row.GetProperty("request").GetRawText())!.AsObject();
            expectedJson["meta"] = JsonNode.Parse(data.GetProperty("meta").GetRawText());
            var expected = adapter.ParseRequest(expectedJson.ToJsonString());
            Require(request!.Equals(expected), id + ": the decoded typed request equals the independent expectation");
            var boundMeta = request.Descriptor.FindFieldByName("meta").Accessor.GetValue(request);
            Require(boundMeta is not null && !ReferenceEquals(boundMeta, meta) && boundMeta.Equals(meta), id + ": the caller meta is bound as a copy");
            var (again, encodeFault) = adapter.EncodeArguments(request);
            Require(again is not null && encodeFault is null && again.SchemaId == adapter.RequestSchemaId && again.Value.Equals(arguments.Value),
                id + ": the argument encoder reproduces the canonical structured form");
            seen.Add(adapter.OperationId);
            count++;
        }
        Require(seen.SetEquals(byId.Keys), "CON.43: every operation decodes at least one vector");
        return count;
    }

    private static int Refusals(JsonElement data, Dictionary<string, Adapter> byId, F.RequestMeta meta, P.LocalCallContext context)
    {
        var count = 0;
        var kinds = new HashSet<D.LocalOperationFaultKind>();
        foreach (var row in data.GetProperty("refuse").EnumerateArray())
        {
            var id = row.GetProperty("id").GetString()!;
            var adapter = byId[row.GetProperty("operation").GetString()!];
            var argumentsJson = row.GetProperty("arguments");
            var arguments = argumentsJson.ValueKind == JsonValueKind.Null ? null : new U.CapabilityArguments
            {
                SchemaId = row.TryGetProperty("schemaId", out var schemaId) ? schemaId.GetString()! : adapter.RequestSchemaId,
                Value = Structured(argumentsJson),
            };
            var original = arguments?.Clone();
            var callMeta = meta.Clone();
            if (row.TryGetProperty("meta", out var metaMode))
            {
                if (metaMode.ValueKind == JsonValueKind.False) callMeta = null;
                else if (metaMode.GetString() == "noExpectedNative") callMeta.ExpectedNative = null;
                else throw new InvalidOperationException(id + ": unknown meta mode");
            }
            var callContext = context.Clone();
            if (row.TryGetProperty("context", out var contextMode))
            {
                if (contextMode.GetString() == "none") callContext = null;
                else if (contextMode.GetString() == "noActor") callContext.Actor = null;
                else throw new InvalidOperationException(id + ": unknown context mode");
            }
            var (request, fault) = adapter.Decode(arguments, callMeta, callContext);
            var kind = Enum.Parse<D.LocalOperationFaultKind>(row.GetProperty("kind").GetString()!);
            Require(request is null && fault is not null, id + ": refused before any owner code");
            Require(fault!.Kind == kind && fault.Path == row.GetProperty("path").GetString(), id + ": typed fault " + kind + " at '"
                + row.GetProperty("path").GetString() + "', got " + fault);
            Require(original is null || arguments!.Equals(original), id + ": nothing is partially applied to the input");
            ArcErrorOf(fault, id);
            kinds.Add(kind);
            count++;
        }
        foreach (var required in new[] { D.LocalOperationFaultKind.UnknownField, D.LocalOperationFaultKind.MissingRequired, D.LocalOperationFaultKind.OutOfRange,
            D.LocalOperationFaultKind.TooManyItems, D.LocalOperationFaultKind.TooDeep, D.LocalOperationFaultKind.ExplicitNull, D.LocalOperationFaultKind.WrongKind,
            D.LocalOperationFaultKind.InvalidIdentity, D.LocalOperationFaultKind.InvalidEnum, D.LocalOperationFaultKind.InvalidBytes,
            D.LocalOperationFaultKind.OneofConflict, D.LocalOperationFaultKind.SchemaMismatch, D.LocalOperationFaultKind.InvalidEnvelope,
            D.LocalOperationFaultKind.MissingMeta, D.LocalOperationFaultKind.MissingContext, D.LocalOperationFaultKind.MissingActor,
            D.LocalOperationFaultKind.ShapeInvalid })
        {
            Require(kinds.Contains(required), "CON.43: the refusal vectors cover " + required);
        }
        return count;
    }

    private static int ResultVectors(JsonElement data, Dictionary<string, Adapter> byId)
    {
        var count = 0;
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var row in data.GetProperty("results").EnumerateArray())
        {
            var id = row.GetProperty("id").GetString()!;
            var adapter = byId[row.GetProperty("operation").GetString()!];
            var value = adapter.ParseValue(row.GetProperty("value").GetRawText());
            var (result, fault) = adapter.EncodeResult(value);
            Require(result is not null && fault is null, id + ": encodes (" + fault + ")");
            Require(result!.SchemaId == adapter.ResultSchemaId && PlatformShape.IsValid(result), id + ": a valid structured result");
            Require(result.Value.Equals(Structured(row.GetProperty("result"))), id + ": the encoded result equals the independent expectation");
            var (back, decodeFault) = adapter.DecodeResult(result);
            Require(back is not null && decodeFault is null && back.Equals(value), id + ": the result decodes back to the typed value");
            var mismatched = new U.CapabilityResult { SchemaId = adapter.RequestSchemaId, Value = result.Value.Clone() };
            var (none, mismatch) = adapter.DecodeResult(mismatched);
            Require(none is null && mismatch?.Kind == D.LocalOperationFaultKind.SchemaMismatch, id + ": a result under another schema ID is refused");
            seen.Add(adapter.OperationId);
            count++;
        }
        Require(seen.SetEquals(byId.Keys), "CON.43: every operation encodes at least one result");
        return count;
    }

    private static int EncodeRefusals(JsonElement data, Dictionary<string, Adapter> byId)
    {
        var count = 0;
        foreach (var row in data.GetProperty("encodeRefuse").EnumerateArray())
        {
            var id = row.GetProperty("id").GetString()!;
            var adapter = byId[row.GetProperty("operation").GetString()!];
            var (result, fault) = adapter.EncodeResult(adapter.ParseValue(row.GetProperty("value").GetRawText()));
            var kind = Enum.Parse<D.LocalOperationFaultKind>(row.GetProperty("kind").GetString()!);
            Require(result is null && fault is not null && fault.Kind == kind && fault.Path == row.GetProperty("path").GetString(),
                id + ": encode refused as " + kind + " at '" + row.GetProperty("path").GetString() + "', got " + fault);
            ArcErrorOf(fault!, id);
            count++;
        }
        return count;
    }

    private static void Guards(F.RequestMeta meta, P.LocalCallContext context)
    {
        foreach (var adapter in Adapters)
        {
            Require(adapter.EncodeResult(null).Fault?.Kind == D.LocalOperationFaultKind.ShapeInvalid, adapter.OperationId + ": a null result is refused");
            Require(adapter.DecodeResult(null).Fault?.Kind == D.LocalOperationFaultKind.InvalidEnvelope, adapter.OperationId + ": a null structured result is refused");
            Require(adapter.EncodeArguments(null).Fault?.Kind == D.LocalOperationFaultKind.ShapeInvalid, adapter.OperationId + ": a null request is refused");
            var empty = new U.CapabilityArguments { SchemaId = adapter.RequestSchemaId };
            Require(adapter.Decode(empty, meta, context).Fault?.Kind == D.LocalOperationFaultKind.InvalidEnvelope, adapter.OperationId + ": arguments without a value are refused");
            foreach (var other in Adapters.Where(other => other != adapter))
            {
                var foreign = new U.CapabilityArguments { SchemaId = other.RequestSchemaId, Value = new U.StructuredValue { Record = new U.ValueRecord() } };
                Require(adapter.Decode(foreign, meta, context).Fault?.Kind == D.LocalOperationFaultKind.SchemaMismatch,
                    adapter.OperationId + ": arguments of " + other.OperationId + " are refused");
            }
        }
        Require(Throws(() => new D.LocalOperationFault(D.LocalOperationFaultKind.Unspecified, "")), "CON.43: a fault needs a kind");
        Require(Throws(() => new D.LocalOperationFault(D.LocalOperationFaultKind.UnknownField, null!)), "CON.43: a fault needs a path");
        Require(Throws(() => new D.LocalOperationFault(D.LocalOperationFaultKind.UnknownField, "").ToArcError(null!)), "CON.43: an error needs a correlation ID");
    }

    private static void ArcErrorOf(D.LocalOperationFault fault, string id)
    {
        var correlation = new F.Id { Value = ByteString.CopyFrom([0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80, 0x90, 0xa0, 0xb0, 0xc0, 0xd0, 0xe0, 0xf0, 0x77]) };
        var error = fault.ToArcError(correlation);
        Require(PlatformShape.IsValid(error) && error.Code == "validation.invalid_request" && error.MessageKey == "validation.invalid_request"
            && error.Category == F.ErrorCategory.Validation && error.Effect == F.EffectCertainty.DidNotHappen && error.Retry.Mode == F.RetryMode.Never
            && error.CorrelationId.Equals(correlation) && !ReferenceEquals(error.CorrelationId, correlation), id + ": validation.invalid_request, did not happen, no retry");
    }

    /// <summary>The fixture's compact structured notation, read independently of the generated codecs.</summary>
    private static U.StructuredValue Structured(JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Null:
                return new U.StructuredValue { Null = true };
            case JsonValueKind.True:
            case JsonValueKind.False:
                return new U.StructuredValue { Boolean = value.GetBoolean() };
            case JsonValueKind.String:
                return new U.StructuredValue { Text = value.GetString()! };
            case JsonValueKind.Number:
                return new U.StructuredValue { Integer = value.GetInt64() };
            case JsonValueKind.Array:
                var list = new U.ValueList();
                foreach (var item in value.EnumerateArray()) list.Items.Add(Structured(item));
                return new U.StructuredValue { List = list };
            case JsonValueKind.Object:
                var properties = value.EnumerateObject().ToArray();
                if (properties.Length == 1 && properties[0].Name.StartsWith('$'))
                {
                    var inner = properties[0].Value;
                    return properties[0].Name switch
                    {
                        "$number" => new U.StructuredValue { Number = inner.GetDouble() },
                        "$instant" => new U.StructuredValue { Instant = JsonParser.Default.Parse<F.Instant>(inner.GetRawText()) },
                        "$decimal" => new U.StructuredValue { Decimal = new F.Decimal { Value = inner.GetString()! } },
                        "$resource" => new U.StructuredValue { Resource = JsonParser.Default.Parse<F.ResourceRef>(inner.GetRawText()) },
                        "$value" => JsonParser.Default.Parse<U.StructuredValue>(inner.GetRawText()),
                        "$record" => new U.StructuredValue { Record = Record(inner.EnumerateArray().Select(pair => (pair[0].GetString()!, pair[1]))) },
                        _ => throw new InvalidOperationException("Unknown fixture notation " + properties[0].Name),
                    };
                }
                return new U.StructuredValue { Record = Record(properties.Select(property => (property.Name, property.Value))) };
            default:
                throw new InvalidOperationException("Unsupported fixture value");
        }
    }

    private static U.ValueRecord Record(IEnumerable<(string Name, JsonElement Value)> entries)
    {
        var record = new U.ValueRecord();
        foreach (var (name, value) in entries) record.Entries.Add(new U.ValueEntry { Name = name, Value = Structured(value) });
        return record;
    }

    private static bool Throws(Action action)
    {
        try
        {
            action();
            return false;
        }
        catch (ArgumentException)
        {
            return true;
        }
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
