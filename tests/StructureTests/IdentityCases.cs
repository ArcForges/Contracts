// SPDX-License-Identifier: Apache-2.0
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using ArcForges.Contracts.Foundation.Serialization;
using ArcForges.Contracts.PublicApi.Http.V1.Browser;
using ArcForges.Contracts.PublicApi.Http.V1.NativeAuth;
using ArcForges.Contracts.PublicApi.V1;
using ArcForges.Contracts.Validation;
using Google.Protobuf;
using Google.Protobuf.Reflection;

/// <summary>CON.07 independent identity, workspace, device and authentication-exception vectors for generated C#.</summary>
internal static class IdentityCases
{
    private static readonly Assembly PublicApi = typeof(IdentityReflection).Assembly;
    private static readonly Assembly Validation = typeof(ContractShapeValidation).Assembly;

    internal static void Run(string root)
    {
        using var fixtureDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-07-identity.json")));
        using var exportDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/operations/con-07.json")));
        var fixture = fixtureDocument.RootElement;
        var operations = fixture.GetProperty("operations").EnumerateArray().ToArray();
        Require(operations.Length == 49, "exact operation count");

        var services = IdentityReflection.Descriptor.Services.ToDictionary(service => service.FullName);
        Require(services.Count == 3, "exact three identity services");
        foreach (var expected in fixture.GetProperty("services").EnumerateObject())
        {
            Require(services.TryGetValue(expected.Name, out var service), "service " + expected.Name);
            Require(service!.Methods.Select(method => method.Name).SequenceEqual(expected.Value.EnumerateArray().Select(value => value.GetString()!)),
                "exact method order " + expected.Name);
        }

        var exports = exportDocument.RootElement.GetProperty("operations").EnumerateArray().ToDictionary(row => row.GetProperty("operationId").GetString()!);
        Require(exports.Count == operations.Length, "operation export count");
        foreach (var row in operations)
        {
            var id = row.GetProperty("id").GetString()!;
            var serviceName = "arcforges.publicapi.v1." + row.GetProperty("service").GetString();
            var methodName = row.GetProperty("method").GetString()!;
            var method = services[serviceName].FindMethodByName(methodName);
            Require(method is not null && !method.IsClientStreaming && !method.IsServerStreaming, id + " unary method");
            Require(method!.InputType.Name == row.GetProperty("service").GetString() + methodName + "Request", id + " request type");
            Require(method.OutputType.Name == row.GetProperty("service").GetString() + methodName + "Response", id + " response type");
            Require(Shape(method.InputType) == row.GetProperty("requestTags").GetString(), id + " request tags");
            var value = method.OutputType.FindFieldByNumber(2)!.MessageType;
            Require(Shape(value) == row.GetProperty("valueTags").GetString(), id + " value tags");
            Require(method.OutputType.FindFieldByNumber(1)?.MessageType == ArcForges.Contracts.Foundation.V1.ResponseMeta.Descriptor, id + " response metadata");
            Require(method.OutputType.FindFieldByNumber(3)?.MessageType == ArcForges.Contracts.Foundation.V1.ArcError.Descriptor, id + " typed error");
            Require(method.OutputType.FindFieldByNumber(2)?.ContainingOneof?.Name == "outcome" && method.OutputType.FindFieldByNumber(3)?.ContainingOneof?.Name == "outcome", id + " outcome oneof");
            Require((method.OutputType.FindFieldByNumber(4) is not null) == row.GetProperty("encodedBody").GetBoolean(), id + " encoded body");
            for (var tag = 2; tag <= 9; tag++) Require(method.InputType.FindFieldByNumber(tag) is null, id + " reserved request tag");
            for (var tag = 5; tag <= 9; tag++) Require(method.OutputType.FindFieldByNumber(tag) is null, id + " reserved response tag");

            var export = exports[id];
            var auth = export.GetProperty("authorization");
            Require(export.GetProperty("binding").GetString() == serviceName + "/" + methodName && export.GetProperty("kind").GetString() == "proto" &&
                export.GetProperty("surface").GetString() == "public" && export.GetProperty("scope").GetString() == row.GetProperty("scope").GetString() &&
                export.GetProperty("profile").GetString() == row.GetProperty("profile").GetString() &&
                export.GetProperty("idempotency").GetString() == row.GetProperty("idempotency").GetString(), id + " export identity");
            Require(auth.EnumerateObject().Count() == 8 && auth.GetProperty("capability").ValueKind == JsonValueKind.Null &&
                auth.GetProperty("risk").GetString() == row.GetProperty("risk").GetString() && auth.GetProperty("approval").GetString() == "none" &&
                auth.GetProperty("stepUp").GetBoolean() == row.GetProperty("stepUp").GetBoolean() && !auth.GetProperty("localPresence").GetBoolean() &&
                auth.GetProperty("egress").GetString() == "none" && auth.GetProperty("patEligible").GetBoolean() == row.GetProperty("patEligible").GetBoolean() &&
                auth.GetProperty("actorKinds").EnumerateArray().Select(actor => actor.GetString()).SequenceEqual(row.GetProperty("actorKinds").EnumerateArray().Select(actor => actor.GetString())),
                id + " exact eight authorization fields");
        }

        foreach (var record in fixture.GetProperty("records").EnumerateObject())
        {
            var type = PublicApi.GetType("ArcForges.Contracts.PublicApi.V1." + record.Name) ?? throw new InvalidOperationException("record type " + record.Name);
            var descriptor = (MessageDescriptor)type.GetProperty("Descriptor", BindingFlags.Public | BindingFlags.Static)!.GetValue(null)!;
            Require(Shape(descriptor) == record.Value.GetString(), record.Name + " exact tags");
        }
        foreach (var enumeration in fixture.GetProperty("enums").EnumerateObject())
        {
            var descriptor = IdentityReflection.Descriptor.EnumTypes.Single(item => item.Name == enumeration.Name);
            var prefix = UpperSnake(enumeration.Name);
            var expected = new[] { prefix + "_UNSPECIFIED" }.Concat(enumeration.Value.EnumerateArray().Select(member => prefix + "_" + UpperSnake(member.GetString()!)));
            Require(descriptor.Values.Select(value => value.Name).SequenceEqual(expected), enumeration.Name + " exact values");
            Require(descriptor.Values.Select(value => value.Number).SequenceEqual(Enumerable.Range(0, descriptor.Values.Count)), enumeration.Name + " exact numbers");
        }
        foreach (var oneof in fixture.GetProperty("oneofs").EnumerateObject())
        {
            var type = PublicApi.GetType("ArcForges.Contracts.PublicApi.V1." + oneof.Name)!;
            var descriptor = (MessageDescriptor)type.GetProperty("Descriptor", BindingFlags.Public | BindingFlags.Static)!.GetValue(null)!;
            Require(descriptor.Oneofs.Count == 1 && descriptor.Oneofs[0].Name == oneof.Value.GetProperty("group").GetString() &&
                descriptor.Oneofs[0].Fields.Select(field => field.JsonName).SequenceEqual(oneof.Value.GetProperty("members").EnumerateArray().Select(member => member.GetString()!)),
                oneof.Name + " exact oneof members");
        }
        Require(DeviceView.Descriptor.Fields.InDeclarationOrder().Select(field => field.FieldNumber).SequenceEqual(new[] { 1, 2, 3, 4, 5, 6, 8, 10 }), "DeviceView reserves tags 7, 9 and 11");

        var shapeCases = fixture.GetProperty("cases").EnumerateArray().ToArray();
        Require(shapeCases.Length >= 90, "shape vector coverage");
        foreach (var item in shapeCases)
        {
            var target = item.GetProperty("target").GetString()!;
            var type = PublicApi.GetType("ArcForges.Contracts.PublicApi.V1." + target) ?? throw new InvalidOperationException("target " + target);
            var descriptor = (MessageDescriptor)type.GetProperty("Descriptor", BindingFlags.Public | BindingFlags.Static)!.GetValue(null)!;
            var message = JsonParser.Default.Parse(item.GetProperty("value").GetRawText(), descriptor);
            var validate = typeof(ContractShapeValidation).GetMethod("IsValid", [type]) ?? throw new InvalidOperationException("validator " + target);
            var actual = (bool)validate.Invoke(null, [message])!;
            Require(actual == item.GetProperty("valid").GetBoolean(), item.GetProperty("id").GetString()!);
            if (actual)
            {
                var clone = descriptor.Parser.ParseFrom(message.ToByteArray());
                Require((bool)validate.Invoke(null, [clone])!, item.GetProperty("id").GetString() + " binary round-trip");
            }
        }

        var httpVectors = fixture.GetProperty("httpVectors").EnumerateArray().ToArray();
        Require(httpVectors.Length >= 100, "HTTP vector coverage");
        foreach (var item in httpVectors) RunHttpVector(item);
        RunBounds();
        RunRoutes(fixture.GetProperty("routes"));
        RunJourneys(fixture, operations);
        Console.WriteLine($"CON.07: 3 services, {operations.Length} operations, {shapeCases.Length} shape and {httpVectors.Length} HTTP exception vectors passed.");
    }

    private static void RunHttpVector(JsonElement item)
    {
        var id = item.GetProperty("id").GetString()!;
        var wire = item.GetProperty("wire").GetString()!;
        var validator = Validation.GetType("ArcForges.Contracts.Validation." + item.GetProperty("root").GetString() + (wire == "json" ? "Json" : "Form"))
            ?? throw new InvalidOperationException(id + " validator");
        var tryParse = validator.GetMethod("TryParse") ?? throw new InvalidOperationException(id + " TryParse");
        var serialize = validator.GetMethod("Serialize") ?? throw new InvalidOperationException(id + " Serialize");
        var text = item.GetProperty("text").GetString()!;
        var arguments = new object?[] { new ReadOnlyMemory<byte>(Encoding.UTF8.GetBytes(text)), null, null };
        var ok = (bool)tryParse.Invoke(null, arguments)!;
        Require(ok == item.GetProperty("valid").GetBoolean(), id);
        if (ok)
        {
            var bytes = (byte[])serialize.Invoke(null, [arguments[1]])!;
            if (item.TryGetProperty("canonical", out var canonical)) Require(Encoding.UTF8.GetString(bytes) == canonical.GetString(), id + " canonical");
            var again = new object?[] { new ReadOnlyMemory<byte>(bytes), null, null };
            Require((bool)tryParse.Invoke(null, again)!, id + " round-trip");
            Require(((byte[])serialize.Invoke(null, [again[1]])!).AsSpan().SequenceEqual(bytes), id + " lossless");
        }
        else
        {
            var failure = arguments[2]!.ToString()!;
            Require(char.ToLowerInvariant(failure[0]) + failure[1..] == item.GetProperty("failure").GetString(), id + " failure kind");
        }
    }

    private static void RunBounds()
    {
        Require(NativeTokenRequestForm.MaxBytes == 16384 && NativeAuthorizeRequestForm.MaxBytes == 16384, "specified 16 KiB form bound");
        Require(BrowserAuthChallengeJson.MaxBytes == 65536 && BrowserAuthChallengeJson.MaxDepth == 32, "strict JSON bound and depth");
        const string form = "grant_type=authorization_code&code=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopq&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk&client_id=arcscope.desktop&redirect_uri=com.arcforges.arcscope%3A%2Fauth%2Fcallback&installationId=11223344-5566-4788-99aa-bbccddeeff00";
        var bytes = Encoding.ASCII.GetBytes(form);
        Require(NativeTokenRequestForm.TryParse(bytes, out var parsed, out _) && parsed!.ClientId == "arcscope.desktop" &&
            parsed.RedirectUri == "com.arcforges.arcscope:/auth/callback", "native token form decodes percent escapes");
        Require(!NativeTokenRequestForm.TryParse(Encoding.ASCII.GetBytes(form + "&x=" + new string('a', 16384)), out _, out var tooLarge) && tooLarge == ContractSerializationFailure.TooLarge, "form above 16 KiB");
        Require(!NativeTokenRequestForm.TryParse(new byte[] { 0xff, 0x3d, 0x61 }, out _, out var raw) && raw == ContractSerializationFailure.Malformed, "raw non-ASCII form byte");
        Require(!NativeTokenRequestForm.TryParse(Encoding.ASCII.GetBytes(form.Replace("&", "\n")), out _, out _), "raw control in form");
        Require(NativeTokenRequestForm.Serialize(parsed!).AsSpan().SequenceEqual(bytes), "native token form serializes deterministically");
        var thrown = false;
        try { NativeTokenRequestForm.Parse(Encoding.ASCII.GetBytes("grant_type=authorization_code")); }
        catch (ContractSerializationException) { thrown = true; }
        Require(thrown, "incomplete form is refused with a typed exception");
        var duplicateParsed = BrowserSessionViewJson.TryParse(Encoding.UTF8.GetBytes("{\"sessionId\":\"11223344-5566-4788-99aa-bbccddeeff00\",\"sessionId\":\"11223344-5566-4788-99aa-bbccddeeff00\"}"), out _, out var duplicate);
        Require(!duplicateParsed && duplicate == ContractSerializationFailure.Malformed, "duplicate JSON property is malformed");
    }

    private static void RunRoutes(JsonElement routes)
    {
        AssertRoutes(BrowserSessionRoutes.All.Select(Describe).ToArray(), routes.GetProperty("BrowserSession"), "BrowserSession");
        AssertRoutes(NativeAuthRoutes.All.Select(Describe).ToArray(), routes.GetProperty("NativeAuth"), "NativeAuth");
        var all = BrowserSessionRoutes.All.Select(route => (route.Id, route.Method, route.Path, route.Cache, route.Csrf, route.Origin, route.SetCookie))
            .Concat(NativeAuthRoutes.All.Select(route => (route.Id, route.Method, route.Path, route.Cache, route.Csrf, route.Origin, route.SetCookie))).ToArray();
        Require(all.Select(route => route.Method + " " + route.Path).Distinct().Count() == all.Length, "unique method and path");
        Require(all.All(route => route.Cache == "no-store" && route.Path.StartsWith("/session/v1/", StringComparison.Ordinal)), "no-store session routes");
        Require(all.Count(route => route.Id.StartsWith("browser.", StringComparison.Ordinal) && route.Method == "POST") == 8 &&
            all.Where(route => route.Id.StartsWith("browser.", StringComparison.Ordinal) && route.Method == "POST").All(route => route.Csrf == "required" && route.Origin == "exact-configured"), "every browser POST requires Origin and CSRF");
        Require(all.Where(route => route.SetCookie == "session").Select(route => route.Id).SequenceEqual(new[] { "browser.completeAuthentication", "browser.completeEnrollment" }), "session cookie only from completion routes");
    }

    private static string Describe(BrowserSessionRoute route) =>
        string.Join("|", route.Id, route.Method, route.Path, route.Credential, route.Origin, route.Csrf, route.SetCookie, route.Cache, route.RequestWire, string.Join(",", route.RequestRoots), route.ResponseWire, string.Join(",", route.ResponseRoots));

    private static string Describe(NativeAuthRoute route) =>
        string.Join("|", route.Id, route.Method, route.Path, route.Credential, route.Origin, route.Csrf, route.SetCookie, route.Cache, route.RequestWire, string.Join(",", route.RequestRoots), route.ResponseWire, string.Join(",", route.ResponseRoots));

    private static void AssertRoutes(string[] actual, JsonElement expected, string bundle)
    {
        var rows = expected.EnumerateArray().Select(route => string.Join("|", route.GetProperty("id").GetString(), route.GetProperty("method").GetString(), route.GetProperty("path").GetString(),
            route.GetProperty("credential").GetString(), route.GetProperty("origin").GetString(), route.GetProperty("csrf").GetString(), route.GetProperty("setCookie").GetString(),
            route.GetProperty("cache").GetString(), route.GetProperty("requestWire").GetString(), string.Join(",", route.GetProperty("requestRoots").EnumerateArray().Select(value => value.GetString())),
            route.GetProperty("responseWire").GetString(), string.Join(",", route.GetProperty("responseRoots").EnumerateArray().Select(value => value.GetString())))).ToArray();
        Require(actual.SequenceEqual(rows), bundle + " exact route table");
    }

    private static void RunJourneys(JsonElement fixture, JsonElement[] operations)
    {
        var steps = operations.ToDictionary(row => row.GetProperty("id").GetString()!, row => row.GetProperty("stepUp").GetBoolean());
        var routeIds = BrowserSessionRoutes.All.Select(route => route.Id).Concat(NativeAuthRoutes.All.Select(route => route.Id)).ToHashSet();
        var journeys = fixture.GetProperty("journeys").EnumerateArray().ToArray();
        Require(journeys.Length == 14, "exact journey inventory");
        foreach (var journey in journeys)
        {
            var id = journey.GetProperty("id").GetString()!;
            Require(journey.GetProperty("evidenceClass").GetString() == "declarative-owner-runtime-vector-not-executed-by-con07", id + " evidence class");
            var credits = 0;
            foreach (var step in journey.GetProperty("steps").EnumerateArray())
            {
                var stepId = step.GetProperty("id").GetString()!;
                if (step.GetProperty("kind").GetString() == "route") { Require(routeIds.Contains(stepId), id + " route " + stepId); continue; }
                Require(steps.TryGetValue(stepId, out var needsStepUp), id + " operation " + stepId);
                if (stepId == "identity.completeStepUp") credits++;
                if (needsStepUp) { Require(credits > 0, id + " " + stepId + " needs fresh step-up"); credits--; }
            }
        }
    }

    private static string Shape(MessageDescriptor descriptor) =>
        string.Join(",", descriptor.Fields.InDeclarationOrder().Select(field => $"{field.FieldNumber}:{field.Name}"));

    private static string UpperSnake(string value) => Regex.Replace(value, "([a-z0-9])([A-Z])", "$1_$2").ToUpperInvariant();

    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("CON.07 fixture: " + name);
    }
}
