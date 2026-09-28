// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using Google.Protobuf;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.PublicApi.V1;
using ArcForges.Contracts.Validation;

internal static class Con03Cases
{
    internal static void Run(string root)
    {
        using var fixture = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-03-sync-allowlist.json")));
        var data = fixture.RootElement;
        foreach (var item in data.GetProperty("cases").EnumerateArray())
        {
            string caseId = item.GetProperty("id").GetString()!;
            var sourceBody = BuildBody(item.GetProperty("body"));
            if (item.TryGetProperty("resolvedBody", out var resolvedBody))
                Require(sourceBody is not null && ContractShapeValidation.IsValid(sourceBody), caseId + ": external source shape");
            var candidate = BuildBody(resolvedBody.ValueKind == JsonValueKind.Undefined ? item.GetProperty("body") : resolvedBody);
            bool validShape = candidate is not null && ContractShapeValidation.IsValid(candidate);
            Require(validShape == item.GetProperty("bodyShapeValid").GetBoolean(), caseId + ": shape validity");

            long? expectedRevision = Revision(item.GetProperty("expectedRevision"));
            long? actualRevision = Revision(item.GetProperty("actualRevision"));
            bool allowed = ContractShapeValidation.IsSyncClientWriteAllowed(candidate,
                item.GetProperty("expectedOwner").GetString(), item.GetProperty("actualOwner").GetString(),
                expectedRevision, actualRevision);
            Require(allowed == item.GetProperty("allowed").GetBoolean(), caseId + ": Sync write admission");
        }

        byte[] unknownResponse = Convert.FromHexString(data.GetProperty("compatibleUnknownResponse").GetProperty("wireHex").GetString()!);
        var response = AggregateBody.Parser.ParseFrom(unknownResponse);
        Require(response.BodyCase == AggregateBody.BodyOneofCase.ScopeProjectMetadata
            && ContractShapeValidation.IsValid(response), "compatible unknown response profile");
        Require(response.ToByteArray().AsSpan().SequenceEqual(unknownResponse), "unknown response fields must survive unchanged");
        Console.WriteLine("CON.03 closed Sync allowlist, owner/revision negatives, opaque/forbidden/tombstone vectors and unknown-response preservation passed.");
    }

    private static AggregateBody? BuildBody(JsonElement body) => body.GetProperty("kind").GetString() switch
    {
        "none" => null,
        "opaque" => AggregateBody.Parser.ParseFrom(Convert.FromHexString(body.GetProperty("wireHex").GetString()!)),
        "scopeProjectMetadata" => new AggregateBody
        {
            ScopeProjectMetadata = new ScopeProjectMetadata
            {
                ProjectId = Id(body.GetProperty("projectIdHex").GetString()!),
                Name = body.GetProperty("name").GetString()!
            }
        },
        "scopeMetadata" => ScopeMetadataBody(body),
        "taskSnapshot" => new AggregateBody
        {
            Task = new TaskSnapshot
            {
                TaskId = Id(body.GetProperty("taskIdHex").GetString()!),
                State = (TaskState)1,
                Revision = new Revision { Value = 1 },
                HasUnknownEffect = false,
                CompletedSteps = 0,
                TotalSteps = 0,
                ReasonFacet = (TaskReasonFacet)1
            }
        },
        "externalBody" => ExternalBody(body),
        var kind => throw new InvalidOperationException("Unknown CON.03 body fixture kind " + kind)
    };

    private static AggregateBody ScopeMetadataBody(JsonElement body)
    {
        var channel = new ChannelDefinition
        {
            ChannelId = Id("11111111111141118111111111111111"),
            Name = "Voltage",
            Unit = "V",
            SampleType = "f64",
            Rate = new Rational { Numerator = 1, Denominator = 1 }
        };
        var configuration = new ScopeConfiguration
        {
            ConfigurationId = Id("22222222222242228222222222222222"),
            ParserProfile = "scope.parser.v1",
            Revision = new NativeContentRev { Value = 1 },
            Framing = new FrameConfiguration
            {
                Kind = "canonicalReplay",
                Start = ByteString.Empty,
                End = ByteString.Empty,
                Header = false,
                ByteOrder = "little"
            }
        };
        configuration.Channels.Add(channel);
        return new AggregateBody
        {
            ScopeMetadata = new ScopeMetadata
            {
                SessionId = Id(body.GetProperty("sessionIdHex").GetString()!),
                ProjectId = Id(body.GetProperty("projectIdHex").GetString()!),
                Name = body.GetProperty("name").GetString()!,
                Configuration = configuration
            }
        };
    }

    private static AggregateBody ExternalBody(JsonElement body)
    {
        var resource = body.GetProperty("resourceVersionRef");
        return new AggregateBody
        {
            ExternalBody = new ResourceVersionRef
            {
                Resource = new ResourceRef
                {
                    RealmId = Id(resource.GetProperty("realmIdHex").GetString()!),
                    ResourceId = Id(resource.GetProperty("resourceIdHex").GetString()!),
                    OwnerAppId = resource.GetProperty("ownerAppId").GetString()!,
                    ResourceKind = resource.GetProperty("resourceKind").GetString()!,
                    Availability = (ResourceAvailability)1
                },
                Cloud = new Revision { Value = 1 }
            }
        };
    }

    private static Id Id(string hex) => new() { Value = ByteString.CopyFrom(Convert.FromHexString(hex)) };

    private static long? Revision(JsonElement value) => value.ValueKind == JsonValueKind.Null ? null : value.GetInt64();

    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("CON.03 fixture refused: " + name);
    }
}
