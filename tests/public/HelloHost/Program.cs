// SPDX-License-Identifier: Apache-2.0
using System.Net;
using ArcForges.Contracts.Hello.V1;
using Grpc.Core;
using Microsoft.AspNetCore.Server.Kestrel.Core;

var builder = WebApplication.CreateBuilder(args);
var grpcPort = int.Parse(builder.Configuration["grpc-port"] ?? "50051",
    System.Globalization.CultureInfo.InvariantCulture);
var webPort = int.Parse(builder.Configuration["web-port"] ?? "50052",
    System.Globalization.CultureInfo.InvariantCulture);
builder.WebHost.ConfigureKestrel(options =>
{
    options.Listen(IPAddress.Loopback, grpcPort, listen => listen.Protocols = HttpProtocols.Http2);
    options.Listen(IPAddress.Loopback, webPort, listen => listen.Protocols = HttpProtocols.Http1);
});
builder.Services.AddGrpc();
var app = builder.Build();
app.UseGrpcWeb();
app.MapGrpcService<HelloEndpoint>().EnableGrpcWeb();
await app.RunAsync();

internal sealed class HelloEndpoint : HelloService.HelloServiceBase
{
    public override Task<SayHelloResponse> SayHello(SayHelloRequest request, ServerCallContext context)
    {
        if (request.Name.Length == 0)
        {
            throw new RpcException(new Status(StatusCode.InvalidArgument, "name must not be empty"));
        }

        return Task.FromResult(new SayHelloResponse { Message = $"Hello, {request.Name}!" });
    }
}
