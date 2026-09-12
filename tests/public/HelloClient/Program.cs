// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using ArcForges.Contracts.Hello.V1;
using Google.Protobuf;
using Grpc.Core;
using Grpc.Net.Client;

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
