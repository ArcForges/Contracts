// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using ArcForges.Contracts.Hello.V1;
using Google.Protobuf;
using Grpc.Core;
using Grpc.Net.Client;

if (args.Length >= 3 && args[0] == "--inspect-build")
{
    using var expected = JsonDocument.Parse(File.ReadAllText(args[1]));
    foreach (var path in args.Skip(2))
    {
        using var stream = File.OpenRead(path);
        using var pe = new PEReader(stream);
        var reader = pe.GetMetadataReader();
        var values = new Dictionary<string, string>();
        foreach (var handle in reader.GetAssemblyDefinition().GetCustomAttributes())
        {
            var attribute = reader.GetCustomAttribute(handle);
            if (attribute.Constructor.Kind != HandleKind.MemberReference) continue;
            var reference = reader.GetMemberReference((MemberReferenceHandle)attribute.Constructor);
            if (reference.Parent.Kind != HandleKind.TypeReference) continue;
            var type = reader.GetTypeReference((TypeReferenceHandle)reference.Parent);
            if (reader.GetString(type.Namespace) != "System.Reflection" || reader.GetString(type.Name) != "AssemblyMetadataAttribute") continue;
            var blob = reader.GetBlobReader(attribute.Value);
            if (blob.ReadUInt16() != 1) throw new InvalidOperationException("Invalid attribute encoding");
            values.Add(blob.ReadSerializedString()!, blob.ReadSerializedString()!);
        }
        VerifyMetadata(values, expected.RootElement);
    }
    Console.WriteLine("Every owner-authored assembly contains the expected compiled build identity.");
    return;
}

var expectedBuild = Environment.GetEnvironmentVariable("ARCFORGES_EXPECTED_BUILD");
if (expectedBuild is not null)
{
    using var expected = JsonDocument.Parse(File.ReadAllText(expectedBuild));
    var values = typeof(SayHelloRequest).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
        .ToDictionary(item => item.Key, item => item.Value!);
    VerifyMetadata(values, expected.RootElement);
    Console.WriteLine("Published C# assembly build identity verified.");
}

if (args.Length != 2)
{
    throw new ArgumentException("Usage: HelloClient <gRPC URL> <hello.json>");
}

using var fixture = JsonDocument.Parse(File.ReadAllText(args[1]));
using var channel = GrpcChannel.ForAddress(args[0]);
var client = new HelloService.HelloServiceClient(channel);
foreach (var item in fixture.RootElement.GetProperty("cases").EnumerateArray())
{
    var name = item.GetProperty("name").GetString()!;
    var expected = item.GetProperty("message").GetString()!;
    var request = new SayHelloRequest { Name = name };
    var decoded = SayHelloRequest.Parser.ParseFrom(request.ToByteArray());
    if (decoded.Name != name) throw new InvalidOperationException("protobuf roundtrip failed");
    var reply = await client.SayHelloAsync(decoded, deadline: DateTime.UtcNow.AddSeconds(5));
    if (reply.Message != expected) throw new InvalidOperationException("gRPC reply mismatch");
}

try
{
    await client.SayHelloAsync(new SayHelloRequest(), deadline: DateTime.UtcNow.AddSeconds(5));
    throw new InvalidOperationException("Empty name must fail");
}
catch (RpcException error) when (error.StatusCode == StatusCode.InvalidArgument)
{
    Console.WriteLine("C# protobuf and real gRPC success/error checks passed.");
}

static void VerifyMetadata(Dictionary<string, string> actual, JsonElement expected)
{
    foreach (var (key, field) in new[] { ("SourceCommit", "sourceCommit"), ("SourceDateEpoch", "sourceDateEpoch"),
        ("BuildId", "buildId"), ("BuildKind", "kind"), ("PipelineRun", "pipelineRun") })
    {
        var element = expected.GetProperty(field);
        var value = element.ValueKind == JsonValueKind.Null ? "local" : element.ToString();
        if (!actual.TryGetValue("ArcForges." + key, out var found) || found != value)
            throw new InvalidOperationException("Compiled assembly build identity mismatch: " + key);
    }
}
