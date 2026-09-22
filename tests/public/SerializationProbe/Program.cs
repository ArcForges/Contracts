// SPDX-License-Identifier: Apache-2.0
// WP03.02 Native AOT probe: executes fixtures/public/wp03-02.json against the generated contract closure.
using System.Text.Json;
using System.Text.Json.Nodes;
using ArcForges.Contracts.CloudInternal.Http.V1;
using ArcForges.Contracts.Foundation.Serialization;
using ArcForges.Contracts.Validation;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using Grpc.Core;

var root = args.Length >= 1 ? Path.GetFullPath(args[0]) : Directory.GetCurrentDirectory();
var report = args.Length >= 3 && args[1] == "--report" ? Path.GetFullPath(args[2]) : null;
using var fixture = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/public/wp03-02.json")));
var failures = new List<string>();
var counts = new Dictionary<string, int>(StringComparer.Ordinal);

void Require(bool condition, string message)
{
    if (!condition) failures.Add(message);
}

void Count(string key) => counts[key] = counts.GetValueOrDefault(key) + 1;

// Limits are the registry constants, compared with the independent fixture.
var limits = fixture.RootElement.GetProperty("limits");
Require(WireLimits.UnaryMessageBytes == limits.GetProperty("unaryMessage").GetInt32(), "unary limit");
Require(WireLimits.HelperMessageBytes == limits.GetProperty("helperMessage").GetInt32(), "helper limit");
Require(WireLimits.InlinePageBytes == limits.GetProperty("inlinePage").GetInt32(), "inline page limit");
Require(WireLimits.StreamFrameBytes == limits.GetProperty("streamFrame").GetInt32(), "stream frame limit");
Require(WireLimits.LargeProjectionBytes == limits.GetProperty("largeProjection").GetInt32(), "large projection limit");
Require(WireLimits.NestedMessageLevels == limits.GetProperty("nestedMessageLevels").GetInt32(), "nesting limit");

foreach (var item in fixture.RootElement.GetProperty("binary").EnumerateArray())
{
    var construct = item.GetProperty("construct");
    var target = construct.GetProperty("target").GetString();
    var outcome = target switch
    {
        "arcforges.foundation.v1.Id" => Binary.Run(ArcForges.Contracts.Foundation.V1.Id.Parser, item),
        "arcforges.foundation.v1.ArcError" => Binary.Run(ArcForges.Contracts.Foundation.V1.ArcError.Parser, item),
        "arcforges.publicapi.v1.NotesFilter" => Binary.Run(ArcForges.Contracts.PublicApi.V1.NotesFilter.Parser, item),
        _ => "unknown target " + target,
    };
    Require(outcome.Length == 0, "binary " + item.GetProperty("id").GetString() + ": " + outcome);
    Count("binary");
}

foreach (var item in fixture.RootElement.GetProperty("json").EnumerateArray())
{
    var bytes = Json.Bytes(item);
    var outcome = item.GetProperty("schema").GetString() switch
    {
        "PartReceipt" => Json.Run<ArcForges.Contracts.PublicApi.Http.V1.PartReceipt>(bytes, item, PartReceiptJson.TryParse, PartReceiptJson.Serialize),
        "CommitReceipt" => Json.Run<CommitReceipt>(bytes, item, CommitReceiptJson.TryParse, CommitReceiptJson.Serialize),
        "PackageInventory" => Json.Run<ArcForges.Sdk.Contracts.Inventory.V1.PackageInventory>(bytes, item, PackageInventoryJson.TryParse, PackageInventoryJson.Serialize),
        var schema => "unknown schema " + schema,
    };
    Require(outcome.Length == 0, "json " + item.GetProperty("id").GetString() + ": " + outcome);
    Count("json");
}

// Explicit catalogues and binding: generated BindService methods register exactly the authored methods.
var services = fixture.RootElement.GetProperty("services");
var catalogues = new Dictionary<string, IReadOnlyList<ServiceDescriptor>>(StringComparer.Ordinal)
{
    ["ArcForges.Contracts.PublicApi"] = ArcForges.Contracts.PublicApi.ContractServices.All,
    ["ArcForges.Sdk.Contracts"] = ArcForges.Sdk.Contracts.ContractServices.All,
};
foreach (var package in services.GetProperty("csharp").EnumerateObject())
{
    var expected = package.Value.EnumerateArray().Select(value => value.GetString()!).ToArray();
    Require(catalogues.TryGetValue(package.Name, out var catalogue)
        && catalogue.Select(service => service.FullName).SequenceEqual(expected), "catalogue " + package.Name);
    Count("catalogue");
}
var binder = new RecordingBinder();
ArcForges.Contracts.Hello.V1.HelloService.BindService(binder, new HelloEndpoint());
ArcForges.Sdk.Contracts.V1.ExtensionHostService.BindService(binder, new ExtensionEndpoint());
var expectedMethods = services.GetProperty("methods").EnumerateObject()
    .SelectMany(service => service.Value.EnumerateArray().Select(value => value.GetString()!)).ToArray();
Require(binder.Methods.SequenceEqual(expectedMethods), "bound methods " + string.Join(",", binder.Methods));

// Every generated message parser in every library is reachable and round-trips under Native AOT.
FileDescriptor[] files =
[
    ArcForges.Contracts.Foundation.V1.FoundationReflection.Descriptor,
    ArcForges.Contracts.Hello.V1.HelloReflection.Descriptor,
    ArcForges.Contracts.PublicApi.V1.ContentReflection.Descriptor,
    ArcForges.Contracts.Events.V1.EventsReflection.Descriptor,
    ArcForges.Sdk.Contracts.V1.ExtensionsReflection.Descriptor,
    ArcForges.Contracts.LocalRpc.Platform.V1.PlatformReflection.Descriptor,
    ArcForges.Contracts.LocalRpc.Sandbox.V1.SandboxReflection.Descriptor,
    ArcForges.Contracts.LocalRpc.Chat.V1.ChatReflection.Descriptor,
    ArcForges.Contracts.LocalRpc.Notes.V1.NotesReflection.Descriptor,
    ArcForges.Contracts.LocalRpc.Scope.V1.ScopeReflection.Descriptor,
    ArcForges.Contracts.LocalRpc.Slate.V1.SlateReflection.Descriptor,
    ArcForges.Contracts.CloudInternal.Operator.V1.OperatorReflection.Descriptor,
];
var serviceCount = 0;
foreach (var file in files)
{
    serviceCount += file.Services.Count;
    var pending = new Stack<MessageDescriptor>(file.MessageTypes);
    while (pending.TryPop(out var message))
    {
        foreach (var nested in message.NestedTypes) pending.Push(nested);
        if (message.Parser is null) continue; // map entry descriptors have no generated message class
        var parsed = message.Parser.ParseFrom(ReadOnlySpan<byte>.Empty);
        Require(parsed.CalculateSize() == 0 && parsed.ToByteArray().Length == 0, "empty round trip " + message.FullName);
        Count("messages");
    }
}
Require(serviceCount == catalogues.Values.Sum(catalogue => catalogue.Count), "descriptor services differ from catalogues");
Require(counts.GetValueOrDefault("messages") > 0, "no generated messages were exercised");

// Reflection-based System.Text.Json is disabled in this published artifact.
Require(!JsonSerializer.IsReflectionEnabledByDefault, "reflection-based JSON serialization is enabled");

var result = failures.Count == 0 ? "passed" : "failed";
if (report is not null)
{
    Directory.CreateDirectory(Path.GetDirectoryName(report)!);
    using var stream = File.Create(report);
    using var writer = new Utf8JsonWriter(stream, new JsonWriterOptions { Indented = true });
    writer.WriteStartObject();
    writer.WriteString("schemaVersion", "wp03-02-serialization-probe.v1");
    writer.WriteString("result", result);
    writer.WriteString("runtimeIdentifier", System.Runtime.InteropServices.RuntimeInformation.RuntimeIdentifier);
    writer.WriteBoolean("nativeAot", !System.Runtime.CompilerServices.RuntimeFeature.IsDynamicCodeSupported);
    foreach (var (key, value) in counts.OrderBy(pair => pair.Key, StringComparer.Ordinal)) writer.WriteNumber(key, value);
    writer.WriteNumber("boundMethods", binder.Methods.Count);
    writer.WriteStartArray("failures");
    foreach (var failure in failures) writer.WriteStringValue(failure);
    writer.WriteEndArray();
    writer.WriteEndObject();
}
foreach (var failure in failures) Console.Error.WriteLine(failure);
Console.WriteLine($"Serialization probe {result}: {counts.GetValueOrDefault("binary")} binary, {counts.GetValueOrDefault("json")} JSON, "
    + $"{counts.GetValueOrDefault("messages")} messages, {binder.Methods.Count} bound methods; dynamic code supported: "
    + System.Runtime.CompilerServices.RuntimeFeature.IsDynamicCodeSupported + ".");
return failures.Count == 0 ? 0 : 1;

internal static class Binary
{
    private static readonly Dictionary<string, WireLimit> Limits = new(StringComparer.Ordinal)
    {
        ["unaryMessage"] = WireLimit.UnaryMessage,
        ["helperMessage"] = WireLimit.HelperMessage,
        ["inlinePage"] = WireLimit.InlinePage,
        ["streamFrame"] = WireLimit.StreamFrame,
        ["largeProjection"] = WireLimit.LargeProjection,
    };

    public static string Run<T>(MessageParser<T> parser, JsonElement item) where T : IMessage<T>
    {
        var bytes = Construct(item.GetProperty("construct"));
        var limit = Limits[item.GetProperty("limit").GetString()!];
        var expected = item.GetProperty("expect").GetString();
        string actual;
        byte[]? encoded = null;
        if (item.GetProperty("operation").GetString() == "encode")
        {
            var message = ContractWire.Decode(parser, bytes, WireLimit.LargeProjection);
            try
            {
                encoded = ContractWire.Encode(message, limit);
                actual = "accept";
            }
            catch (ContractSerializationException error)
            {
                actual = Name(error.Failure);
            }
        }
        else
        {
            actual = ContractWire.TryDecode(parser, bytes, limit, out var message, out var failure) ? "accept" : Name(failure);
            if (message is not null) encoded = ContractWire.Encode(message, WireLimit.LargeProjection);
        }
        if (actual != expected) return $"expected {expected}, got {actual}";
        if (encoded is null) return "";
        if (!encoded.AsSpan().SequenceEqual(bytes)) return "re-encoding lost or reordered bytes";
        if (item.TryGetProperty("reencodeHex", out var hex) && Convert.ToHexStringLower(encoded) != hex.GetString()) return "re-encoding differs";
        return "";
    }

    public static string Name(ContractSerializationFailure failure) => failure switch
    {
        ContractSerializationFailure.TooLarge => "tooLarge",
        ContractSerializationFailure.TooDeep => "tooDeep",
        ContractSerializationFailure.Malformed => "malformed",
        ContractSerializationFailure.Invalid => "invalid",
        _ => "unknown",
    };

    private static byte[] Construct(JsonElement construct)
    {
        switch (construct.GetProperty("kind").GetString())
        {
            case "hex":
                return Convert.FromHexString(construct.GetProperty("hex").GetString()!);
            case "filler":
                var total = construct.GetProperty("totalBytes").GetInt32();
                var tag = Varint(15999 * 8 + 2).Length;
                for (var width = 1; width <= 5; width++)
                {
                    var length = total - tag - width;
                    if (length >= 0 && Varint((ulong)length).Length == width) return Delimited(15999, new byte[length]);
                }
                throw new InvalidOperationException("No exact filler length.");
            case "nested":
                var fields = construct.GetProperty("fields").EnumerateArray().Select(field => field.GetInt32()).ToArray();
                var inner = Array.Empty<byte>();
                for (var level = construct.GetProperty("levels").GetInt32(); level >= 1; level--)
                    inner = Delimited(fields[(level - 1) % fields.Length], inner);
                return inner;
            default:
                throw new InvalidOperationException("Unknown construction.");
        }
    }

    private static byte[] Varint(ulong value)
    {
        var output = new List<byte>();
        do
        {
            var low = (byte)(value & 0x7f);
            value >>= 7;
            output.Add(value > 0 ? (byte)(low | 0x80) : low);
        } while (value > 0);
        return [.. output];
    }

    private static byte[] Delimited(int field, byte[] payload) =>
        [.. Varint((ulong)field * 8 + 2), .. Varint((ulong)payload.Length), .. payload];
}

internal delegate bool TryParseJson<T>(ReadOnlyMemory<byte> utf8, out T? value, out ContractSerializationFailure failure);

internal static class Json
{
    public static byte[] Bytes(JsonElement item)
    {
        if (item.TryGetProperty("hex", out var hex)) return Convert.FromHexString(hex.GetString()!);
        if (item.TryGetProperty("construct", out var construct))
        {
            var text = System.Text.Encoding.UTF8.GetBytes(construct.GetProperty("base").GetString()!);
            var output = new byte[construct.GetProperty("totalBytes").GetInt32()];
            output.AsSpan().Fill((byte)' ');
            text.CopyTo(output, 0);
            return output;
        }
        return System.Text.Encoding.UTF8.GetBytes(item.GetProperty("text").GetString()!);
    }

    public static string Run<T>(byte[] bytes, JsonElement item, TryParseJson<T> tryParse, Func<T, byte[]> serialize) where T : class
    {
        var expected = item.GetProperty("expect").GetString();
        var actual = tryParse(bytes, out var value, out var failure) ? "accept" : Binary.Name(failure);
        if (actual != expected) return $"expected {expected}, got {actual}";
        if (value is null) return "";
        var written = serialize(value);
        var canonical = JsonNode.Parse(item.GetProperty("canonical").GetRawText());
        if (!JsonNode.DeepEquals(JsonNode.Parse(written), canonical)) return "canonical value differs";
        if (!tryParse(written, out var again, out _) || !serialize(again!).AsSpan().SequenceEqual(written)) return "output is not stable";
        return "";
    }
}

internal sealed class RecordingBinder : ServiceBinderBase
{
    public List<string> Methods { get; } = [];

    public override void AddMethod<TRequest, TResponse>(Method<TRequest, TResponse> method, UnaryServerMethod<TRequest, TResponse>? handler)
        => Methods.Add(method.FullName);

    public override void AddMethod<TRequest, TResponse>(Method<TRequest, TResponse> method, ClientStreamingServerMethod<TRequest, TResponse>? handler)
        => Methods.Add(method.FullName);

    public override void AddMethod<TRequest, TResponse>(Method<TRequest, TResponse> method, ServerStreamingServerMethod<TRequest, TResponse>? handler)
        => Methods.Add(method.FullName);

    public override void AddMethod<TRequest, TResponse>(Method<TRequest, TResponse> method, DuplexStreamingServerMethod<TRequest, TResponse>? handler)
        => Methods.Add(method.FullName);
}

internal sealed class HelloEndpoint : ArcForges.Contracts.Hello.V1.HelloService.HelloServiceBase;

internal sealed class ExtensionEndpoint : ArcForges.Sdk.Contracts.V1.ExtensionHostService.ExtensionHostServiceBase;
