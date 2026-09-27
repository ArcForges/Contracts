// SPDX-License-Identifier: Apache-2.0
using Google.Protobuf;
using Google.Protobuf.Reflection;
using F = ArcForges.Contracts.Foundation.V1;
using E = ArcForges.Sdk.Contracts.V1;
using P = ArcForges.Contracts.LocalRpc.Platform.V1;
using PublicShape = ArcForges.Contracts.Validation.ContractShapeValidation;
using LocalShape = ArcForges.Contracts.LocalRpc.Platform.Shapes.ContractShapeValidation;

internal static class Con05Cases
{
    public static void Run()
    {
        VerifyService(E.ExtensionsReflection.Descriptor, "ExtensionHostService", ["Handshake", "Invoke", "RenewLease", "Stop"]);
        VerifyService(P.PlatformReflection.Descriptor, "LocalBootstrapService", ["Challenge", "Confirm", "Renew"]);
        VerifyService(P.PlatformReflection.Descriptor, "ConnectorBrokerService", ["ListDefinitions", "ListConnections", "BeginConnection", "CompleteConnection", "GetConnection", "RevokeConnection"]);
        Require(E.Invocation.Descriptor.FindFieldByNumber(8).ContainingOneof == E.Invocation.Descriptor.FindFieldByNumber(10).ContainingOneof, "Invocation preconditions must be exclusive.");
        Require(E.Invocation.Descriptor.FindFieldByNumber(9) is null, "Retired expectedLocal tag must remain absent.");
        var proof = new P.ConnectorProof { CallbackReceipt = "receipt" };
        Require(LocalShape.IsValid(proof), "A typed callback receipt is admitted.");
        Require(!LocalShape.IsValid(new P.ConnectorProof()), "A proof branch is required.");
        proof.CallbackReceipt = "";
        Require(!LocalShape.IsValid(proof), "An empty proof is refused.");
        proof.PersonalToken = new string('x', 8192);
        Require(LocalShape.IsValid(proof), "SecretText permits its exact 8192-byte boundary.");
        proof.PersonalToken = new string('x', 8193);
        Require(!LocalShape.IsValid(proof), "An oversized token is refused.");
        proof.PersonalToken = "fixture-token";
        Require(proof.ProofCase == P.ConnectorProof.ProofOneofCase.PersonalToken && proof.CallbackReceipt == "", "Proof is a generated exclusive oneof.");
        var confirm = new P.LocalBootstrapServiceConfirmRequest { Meta = Meta(), ChallengeId = Id(), Proof = ByteString.CopyFrom(new byte[32]) };
        Require(LocalShape.IsValid(confirm), "A complete confirm shape is valid; cryptographic authorization is separate.");
        var binary = confirm.ToByteArray();
        Require(confirm.Equals(P.LocalBootstrapServiceConfirmRequest.Parser.ParseFrom(binary)), "Confirm generated wire round trip.");
        confirm.Proof = ByteString.CopyFrom(new byte[31]);
        Require(!LocalShape.IsValid(confirm), "A short HMAC is refused.");
        confirm.Proof = ByteString.CopyFrom(new byte[32]);
        confirm.ChallengeId = null;
        Require(!LocalShape.IsValid(confirm), "Missing challenge identity refuses.");
        var handshake = new E.ExtensionHostServiceHandshakeRequest { Meta = Meta(), PackageId = "fixture.extension", PackageVersion = "1.0.0", InstallationId = Id(), Nonce = ByteString.CopyFrom(new byte[32]) };
        handshake.ProtocolVersions.Add("1");
        Require(PublicShape.IsValid(handshake), "A complete extension handshake shape is valid.");
        handshake.ProtocolVersions.Add("1");
        Require(!PublicShape.IsValid(handshake), "Duplicate offered protocol versions refuse.");
        handshake.ProtocolVersions.RemoveAt(1);
        handshake.Nonce = ByteString.Empty;
        Require(!PublicShape.IsValid(handshake), "Absent peer nonce refuses.");
        var connection = new P.ConnectorConnection { ConnectionId = Id(), DefinitionId = "fixture.connector", Name = "Fixture", State = "connected", Revision = new F.Revision { Value = 1 } };
        Require(LocalShape.IsValid(connection), "Canonical connector state is admitted.");
        connection.Name = string.Concat(Enumerable.Repeat("😀", 256));
        Require(LocalShape.IsValid(connection), "Name uses Unicode scalars rather than UTF8 bytes or UTF16 units.");
        connection.Name += "a";
        Require(!LocalShape.IsValid(connection), "Name over 256 scalars refuses.");
        connection.Name = "Fixture";
        connection.State = "unknown-future-state";
        Require(!LocalShape.IsValid(connection), "Unknown mutation state is refused.");
        Require(!LocalShape.IsValid(new P.LocalBootstrapServiceConfirmResponse { Meta = new F.ResponseMeta { CorrelationId = Id() } }), "A response cannot silently omit outcome.");
        Console.WriteLine("CON.05 generated method/envelope/oneof/shape and protobuf round-trip cases passed; no runtime authorization evidence.");
    }

    private static void VerifyService(FileDescriptor file, string name, string[] methods)
    {
        var service = file.Services.Single(item => item.Name == name);
        Require(service.Methods.Select(item => item.Name).SequenceEqual(methods), "Registry service method inventory: " + name);
        foreach (var method in service.Methods)
        {
            Require(!method.IsClientStreaming && !method.IsServerStreaming, "Helper methods are bounded unary.");
            Require(method.InputType.FindFieldByNumber(1).MessageType.FullName == "arcforges.foundation.v1.RequestMeta", "RequestMeta tag 1.");
            Require(method.OutputType.FindFieldByNumber(1).MessageType.FullName == "arcforges.foundation.v1.ResponseMeta", "ResponseMeta tag 1.");
            Require(method.OutputType.FindFieldByNumber(2).ContainingOneof.Name == "outcome" && method.OutputType.FindFieldByNumber(3).ContainingOneof.Name == "outcome", "Typed value/error outcome tags.");
            Require(method.OutputType.FindFieldByNumber(3).MessageType.FullName == "arcforges.foundation.v1.ArcError", "Typed error field.");
            for (int tag = 2; tag <= 9; tag++) Require(method.InputType.FindFieldByNumber(tag) is null, "Request reserved envelope tag.");
            for (int tag = 4; tag <= 9; tag++) Require(method.OutputType.FindFieldByNumber(tag) is null, "Response reserved envelope tag.");
        }
    }

    private static F.Id Id() => new() { Value = ByteString.CopyFrom(Convert.FromHexString("00112233445566778899aabbccddeeff")) };
    private static F.RequestMeta Meta() => new() { CorrelationId = Id() };
    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
