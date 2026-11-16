// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using ArcForges.Contracts.Foundation.Serialization;
using Sandbox = ArcForges.Contracts.Sandbox.V2;
using Management = ArcForges.Contracts.Management.V2;
using SandboxShape = ArcForges.Contracts.Sandbox.V2.Shapes.ContractShapeValidation;
using ManagementShape = ArcForges.Contracts.Management.V2.Shapes.ContractShapeValidation;

/// <summary>Offline contract checks shared by the structure suite and the Native AOT probe.</summary>
internal static class V2ContractCases
{
    private static void Require(bool condition, string label)
    {
        if (!condition) throw new InvalidOperationException("AFV2-API-01: " + label);
    }

    internal static void Run(string root)
    {
        using var fixture = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/public/afv2-api-01.json")));
        var count = 0;
        foreach (var row in fixture.RootElement.GetProperty("vectors").EnumerateArray())
        {
            var bytes = Convert.FromHexString(row.GetProperty("wireHex").GetString()!);
            var valid = Check(row.GetProperty("type").GetString()!, bytes);
            Require(valid == row.GetProperty("valid").GetBoolean(), row.GetProperty("name").GetString()!);
            count++;
        }

        var files = new[] { Sandbox.PlatformReflection.Descriptor, Sandbox.CenterControlReflection.Descriptor, Management.DevicesReflection.Descriptor };
        var messages = files.SelectMany(x => x.MessageTypes).ToArray();
        Require(messages.Length == 153, "complete adopted message inventory");
        var unknown = new byte[] { 0xC0, 0xDE, 0x1F, 0x37 }; // field 65000, varint 55; independent of every declared V2 tag.
        foreach (var descriptor in messages)
        {
            var value = descriptor.Parser.ParseFrom(unknown);
            Require(value.ToByteArray().SequenceEqual(unknown), "unknown-field roundtrip " + descriptor.FullName);
            foreach (var field in descriptor.Fields.InFieldNumberOrder().Where(x => x.FieldType == FieldType.Enum))
            {
                foreach (var number in field.EnumType.Values.Select(x => x.Number).Append(999))
                {
                    using var memory = new MemoryStream();
                    using (var wire = new CodedOutputStream(memory, leaveOpen: true)) { wire.WriteTag(field.FieldNumber, WireFormat.WireType.Varint); wire.WriteEnum(number); }
                    var bytes = memory.ToArray();
                    Require(descriptor.Parser.ParseFrom(bytes).ToByteArray().SequenceEqual(bytes), "known/unknown enum roundtrip " + field.FullName);
                }
            }
        }

        var compiled = FileDescriptorSet.Parser.ParseFrom(File.ReadAllBytes(Path.Combine(root, "artifacts/go-module.binpb")));
        foreach (var file in files)
        {
            var expected = compiled.File.Single(x => x.Name == file.Name);
            Require(file.ToProto().Equals(expected), "all compiled fields/enums/routes " + file.Name);
        }

        var methods = Sandbox.ContractMethods.All.Select(x => (x.Binding, x.Kind, x.LocalOnly, x.OwnerEpoch, x.ServerStreaming, x.MaxRequestBytes, x.MaxResponseBytes))
            .Concat(Management.ContractMethods.All.Select(x => (x.Binding, x.Kind, x.LocalOnly, x.OwnerEpoch, x.ServerStreaming, x.MaxRequestBytes, x.MaxResponseBytes))).ToArray();
        var routes = files.SelectMany(file => file.Services).SelectMany(service => service.Methods.Select(method => service.FullName + "/" + method.Name)).Order(StringComparer.Ordinal);
        Require(methods.Select(x => x.Binding).Order(StringComparer.Ordinal).SequenceEqual(routes), "every compiled route has a generated policy");
        Require(methods.Length == 42 && methods.Count(x => x.Kind == "transient_terminal") == 4, "complete method classification");
        Require(methods.Where(x => x.Kind == "transient_terminal").All(x => x.LocalOnly && !x.OwnerEpoch), "transient terminal has no durable epoch");
        Require(methods.Where(x => x.Kind == "durable_node").All(x => x.OwnerEpoch), "durable Node epoch binding");
        Require(methods.Where(x => x.Binding.Contains("CenterControlService/", StringComparison.Ordinal)).All(x => x.LocalOnly), "Center control cannot be routed remotely");
        Require(methods.Single(x => x.Binding.EndsWith("/InspectTransfer", StringComparison.Ordinal)).Kind == "read", "progress inspection cannot replay creation");
        var writeRow = fixture.RootElement.GetProperty("vectors").EnumerateArray().Single(x => x.GetProperty("name").GetString() == "terminal-write");
        var write = Sandbox.RunServiceWriteTerminalRequest.Parser.ParseFrom(Convert.FromHexString(writeRow.GetProperty("wireHex").GetString()!));
        var now = new ArcForges.Contracts.Foundation.V1.Instant { UnixSeconds = -1, Nanos = 0 };
        Require(Sandbox.TerminalProtocol.CanAdmitWrite(write, write.Lease.Clone(), "run-epoch", 0, now), "current writer next sequence");
        Require(!Sandbox.TerminalProtocol.CanAdmitWrite(write, write.Lease.Clone(), "run-epoch", 1, now), "consumed input never becomes a new write after acknowledgment eviction");
        var stale = write.Lease.Clone(); stale.Generation++;
        Require(!Sandbox.TerminalProtocol.CanAdmitWrite(write, stale, "run-epoch", 0, now), "stale generation");
        Require(!Sandbox.TerminalProtocol.CanAdmitWrite(write, write.Lease.Clone(), "new-run-epoch", 0, now), "stale Run epoch");
        now.UnixSeconds = 1;
        Require(!Sandbox.TerminalProtocol.CanAdmitWrite(write, write.Lease.Clone(), "run-epoch", 0, now), "expired live lease");
        Require(Sandbox.TerminalProtocol.AckWindowMs == 30000 && Sandbox.TerminalProtocol.AckRecords == 256 && Sandbox.TerminalProtocol.AckBytes == 1048576, "transient acknowledgment ceilings");

        var unary = fixture.RootElement.GetProperty("limits").GetProperty("unaryBytes").GetInt32();
        Require(!Sandbox.Serialization.V2Wire.TryDecode(new byte[unary + 1], out Sandbox.RunServiceStartRequest? _, out var failure) && failure == ContractSerializationFailure.TooLarge, "V2 unary rejects before parsing");
        var transfer = fixture.RootElement.GetProperty("limits").GetProperty("transferWireBytes").GetInt32();
        Require(!Sandbox.Serialization.V2Wire.TryDecode(new byte[transfer + 1], out Sandbox.DataServiceWriteImportRequest? _, out failure) && failure == ContractSerializationFailure.TooLarge, "V2 transfer ceiling");
        Require(WireLimits.UnaryMessageBytes == 4 * 1024 * 1024 && WireLimits.StreamFrameBytes == 32768, "retained v1 limits unchanged");
        var frame = new Sandbox.OutputChunk { Epoch = "r", Offset = 0, Stream = Sandbox.StreamKind.Stdout, Data = ByteString.CopyFrom(new byte[65536]), NextOffset = 65536 };
        Require(SandboxShape.IsValid(frame), "64 KiB V2 output payload supported");
        frame.Data = ByteString.CopyFrom(new byte[65537]); frame.NextOffset = 65537;
        Require(!SandboxShape.IsValid(frame), "oversized output payload refused");
        var roundtrip = Sandbox.TerminalSize.Parser.ParseFrom(unknown);
        var encoded = Sandbox.Serialization.V2Wire.Encode(roundtrip);
        Require(Sandbox.Serialization.V2Wire.TryDecode(encoded, out Sandbox.TerminalSize? restored, out _) && restored!.ToByteArray().SequenceEqual(unknown), "typed V2 codec preserves unknown read fields");
        Console.WriteLine($"AFV2-API-01: {count} shared vectors; {messages.Length} unknown-field codecs; {methods.Length} descriptor/policy routes; V2 bounds passed.");
    }

    private static bool Check(string type, byte[] bytes) => type switch
    {
        "TerminalSize" => SandboxShape.IsValid(Sandbox.TerminalSize.Parser.ParseFrom(bytes)),
        "RunServiceStartRequest" => SandboxShape.IsValid(Sandbox.RunServiceStartRequest.Parser.ParseFrom(bytes)),
        "OutputChunk" => SandboxShape.IsValid(Sandbox.OutputChunk.Parser.ParseFrom(bytes)),
        "RunServiceWriteTerminalRequest" => SandboxShape.IsValid(Sandbox.RunServiceWriteTerminalRequest.Parser.ParseFrom(bytes)),
        "RunServiceResizeTerminalRequest" => SandboxShape.IsValid(Sandbox.RunServiceResizeTerminalRequest.Parser.ParseFrom(bytes)),
        "SandboxServiceDeleteRequest" => SandboxShape.IsValid(Sandbox.SandboxServiceDeleteRequest.Parser.ParseFrom(bytes)),
        "CenterControlServiceBeginConnectRequest" => SandboxShape.IsValid(Sandbox.CenterControlServiceBeginConnectRequest.Parser.ParseFrom(bytes)),
        "DataServiceInspectTransferRequest" => SandboxShape.IsValid(Sandbox.DataServiceInspectTransferRequest.Parser.ParseFrom(bytes)),
        "Transfer" => SandboxShape.IsValid(Sandbox.Transfer.Parser.ParseFrom(bytes)),
        "Operation" => SandboxShape.IsValid(Sandbox.Operation.Parser.ParseFrom(bytes)),
        "DeviceServiceRevokeRequest" => ManagementShape.IsValid(Management.DeviceServiceRevokeRequest.Parser.ParseFrom(bytes)),
        "NodeServiceHandshakeResponse" => SandboxShape.IsValid(Sandbox.NodeServiceHandshakeResponse.Parser.ParseFrom(bytes)),
        _ => throw new InvalidOperationException("Unregistered V2 fixture type " + type),
    };
}
