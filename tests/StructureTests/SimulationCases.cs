// SPDX-License-Identifier: Apache-2.0
using System.Globalization;
using System.Text.Json;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.Simulation.V1;
using ArcForges.Contracts.Validation;

internal static class SimulationCases
{
    internal static void Run(string root)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-21-simulation.json")));
        var fixture = document.RootElement;
        var operations = fixture.GetProperty("operations").EnumerateArray().ToArray();
        using var operationMetadata = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/operations/con-21.json")));
        var registeredOperations = operationMetadata.RootElement.GetProperty("operations").EnumerateArray().ToArray();
        Require(operations.Length == fixture.GetProperty("operationCount").GetInt32(), "operation count");
        Require(registeredOperations.Length == operations.Length, "registered operation count");
        Require(operations.Select(item => item.GetProperty("operationId").GetString()).Distinct(StringComparer.Ordinal).Count() == operations.Length,
            "unique operation identifiers");

        var service = SimulationReflection.Descriptor.Services.Single();
        Require(service.FullName == fixture.GetProperty("service").GetString(), "service identity");
        Require(service.Methods.Select(method => method.Name).SequenceEqual(operations.Select(item => item.GetProperty("method").GetString())),
            "exact 13-method descriptor inventory");
        foreach (var item in operations)
        {
            var operationId = item.GetProperty("operationId").GetString()!;
            var methodName = item.GetProperty("method").GetString()!;
            var registered = registeredOperations.Single(row => row.GetProperty("operationId").GetString() == operationId);
            var profile = fixture.GetProperty("operationProfile");
            Require(registered.GetProperty("binding").GetString() == service.FullName + "/" + methodName, operationId + ": binding");
            Require(registered.GetProperty("kind").GetString() == profile.GetProperty("kind").GetString()
                && registered.GetProperty("source").GetString() == profile.GetProperty("source").GetString()
                && registered.GetProperty("scope").GetString() == profile.GetProperty("scope").GetString()
                && registered.GetProperty("surface").GetString() == profile.GetProperty("surface").GetString()
                && registered.GetProperty("profile").GetString() == profile.GetProperty("profile").GetString()
                && registered.GetProperty("sourceRule").GetString() == profile.GetProperty("sourceRule").GetString()
                && registered.GetProperty("idempotency").GetString() == item.GetProperty("class").GetString(), operationId + ": operation profile");
            var idempotency = item.GetProperty("class").GetString();
            var expectedRisk = idempotency switch { "Q" or "NI" => "R1", "CC" or "IW" => "R2", _ => throw new InvalidOperationException("Unknown simulation idempotency class") };
            var expectedCompatibility = idempotency switch { "Q" => "AO", "CC" or "IW" or "NI" => "FR", _ => throw new InvalidOperationException("Unknown simulation idempotency class") };
            Require(item.GetProperty("risk").GetString() == expectedRisk
                && item.GetProperty("compatibility").GetString() == expectedCompatibility, operationId + ": compatibility classification");
            var authorization = registered.GetProperty("authorization");
            Require(profile.GetProperty("capability").ValueKind == JsonValueKind.Null
                && authorization.GetProperty("capability").ValueKind == JsonValueKind.Null
                && authorization.GetProperty("risk").GetString() == item.GetProperty("risk").GetString()
                && authorization.GetProperty("approval").GetString() == profile.GetProperty("approval").GetString()
                && authorization.GetProperty("stepUp").GetBoolean() == profile.GetProperty("stepUp").GetBoolean()
                && authorization.GetProperty("localPresence").GetBoolean() == profile.GetProperty("localPresence").GetBoolean()
                && authorization.GetProperty("egress").GetString() == profile.GetProperty("egress").GetString()
                && authorization.GetProperty("patEligible").GetBoolean() == profile.GetProperty("patEligible").GetBoolean()
                && Strings(authorization.GetProperty("actorKinds")).SequenceEqual(Strings(profile.GetProperty("actorKinds"))), operationId + ": authorization fields");

            var method = service.FindMethodByName(methodName)!;
            Require(!method.IsClientStreaming && !method.IsServerStreaming, item.GetProperty("operationId").GetString()! + ": unary");
            Require(method.InputType.FindFieldByNumber(1).MessageType.FullName == "arcforges.foundation.v1.RequestMeta", "request envelope");
            Require(method.OutputType.FindFieldByNumber(1).MessageType.FullName == "arcforges.foundation.v1.ResponseMeta", "response envelope");
            Require(BusinessFields(method.InputType).SequenceEqual(ExpectedFields(item.GetProperty("requestFields"))),
                item.GetProperty("operationId").GetString()! + ": request fields");
            Require(BusinessTagNumbers(method.InputType).SequenceEqual(
                Enumerable.Range(10, ExpectedFields(item.GetProperty("requestFields")).Length)),
                item.GetProperty("operationId").GetString()! + ": request tag allocation");
            var valueType = method.OutputType.FindFieldByNumber(2)?.MessageType;
            Require(valueType is not null, item.GetProperty("operationId").GetString()! + ": success value");
            Require(BusinessFields(valueType!).SequenceEqual(ExpectedFields(item.GetProperty("responseFields"))),
                item.GetProperty("operationId").GetString()! + ": response fields");
            Require(BusinessTagNumbers(valueType!).SequenceEqual(
                Enumerable.Range(10, ExpectedFields(item.GetProperty("responseFields")).Length)),
                item.GetProperty("operationId").GetString()! + ": response tag allocation");
            Require((method.OutputType.FindFieldByNumber(4) is not null) == item.GetProperty("encodedBody").GetBoolean(),
                item.GetProperty("operationId").GetString()! + ": read projection tag");
        }

        var states = Strings(fixture.GetProperty("states"));
        var rejectedStates = Strings(fixture.GetProperty("stateRejected"));
        var extents = Strings(fixture.GetProperty("extents"));
        var rejectedExtents = Strings(fixture.GetProperty("extentRejected"));
        Require(states.SequenceEqual(new[] { "queued", "starting", "running", "pausing", "paused", "stopping", "canceled", "succeeded", "failed" }),
            "closed simulation state values");
        Require(rejectedStates.SequenceEqual(new[] { "active", "completed", "cancelled", "unknown" }), "exact rejected state vectors");
        Require(rejectedStates.All(value => !states.Contains(value, StringComparer.Ordinal)), "state rejection vectors");
        Require(extents.SequenceEqual(new[] { "complete", "partial" }), "closed run extent values");
        Require(rejectedExtents.SequenceEqual(new[] { "terminal", "full", "unknown" }), "exact rejected extent vectors");
        Require(rejectedExtents.All(value => !extents.Contains(value, StringComparer.Ordinal)), "extent rejection vectors");

        Require(VectorIds(fixture.GetProperty("runExtentVectors")).SequenceEqual(new[] {
            "active-partial-prefix", "succeeded-complete-range", "canceled-partial-range", "unknown-state-refused", "unsupported-extent-refused"
        }), "exact run state/extent vectors");
        var baseRun = JsonParser.Default.Parse<SimulationRun>(fixture.GetProperty("runShapeBase").GetRawText());
        foreach (var item in fixture.GetProperty("runExtentVectors").EnumerateArray())
        {
            var run = baseRun.Clone();
            run.State = item.GetProperty("state").GetString()!;
            run.Extent = item.GetProperty("extent").GetString()!;
            run.LogicalEnd = ulong.Parse(item.GetProperty("logicalEnd").GetString()!, CultureInfo.InvariantCulture);
            Require(ContractShapeValidation.IsValid(run) == item.GetProperty("valid").GetBoolean(),
                item.GetProperty("id").GetString()!);
        }

        var profileVectors = fixture.GetProperty("profile").GetProperty("vectors");
        Require(VectorIds(profileVectors).SequenceEqual(new[] {
            "minimum-profile", "maximum-batch-profile", "zero-sample-count-refused", "zero-batch-refused",
            "oversized-batch-refused", "zero-rate-denominator-refused", "unsupported-execution-profile-refused"
        }), "exact profile vectors");
        foreach (var item in profileVectors.EnumerateArray())
        {
            bool valid = TryValid(item.GetProperty("value"), SimulationProfile.Parser, ContractShapeValidation.IsValid);
            Require(valid == item.GetProperty("valid").GetBoolean(), item.GetProperty("id").GetString()!);
        }
        var astVectors = fixture.GetProperty("astVectors");
        Require(VectorIds(astVectors).SequenceEqual(new[] {
            "constant-expression", "variable-expression", "unary-expression", "binary-expression", "function-expression",
            "unrecognized-expression", "missing-expression", "multiple-oneof-arms-refused"
        }), "exact AST vectors");
        foreach (var item in astVectors.EnumerateArray())
        {
            bool valid = TryValid(item.GetProperty("value"), AstNode.Parser, ContractShapeValidation.IsValid);
            Require(valid == item.GetProperty("valid").GetBoolean(), item.GetProperty("id").GetString()!);
        }

        var pageLimits = fixture.GetProperty("listRuns").GetProperty("pageLimits");
        Require(VectorIds(pageLimits).SequenceEqual(new[] { "default", "minimum", "maximum", "zero", "above-maximum" }), "exact page bound vectors");
        foreach (var item in pageLimits.EnumerateArray())
        {
            var page = new PageRequest();
            if (item.GetProperty("limit").ValueKind != JsonValueKind.Null)
                page.Limit = item.GetProperty("limit").GetUInt32();
            Require(ContractShapeValidation.IsValid(page) == item.GetProperty("valid").GetBoolean(), item.GetProperty("id").GetString()!);
        }

        var listRuns = fixture.GetProperty("listRuns");
        var authorization = listRuns.GetProperty("authorization");
        Require(authorization.GetProperty("membership").GetString() == "current-workspace", "current workspace authorization scope");
        Require(authorization.GetProperty("role").GetString() == "read" && authorization.GetProperty("productId").GetString() == "arcscope",
            "read authorization owner");
        Require(authorization.GetProperty("recheckEveryPage").GetBoolean(), "authorization rechecked for each page");
        Require(Strings(listRuns.GetProperty("filters")).SequenceEqual(new[] { "exact scenarioVersionId", "exact simulation_run state" }), "exact list filters");
        Require(Strings(listRuns.GetProperty("order")).SequenceEqual(new[] { "createdAt descending", "runId descending" }), "deterministic list order");
        Require(Strings(listRuns.GetProperty("pageStateBinds")).SequenceEqual(
            new[] { "realm", "workspace", "actor", "recoveryGeneration", "filters", "sort", "schema", "snapshot" }),
            "snapshot-bound continuation");
        Require(listRuns.GetProperty("includesRetainedPartialAndTerminalRuns").GetBoolean()
            && !listRuns.GetProperty("requiresKnownRunId").GetBoolean()
            && !listRuns.GetProperty("requiresTerminalNotification").GetBoolean(), "fresh discovery and retained runs");

        Require(Strings(fixture.GetProperty("generatorKinds")).SequenceEqual(
            new[] { "constant", "sine", "square", "triangle", "sawtooth", "noise", "randomWalk", "pulse", "stepSequence", "csv" }),
            "closed generator vocabulary");
        Require(Strings(fixture.GetProperty("faultKinds")).SequenceEqual(
            new[] { "latency", "jitter", "drop", "duplicate", "reorder", "disconnect", "malformed", "outlier" }),
            "closed fault vocabulary");
        Console.WriteLine("CON.21 exact SimulationService descriptor, profile/AST/page vectors, and listRuns declaration passed; no simulator runtime executed.");
    }

    private static string[] BusinessFields(MessageDescriptor descriptor) => descriptor.Fields.InFieldNumberOrder()
        .Where(field => field.FieldNumber >= 10).Select(field => field.JsonName).ToArray();

    private static int[] BusinessTagNumbers(MessageDescriptor descriptor) => descriptor.Fields.InFieldNumberOrder()
        .Where(field => field.FieldNumber >= 10).Select(field => field.FieldNumber).ToArray();

    private static string[] ExpectedFields(JsonElement value) => Strings(value).Select(name => name.EndsWith("?", StringComparison.Ordinal) ? name[..^1] : name).ToArray();

    private static string[] Strings(JsonElement value) => value.EnumerateArray().Select(item => item.GetString()!).ToArray();

    private static string[] VectorIds(JsonElement value) => value.EnumerateArray()
        .Select(item => item.GetProperty("id").GetString()!).ToArray();

    private static bool TryValid<T>(JsonElement value, MessageParser<T> parser, Func<T, bool> validate) where T : IMessage<T>
    {
        try { return validate(parser.Parse(value.GetRawText())); }
        catch (InvalidProtocolBufferException) { return false; }
        catch (InvalidJsonException) { return false; }
        catch (FormatException) { return false; }
    }

    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("CON.21 fixture failed: " + name);
    }
}
