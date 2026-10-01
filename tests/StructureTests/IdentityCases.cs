// SPDX-License-Identifier: Apache-2.0
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
    private delegate bool TryParse<T>(ReadOnlyMemory<byte> input, out T? value, out ContractSerializationFailure failure) where T : class;

    private sealed record Outcome(bool Ok, string Failure, string? Canonical, bool Lossless);

    private static readonly Dictionary<string, Func<string, bool>> Shapes = new(StringComparer.Ordinal)
    {
        ["AccountProfile"] = Shape(AccountProfile.Parser, ContractShapeValidation.IsValid),
        ["ApiTokenView"] = Shape(ApiTokenView.Parser, ContractShapeValidation.IsValid),
        ["AuthChallenge"] = Shape(AuthChallenge.Parser, ContractShapeValidation.IsValid),
        ["AuthProof"] = Shape(AuthProof.Parser, ContractShapeValidation.IsValid),
        ["AuthProviderView"] = Shape(AuthProviderView.Parser, ContractShapeValidation.IsValid),
        ["CredentialReplacement"] = Shape(CredentialReplacement.Parser, ContractShapeValidation.IsValid),
        ["CredentialSummary"] = Shape(CredentialSummary.Parser, ContractShapeValidation.IsValid),
        ["DataDeletionPreview"] = Shape(DataDeletionPreview.Parser, ContractShapeValidation.IsValid),
        ["DataDeletionView"] = Shape(DataDeletionView.Parser, ContractShapeValidation.IsValid),
        ["DeletionStatus"] = Shape(DeletionStatus.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRegisterRequest"] = Shape(DeviceServiceRegisterRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceView"] = Shape(DeviceView.Parser, ContractShapeValidation.IsValid),
        ["EnrollmentProof"] = Shape(EnrollmentProof.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginAuthenticationRequest"] = Shape(IdentityServiceBeginAuthenticationRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginAuthenticationResponse"] = Shape(IdentityServiceBeginAuthenticationResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceChangePasswordRequest"] = Shape(IdentityServiceChangePasswordRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteAuthenticationRequest"] = Shape(IdentityServiceCompleteAuthenticationRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCreateApiTokenRequest"] = Shape(IdentityServiceCreateApiTokenRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListSessionsRequest"] = Shape(IdentityServiceListSessionsRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRefreshSessionRequest"] = Shape(IdentityServiceRefreshSessionRequest.Parser, ContractShapeValidation.IsValid),
        ["InstallationClaim"] = Shape(InstallationClaim.Parser, ContractShapeValidation.IsValid),
        ["InstalledProduct"] = Shape(InstalledProduct.Parser, ContractShapeValidation.IsValid),
        ["NativeSession"] = Shape(NativeSession.Parser, ContractShapeValidation.IsValid),
        ["ProfileUpdate"] = Shape(ProfileUpdate.Parser, ContractShapeValidation.IsValid),
        ["RecoveryCodeSet"] = Shape(RecoveryCodeSet.Parser, ContractShapeValidation.IsValid),
        ["RemoteCapabilityPolicy"] = Shape(RemoteCapabilityPolicy.Parser, ContractShapeValidation.IsValid),
        ["SecurityActivity"] = Shape(SecurityActivity.Parser, ContractShapeValidation.IsValid),
        ["SessionSummary"] = Shape(SessionSummary.Parser, ContractShapeValidation.IsValid),
        ["SessionView"] = Shape(SessionView.Parser, ContractShapeValidation.IsValid),
        ["StepUpEvidence"] = Shape(StepUpEvidence.Parser, ContractShapeValidation.IsValid),
        ["WebAuthnAssertion"] = Shape(WebAuthnAssertion.Parser, ContractShapeValidation.IsValid),
        ["WebAuthnCreation"] = Shape(WebAuthnCreation.Parser, ContractShapeValidation.IsValid),
        ["WebAuthnOptions"] = Shape(WebAuthnOptions.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceHealth"] = Shape(WorkspaceHealth.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceRequestDataDeletionRequest"] = Shape(WorkspaceServiceRequestDataDeletionRequest.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceView"] = Shape(WorkspaceView.Parser, ContractShapeValidation.IsValid)
    };

    private static readonly Dictionary<string, MessageDescriptor> Records = new(StringComparer.Ordinal)
    {
        ["InstallationClaim"] = InstallationClaim.Descriptor,
        ["AuthChallenge"] = AuthChallenge.Descriptor,
        ["WebAuthnOptions"] = WebAuthnOptions.Descriptor,
        ["WebAuthnCreation"] = WebAuthnCreation.Descriptor,
        ["WebAuthnAssertion"] = WebAuthnAssertion.Descriptor,
        ["AuthProof"] = AuthProof.Descriptor,
        ["NativeSession"] = NativeSession.Descriptor,
        ["SessionView"] = SessionView.Descriptor,
        ["CredentialSummary"] = CredentialSummary.Descriptor,
        ["StepUpEvidence"] = StepUpEvidence.Descriptor,
        ["DeletionStatus"] = DeletionStatus.Descriptor,
        ["AccountProfile"] = AccountProfile.Descriptor,
        ["ProfileUpdate"] = ProfileUpdate.Descriptor,
        ["AuthProviderView"] = AuthProviderView.Descriptor,
        ["SessionSummary"] = SessionSummary.Descriptor,
        ["ApiTokenView"] = ApiTokenView.Descriptor,
        ["RecoveryCodeSet"] = RecoveryCodeSet.Descriptor,
        ["RemoteCapabilityPolicy"] = RemoteCapabilityPolicy.Descriptor,
        ["SecurityActivity"] = SecurityActivity.Descriptor,
        ["DataDeletionPreview"] = DataDeletionPreview.Descriptor,
        ["DeletionCount"] = DeletionCount.Descriptor,
        ["WorkspaceHealth"] = WorkspaceHealth.Descriptor,
        ["DataDeletionView"] = DataDeletionView.Descriptor,
        ["WorkspaceView"] = WorkspaceView.Descriptor,
        ["DeviceView"] = DeviceView.Descriptor,
        ["InstalledProduct"] = InstalledProduct.Descriptor,
        ["DeviceCapabilityView"] = DeviceCapabilityView.Descriptor,
        ["CredentialReplacement"] = CredentialReplacement.Descriptor,
        ["EnrollmentProof"] = EnrollmentProof.Descriptor
    };

    private static readonly Dictionary<string, Func<byte[], Outcome>> Codecs = new(StringComparer.Ordinal)
    {
        ["BrowserAuthChallenge"] = Codec<BrowserAuthChallenge>(BrowserAuthChallengeJson.TryParse, BrowserAuthChallengeJson.Serialize),
        ["BrowserBeginAuthenticationRequest"] = Codec<BrowserBeginAuthenticationRequest>(BrowserBeginAuthenticationRequestJson.TryParse, BrowserBeginAuthenticationRequestJson.Serialize),
        ["BrowserBeginRecoveryRequest"] = Codec<BrowserBeginRecoveryRequest>(BrowserBeginRecoveryRequestJson.TryParse, BrowserBeginRecoveryRequestJson.Serialize),
        ["BrowserBeginStepUpRequest"] = Codec<BrowserBeginStepUpRequest>(BrowserBeginStepUpRequestJson.TryParse, BrowserBeginStepUpRequestJson.Serialize),
        ["BrowserBootstrapResponse"] = Codec<BrowserBootstrapResponse>(BrowserBootstrapResponseJson.TryParse, BrowserBootstrapResponseJson.Serialize),
        ["BrowserCompleteAuthenticationRequest"] = Codec<BrowserCompleteAuthenticationRequest>(BrowserCompleteAuthenticationRequestJson.TryParse, BrowserCompleteAuthenticationRequestJson.Serialize),
        ["BrowserCompleteEnrollmentRequest"] = Codec<BrowserCompleteEnrollmentRequest>(BrowserCompleteEnrollmentRequestJson.TryParse, BrowserCompleteEnrollmentRequestJson.Serialize),
        ["BrowserCompleteRecoveryRequest"] = Codec<BrowserCompleteRecoveryRequest>(BrowserCompleteRecoveryRequestJson.TryParse, BrowserCompleteRecoveryRequestJson.Serialize),
        ["BrowserCompleteStepUpRequest"] = Codec<BrowserCompleteStepUpRequest>(BrowserCompleteStepUpRequestJson.TryParse, BrowserCompleteStepUpRequestJson.Serialize),
        ["BrowserOidcCallbackFailure"] = Codec<BrowserOidcCallbackFailure>(BrowserOidcCallbackFailureForm.TryParse, BrowserOidcCallbackFailureForm.Serialize),
        ["BrowserOidcCallbackSuccess"] = Codec<BrowserOidcCallbackSuccess>(BrowserOidcCallbackSuccessForm.TryParse, BrowserOidcCallbackSuccessForm.Serialize),
        ["BrowserReceipt"] = Codec<BrowserReceipt>(BrowserReceiptJson.TryParse, BrowserReceiptJson.Serialize),
        ["BrowserSessionView"] = Codec<BrowserSessionView>(BrowserSessionViewJson.TryParse, BrowserSessionViewJson.Serialize),
        ["BrowserStepUpEvidence"] = Codec<BrowserStepUpEvidence>(BrowserStepUpEvidenceJson.TryParse, BrowserStepUpEvidenceJson.Serialize),
        ["NativeAuthorizeCallbackFailure"] = Codec<NativeAuthorizeCallbackFailure>(NativeAuthorizeCallbackFailureForm.TryParse, NativeAuthorizeCallbackFailureForm.Serialize),
        ["NativeAuthorizeCallbackSuccess"] = Codec<NativeAuthorizeCallbackSuccess>(NativeAuthorizeCallbackSuccessForm.TryParse, NativeAuthorizeCallbackSuccessForm.Serialize),
        ["NativeAuthorizeRequest"] = Codec<NativeAuthorizeRequest>(NativeAuthorizeRequestForm.TryParse, NativeAuthorizeRequestForm.Serialize),
        ["NativeTokenRequest"] = Codec<NativeTokenRequest>(NativeTokenRequestForm.TryParse, NativeTokenRequestForm.Serialize),
        ["NativeTokenResponse"] = Codec<NativeTokenResponse>(NativeTokenResponseJson.TryParse, NativeTokenResponseJson.Serialize)
    };

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
            Require(Shape(Records[record.Name]) == record.Value.GetString(), record.Name + " exact tags");
        Require(Records.Count == fixture.GetProperty("records").EnumerateObject().Count(), "record inventory");
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
            // proto3 optional presence adds synthetic oneofs that are not part of the registry contract.
            var real = Records[oneof.Name].Oneofs.Where(group => !group.IsSynthetic).ToArray();
            Require(real.Length == 1 && real[0].Name == oneof.Value.GetProperty("group").GetString() &&
                real[0].Fields.Select(field => field.JsonName).SequenceEqual(oneof.Value.GetProperty("members").EnumerateArray().Select(member => member.GetString()!)),
                oneof.Name + " exact oneof members");
        }
        Require(DeviceView.Descriptor.Fields.InDeclarationOrder().Select(field => field.FieldNumber).SequenceEqual(new[] { 1, 2, 3, 4, 5, 6, 8, 10 }), "DeviceView reserves tags 7, 9 and 11");

        var shapeCases = fixture.GetProperty("cases").EnumerateArray().ToArray();
        Require(shapeCases.Length >= 90, "shape vector coverage");
        foreach (var item in shapeCases)
        {
            var target = item.GetProperty("target").GetString()!;
            Require(Shapes.TryGetValue(target, out var validate), "shape target " + target);
            var actual = validate!(item.GetProperty("value").GetRawText());
            Require(actual == item.GetProperty("valid").GetBoolean(), item.GetProperty("id").GetString()!);
        }

        var httpVectors = fixture.GetProperty("httpVectors").EnumerateArray().ToArray();
        Require(httpVectors.Length >= 100, "HTTP vector coverage");
        foreach (var item in httpVectors) RunHttpVector(item);
        RunBounds();
        RunRoutes(fixture.GetProperty("routes"));
        RunJourneys(fixture, operations);
        Console.WriteLine($"CON.07: 3 services, {operations.Length} operations, {shapeCases.Length} shape and {httpVectors.Length} HTTP exception vectors passed.");
    }

    private static Func<string, bool> Shape<T>(MessageParser<T> parser, Func<T, bool> validate) where T : class, IMessage<T>, new() => json =>
    {
        var message = JsonParser.Default.Parse<T>(json);
        var valid = validate(message);
        if (valid) Require(validate(parser.ParseFrom(message.ToByteArray())), "binary round-trip");
        return valid;
    };

    private static Func<byte[], Outcome> Codec<T>(TryParse<T> tryParse, Func<T, byte[]> serialize) where T : class => bytes =>
    {
        if (!tryParse(bytes, out var value, out var failure))
        {
            var name = failure.ToString();
            return new Outcome(false, char.ToLowerInvariant(name[0]) + name[1..], null, false);
        }
        var canonical = serialize(value!);
        var again = tryParse(canonical, out var reparsed, out _);
        return new Outcome(true, "", Encoding.UTF8.GetString(canonical), again && serialize(reparsed!).AsSpan().SequenceEqual(canonical));
    };

    private static void RunHttpVector(JsonElement item)
    {
        var id = item.GetProperty("id").GetString()!;
        Require(Codecs.TryGetValue(item.GetProperty("root").GetString()!, out var codec), id + " codec");
        var outcome = codec!(Encoding.UTF8.GetBytes(item.GetProperty("text").GetString()!));
        Require(outcome.Ok == item.GetProperty("valid").GetBoolean(), id);
        if (outcome.Ok)
        {
            if (item.TryGetProperty("canonical", out var canonical)) Require(outcome.Canonical == canonical.GetString(), id + " canonical");
            Require(outcome.Lossless, id + " lossless round-trip");
        }
        else Require(outcome.Failure == item.GetProperty("failure").GetString(), id + " failure kind");
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
