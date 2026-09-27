// SPDX-License-Identifier: Apache-2.0
using System.Security.Cryptography;
using System.Text.Json;
using Google.Protobuf;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.Foundation.Serialization;
using ArcForges.Contracts.PublicApi.V1;
using ArcForges.Contracts.Hello.V1;
using ArcForges.Contracts.Validation;

internal static class Con02Cases
{
    private static void Require(bool condition) { if (!condition) throw new InvalidOperationException("CON.02 fixture refused."); }
    internal static void Run(string root)
    {
        using var fixture = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-02-descriptors.json")));
        var data = fixture.RootElement;
        byte[] Wire(string key) => Convert.FromHexString(data.GetProperty("wire").GetProperty(key).GetString()!);
        var binding = OperationBinding.Parser.ParseFrom(Wire("operationBinding"));
        Require(ContractShapeValidation.IsValid(binding) && (int)binding.Protocol == 6);
        Require(binding.ToByteArray().AsSpan().SequenceEqual(Wire("operationBinding")));
        var action = ActionDescriptor.Parser.ParseFrom(Wire("actionDescriptor"));
        Require(ContractShapeValidation.IsValid(action) && action.ToByteArray().AsSpan().SequenceEqual(Wire("actionDescriptor")));
        var provider = ContextProvider.Parser.ParseFrom(Wire("contextProvider"));
        Require(ContractShapeValidation.IsValid(provider) && provider.ToByteArray().AsSpan().SequenceEqual(Wire("contextProvider")));
        var features = FeatureSet.Parser.ParseFrom(Wire("featureSet"));
        Require(ContractShapeValidation.IsValid(features) && features.ToByteArray().AsSpan().SequenceEqual(Wire("featureSet")));
        binding.Protocol = (BindingProtocol)99; Require(!ContractShapeValidation.IsValid(binding));
        provider.MaxItems = 201; Require(!ContractShapeValidation.IsValid(provider));
        provider.MaxItems = 1; provider.MaxBytes = 262145; Require(!ContractShapeValidation.IsValid(provider));
        features.Features.Add("a"); Require(!ContractShapeValidation.IsValid(features));
        Require(ContractShapeValidation.IsValid(new InstanceReadiness { AcceptsWork = false }));
        var descriptorId = new Id { Value = ByteString.CopyFrom(Convert.FromHexString("00112233445566778899aabbccddeeff")) };
        var health = new HealthSnapshot { InstanceId = descriptorId, ObservedAt = new() { UnixSeconds = 1, Nanos = 0 },
            Health = (InstanceHealth)3, Readiness = new() { AcceptsWork = true } };
        Require(ContractShapeValidation.IsValid(HealthSnapshot.Parser.ParseFrom(health.ToByteArray())));
        health.Health = (InstanceHealth)99;
        Require((int)HealthSnapshot.Parser.ParseFrom(health.ToByteArray()).Health == 99 && !ContractShapeValidation.IsValid(health));
        var context = new ContextDescriptor { Key = "selection", Provider = "provider", Kind = "selection", TitleKey = "title",
            Context = new() { Source = new() { Kind = "scopeMetadata", Id = descriptorId }, Lifetime = (ContextLifetime)4 },
            ObservedAt = new() { UnixSeconds = 1, Nanos = 0 } };
        Require(ContractShapeValidation.IsValid(ContextDescriptor.Parser.ParseFrom(context.ToByteArray())));
        context.Context.Revision = new() { Value = 0 }; Require(!ContractShapeValidation.IsValid(context));
        var capability = new CapabilityDescriptor { Key = "read", Version = "1.0.0", RequestSchema = "Request", ResponseSchema = "Response",
            Risk = "R1", Locality = (ToolLocality)2, Idempotency = "query", Exclusive = false, Egress = "none", Approval = "none",
            Binding = OperationBinding.Parser.ParseFrom(Wire("operationBinding")), Execution = (ExecutionLocus)2, Effect = (EffectKind)1,
            Retry = (RetryMode)1, Cancel = new() { Accepted = true, BeforeDispatchOnly = true }, Checkpoint = false,
            Limits = new() { MaxInputBytes = 1, MaxOutputBytes = 1, MaxDurationMs = 1, MaxConcurrency = 1, MaxContextItems = 64 } };
        Require(ContractShapeValidation.IsValid(CapabilityDescriptor.Parser.ParseFrom(capability.ToByteArray())));
        capability.Writes.Add("resource"); Require(!ContractShapeValidation.IsValid(capability));
        capability.Writes.Clear(); capability.Limits.MaxContextItems = 65; Require(!ContractShapeValidation.IsValid(capability));
        foreach (var version in data.GetProperty("validVersions").EnumerateArray())
            Require(ContractShapeValidation.IsValid(new ContractVersion { Key = "foundation", Version = version.GetString()! }));
        foreach (var version in data.GetProperty("invalidVersions").EnumerateArray())
            Require(!ContractShapeValidation.IsValid(new ContractVersion { Key = "foundation", Version = version.GetString()! }));
        Require(!ContractShapeValidation.IsValid(new ContractVersion { Key = "not+key", Version = "1.0.0+build" }));
        Require(!ContractShapeValidation.IsValid(new ContractVersion { Key = "foundation", Version = "1.0.0+" + new string('x', 123) }));
        foreach (var row in data.GetProperty("compatibility").EnumerateArray())
        {
            var version = row.GetProperty("version").GetString()!;
            var minimum = row.GetProperty("minimum").GetString()!;
            Require(ContractShapeValidation.IsValid(new ContractCompatibility { Contract = new() { Key = "foundation", Version = version },
                MinReadable = minimum, MinWritable = minimum }) == row.GetProperty("valid").GetBoolean());
        }
        var duplicate = new ContractCompatibility { Contract = new() { Key = "k", Version = "1.0.0" }, MinReadable = "1.0.0", MinWritable = "1.0.0" };
        Require(!ContractShapeValidation.IsValid(new CompatibilityDescriptor { Foundation = duplicate, Contracts = { duplicate, duplicate.Clone() }, Features = new() }));
        var bytes = new SayHelloResponse { Message = "A" }.ToByteArray();
        Require(Read(Reference(bytes), bytes, SayHelloResponse.Parser).Message == "A");
        var parserCalls = 0;
        var countingParser = new MessageParser<SayHelloResponse>(() => { parserCalls++; return new(); });
        foreach (Action<EncodedBodyRef> mutate in new Action<EncodedBodyRef>[] {
            r => r.MessageType = "wrong", r => r.DescriptorHash = new string('b', 64),
            r => r.SnapshotToken = "wrong", r => r.ByteLength++, r => r.ExpiresAt.Nanos = 0,
            r => r.Resource.ContentHash = new string('b', 64), r => r.Resource.ClearContentHash() })
        {
            var bound = Reference(bytes); mutate(bound);
            Refuses(() => Read(bound, bytes, countingParser), ContractSerializationFailure.Invalid);
        }
        Require(parserCalls == 0);
        var large = new byte[WireLimits.LargeProjectionBytes];
        Array.Fill(large, (byte)'A');
        new byte[] { 10, 251, 255, 255, 31 }.CopyTo(large, 0);
        Require(Read(Reference(large), large, SayHelloResponse.Parser).Message.Length == large.Length - 5);
        Refuses(() => Read(Reference(bytes), new byte[WireLimits.LargeProjectionBytes + 1], countingParser), ContractSerializationFailure.TooLarge);
        Require(parserCalls == 0);
        Console.WriteLine("CON.02 independent wire, SemVer, descriptor and exact64MiB admission fixtures passed.");
    }
    private static void Refuses(Action action, ContractSerializationFailure failure)
    {
        try { action(); } catch (ContractSerializationException error) when (error.Failure == failure) { return; }
        throw new InvalidOperationException("Expected CON.02 admission refusal.");
    }
    private static SayHelloResponse Read(EncodedBodyRef reference, byte[] bytes, MessageParser<SayHelloResponse> parser) =>
        EncodedBodyReader.Read(reference, bytes, "arcforges.hello.v1.SayHelloResponse", new string('a', 64), "bound-snapshot",
            new Instant { UnixSeconds = 200, Nanos = 0 }, parser);
    private static EncodedBodyRef Reference(byte[] bytes)
    {
        var id = new Id { Value = ByteString.CopyFrom(Convert.FromHexString("00112233445566778899aabbccddeeff")) };
        return new EncodedBodyRef {
            Resource = new ResourceVersionRef { Resource = new ResourceRef { RealmId = id, ResourceId = id.Clone(),
                OwnerAppId = "arcscope", ResourceKind = "projection", Availability = (ResourceAvailability)1 },
                Cloud = new Revision { Value = 1 }, ContentHash = Convert.ToHexStringLower(SHA256.HashData(bytes)) },
            MessageType = "arcforges.hello.v1.SayHelloResponse", DescriptorHash = new string('a', 64), ByteLength = (ulong)bytes.Length,
            SnapshotToken = "bound-snapshot", ExpiresAt = new Instant { UnixSeconds = 200, Nanos = 1 }
        };
    }
}
