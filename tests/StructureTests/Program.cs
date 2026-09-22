// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using System.Text.Json.Nodes;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using Grpc.Core;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Sdk.Contracts.V1;
using Validation = ArcForges.Contracts.Validation.ContractShapeValidation;

var root = args.Length >= 1 ? Path.GetFullPath(args[0]) : Directory.GetCurrentDirectory();
if (args.Contains("--verify-foundation-exchange", StringComparer.Ordinal))
{
    FoundationCases.VerifyExchange(root);
    return 0;
}
var count = 0;
foreach (var visibility in new[] { "public", "internal" })
{
    using var fixture = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures", visibility, "wp03-00.json")));
    foreach (var item in fixture.RootElement.GetProperty("cases").EnumerateArray())
    {
        var actual = Check(item.GetProperty("target").GetString()!, item.GetProperty("value"));
        if (actual != item.GetProperty("valid").GetBoolean())
        {
            throw new InvalidOperationException("Shape fixture failed: " + item.GetProperty("id").GetString());
        }
        count++;
    }
}

// JsonElement retains duplicate keys: shape validation must reject them before model deserialization.
using (var duplicate = JsonDocument.Parse("""{"schemaVersion":"inventory.v1","schemaVersion":"inventory.v1","files":[]}"""))
{
    if (ArcForges.Contracts.Validation.PackageInventoryJson.IsValid(duplicate.RootElement)) throw new InvalidOperationException("Duplicate JSON property accepted");
}

var invoker = new RecordingInvoker();
var client = new ArcForges.Sdk.Client.ExtensionLeaseClient(invoker);
var id = new Id { Value = ByteString.CopyFrom(Convert.FromHexString("00112233445566778899aabbccddeeff")) };
var request = new ExtensionHostServiceRenewLeaseRequest { Meta = new RequestMeta { CorrelationId = id }, LeaseId = id };
using (var call = client.RenewLeaseAsync(request, new CallOptions(cancellationToken: new CancellationToken(true))))
{
    if (!ReferenceEquals(invoker.Request, request) || !invoker.Options.CancellationToken.IsCancellationRequested || invoker.Method != "/arcforges.extensions.v1.ExtensionHostService/RenewLease")
        throw new InvalidOperationException("SDK wrapper did not preserve caller-owned call arguments");
}
try
{
    using var invalid = client.RenewLeaseAsync(new ExtensionHostServiceRenewLeaseRequest());
    throw new InvalidOperationException("SDK wrapper accepted missing required envelope");
}
catch (ArgumentException) { }

Console.WriteLine($"Validated {count} independent shape fixtures, duplicate-key rejection and SDK caller-owned invocation.");
FoundationCases.Run(root, args.Contains("--foundation-exchange", StringComparer.Ordinal));
return 0;

static bool Proto<T>(JsonElement value, Func<T, bool> validate) where T : IMessage<T>, new()
{
    try
    {
        // Independent wire fixtures use unpadded base64url; Google.JsonParser expects
        // standard padded base64. Only declared byte fields are adapted in this test.
        var input = JsonNode.Parse(value.GetRawText());
        NormalizeFixtureBytes(input, new T().Descriptor);
        return validate(JsonParser.Default.Parse<T>(input!.ToJsonString()));
    }
    catch (InvalidProtocolBufferException) { return false; }
    catch (InvalidJsonException) { return false; }
    catch (FormatException) { return false; }
}

static void NormalizeFixtureBytes(JsonNode? node, MessageDescriptor descriptor)
{
    if (node is not JsonObject record) return;
    foreach (var field in descriptor.Fields.InFieldNumberOrder())
    {
        if (!record.TryGetPropertyValue(field.JsonName, out var value) || value is null) continue;
        if (field.FieldType == FieldType.Bytes)
        {
            if (value is not JsonValue scalar || !scalar.TryGetValue<string>(out var encoded)) continue;
            if (encoded.Any(c => !(c is >= 'A' and <= 'Z' or >= 'a' and <= 'z' or >= '0' and <= '9' or '-' or '_')) || encoded.Length % 4 == 1)
                throw new FormatException("Fixture bytes must be canonical unpadded base64url.");
            var standard = encoded.Replace('-', '+').Replace('_', '/');
            standard = standard.PadRight((standard.Length + 3) / 4 * 4, '=');
            var bytes = Convert.FromBase64String(standard);
            var canonical = Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
            if (canonical != encoded) throw new FormatException("Fixture byte encoding has noncanonical trailing bits.");
            record[field.JsonName] = Convert.ToBase64String(bytes);
        }
        else if (field.FieldType == FieldType.Message)
        {
            if (field.IsRepeated && value is JsonArray values)
            {
                foreach (var item in values) NormalizeFixtureBytes(item, field.MessageType);
            }
            else NormalizeFixtureBytes(value, field.MessageType);
        }
    }
}

static bool Check(string target, JsonElement value) => target switch
{
    "PartReceipt" => ArcForges.Contracts.Validation.PartReceiptJson.IsValid(value),
    "PackageInventory" => ArcForges.Contracts.Validation.PackageInventoryJson.IsValid(value),
    "CommitReceipt" => ArcForges.Contracts.CloudInternal.Http.V1.CommitReceiptJson.IsValid(value),
    "arcforges.foundation.v1.Id" => Proto<Id>(value, Validation.IsValid),
    "arcforges.foundation.v1.Revision" => Proto<Revision>(value, Validation.IsValid),
    "arcforges.foundation.v1.LocalNotesVersion" => Proto<LocalNotesVersion>(value, Validation.IsValid),
    "arcforges.foundation.v1.NativeContentRev" => Proto<NativeContentRev>(value, Validation.IsValid),
    "arcforges.foundation.v1.Instant" => Proto<Instant>(value, Validation.IsValid),
    "arcforges.foundation.v1.Decimal" => Proto<ArcForges.Contracts.Foundation.V1.Decimal>(value, Validation.IsValid),
    "arcforges.foundation.v1.AggregateRef" => Proto<AggregateRef>(value, Validation.IsValid),
    "arcforges.foundation.v1.VersionedRef" => Proto<VersionedRef>(value, Validation.IsValid),
    "arcforges.foundation.v1.Receipt" => Proto<Receipt>(value, Validation.IsValid),
    "arcforges.foundation.v1.ApplicationScope" => Proto<ApplicationScope>(value, Validation.IsValid),
    "arcforges.foundation.v1.RequestMeta" => Proto<RequestMeta>(value, Validation.IsValid),
    "arcforges.foundation.v1.ResponseMeta" => Proto<ResponseMeta>(value, Validation.IsValid),
    "arcforges.foundation.v1.ArcError" => Proto<ArcError>(value, Validation.IsValid),
    "arcforges.foundation.v1.RetryAdvice" => Proto<RetryAdvice>(value, Validation.IsValid),
    "arcforges.foundation.v1.ErrorDetails" => Proto<ErrorDetails>(value, Validation.IsValid),
    "arcforges.foundation.v1.RevisionConflict" => Proto<RevisionConflict>(value, Validation.IsValid),
    "arcforges.foundation.v1.LimitFailure" => Proto<LimitFailure>(value, Validation.IsValid),
    "arcforges.foundation.v1.VersionFailure" => Proto<VersionFailure>(value, Validation.IsValid),
    "arcforges.foundation.v1.StateFailure" => Proto<StateFailure>(value, Validation.IsValid),
    "arcforges.events.v1.EntitlementChanged" => Proto<ArcForges.Contracts.Events.V1.EntitlementChanged>(value, Validation.IsValid),
    "arcforges.extensions.v1.ExtensionLease" => Proto<ExtensionLease>(value, Validation.IsValid),
    "arcforges.extensions.v1.ExtensionHostServiceRenewLeaseRequest" => Proto<ExtensionHostServiceRenewLeaseRequest>(value, Validation.IsValid),
    "arcforges.extensions.v1.ExtensionHostServiceRenewLeaseResponse" => Proto<ExtensionHostServiceRenewLeaseResponse>(value, Validation.IsValid),
    "arcforges.extensions.v1.ExtensionHostServiceRenewLeaseValue" => Proto<ExtensionHostServiceRenewLeaseValue>(value, Validation.IsValid),
    "arcforges.local.platform.v1.LocalChunk" => Proto<ArcForges.Contracts.LocalRpc.Platform.V1.LocalChunk>(value, ArcForges.Contracts.LocalRpc.Platform.Shapes.ContractShapeValidation.IsValid),
    "arcforges.local.sandbox.v1.SandboxLimits" => Proto<ArcForges.Contracts.LocalRpc.Sandbox.V1.SandboxLimits>(value, ArcForges.Contracts.LocalRpc.Sandbox.Shapes.ContractShapeValidation.IsValid),
    "arcforges.local.chat.v1.ChatOperationsServiceOpenArtifactValue" => Proto<ArcForges.Contracts.LocalRpc.Chat.V1.ChatOperationsServiceOpenArtifactValue>(value, ArcForges.Contracts.LocalRpc.Chat.Shapes.ContractShapeValidation.IsValid),
    "arcforges.local.notes.v1.NotesOperationsServiceTrashDocumentValue" => Proto<ArcForges.Contracts.LocalRpc.Notes.V1.NotesOperationsServiceTrashDocumentValue>(value, ArcForges.Contracts.LocalRpc.Notes.Shapes.ContractShapeValidation.IsValid),
    "arcforges.local.scope.v1.ScopeOperationsServiceCreateFindingValue" => Proto<ArcForges.Contracts.LocalRpc.Scope.V1.ScopeOperationsServiceCreateFindingValue>(value, ArcForges.Contracts.LocalRpc.Scope.Shapes.ContractShapeValidation.IsValid),
    "arcforges.local.slate.v1.SlateOperationsServiceApplyTimelineEditsValue" => Proto<ArcForges.Contracts.LocalRpc.Slate.V1.SlateOperationsServiceApplyTimelineEditsValue>(value, ArcForges.Contracts.LocalRpc.Slate.Shapes.ContractShapeValidation.IsValid),
    "arcforges.operator.v1.OperatorCallContext" => Proto<ArcForges.Contracts.CloudInternal.Operator.V1.OperatorCallContext>(value, ArcForges.Contracts.CloudInternal.Shapes.ContractShapeValidation.IsValid),
    _ => throw new InvalidOperationException("No explicit fixture dispatch for " + target),
};

sealed class RecordingInvoker : CallInvoker
{
    public object? Request { get; private set; }
    public CallOptions Options { get; private set; }
    public string? Method { get; private set; }

    public override AsyncUnaryCall<TResponse> AsyncUnaryCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options, TRequest request)
    {
        Request = request;
        Options = options;
        Method = method.FullName;
        return new AsyncUnaryCall<TResponse>(Task.FromResult((TResponse)(object)new ExtensionHostServiceRenewLeaseResponse()), Task.FromResult(new Metadata()), () => Status.DefaultSuccess, () => new Metadata(), () => { });
    }
    public override TResponse BlockingUnaryCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options, TRequest request) => throw new NotSupportedException();
    public override AsyncServerStreamingCall<TResponse> AsyncServerStreamingCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options, TRequest request) => throw new NotSupportedException();
    public override AsyncClientStreamingCall<TRequest, TResponse> AsyncClientStreamingCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options) => throw new NotSupportedException();
    public override AsyncDuplexStreamingCall<TRequest, TResponse> AsyncDuplexStreamingCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options) => throw new NotSupportedException();
}
