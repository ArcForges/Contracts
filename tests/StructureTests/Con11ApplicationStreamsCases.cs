// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using System.Security.Cryptography;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using F = ArcForges.Contracts.Foundation.V1;
using P = ArcForges.Contracts.PublicApi.V1;
using E = ArcForges.Contracts.Events.V1;
using C = ArcForges.Contracts.CloudInternal.Cf.V1;

internal static class Con11ApplicationStreamsCases
{
    public static void Run(string root)
    {
        using var publicFixture = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/public/con-11-application-streams.json")));
        using var privateFixture = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/internal/con-11-run-stream.json")));
        using var operationExport = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "eng/operations/con-11.json")));
        using var publicConstraints = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "public/proto/constraints/con-11-application-streams.json")));
        using var privateConstraints = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "internal/proto/constraints/con-11-run-stream.json")));
        var seen = new HashSet<string>(StringComparer.Ordinal);

        var operationRows = operationExport.RootElement.GetProperty("operations").EnumerateArray().ToArray();
        var rpcVectors = publicFixture.RootElement.GetProperty("rpcVectors").EnumerateArray().ToArray();
        Require(operationRows.Length == 14 && rpcVectors.Length == 14, "exactly the 14 authorized public RPC vectors are present");
        Require(operationRows.Select(x => x.GetProperty("operationId").GetString()).Distinct(StringComparer.Ordinal).Count() == 14,
            "Poll and Watch remain distinct operation IDs");
        foreach (var file in new[] { P.ApplicationReflection.Descriptor, E.EventsReflection.Descriptor })
        {
            var expectedServices = rpcVectors.Where(x => FileForService(S(x, "service")).Name == file.Name)
                .Select(x => S(x, "service")).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal);
            Require(file.Services.Select(x => x.FullName).Order(StringComparer.Ordinal).SequenceEqual(expectedServices),
                "exact public service set in " + file.Name);
        }
        foreach (var group in rpcVectors.GroupBy(x => S(x, "service")))
        {
            var service = FileForService(group.Key).Services.Single(x => x.FullName == group.Key);
            Require(service.Methods.Select(x => x.Name).Order(StringComparer.Ordinal)
                .SequenceEqual(group.Select(x => S(x, "method")).Order(StringComparer.Ordinal)),
                "exact public RPC method set: " + group.Key);
        }
        foreach (var vector in rpcVectors)
        {
            Consume(vector, seen);
            var operationId = S(vector, "operationId");
            var binding = S(vector, "service") + "/" + S(vector, "method");
            var row = operationRows.Single(x => S(x, "operationId") == operationId);
            Require(S(row, "binding") == binding && S(row, "kind") == "proto" && S(row, "surface") == "public",
                "public RPC maps to its distinct authorized operation: " + operationId);
            Require(S(row, "source") == (S(vector, "service").StartsWith("arcforges.publicapi.", StringComparison.Ordinal)
                ? "public/proto/arcforges/publicapi/v1/application.proto"
                : "public/proto/arcforges/events/v1/events.proto"), "operation source path: " + operationId);

            var file = FileForService(S(vector, "service"));
            var service = file.Services.Single(x => x.FullName == S(vector, "service"));
            var method = service.Methods.Single(x => x.Name == S(vector, "method"));
            Require(method.InputType.Name == S(vector, "input"), "RPC request descriptor: " + operationId);
            Require(method.OutputType.Name == S(vector, "output"), "RPC response descriptor: " + operationId);
            var streaming = S(vector, "streamType") == "serverStreaming";
            Require(!method.IsClientStreaming && method.IsServerStreaming == streaming, "RPC stream kind: " + operationId);
            CheckFields(method.InputType, vector.GetProperty("inputFields"), operationId + " request");

            if (!streaming)
            {
                var outcome = method.OutputType.Oneofs.Single(x => x.Name == "outcome");
                var expected = new List<(string Name, int Number)> { ("value", 2), ("error", 3) };
                var readProjectionIds = publicFixture.RootElement.GetProperty("unaryOutcomeProfile")
                    .GetProperty("readProjectionOperationIds").EnumerateArray().Select(x => x.GetString()!).ToHashSet(StringComparer.Ordinal);
                if (readProjectionIds.Contains(operationId)) expected.Add(("encodedBody", 4));
                Require(outcome.Fields.Select(x => (x.JsonName, x.FieldNumber)).SequenceEqual(expected),
                    "unary outcome alternatives and read-projection body tag: " + operationId);
            }
            if (operationId == "events.poll")
            {
                var auth = row.GetProperty("authorization");
                var profile = publicFixture.RootElement.GetProperty("pollProfile");
                Require(S(row, "scope") == S(profile, "scope") && S(row, "idempotency") == S(profile, "idempotency")
                    && S(auth, "egress") == S(profile, "egress") && S(auth, "risk") == S(profile, "risk")
                    && S(auth, "approval") == S(profile, "approval") && auth.GetProperty("capability").ValueKind == JsonValueKind.Null
                    && auth.GetProperty("stepUp").GetBoolean() == profile.GetProperty("stepUp").GetBoolean()
                    && auth.GetProperty("localPresence").GetBoolean() == profile.GetProperty("localPresence").GetBoolean()
                    && auth.GetProperty("patEligible").GetBoolean() == profile.GetProperty("patEligible").GetBoolean()
                    && auth.GetProperty("actorKinds").EnumerateArray().Select(x => x.GetString())
                        .SequenceEqual(profile.GetProperty("actorKinds").EnumerateArray().Select(x => x.GetString())),
                    "Poll export and independent fixture agree on the exact eight-field resource-owner profile");
                Require(S(publicFixture.RootElement.GetProperty("pollProfile"), "noCursor") == "emptyPageWithSignedHighWaterCursorAndResetRequired",
                    "Poll no-cursor repair profile");
            }
            else if (operationId == "execution.startTransientTurn")
            {
                Require(S(row.GetProperty("authorization"), "egress")
                    == "existingAdmissionContextPolicyToSelectedCloudOrWorkersAiRoute",
                    "temporary execution egress is bound to existing admission/context policy and selected model route");
            }
            else if (operationId == "history.beginImport")
            {
                Require(S(row.GetProperty("authorization"), "egress") == "thisApplicationAdmittedCloudHistoryDestinationOnly",
                    "history import begin cannot select another product or destination");
            }
            else if (operationId == "history.finalizeImport")
            {
                Require(S(row.GetProperty("authorization"), "egress") == "recordedBeginConsentDestinationAndSnapshotOnly",
                    "history import finalize reuses its recorded destination and snapshot only");
            }
            else if (operationId is "application.list" or "history.getImport" or "execution.readOutput" or "execution.watchOutput" or "events.watch")
            {
                Require(S(row.GetProperty("authorization"), "egress") == "none", "ordinary authorized response is not a new egress destination: " + operationId);
            }
        }

        foreach (var vector in publicFixture.RootElement.GetProperty("messageFieldVectors").EnumerateArray())
        {
            Consume(vector, seen);
            var message = FindMessage(S(vector, "message"));
            var expectedFields = vector.GetProperty("fields").EnumerateArray().Select(x => (x[0].GetString()!, x[1].GetInt32())).ToList();
            if (S(vector, "message") == "Event")
                expectedFields.AddRange(publicFixture.RootElement.GetProperty("eventPayloadVectors").EnumerateArray()
                    .Select(x => (S(x, "field"), x.GetProperty("tag").GetInt32())));
            CheckFields(message, expectedFields, S(vector, "id"));
            if (vector.TryGetProperty("oneofFields", out var groups))
                foreach (var group in groups.EnumerateObject())
                {
                    var oneof = message.Oneofs.Single(x => x.Name == group.Name);
                    var expected = group.Value.EnumerateArray().Select(x => x.GetString()!).ToArray();
                    Require(oneof.Fields.Select(x => x.JsonName).SequenceEqual(expected), "closed oneof fields: " + S(vector, "id"));
                }
            if (vector.TryGetProperty("payloadOneof", out var payloadOneof))
                Require(message.Oneofs.Any(x => x.Name == payloadOneof.GetString()), "event payload oneof exists");
        }

        foreach (var vector in publicFixture.RootElement.GetProperty("eventPayloadVectors").EnumerateArray())
        {
            Consume(vector, seen);
            var eventMessage = FindMessage("Event");
            var field = eventMessage.Fields.Single(x => x.JsonName == S(vector, "field"));
            Require(field.FieldNumber == vector.GetProperty("tag").GetInt32()
                && field.ContainingOneof?.Name == "payload"
                && field.MessageType?.Name == S(vector, "message"), "Registry04 event tag/type/oneof: " + S(vector, "id"));
            CheckFields(field.MessageType!, vector.GetProperty("fields"), S(vector, "id"));
        }

        var profile = publicFixture.RootElement.GetProperty("pollProfile");
        Require(S(profile, "operationId") == "events.poll" && S(profile, "scope") == "resource-owner"
            && S(profile, "idempotency") == "Q" && S(profile, "compatibility") == "AO" && S(profile, "risk") == "R1"
            && S(profile, "egress") == "authorizedHintResponseOnly" && !profile.GetProperty("patEligible").GetBoolean()
            && S(profile, "approval") == "none" && profile.GetProperty("capability").ValueKind == JsonValueKind.Null
            && !profile.GetProperty("stepUp").GetBoolean() && !profile.GetProperty("localPresence").GetBoolean()
            && profile.GetProperty("actorKinds").EnumerateArray().Select(x => x.GetString()).SequenceEqual(["human"]),
            "independent Poll authorization profile");
        Require(S(profile, "retry") == "sameCursorPureQuery; authorizationRefusalWaitsForNewSession; unavailableUsesRetryAfterBackoff",
            "Poll cursor, authorization-refusal, and retry/backoff profile");

        CheckConstraintProfiles(publicConstraints.RootElement);
        CheckRequiredProtoPresence(publicConstraints.RootElement);
        CheckAggregateBoundaries(publicFixture.RootElement.GetProperty("aggregateBoundaryVectors"), seen);
        CheckLimits(publicFixture.RootElement.GetProperty("limits"));
        var limitations = publicFixture.RootElement.GetProperty("shapeLimitations").EnumerateArray().Select(x => x.GetString()!).ToArray();
        Require(limitations.Length == 3 && limitations.Any(x => x.Contains("not by this message shape alone", StringComparison.Ordinal))
            && limitations.Any(x => x.Contains("not runtime streaming enforcement", StringComparison.Ordinal))
            && limitations.Any(x => x.Contains("not represented by this per-field constraint grammar", StringComparison.Ordinal)),
            "fixture limits its claims to what task-owned offline shapes can prove");
        CheckPrivateProjection(privateFixture.RootElement, privateConstraints.RootElement, seen,
            publicFixture.RootElement.GetProperty("limits").GetProperty("outputChunkBytes").GetInt32());

        var expectedIds = publicFixture.RootElement.GetProperty("rpcVectors").EnumerateArray().Select(x => S(x, "id"))
            .Concat(publicFixture.RootElement.GetProperty("messageFieldVectors").EnumerateArray().Select(x => S(x, "id")))
            .Concat(publicFixture.RootElement.GetProperty("eventPayloadVectors").EnumerateArray().Select(x => S(x, "id")))
            .Concat(publicFixture.RootElement.GetProperty("aggregateBoundaryVectors").EnumerateObject()
                .SelectMany(group => group.Value.EnumerateArray().Select(x => S(x, "id"))))
            .Concat(privateFixture.RootElement.GetProperty("rpcVectors").EnumerateArray().Select(x => S(x, "id")))
            .Concat(privateFixture.RootElement.GetProperty("runStreamFrameVariants").EnumerateArray().Select(x => S(x, "id")))
            .Concat(privateFixture.RootElement.GetProperty("encodedFrameBoundaryVectors").EnumerateArray().Select(x => S(x, "id")))
            .ToHashSet(StringComparer.Ordinal);
        Require(seen.SetEquals(expectedIds), "every known public and private fixture vector is consumed exactly once; no unknown vectors");
        Console.WriteLine($"CON.11 consumed {seen.Count} independent public/private descriptor, event, and byte/count boundary vectors.");
    }

    private static void CheckPrivateProjection(JsonElement fixture, JsonElement constraints, HashSet<string> seen, int publicOutputChunkLimit)
    {
        var vectors = fixture.GetProperty("rpcVectors").EnumerateArray().ToArray();
        Require(vectors.Length == 1, "exactly one private RunStream RPC vector");
        foreach (var vector in vectors)
        {
            Consume(vector, seen);
            var method = C.RunStreamService.Descriptor.Methods.Single(x => x.Name == S(vector, "method"));
            Require(C.RunStreamService.Descriptor.FullName == S(vector, "service")
                && method.InputType.Name == S(vector, "input")
                && method.OutputType.FullName == S(vector, "output")
                && !method.IsClientStreaming && method.IsServerStreaming, "private RunStream descriptor");
            CheckFields(method.InputType, vector.GetProperty("requestFields"), S(vector, "id"));
            Require(method.InputType.Fields.Single(x => x.JsonName == "generation").HasPresence,
                "private generation uses proto3 optional presence");
            var run = constraints.GetProperty("messages").GetProperty("arcforges.cf.v1.RunStreamRequest").GetProperty("fields");
            Require(run.GetProperty("generation").GetProperty("required").GetBoolean()
                && !run.GetProperty("generation").TryGetProperty("min", out _), "generation presence only; no invented lower bound");
        }

        var streamFile = C.StreamReflection.Descriptor;
        var eventFile = E.EventsReflection.Descriptor;
        Require(streamFile.Dependencies.Select(x => x.Name).ToHashSet(StringComparer.Ordinal)
            .SetEquals(["arcforges/foundation/v1/foundation.proto", "arcforges/publicapi/v1/chat.proto", "arcforges/events/v1/events.proto"]),
            "private RunStream has only its three required public dependencies");
        Require(!eventFile.Dependencies.Any(x => x.Name.Contains("internal", StringComparison.Ordinal)
            || x.Name.Contains("cloudinternal", StringComparison.OrdinalIgnoreCase)), "public events do not import private projections");

        var stream = FindMessage("StreamFrame");
        foreach (var vector in fixture.GetProperty("runStreamFrameVariants").EnumerateArray())
        {
            Consume(vector, seen);
            var field = stream.Fields.Single(x => x.JsonName == S(vector, "field"));
            Require(field.FieldNumber == vector.GetProperty("tag").GetInt32() && field.ContainingOneof?.Name == "frame",
                "private stream uses the public StreamFrame field: " + S(vector, "id"));
            var expectedAllowed = S(vector, "field") is "output" or "reset" or "heartbeat";
            Require(vector.GetProperty("allowed").GetBoolean() == expectedAllowed, "RunStream admits only its section-7 variants: " + S(vector, "id"));
        }

        var limit = fixture.GetProperty("limits").GetProperty("encodedFrameBytes").GetInt32();
        Require(fixture.GetProperty("limits").GetProperty("outputChunkBytes").GetInt32() == publicOutputChunkLimit,
            "private RunStream reuses the public encoded OutputChunk cap");
        foreach (var vector in fixture.GetProperty("encodedFrameBoundaryVectors").EnumerateArray())
        {
            Consume(vector, seen);
            var bytes = vector.GetProperty("serializedBytes").GetInt32();
            Require(vector.GetProperty("limit").GetInt32() == limit
                && (bytes <= limit) == vector.GetProperty("valid").GetBoolean(),
                "private encoded-frame boundary: " + S(vector, "id"));
            var frame = CreateFrame(bytes);
            var wire = frame.ToByteArray();
            Require(wire.Length == bytes && E.StreamFrame.Parser.ParseFrom(wire).CalculateSize() == bytes
                && (wire.Length <= limit) == vector.GetProperty("valid").GetBoolean(),
                "private frame is measured after serialization: " + S(vector, "id"));
        }
    }

    private static void CheckAggregateBoundaries(JsonElement groups, HashSet<string> seen)
    {
        foreach (var vector in groups.GetProperty("transcriptPartTotals").EnumerateArray())
        {
            Consume(vector, seen);
            var counts = vector.GetProperty("perMessageCounts").EnumerateArray().Select(x => x.GetInt32()).ToArray();
            var window = new P.TranscriptWindow
            {
                BranchId = TestId(),
                BranchRevision = 1,
                FirstOrdinal = 0,
                LastOrdinal = (ulong)(counts.Length - 1),
                WindowHash = new string('a', 64),
            };
            foreach (var (count, ordinal) in counts.Select((value, index) => (value, index)))
            {
                var message = new P.TranscriptMessage { MessageId = TestId(ordinal + 1), Ordinal = (ulong)ordinal, Role = P.TranscriptRole.User };
                for (var index = 0; index < count; index++) message.Parts.Add(new P.MessagePart { Text = "x" });
                window.Messages.Add(message);
            }
            var wire = window.ToByteArray();
            var parsed = P.TranscriptWindow.Parser.ParseFrom(wire);
            var actual = parsed.Messages.Sum(x => x.Parts.Count);
            Require(actual == counts.Sum() && wire.Length > 0
                && (actual <= vector.GetProperty("limit").GetInt32()) == vector.GetProperty("valid").GetBoolean(),
                "transcript aggregate part-count boundary: " + S(vector, "id"));
        }
        foreach (var vector in groups.GetProperty("archiveRecordBytes").EnumerateArray())
        {
            Consume(vector, seen);
            var target = vector.GetProperty("serializedBytes").GetInt32();
            var bytes = BuildArchiveRecordBytes(target);
            var parsed = P.HistoryArchiveRecord.Parser.ParseFrom(bytes);
            Require(parsed.RecordCase == P.HistoryArchiveRecord.RecordOneofCase.Message && parsed.CalculateSize() == target,
                "length-delimited archive record serialized-size vector: " + S(vector, "id"));
            Require((bytes.Length <= vector.GetProperty("limit").GetInt32()) == vector.GetProperty("valid").GetBoolean(),
                "1MiB archive-record cap: " + S(vector, "id"));
        }
        foreach (var vector in groups.GetProperty("outputChunkBytes").EnumerateArray())
        {
            Consume(vector, seen);
            var target = vector.GetProperty("serializedBytes").GetInt32();
            var chunk = CreateChunk(target);
            var wire = chunk.ToByteArray();
            Require(wire.Length == target && E.OutputChunk.Parser.ParseFrom(wire).CalculateSize() == target
                && (wire.Length <= vector.GetProperty("limit").GetInt32()) == vector.GetProperty("valid").GetBoolean(),
                "encoded OutputChunk boundary: " + S(vector, "id"));
        }
        foreach (var vector in groups.GetProperty("streamFrameBytes").EnumerateArray())
        {
            Consume(vector, seen);
            var target = vector.GetProperty("serializedBytes").GetInt32();
            var frame = CreateFrame(target);
            var wire = frame.ToByteArray();
            Require(wire.Length == target && E.StreamFrame.Parser.ParseFrom(wire).CalculateSize() == target
                && (wire.Length <= vector.GetProperty("limit").GetInt32()) == vector.GetProperty("valid").GetBoolean(),
                "encoded StreamFrame boundary: " + S(vector, "id"));
        }
    }

    private static byte[] BuildArchiveRecordBytes(int target)
    {
        byte[] Build(int textLength) => new P.HistoryArchiveRecord
        {
            Message = new P.HistoryMessage
            {
                Ordinal = 1,
                CreatedAt = new F.Instant { UnixSeconds = 1 },
                Message = new P.MessageView
                {
                    MessageId = TestId(1),
                    ConversationId = TestId(2),
                    BranchId = TestId(3),
                    Role = "user",
                    State = "complete",
                    Revision = new F.Revision { Value = 1 },
                    Parts = { new P.MessagePart { Text = new string('x', textLength) } },
                },
            },
        }.ToByteArray();

        var low = 0;
        var high = target;
        while (low <= high)
        {
            var length = low + ((high - low) / 2);
            var bytes = Build(length);
            if (bytes.Length == target) return bytes;
            if (bytes.Length < target) low = length + 1;
            else high = length - 1;
        }
        throw new InvalidOperationException("Could not form exact sized protobuf archive-record vector.");
    }

    private static E.OutputChunk CreateChunk(int encodedBytes)
    {
        var baseValue = NewChunk(0);
        var baseSize = baseValue.CalculateSize();
        var low = 0;
        var high = 32768;
        while (low <= high)
        {
            var length = low + ((high - low) / 2);
            var size = baseSize + length + VarintSize((ulong)length) - 1;
            if (size == encodedBytes)
            {
                var value = NewChunk(length);
                Require(value.CalculateSize() == encodedBytes, "exact OutputChunk vector construction");
                return value;
            }
            if (size < encodedBytes) low = length + 1;
            else high = length - 1;
        }
        throw new InvalidOperationException("Could not form exact sized OutputChunk vector.");
    }

    private static E.StreamFrame CreateFrame(int encodedBytes)
    {
        var baseValue = NewFrame(0);
        var baseSize = baseValue.CalculateSize();
        var baseChunkSize = baseValue.Output.CalculateSize();
        for (var length = 0; length <= 32768; length++)
        {
            var dataDelta = length + VarintSize((ulong)length) - 1;
            var chunkSize = baseChunkSize + dataDelta;
            var size = baseSize + dataDelta + VarintSize((ulong)chunkSize) - VarintSize((ulong)baseChunkSize);
            if (size != encodedBytes) continue;
            var value = NewFrame(length);
            Require(value.CalculateSize() == encodedBytes, "exact StreamFrame vector construction");
            return value;
        }
        throw new InvalidOperationException("Could not form exact sized StreamFrame vector.");
    }

    private static E.OutputChunk NewChunk(int dataBytes)
    {
        var id = TestId();
        var data = new byte[dataBytes];
        return new E.OutputChunk
        {
            Execution = new P.ExecutionOwner { TaskId = id },
            Offset = 1,
            Data = ByteString.CopyFrom(data),
            ChunkHash = Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant(),
            Kind = "text",
            AttemptId = TestId(2),
            StreamId = TestId(3),
        };
    }

    private static E.StreamFrame NewFrame(int dataBytes) => new()
    {
        Meta = new F.ResponseMeta { CorrelationId = TestId(4) },
        Position = new E.StreamPosition { Cursor = "c", Sequence = 1, Generation = 1 },
        Output = NewChunk(dataBytes),
    };

    private static F.Id TestId(int suffix = 15) => new()
    {
        Value = ByteString.CopyFrom([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, checked((byte)suffix)]),
    };

    private static void CheckConstraintProfiles(JsonElement constraints)
    {
        var messages = constraints.GetProperty("messages");
        var turn = messages.GetProperty("arcforges.publicapi.v1.TransientTurnRequest").GetProperty("fields");
        Require(turn.GetProperty("mode").GetProperty("required").GetBoolean()
            && turn.GetProperty("mode").GetProperty("enumValues").EnumerateArray().Select(x => x.GetInt32()).SequenceEqual([1, 3]),
            "temporary turns exclude Cloud HistoryMode");
        var decision = messages.GetProperty("arcforges.events.v1.ApprovalResolved").GetProperty("fields").GetProperty("decision");
        Require(decision.GetProperty("enumValues").EnumerateArray().Select(x => x.GetInt32()).SequenceEqual([1, 2]),
            "approval decision rejects unspecified");
        var chunks = messages.GetProperty("arcforges.events.v1.OutputChunk").GetProperty("fields");
        Require(chunks.GetProperty("data").GetProperty("maxLength").GetInt32() == 32768
            && chunks.GetProperty("chunkHash").GetProperty("pattern").GetString() == "^[0-9a-f]{64}$",
            "OutputChunk byte/hash field bounds");
        Require(messages.GetProperty("arcforges.publicapi.v1.HistoryArchiveRecord").GetProperty("oneofRequired")
            .EnumerateArray().Select(x => x.GetString()).SequenceEqual(["record"]), "archive record has exactly one typed variant");
    }

    private static void CheckRequiredProtoPresence(JsonElement constraints)
    {
        foreach (var message in constraints.GetProperty("messages").EnumerateObject())
        {
            var descriptor = FindMessage(message.Name[(message.Name.LastIndexOf('.') + 1)..]);
            foreach (var field in message.Value.GetProperty("fields").EnumerateObject())
            {
                if (!field.Value.TryGetProperty("required", out var required) || !required.GetBoolean()) continue;
                var protoField = descriptor.Fields.Single(x => x.JsonName == field.Name);
                if (!protoField.IsRepeated)
                    Require(protoField.HasPresence, "required field has protobuf presence: " + message.Name + "." + field.Name);
            }
        }
    }

    private static void CheckLimits(JsonElement limits)
    {
        Require(limits.GetProperty("applicationListDefault").GetInt32() == 50
            && limits.GetProperty("applicationListMaximum").GetInt32() == 100
            && limits.GetProperty("eventPollDefault").GetInt32() == 50
            && limits.GetProperty("eventPollMaximum").GetInt32() == 200
            && limits.GetProperty("eventPollResponseBytes").GetInt32() == 262144
            && limits.GetProperty("outputReadMaximumChunks").GetInt32() == 100
            && limits.GetProperty("outputReadResponseBytes").GetInt32() == 262144
            && limits.GetProperty("encodedStreamFrameBytes").GetInt32() == 32768
            && limits.GetProperty("outputChunkBytes").GetInt32() == 32768
            && limits.GetProperty("cursorUtf8Bytes").GetInt32() == 4096
            && limits.GetProperty("archiveRecordBytes").GetInt32() == 1048576
            && limits.GetProperty("presenceExpirySeconds").GetInt32() == 30
            && limits.GetProperty("heartbeatRenewAfterSeconds").GetInt32() == 10
            && limits.GetProperty("transcriptMessages").GetInt32() == 2000
            && limits.GetProperty("transcriptParts").GetInt32() == 16000
            && limits.GetProperty("inlineTranscriptAndEnvelopeBytes").GetInt32() == 262144
            && limits.GetProperty("objectTranscriptBytes").GetInt32() == 8388608,
            "Annex10 pagination, presence, transcript and stream limits are frozen in the independent fixture");
    }

    private static MessageDescriptor FindMessage(string name)
    {
        return P.ApplicationReflection.Descriptor.MessageTypes.Concat(E.EventsReflection.Descriptor.MessageTypes)
            .Single(x => x.Name == name);
    }

    private static FileDescriptor FileForService(string name) => name.StartsWith("arcforges.publicapi.", StringComparison.Ordinal)
        ? P.ApplicationReflection.Descriptor : E.EventsReflection.Descriptor;

    private static void CheckFields(MessageDescriptor message, JsonElement fields, string label)
    {
        var expected = fields.EnumerateArray().Select(pair => (Name: pair[0].GetString()!, Number: pair[1].GetInt32())).ToArray();
        CheckFields(message, expected, label);
    }

    private static void CheckFields(MessageDescriptor message, IEnumerable<(string Name, int Number)> expectedFields, string label)
    {
        var expected = expectedFields.OrderBy(x => x.Number).ToArray();
        var actual = message.Fields.Select(field => (Name: field.JsonName, Number: field.FieldNumber))
            .OrderBy(x => x.Number).ToArray();
        Require(actual.SequenceEqual(expected), "exact field set/names/tags: " + label);
    }

    private static int VarintSize(ulong value)
    {
        var size = 1;
        while (value >= 128) { size++; value >>= 7; }
        return size;
    }

    private static string S(JsonElement value, string name) => value.GetProperty(name).GetString()!;
    private static void Consume(JsonElement vector, HashSet<string> seen) => Require(seen.Add(S(vector, "id")), "fixture vector consumed once: " + S(vector, "id"));
    private static void Require(bool condition, string label)
    {
        if (!condition) throw new InvalidOperationException("CON.11 fixture failed: " + label);
    }
}
