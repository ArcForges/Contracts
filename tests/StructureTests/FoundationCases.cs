// SPDX-License-Identifier: Apache-2.0
using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Google.Protobuf;
using F = ArcForges.Contracts.Foundation.V1;
using P = ArcForges.Contracts.PublicApi.V1;
using V = ArcForges.Contracts.Foundation.Values;
using DocumentId = ArcForges.Contracts.PublicApi.Values.DocumentId;
using ResourceId = ArcForges.Contracts.Foundation.Values.ResourceId;
using Validation = ArcForges.Contracts.Validation.ContractShapeValidation;

internal static class FoundationCases
{
    public static void Run(string root, bool exchange)
    {
        var path = Path.Combine(root, "fixtures", "public", "wp03-01.json");
        var bytes = File.ReadAllBytes(path);
        var fixture = JsonNode.Parse(bytes)!.AsObject();
        var samples = fixture["samples"]!.AsObject();
        Require(samples["RichText"]!["text"]!.GetValue<string>() == "A\u4e2d\ud83d\ude00", "The registry UTF-16 oracle must survive fixture encoding.");
        var cases = fixture["cases"]!.AsArray();
        var errors = new List<string>();
        var ids = new HashSet<string>(StringComparer.Ordinal);
        var names = new HashSet<string>(StringComparer.Ordinal);
        var output = new JsonArray();
        foreach (var node in cases)
        {
            var item = node!.AsObject();
            var id = item["id"]!.GetValue<string>();
            Require(ids.Add(id), "Duplicate fixture id: " + id);
            var target = item["target"]!.GetValue<string>();
            var value = Materialize(item, samples);
            var expected = item["valid"]!.GetValue<bool>();
            var observation = Dispatch(target, value, null);
            var actual = observation.Valid;
            if (actual != expected) { errors.Add(id + ": expected " + expected + ", received " + actual); continue; }
            if (!expected) continue;
            names.Add(target);
            var decoded = Dispatch(target, null, Convert.FromHexString(observation.Hex));
            Require(decoded.Valid && JsonNode.DeepEquals(decoded.Json, observation.Json), id + ": semantic round trip");
            output.Add((JsonNode)new JsonObject { ["id"] = id, ["target"] = target, ["binaryHex"] = observation.Hex, ["json"] = observation.Json.DeepClone() });
        }
        Require(errors.Count == 0, "Independent foundation fixture failures:\n" + string.Join("\n", errors));
        Require(names.SetEquals(samples.Select(p => p.Key).Where(n => !n.StartsWith('$'))), "Every selected record needs a valid semantic round trip.");
        Require(fixture["aggregateVariants"]!.AsObject().Count == 16, "All owner-body branches must remain covered.");
        Require(fixture["errorCategories"]!.AsObject().Count == 45, "All initial error codes must remain covered.");
        foreach (var node in fixture["profileScenarios"]!.AsArray())
        {
            var scenario = node!.AsObject();
            var evidence = scenario["expectedCaseIds"]!.AsArray();
            Require(evidence.Count > 0 && evidence.All(id => ids.Contains(id!.GetValue<string>())), "Profile scenario lacks declared wire fixture evidence.");
            Require(scenario["evidenceBoundary"]!.GetValue<string>().Contains("pending", StringComparison.Ordinal), "Profile fixtures must preserve their pending owner boundary.");
        }
        foreach (var node in fixture["wireVectors"]!.AsArray())
        {
            var item = node!.AsObject();
            var target = item["target"]!.GetValue<string>();
            var expected = item["hex"]!.GetValue<string>();
            var authored = Dispatch(target, item["value"]!, null);
            Require(authored.Hex == expected, item["id"]!.GetValue<string>() + ": independent wire bytes");
            var decoded = Dispatch(target, null, Convert.FromHexString(expected));
            Require(JsonNode.DeepEquals(decoded.Json, authored.Json), item["id"]!.GetValue<string>() + ": independent binary decode");
        }
        BoundaryValues();
        UnknownReadPreservation(samples);
        if (exchange)
        {
            var directory = Path.Combine(root, "artifacts", "tests", "foundation");
            Directory.CreateDirectory(directory);
            var document = new JsonObject { ["fixtureDigest"] = Convert.ToHexStringLower(SHA256.HashData(bytes)), ["cases"] = output };
            File.WriteAllText(Path.Combine(directory, "csharp.json"), document.ToJsonString());
        }
        Console.WriteLine($"Validated {cases.Count} independent C# foundation cases, {names.Count} records, 16 owner bodies, 45 error categories and {fixture["wireVectors"]!.AsArray().Count} binary oracles.");
    }

    public static void VerifyExchange(string root)
    {
        var fixtureBytes = File.ReadAllBytes(Path.Combine(root, "fixtures", "public", "wp03-01.json"));
        var fixture = JsonNode.Parse(fixtureBytes)!.AsObject();
        var samples = fixture["samples"]!.AsObject();
        var expected = fixture["cases"]!.AsArray().Select(n => n!.AsObject()).Where(n => n["valid"]!.GetValue<bool>()).ToDictionary(n => n["id"]!.GetValue<string>(), StringComparer.Ordinal);
        var incoming = JsonNode.Parse(File.ReadAllText(Path.Combine(root, "artifacts", "tests", "foundation", "typescript.json")))!.AsObject();
        Require(incoming["fixtureDigest"]!.GetValue<string>() == Convert.ToHexStringLower(SHA256.HashData(fixtureBytes)), "Exchange uses current independent fixtures.");
        var cases = incoming["cases"]!.AsArray();
        Require(cases.Count == expected.Count, "TypeScript covers every positive fixture.");
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var node in cases)
        {
            var item = node!.AsObject();
            var id = item["id"]!.GetValue<string>();
            Require(seen.Add(id) && expected.ContainsKey(id), "Unexpected TypeScript exchange id " + id);
            var reference = expected[id];
            var target = reference["target"]!.GetValue<string>();
            Require(target == item["target"]!.GetValue<string>(), "Exchange target mismatch: " + id);
            var authored = Dispatch(target, Materialize(reference, samples), null);
            var decoded = Dispatch(target, null, Convert.FromHexString(item["binaryHex"]!.GetValue<string>()));
            Require(decoded.Valid && JsonNode.DeepEquals(decoded.Json, authored.Json), id + ": TypeScript to C#");
        }
        Console.WriteLine($"Verified {cases.Count} TypeScript-to-C# independent fixture exchanges without repeating the full suite.");
    }

    private static JsonNode Expand(JsonNode node, JsonObject samples, HashSet<string>? stack = null)
    {
        stack ??= new HashSet<string>(StringComparer.Ordinal);
        if (node is JsonObject record && record.TryGetPropertyValue("$ref", out var reference))
        {
            var name = reference!.GetValue<string>();
            Require(record.Count == 1 && samples.ContainsKey(name) && stack.Add(name), "Invalid or recursive fixture reference: " + name);
            var result = Expand(samples[name]!, samples, stack);
            stack.Remove(name);
            return result;
        }
        if (node is JsonArray array)
        {
            var result = new JsonArray();
            foreach (var child in array) result.Add(child is null ? null : Expand(child, samples, stack));
            return result;
        }
        if (node is JsonObject obj)
        {
            var result = new JsonObject();
            foreach (var pair in obj) result[pair.Key] = pair.Value is null ? null : Expand(pair.Value, samples, stack);
            return result;
        }
        return node.DeepClone();
    }

    private static JsonNode Materialize(JsonObject item, JsonObject samples)
    {
        var value = Expand(item["value"] ?? samples[item["sample"]!.GetValue<string>()]!, samples);
        if (item["set"] is JsonObject changes)
        {
            foreach (var pair in changes)
            {
                var (parent, key) = Parent(value, pair.Key);
                var replacement = pair.Value is null ? null : Expand(pair.Value, samples);
                if (parent is JsonArray array) array[int.Parse(key, CultureInfo.InvariantCulture)] = replacement;
                else parent[key] = replacement;
            }
        }
        if (item["remove"] is JsonArray removals)
        {
            foreach (var removal in removals)
            {
                var (parent, key) = Parent(value, removal!.GetValue<string>());
                Require(parent is JsonObject obj && obj.Remove(key), "Unknown fixture removal path.");
            }
        }
        return value;
    }

    private static (JsonNode Parent, string Key) Parent(JsonNode node, string path)
    {
        var parts = path.Split('.');
        for (var i = 0; i < parts.Length - 1; i++) node = node is JsonArray array ? array[int.Parse(parts[i], CultureInfo.InvariantCulture)]! : node[parts[i]]!;
        return (node, parts[^1]);
    }

    private sealed record Observation(bool Valid, string Hex, JsonNode Json);
    private static Observation Check<T>(JsonNode? json, byte[]? binary, Func<T, bool> validate) where T : IMessage<T>, new()
    {
        var parser = new MessageParser<T>(() => new T());
        T message;
        try { message = binary is null ? JsonParser.Default.Parse<T>(json!.ToJsonString()) : parser.ParseFrom(binary); }
        catch (Exception e) when (e is InvalidProtocolBufferException or InvalidJsonException or FormatException or OverflowException or ArgumentException)
        {
            return new Observation(false, "", new JsonObject());
        }
        // Semantic validator exceptions are defects, not successful negatives.
        return new Observation(validate(message), Convert.ToHexStringLower(message.ToByteArray()), JsonNode.Parse(JsonFormatter.Default.Format(message))!);
    }

    // This static dispatch is authored against the independent fixture inventory.
    // No runtime discovery or production schema generates fixture expectations.
    private static Observation Dispatch(string target, JsonNode? json, byte[]? binary) => target switch
    {
        "ActorChain" => Check<F.ActorChain>(json, binary, Validation.IsValid),
        "AgentProfile" => Check<P.AgentProfile>(json, binary, Validation.IsValid),
        "AggregateBody" => Check<P.AggregateBody>(json, binary, Validation.IsValid),
        "AggregateRef" => Check<F.AggregateRef>(json, binary, Validation.IsValid),
        "AlignmentSpec" => Check<P.AlignmentSpec>(json, binary, Validation.IsValid),
        "ApplicationScope" => Check<F.ApplicationScope>(json, binary, Validation.IsValid),
        "ArcError" => Check<F.ArcError>(json, binary, Validation.IsValid),
        "ArtifactRef" => Check<F.ArtifactRef>(json, binary, Validation.IsValid),
        "AutomationSpec" => Check<P.AutomationSpec>(json, binary, Validation.IsValid),
        "AutomationView" => Check<P.AutomationView>(json, binary, Validation.IsValid),
        "BlobRef" => Check<F.BlobRef>(json, binary, Validation.IsValid),
        "Block" => Check<P.Block>(json, binary, Validation.IsValid),
        "BlockBody" => Check<P.BlockBody>(json, binary, Validation.IsValid),
        "BlockProperties" => Check<P.BlockProperties>(json, binary, Validation.IsValid),
        "ByteRange" => Check<F.ByteRange>(json, binary, Validation.IsValid),
        "Calibration" => Check<P.Calibration>(json, binary, Validation.IsValid),
        "CapabilityArguments" => Check<P.CapabilityArguments>(json, binary, Validation.IsValid),
        "CapabilityResult" => Check<P.CapabilityResult>(json, binary, Validation.IsValid),
        "CaptureMetadata" => Check<P.CaptureMetadata>(json, binary, Validation.IsValid),
        "ChannelDefinition" => Check<P.ChannelDefinition>(json, binary, Validation.IsValid),
        "ChatProjectRecord" => Check<P.ChatProjectRecord>(json, binary, Validation.IsValid),
        "ChecksumSpec" => Check<P.ChecksumSpec>(json, binary, Validation.IsValid),
        "CodeBlock" => Check<P.CodeBlock>(json, binary, Validation.IsValid),
        "ColourConfiguration" => Check<P.ColourConfiguration>(json, binary, Validation.IsValid),
        "ContentOrigin" => Check<F.ContentOrigin>(json, binary, Validation.IsValid),
        "ContextRef" => Check<P.ContextRef>(json, binary, Validation.IsValid),
        "ContextSelector" => Check<P.ContextSelector>(json, binary, Validation.IsValid),
        "ControlProgress" => Check<P.ControlProgress>(json, binary, Validation.IsValid),
        "ConversationBody" => Check<P.ConversationBody>(json, binary, Validation.IsValid),
        "ConversationView" => Check<P.ConversationView>(json, binary, Validation.IsValid),
        "CursorResult" => Check<P.CursorResult>(json, binary, Validation.IsValid),
        "CursorSpec" => Check<P.CursorSpec>(json, binary, Validation.IsValid),
        "Decimal" => Check<F.Decimal>(json, binary, Validation.IsValid),
        "EffectParameter" => Check<P.EffectParameter>(json, binary, Validation.IsValid),
        "EffectSpec" => Check<P.EffectSpec>(json, binary, Validation.IsValid),
        "EphemeralSelection" => Check<P.EphemeralSelection>(json, binary, Validation.IsValid),
        "ErrorDetails" => Check<F.ErrorDetails>(json, binary, Validation.IsValid),
        "EventTrigger" => Check<P.EventTrigger>(json, binary, Validation.IsValid),
        "FamilyResult" => Check<P.FamilyResult>(json, binary, Validation.IsValid),
        "FilterGroup" => Check<P.FilterGroup>(json, binary, Validation.IsValid),
        "FolderView" => Check<P.FolderView>(json, binary, Validation.IsValid),
        "FrameConfiguration" => Check<P.FrameConfiguration>(json, binary, Validation.IsValid),
        "FrameField" => Check<P.FrameField>(json, binary, Validation.IsValid),
        "GeneratedSource" => Check<P.GeneratedSource>(json, binary, Validation.IsValid),
        "Id" => Check<F.Id>(json, binary, Validation.IsValid),
        "IdList" => Check<P.IdList>(json, binary, Validation.IsValid),
        "ImageLayout" => Check<P.ImageLayout>(json, binary, Validation.IsValid),
        "InlineAtom" => Check<P.InlineAtom>(json, binary, Validation.IsValid),
        "Instant" => Check<F.Instant>(json, binary, Validation.IsValid),
        "Keyframe" => Check<P.Keyframe>(json, binary, Validation.IsValid),
        "KeyframeList" => Check<P.KeyframeList>(json, binary, Validation.IsValid),
        "LimitFailure" => Check<F.LimitFailure>(json, binary, Validation.IsValid),
        "LinkSpec" => Check<P.LinkSpec>(json, binary, Validation.IsValid),
        "LocalNotesVersion" => Check<F.LocalNotesVersion>(json, binary, Validation.IsValid),
        "MarkerView" => Check<P.MarkerView>(json, binary, Validation.IsValid),
        "MathContent" => Check<P.MathContent>(json, binary, Validation.IsValid),
        "MeasurementRequest" => Check<P.MeasurementRequest>(json, binary, Validation.IsValid),
        "MeasurementResult" => Check<P.MeasurementResult>(json, binary, Validation.IsValid),
        "MeasurementSource" => Check<P.MeasurementSource>(json, binary, Validation.IsValid),
        "MeasurementThreshold" => Check<P.MeasurementThreshold>(json, binary, Validation.IsValid),
        "MeasurementValue" => Check<P.MeasurementValue>(json, binary, Validation.IsValid),
        "MeasurementWindow" => Check<P.MeasurementWindow>(json, binary, Validation.IsValid),
        "MediaBin" => Check<P.MediaBin>(json, binary, Validation.IsValid),
        "MediaColourAssignment" => Check<P.MediaColourAssignment>(json, binary, Validation.IsValid),
        "MediaRange" => Check<F.MediaRange>(json, binary, Validation.IsValid),
        "MediaStream" => Check<P.MediaStream>(json, binary, Validation.IsValid),
        "MediaTime" => Check<F.MediaTime>(json, binary, Validation.IsValid),
        "MediaView" => Check<P.MediaView>(json, binary, Validation.IsValid),
        "MemoryRecord" => Check<P.MemoryRecord>(json, binary, Validation.IsValid),
        "MessageDraft" => Check<P.MessageDraft>(json, binary, Validation.IsValid),
        "MessagePart" => Check<P.MessagePart>(json, binary, Validation.IsValid),
        "MessageView" => Check<P.MessageView>(json, binary, Validation.IsValid),
        "MetadataEntry" => Check<P.MetadataEntry>(json, binary, Validation.IsValid),
        "MetadataScalar" => Check<P.MetadataScalar>(json, binary, Validation.IsValid),
        "NativeContentRev" => Check<F.NativeContentRev>(json, binary, Validation.IsValid),
        "NotebookBody" => Check<P.NotebookBody>(json, binary, Validation.IsValid),
        "NotebookView" => Check<P.NotebookView>(json, binary, Validation.IsValid),
        "NotesDocument" => Check<P.NotesDocument>(json, binary, Validation.IsValid),
        "NotesFilter" => Check<P.NotesFilter>(json, binary, Validation.IsValid),
        "NotesQuery" => Check<P.NotesQuery>(json, binary, Validation.IsValid),
        "NotesSelection" => Check<P.NotesSelection>(json, binary, Validation.IsValid),
        "NotesSelectors" => Check<P.NotesSelectors>(json, binary, Validation.IsValid),
        "NotesSort" => Check<P.NotesSort>(json, binary, Validation.IsValid),
        "NotesTextPosition" => Check<P.NotesTextPosition>(json, binary, Validation.IsValid),
        "PageRequest" => Check<F.PageRequest>(json, binary, Validation.IsValid),
        "PageState" => Check<F.PageState>(json, binary, Validation.IsValid),
        "PreferenceRecord" => Check<P.PreferenceRecord>(json, binary, Validation.IsValid),
        "ProcessingEdge" => Check<P.ProcessingEdge>(json, binary, Validation.IsValid),
        "ProcessingGraph" => Check<P.ProcessingGraph>(json, binary, Validation.IsValid),
        "PropertyDefinition" => Check<P.PropertyDefinition>(json, binary, Validation.IsValid),
        "PropertyDefinitionVersion" => Check<P.PropertyDefinitionVersion>(json, binary, Validation.IsValid),
        "PropertyValue" => Check<P.PropertyValue>(json, binary, Validation.IsValid),
        "Rational" => Check<F.Rational>(json, binary, Validation.IsValid),
        "Receipt" => Check<F.Receipt>(json, binary, Validation.IsValid),
        "RenderPreset" => Check<P.RenderPreset>(json, binary, Validation.IsValid),
        "RequestMeta" => Check<F.RequestMeta>(json, binary, Validation.IsValid),
        "ResourceRef" => Check<F.ResourceRef>(json, binary, Validation.IsValid),
        "ResourceVersionRef" => Check<F.ResourceVersionRef>(json, binary, Validation.IsValid),
        "ResponseMeta" => Check<F.ResponseMeta>(json, binary, Validation.IsValid),
        "RetimeCurve" => Check<P.RetimeCurve>(json, binary, Validation.IsValid),
        "RetimePoint" => Check<P.RetimePoint>(json, binary, Validation.IsValid),
        "RetryAdvice" => Check<F.RetryAdvice>(json, binary, Validation.IsValid),
        "Revision" => Check<F.Revision>(json, binary, Validation.IsValid),
        "RevisionConflict" => Check<F.RevisionConflict>(json, binary, Validation.IsValid),
        "RichText" => Check<P.RichText>(json, binary, Validation.IsValid),
        "SampleRange" => Check<P.SampleRange>(json, binary, Validation.IsValid),
        "SavedViewRecord" => Check<P.SavedViewRecord>(json, binary, Validation.IsValid),
        "ScalarPredicate" => Check<P.ScalarPredicate>(json, binary, Validation.IsValid),
        "ScalarValue" => Check<P.ScalarValue>(json, binary, Validation.IsValid),
        "ScheduleSpec" => Check<P.ScheduleSpec>(json, binary, Validation.IsValid),
        "ScopeAnnotation" => Check<P.ScopeAnnotation>(json, binary, Validation.IsValid),
        "ScopeConfiguration" => Check<P.ScopeConfiguration>(json, binary, Validation.IsValid),
        "ScopeFinding" => Check<P.ScopeFinding>(json, binary, Validation.IsValid),
        "ScopeMetadata" => Check<P.ScopeMetadata>(json, binary, Validation.IsValid),
        "ScopeSelection" => Check<P.ScopeSelection>(json, binary, Validation.IsValid),
        "ScopeTime" => Check<P.ScopeTime>(json, binary, Validation.IsValid),
        "SelectOption" => Check<P.SelectOption>(json, binary, Validation.IsValid),
        "SelectedSample" => Check<P.SelectedSample>(json, binary, Validation.IsValid),
        "SequenceView" => Check<P.SequenceView>(json, binary, Validation.IsValid),
        "SkillRecord" => Check<P.SkillRecord>(json, binary, Validation.IsValid),
        "SlateMetadata" => Check<P.SlateMetadata>(json, binary, Validation.IsValid),
        "SlateSelection" => Check<P.SlateSelection>(json, binary, Validation.IsValid),
        "SourceConsentRef" => Check<P.SourceConsentRef>(json, binary, Validation.IsValid),
        "StateFailure" => Check<F.StateFailure>(json, binary, Validation.IsValid),
        "StructuredValue" => Check<P.StructuredValue>(json, binary, Validation.IsValid),
        "TableBlock" => Check<P.TableBlock>(json, binary, Validation.IsValid),
        "TableCell" => Check<P.TableCell>(json, binary, Validation.IsValid),
        "TableRow" => Check<P.TableRow>(json, binary, Validation.IsValid),
        "TagRecord" => Check<P.TagRecord>(json, binary, Validation.IsValid),
        "TaskSnapshot" => Check<P.TaskSnapshot>(json, binary, Validation.IsValid),
        "TextRunSegment" => Check<P.TextRunSegment>(json, binary, Validation.IsValid),
        "TextSpan" => Check<P.TextSpan>(json, binary, Validation.IsValid),
        "TimeRangeUtc" => Check<F.TimeRangeUtc>(json, binary, Validation.IsValid),
        "TimedText" => Check<P.TimedText>(json, binary, Validation.IsValid),
        "TimelineClip" => Check<P.TimelineClip>(json, binary, Validation.IsValid),
        "TimelineTrack" => Check<P.TimelineTrack>(json, binary, Validation.IsValid),
        "TimelineView" => Check<P.TimelineView>(json, binary, Validation.IsValid),
        "ToolProposal" => Check<P.ToolProposal>(json, binary, Validation.IsValid),
        "ToolResult" => Check<P.ToolResult>(json, binary, Validation.IsValid),
        "TransitionSpec" => Check<P.TransitionSpec>(json, binary, Validation.IsValid),
        "TriggerConfiguration" => Check<P.TriggerConfiguration>(json, binary, Validation.IsValid),
        "TriggerSpec" => Check<P.TriggerSpec>(json, binary, Validation.IsValid),
        "TurnInput" => Check<P.TurnInput>(json, binary, Validation.IsValid),
        "ValueEntry" => Check<P.ValueEntry>(json, binary, Validation.IsValid),
        "ValueList" => Check<P.ValueList>(json, binary, Validation.IsValid),
        "ValueRecord" => Check<P.ValueRecord>(json, binary, Validation.IsValid),
        "VersionFailure" => Check<F.VersionFailure>(json, binary, Validation.IsValid),
        "VersionedRef" => Check<F.VersionedRef>(json, binary, Validation.IsValid),
        _ => throw new InvalidOperationException("Unregistered foundation fixture target " + target),
    };

    private static void UnknownReadPreservation(JsonObject samples)
    {
        var unknown = Convert.FromHexString("0800a00607");
        var retained = V.ReadProjection<F.NativeContentRev>.Parse(F.NativeContentRev.Parser, unknown, Validation.IsValid);
        Require(retained.KnownProfile && retained.Preserve().SequenceEqual(unknown), "Unknown read fields must survive a known profile.");
        var future = Expand(samples["ContentOrigin"]!, samples);
        future["profile"] = "arcforges.content-origin.v2";
        var message = JsonParser.Default.Parse<F.ContentOrigin>(future.ToJsonString());
        var bytes = message.ToByteArray();
        var decoded = V.ReadProjection<F.ContentOrigin>.Parse(F.ContentOrigin.Parser, bytes, Validation.IsValid);
        Require(!decoded.KnownProfile && decoded.Preserve().SequenceEqual(bytes), "Unknown origin version must remain readable and unwritable.");
    }

    private static void BoundaryValues()
    {
        var uuid = Guid.Parse("00112233-4455-6677-8899-aabbccddeeff");
        var domain = new DocumentId(uuid);
        Require(Convert.ToHexStringLower(domain.ToWire().Value.Span) == "00112233445566778899aabbccddeeff", "Canonical UUID network order.");
        Require(DocumentId.FromWire(domain.ToWire()) == domain, "Domain identity round trip.");
        Require(typeof(DocumentId) != typeof(ResourceId), "Identifier domains must remain distinct types.");
        Require(!typeof(DocumentId).GetMethods().Any(m => m.Name == "op_Implicit"), "Document identity must have no implicit conversion.");
        var mutable = Convert.FromHexString("00112233445566778899aabbccddeeff");
        var wire = new F.Id { Value = ByteString.CopyFrom(mutable) };
        var safe = DocumentId.FromWire(wire);
        mutable[0] = 255;
        wire.Value = ByteString.CopyFrom(new byte[16]);
        Require(safe == domain, "Identity conversion cannot retain mutable external state.");
        Throws<ArgumentException>(() => new DocumentId(Guid.Empty));
        Throws<ArgumentException>(() => default(DocumentId).ToWire());
        Throws<ArgumentException>(() => V.UuidBoundary.FromWire(new F.Id()));
        Require(V.ExactInteger.ParseInt64("-9223372036854775808") == long.MinValue, "Signed minimum.");
        Require(V.ExactInteger.ParseInt64("9223372036854775807") == long.MaxValue, "Signed maximum.");
        Require(V.ExactInteger.ParseUInt64("18446744073709551615") == ulong.MaxValue, "Unsigned maximum.");
        foreach (var text in new[] { "+1", "01", "-0", "1e3", " 1", "1\n", "1\r", "1\u2028", "9223372036854775808" }) Throws<FormatException>(() => V.ExactInteger.ParseInt64(text));
        foreach (var text in new[] { "-1", "01", "18446744073709551616" }) Throws<FormatException>(() => V.ExactInteger.ParseUInt64(text));
        Require(new V.CloudRevision(9007199254740993).ToWire().Value == 9007199254740993, "Exact committed revision.");
        Throws<ArgumentOutOfRangeException>(() => new V.CloudRevision(0));
        Throws<InvalidOperationException>(() => default(V.CloudRevision).ToWire());
        Require(V.CloudRevision.NewRootPrecondition().HasValue && V.CloudRevision.NewRootPrecondition().Value == 0, "Explicit new-root zero.");
        Require(new V.NativeRevision(ulong.MaxValue).ToWire().Value == ulong.MaxValue, "Exact native token.");
        var local = new V.LocalNotesToken(0, ulong.MaxValue);
        Require(V.LocalNotesToken.FromWire(local.ToWire()) == local, "Local pending sequence survives.");
        Require(V.DeliverySequence.Parse("18446744073709551615").Value == ulong.MaxValue, "Exact delivery sequence.");
        var decimalValue = V.ExactDecimal.FromNotes("-0.000000001");
        Require(decimalValue.Coefficient == BigInteger.MinusOne && decimalValue.Scale == 9, "Exact coefficient/scale.");
        Require(V.ExactDecimal.FromCoefficient(BigInteger.One, 9).ToWire().Value == "0.000000001", "Ninth decimal place.");
        Require(new V.ExactDecimal("1.00").Scale == 2, "Shared decimals preserve declared scale.");
        foreach (var text in new[] { "1.0", "-0", "+1", "1e3", "0.0000000001", "1\n", "1\r", "1\u2028" }) Throws<FormatException>(() => V.ExactDecimal.FromNotes(text));
        Throws<InvalidOperationException>(() => default(V.ExactDecimal).ToWire());
        Require(new V.OpaqueCursor(string.Concat(Enumerable.Repeat("😀", 1024))).Value.Length == 2048, "Cursor uses byte bounds.");
        Throws<ArgumentOutOfRangeException>(() => new V.OpaqueCursor(string.Concat(Enumerable.Repeat("😀", 1025))));
        Throws<InvalidOperationException>(() => default(V.OpaqueCursor).ToWire());
        var wideRate = new V.RationalValue(long.MaxValue, ulong.MaxValue);
        Require(V.RationalValue.ConvertTicksExact(long.MaxValue, wideRate, wideRate) == long.MaxValue, "Wide intermediates retain exact ticks.");
        Require(V.RationalValue.ConvertTicksExact(48000, new(48000, 1), new(705600000, 1)) == 705600000, "One audio second converts exactly to media ticks.");
        Require(V.RationalValue.FromWire(wideRate.ToWire()) == wideRate, "Exact rational wire components.");
        Throws<OverflowException>(() => V.RationalValue.ConvertTicksExact(1, new(3, 1), new(1, 1)));
        Throws<OverflowException>(() => V.RationalValue.ConvertTicksExact(long.MaxValue, new(1, 1), new(2, 1)));
        Throws<ArgumentException>(() => new V.RationalValue(1, 0));
        Throws<ArgumentException>(() => new V.RationalValue(2, 4));
        Throws<InvalidOperationException>(() => default(V.RationalValue).ToWire());
        Throws<ArgumentException>(() => V.RationalValue.FromWire(new F.Rational { Numerator = 1 }));
        Throws<ArgumentException>(() => V.RationalValue.ConvertTicksExact(1, default, new(1, 1)));
        Throws<ArgumentException>(() => V.RationalValue.ConvertTicksExact(1, new(0, 1), new(1, 1)));
    }

    private static void Throws<T>(Action action) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new InvalidOperationException("Expected " + typeof(T).Name + ".");
    }
    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
