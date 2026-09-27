// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using Google.Protobuf;
using ArcForges.Contracts.LocalRpc.Sandbox;
using ArcForges.Contracts.LocalRpc.Sandbox.V1;
using Shape = ArcForges.Contracts.LocalRpc.Sandbox.Shapes.ContractShapeValidation;

internal static class ContentSandboxCases
{
    public static void Run(string root)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures", "internal", "con-04-content-sandbox.json")));
        var fixture = document.RootElement;
        var service = ContentSandboxService.Descriptor;
        Require(service.FullName == fixture.GetProperty("service").GetString(), "service identity");
        Require(service.Methods.Select(m => m.Name).SequenceEqual(fixture.GetProperty("methods").EnumerateArray().Select(m => m.GetString())), "closed method inventory");
        foreach (var retired in fixture.GetProperty("retiredMethods").EnumerateArray())
            Require(service.FindMethodByName(retired.GetString()!) is null, "retired method");
        foreach (var method in service.Methods)
        {
            Require(!method.IsClientStreaming && !method.IsServerStreaming, "unary controls");
            Require(method.InputType.FindFieldByNumber(1).MessageType.FullName == "arcforges.foundation.v1.RequestMeta", "request envelope");
            Require(method.InputType.Fields.InFieldNumberOrder().All(f => f.FieldNumber == 1 || f.FieldNumber >= 10), "request payload tags");
            Require(method.OutputType.FindFieldByNumber(1).MessageType.FullName == "arcforges.foundation.v1.ResponseMeta", "response envelope");
            var success = method.OutputType.FindFieldByNumber(2);
            var error = method.OutputType.FindFieldByNumber(3);
            Require(success.ContainingOneof != null && ReferenceEquals(success.ContainingOneof, error.ContainingOneof), "exclusive result");
            Require(success.MessageType.Fields.InFieldNumberOrder().All(f => f.FieldNumber >= 10), "success payload tags");
            foreach (var binding in fixture.GetProperty("bindings").EnumerateArray())
                Require(ContentSandboxPolicy.IsAdmittedBinding(method,
                    Enum.Parse<ContentSandboxPolicy.EndpointRole>(binding.GetProperty("caller").GetString()!),
                    Enum.Parse<ContentSandboxPolicy.EndpointRole>(binding.GetProperty("receiver").GetString()!),
                    binding.GetProperty("parentAlive").GetBoolean(), binding.GetProperty("sameApplication").GetBoolean()) == binding.GetProperty("valid").GetBoolean(), binding.GetProperty("id").GetString()!);
        }
        var buffer = SandboxBufferDescriptor.Descriptor.ToProto();
        Require(buffer.ReservedRange.Any(r => r.Start == 7 && r.End == 8) && buffer.ReservedName.Contains("frame_id") && buffer.ReservedName.Contains("frameId"), "retired frame identity");
        foreach (var item in fixture.GetProperty("cases").EnumerateArray())
        {
            string json = item.GetProperty("value").GetRawText();
            bool actual = item.GetProperty("target").GetString() switch
            {
                "slot" => Shape.IsValid(JsonParser.Default.Parse<SandboxSlotGrant>(json)),
                "page" => SandboxProfile.IsValid(JsonParser.Default.Parse<SandboxPdfPage>(json)),
                "text" => SandboxProfile.IsValid(JsonParser.Default.Parse<SandboxPdfText>(json)),
                "region" => SandboxProfile.IsValid(JsonParser.Default.Parse<SandboxRegion>(json)),
                _ => throw new InvalidOperationException("Unknown sandbox fixture target")
            };
            Require(actual == item.GetProperty("valid").GetBoolean(), item.GetProperty("id").GetString()!);
        }
        Require(!SandboxProfile.IsValid(new SandboxPdfText { PageIndex = 0, Start = 0, Text = "\ud800" }), "unpaired UTF16 surrogate");
        var id = new ArcForges.Contracts.Foundation.V1.Id { Value = ByteString.CopyFrom(Convert.FromHexString("00112233445566778899aabbccddeeff")) };
        var grant = new SandboxSlotGrant { SlotId = 0, Sequence = 1, Capacity = 64 };
        var region = new SandboxRegion { X = 0, Y = 0, Width = 2, Height = 2, FirstSample = 0, SampleCount = 0, RowStride = 8 };
        var seal = new SandboxBufferDescriptor { Version = 1, InvocationId = id, LeaseId = id, Generation = 1, SlotId = 0, Sequence = 1,
            Kind = 1, Format = 1, FullWidth = 2, FullHeight = 2, TileX = 0, TileY = 0, TileWidth = 2, TileHeight = 2,
            SampleStart = 0, SampleCount = 0, Offset = 0, Length = 16, RowStride = 8, Sha256 = new string('a', 64) };
        Require(SandboxProfile.IsValid(seal, grant, region), "bounded seal");
        var stale = seal.Clone(); stale.Sequence = 2;
        Require(!SandboxProfile.IsValid(stale, grant, region), "stale slot sequence");
        var outside = seal.Clone(); outside.Offset = 60;
        Require(!SandboxProfile.IsValid(outside, grant, region), "slot capacity overflow");
        var geometry = seal.Clone(); geometry.TileX = 1;
        Require(!SandboxProfile.IsValid(geometry, grant, region), "mismatched tile geometry");
        var format = seal.Clone(); format.Format = 3;
        Require(!SandboxProfile.IsValid(format, grant, region), "unadmitted pixel format");
        var truncated = seal.Clone(); truncated.Length = 15;
        Require(!SandboxProfile.IsValid(truncated, grant, region), "truncated pixel rows");
        Console.WriteLine("Validated ContentSandbox closed descriptors, role policy and independent shape/geometry fixtures.");
    }

    private static void Require(bool valid, string name)
    {
        if (!valid) throw new InvalidOperationException("ContentSandbox fixture failed: " + name);
    }
}
