// SPDX-License-Identifier: Apache-2.0
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.Simulation.V1;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using FDecimal = ArcForges.Contracts.Foundation.V1.Decimal;
using Loc = ArcForges.Contracts.LocalRpc.Platform.V1;
using LocShapes = ArcForges.Contracts.LocalRpc.Platform.Shapes.ContractShapeValidation;
using Pub = ArcForges.Contracts.PublicApi.V1;
using PubShapes = ArcForges.Contracts.Validation.ContractShapeValidation;

/// <summary>
/// CON.25 consumer: public ConnectorService (descriptors, authorization export, shape vectors, public/local twin parity),
/// LocalCallContext wire vectors and the canonical af-segment.v1 body (in-test encoder and strict reader over the generated
/// SimulationDataSegment). Every fixture vector is consumed exactly once. No reflection serialization.
/// </summary>
internal static class Con25Cases
{
    private static readonly string[] ConnectorVectorIds =
    [
        "definition-valid-oauth",
        "definition-valid-minimal-no-origins",
        "definition-bad-id-characters",
        "definition-uppercase-manifest-hash",
        "definition-short-manifest-hash",
        "definition-unknown-auth-kind",
        "definition-http-origin",
        "definition-origin-with-path",
        "definition-origin-with-credentials",
        "definition-too-many-origins",
        "definition-duplicate-scope",
        "definition-missing-package-version",
        "connection-valid-connected",
        "connection-valid-failed-with-reason",
        "connection-unknown-state",
        "connection-empty-name",
        "connection-name-too-long",
        "connection-zero-connection-id",
        "connection-missing-revision",
        "connection-duplicate-scope",
        "challenge-valid-oauth-url",
        "challenge-valid-personal-token-no-url",
        "challenge-http-url",
        "challenge-missing-expiry",
        "challenge-zero-flow-id",
        "proof-valid-callback-receipt",
        "proof-valid-personal-token",
        "proof-no-arm",
        "proof-empty-secret",
        "proof-oversize-secret",
        "begin-request-valid",
        "begin-request-missing-name",
        "begin-request-bad-definition-id",
        "complete-request-valid",
        "complete-request-missing-proof",
        "revoke-request-valid",
        "revoke-request-zero-connection-id",
        "list-connections-value-valid",
        "list-connections-value-over-page-bound"
    ];

    private static readonly string[] SegmentVectorIds =
    [
        "empty-segment-keeps-every-ordered-repeated-field",
        "numeric-digital-and-event-samples-in-delivered-order",
        "duplicate-delivery-differs-only-by-ordinal-and-fault-marker",
        "gap-and-fault-markers-with-and-without-channel",
        "binary64-bit-words-preserve-sign-and-extremes",
        "integral-extremes-use-exact-strings",
        "text-metadata-escapes-and-unicode"
    ];

    // Expected refusal code per fixture refusal: the strict reader must refuse each text for its intended reason.
    private static readonly Dictionary<string, string> SegmentRefusals = new(StringComparer.Ordinal)
    {
        ["refuse-uppercase-uuid"] = "id",
        ["refuse-json-number-for-uint64"] = "type",
        ["refuse-leading-zero-uint64"] = "int",
        ["refuse-uint64-overflow"] = "int",
        ["refuse-negative-zero-sint64"] = "int",
        ["refuse-double-as-json-number"] = "type",
        ["refuse-uppercase-hex-double"] = "double",
        ["refuse-short-hex-double"] = "double",
        ["refuse-nan-bit-word"] = "double",
        ["refuse-infinity-bit-word"] = "double",
        ["refuse-unsorted-members"] = "order",
        ["refuse-missing-empty-repeated"] = "member",
        ["refuse-two-oneof-arms"] = "oneof",
        ["refuse-no-oneof-arm"] = "oneof",
        ["refuse-insignificant-whitespace"] = "form",
        ["refuse-null-for-absent-optional"] = "type",
        ["refuse-unknown-member"] = "member",
        ["refuse-duplicate-member"] = "duplicate",
        ["refuse-wrong-encoding-profile"] = "profile",
        ["refuse-wrong-execution-profile"] = "profile",
        ["refuse-resource-metadata-arm"] = "metadata",
        ["refuse-out-of-order-ordinals"] = "ordinal",
        ["refuse-duplicate-ordinal"] = "ordinal",
        ["refuse-unknown-gap-kind"] = "gapKind",
        ["refuse-zero-rate-denominator"] = "rate",
        ["refuse-non-minimal-escape"] = "form",
        ["refuse-uppercase-escape-digits"] = "form",
        ["refuse-byte-order-mark"] = "bom"
    };

    private static readonly string[] ContextVectorIds =
    [
        "product-call-full-context",
        "infrastructure-call-omits-actor",
        "empty-context",
        "turn-owner",
        "thirty-two-scope-roots-within-four-kib",
        "refuse-thirty-three-scope-roots",
        "refuse-over-four-kib",
        "refuse-zero-invocation-id",
        "refuse-zero-lease-id",
        "refuse-execution-owner-without-arm",
        "refuse-actor-kind-not-a-key",
        "refuse-scope-root-bad-kind"
    ];

    private static readonly string[] MethodNames =
        ["ListDefinitions", "ListConnections", "BeginConnection", "CompleteConnection", "GetConnection", "RevokeConnection"];

    private static readonly string[] ReadMethods = ["ListDefinitions", "ListConnections", "GetConnection"];
    private static readonly string[] RecordNames = ["ConnectorDefinition", "ConnectorConnection", "ConnectorChallenge", "ConnectorProof"];

    private sealed record AuthRow(string OperationId, string Method, string Idempotency, string Risk, string Approval, bool StepUp, string Egress, string Compatibility, bool Foreground);

    private static readonly AuthRow[] AuthTable =
    [
        new("connector.listDefinitions", "ListDefinitions", "Q", "R1", "none", false, "none", "AO", false),
        new("connector.listConnections", "ListConnections", "Q", "R1", "none", false, "none", "AO", false),
        new("connector.beginConnection", "BeginConnection", "CC", "R3", "foreground-human-consent", true, "definition-hash-bound-provider-origins-scopes", "FR", true),
        new("connector.completeConnection", "CompleteConnection", "NI", "R3", "original-foreground-human-consent-flow", true, "definition-hash-bound-provider-origins-scopes", "FR", true),
        new("connector.getConnection", "GetConnection", "Q", "R1", "none", false, "none", "AO", false),
        new("connector.revokeConnection", "RevokeConnection", "DE", "R2", "foreground-human-confirmation", false, "definition-hash-bound-existing-provider-revocation", "FR", true)
    ];

    private const string FoundationId = "arcforges.foundation.v1.Id";
    private const string PageRequestType = "arcforges.foundation.v1.PageRequest";
    private const string PageStateType = "arcforges.foundation.v1.PageState";
    private const string PubPackage = "arcforges.publicapi.v1.";

    private static readonly (string Message, int Tag, string Type, bool Repeated)[] PayloadTypes =
    [
        ("ConnectorServiceListDefinitionsRequest", 10, PageRequestType, false),
        ("ConnectorServiceListConnectionsRequest", 10, PageRequestType, false),
        ("ConnectorServiceBeginConnectionRequest", 10, FoundationId, false),
        ("ConnectorServiceBeginConnectionRequest", 11, "string", false),
        ("ConnectorServiceBeginConnectionRequest", 12, "string", false),
        ("ConnectorServiceCompleteConnectionRequest", 10, FoundationId, false),
        ("ConnectorServiceCompleteConnectionRequest", 11, PubPackage + "ConnectorProof", false),
        ("ConnectorServiceGetConnectionRequest", 10, FoundationId, false),
        ("ConnectorServiceRevokeConnectionRequest", 10, FoundationId, false),
        ("ConnectorServiceListDefinitionsValue", 10, PubPackage + "ConnectorDefinition", true),
        ("ConnectorServiceListDefinitionsValue", 11, PageStateType, false),
        ("ConnectorServiceListConnectionsValue", 10, PubPackage + "ConnectorConnection", true),
        ("ConnectorServiceListConnectionsValue", 11, PageStateType, false),
        ("ConnectorServiceBeginConnectionValue", 10, PubPackage + "ConnectorChallenge", false),
        ("ConnectorServiceCompleteConnectionValue", 10, PubPackage + "ConnectorConnection", false),
        ("ConnectorServiceGetConnectionValue", 10, PubPackage + "ConnectorConnection", false),
        ("ConnectorServiceRevokeConnectionValue", 10, PubPackage + "ConnectorConnection", false)
    ];

    internal static void Run(string root)
    {
        RunConnector(root);
        RunLocalCallContext(root);
        RunAfSegment(root);
    }

    // ------------------------------------------------------------------------------------------------------------
    // Part 1: ConnectorService
    // ------------------------------------------------------------------------------------------------------------

    private static void RunConnector(string root)
    {
        using var fixtureDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-25-connector.json")));
        var fixture = fixtureDocument.RootElement;
        Require(fixture.GetProperty("schemaVersion").GetString() == "con-25-connector.v1", "connector fixture schema");
        Require(fixture.GetProperty("evidenceClass").GetString() == "offline-contract-only-no-owner-service-or-provider", "connector fixture boundary");
        Require(fixture.GetProperty("service").GetString() == "arcforges.publicapi.v1.ConnectorService", "fixture service identity");

        var service = Pub.ConnectorService.Descriptor;
        Require(service.FullName == "arcforges.publicapi.v1.ConnectorService", "service identity");
        Require(service.Methods.Select(method => method.Name).SequenceEqual(MethodNames), "exact six ordered ConnectorService methods");
        var file = service.File;
        Require(file.Package == "arcforges.publicapi.v1" && file.Name == "arcforges/publicapi/v1/connector.proto", "connector file identity");
        Require(file.Dependencies.All(dependency => dependency.Name.StartsWith("arcforges/foundation/", StringComparison.Ordinal)), "public connector.proto imports only foundation");
        var expectedMessages = new List<string>(RecordNames);
        foreach (var method in MethodNames)
        {
            expectedMessages.Add("ConnectorService" + method + "Request");
            expectedMessages.Add("ConnectorService" + method + "Response");
            expectedMessages.Add("ConnectorService" + method + "Value");
        }
        Require(file.MessageTypes.Select(message => message.Name).Order(StringComparer.Ordinal)
            .SequenceEqual(expectedMessages.Order(StringComparer.Ordinal), StringComparer.Ordinal), "exact connector.proto message inventory");
        foreach (var path in Directory.EnumerateFiles(Path.Combine(root, "public/proto"), "*.proto", SearchOption.AllDirectories))
        {
            foreach (var line in File.ReadAllLines(path))
            {
                var trimmed = line.TrimStart();
                Require(!(trimmed.StartsWith("import ", StringComparison.Ordinal) &&
                    (trimmed.Contains("arcforges/local/", StringComparison.Ordinal) || trimmed.Contains("internal/", StringComparison.Ordinal))),
                    "no public proto imports local or internal schema: " + path);
            }
        }

        var requestMeta = RequestMeta.Descriptor;
        Require(requestMeta.FindFieldByNumber(2)?.JsonName == "expectedRev", "RequestMeta tag 2 is expectedRev");

        var operations = fixture.GetProperty("operations").EnumerateArray().ToArray();
        Require(operations.Select(item => item.GetProperty("operationId").GetString()).SequenceEqual(AuthTable.Select(row => row.OperationId)), "fixture operation ids and order");
        for (var index = 0; index < operations.Length; index++)
        {
            var operation = operations[index];
            var row = AuthTable[index];
            var method = service.FindMethodByName(row.Method) ?? throw new InvalidOperationException(row.Method + " descriptor missing");
            Require(operation.GetProperty("rpc").GetString() == "ConnectorService/" + row.Method, row.Method + " rpc name");
            Require(!method.IsClientStreaming && !method.IsServerStreaming, row.Method + " unary");
            Require(method.InputType.Name == operation.GetProperty("requestType").GetString() &&
                FieldList(method.InputType, operation.GetProperty("requestFields"), 1, int.MaxValue), row.Method + " request fields match fixture");
            Require(method.InputType.FindFieldByNumber(1)?.MessageType?.FullName == "arcforges.foundation.v1.RequestMeta" &&
                method.InputType.FindFieldByNumber(1)?.JsonName == "meta", row.Method + " request meta tag 1");
            Require(method.InputType.Fields.InFieldNumberOrder().All(field => field.FieldNumber == 1 || field.FieldNumber >= 10), row.Method + " request payload tags");
            var value = method.OutputType.FindFieldByNumber(2)?.MessageType ?? throw new InvalidOperationException(row.Method + " value descriptor missing");
            Require(value.Name == operation.GetProperty("valueType").GetString() &&
                FieldList(value, operation.GetProperty("valueFields"), 1, int.MaxValue) &&
                value.Fields.InFieldNumberOrder().All(field => field.FieldNumber >= 10), row.Method + " value fields match fixture");
            Require(method.OutputType.Name == operation.GetProperty("responseType").GetString() &&
                FieldList(method.OutputType, operation.GetProperty("outcomeFields"), 2, int.MaxValue), row.Method + " response fields match fixture");
            Require(method.OutputType.FindFieldByNumber(1)?.MessageType?.FullName == "arcforges.foundation.v1.ResponseMeta" &&
                method.OutputType.FindFieldByNumber(1)?.JsonName == "meta", row.Method + " response meta tag 1");
            var isRead = ReadMethods.Contains(row.Method);
            var outcomeFields = method.OutputType.Fields.InFieldNumberOrder().Where(field => field.FieldNumber >= 2).ToArray();
            Require(outcomeFields.Select(field => field.FieldNumber).SequenceEqual(isRead ? new[] { 2, 3, 4 } : new[] { 2, 3 }), row.Method + " outcome tags (encodedBody=4 only for list/get)");
            Require(outcomeFields.All(field => field.ContainingOneof is { IsSynthetic: false, Name: "outcome" }), row.Method + " exclusive outcome oneof");
            Require(method.OutputType.FindFieldByNumber(3)?.MessageType?.FullName == "arcforges.foundation.v1.ArcError" &&
                method.OutputType.FindFieldByNumber(3)?.JsonName == "error", row.Method + " error arm");
            Require(isRead == (method.OutputType.FindFieldByNumber(4)?.MessageType?.FullName == "arcforges.foundation.v1.EncodedBodyRef"), row.Method + " encodedBody arm");
            Require(method.OutputType.FindFieldByNumber(2)?.JsonName == "value", row.Method + " value arm name");

            // Authorization facts: independent table versus fixture.
            var authorization = operation.GetProperty("authorization");
            Require(authorization.GetProperty("scope").GetString() == "assistant" && authorization.GetProperty("capability").ValueKind == JsonValueKind.Null &&
                !authorization.GetProperty("localPresence").GetBoolean() && !authorization.GetProperty("patEligible").GetBoolean() &&
                !authorization.GetProperty("toolReachable").GetBoolean(), row.OperationId + " fixture fixed authorization facts");
            Require(authorization.GetProperty("actorKinds").GetArrayLength() == 1 && authorization.GetProperty("actorKinds")[0].GetString() == "human", row.OperationId + " fixture actor kinds");
            Require(authorization.GetProperty("idempotency").GetString() == row.Idempotency && authorization.GetProperty("risk").GetString() == row.Risk &&
                authorization.GetProperty("approval").GetString() == row.Approval && authorization.GetProperty("stepUp").GetBoolean() == row.StepUp &&
                authorization.GetProperty("egress").GetString() == row.Egress && authorization.GetProperty("compatibility").GetString() == row.Compatibility &&
                authorization.GetProperty("foreground").GetBoolean() == row.Foreground, row.OperationId + " fixture authorization matches expected table");
        }
        var revoke = service.FindMethodByName("RevokeConnection")!;
        Require(FieldList(revoke.InputType, ExpectedList(("meta", 1), ("connectionId", 10)), 1, int.MaxValue), "RevokeConnection request is exactly meta and connectionId");

        var messageByName = file.MessageTypes.ToDictionary(message => message.Name, StringComparer.Ordinal);
        foreach (var (messageName, tag, type, repeated) in PayloadTypes)
        {
            var field = messageByName[messageName].FindFieldByNumber(tag) ?? throw new InvalidOperationException(messageName + " tag " + tag);
            Require(field.IsRepeated == repeated, messageName + "." + field.Name + " repeated flag");
            if (type == "string") Require(field.FieldType == FieldType.String && !field.IsRepeated, messageName + "." + field.Name + " string");
            else Require(field.FieldType == FieldType.Message && field.MessageType.FullName == type, messageName + "." + field.Name + " type " + type);
        }

        // Record descriptors: fixture field lists plus independently expected presence shapes.
        var records = fixture.GetProperty("records");
        foreach (var name in RecordNames)
        {
            var descriptor = messageByName[name];
            var expected = records.GetProperty(name).EnumerateArray().ToArray();
            var actualFields = descriptor.Fields.InFieldNumberOrder().ToArray();
            Require(actualFields.Length == expected.Length, name + " field count");
            for (var index = 0; index < expected.Length; index++)
            {
                var field = actualFields[index];
                var spec = expected[index];
                Require(field.JsonName == spec[0].GetString() && field.FieldNumber == ParseInt(spec[1]), name + " field " + index + " name and tag");
                var typeText = spec[2].GetString()!;
                var isRepeated = typeText.StartsWith("repeated ", StringComparison.Ordinal);
                var typeName = isRepeated ? typeText["repeated ".Length..] : typeText;
                Require(field.IsRepeated == isRepeated, name + "." + field.JsonName + " repeated");
                if (typeName == "string") Require(field.FieldType == FieldType.String, name + "." + field.JsonName + " string type");
                else Require(field.FieldType == FieldType.Message && field.MessageType.FullName == typeName, name + "." + field.JsonName + " message type");
                if (name == "ConnectorProof") Require(field.ContainingOneof is { IsSynthetic: false, Name: "proof" }, "ConnectorProof arms are one oneof");
                else if (isRepeated) Require(field.ContainingOneof is null && !field.HasPresence, name + "." + field.JsonName + " repeated no presence");
                else if (typeName == "string") Require(field.ContainingOneof is { IsSynthetic: true } && field.HasPresence, name + "." + field.JsonName + " proto3 optional");
                else Require(field.ContainingOneof is null && field.HasPresence, name + "." + field.JsonName + " message presence");
            }
        }

        // Local twin parity (descriptors) and the discriminating self-test of the comparison.
        var local = fixture.GetProperty("localTwin");
        Require(local.GetProperty("package").GetString() == "arcforges.local.platform.v1" && local.GetProperty("service").GetString() == "ConnectorBrokerService" &&
            ParseInt(local.GetProperty("pageBound")) == 200 && ParseInt(local.GetProperty("publicPageBound")) == 100, "local twin fixture facts");
        var localService = Loc.ConnectorBrokerService.Descriptor;
        Require(localService.FullName == "arcforges.local.platform.v1.ConnectorBrokerService", "local twin service identity");
        Require(localService.Methods.Select(method => method.Name).SequenceEqual(MethodNames), "local twin methods map 1:1 by name and order");
        var localFile = localService.File;
        var localMessages = localFile.MessageTypes.ToDictionary(message => message.Name, StringComparer.Ordinal);
        foreach (var name in RecordNames)
        {
            var publicSignature = Signature(messageByName[name]);
            var localSignature = Signature(localMessages[name]);
            Require(publicSignature.Length > 0 && publicSignature.SequenceEqual(localSignature), name + " public and local record descriptors are field-for-field equal");
            Require(messageByName[name].FullName != localMessages[name].FullName, name + " twins are distinct types");
        }
        for (var index = 0; index < MethodNames.Length; index++)
        {
            var publicMethod = service.Methods[index];
            var localMethod = localService.Methods[index];
            Require(publicMethod.Name == localMethod.Name, "twin method " + index);
            Require(Signature(publicMethod.InputType).SequenceEqual(Signature(localMethod.InputType)), publicMethod.Name + " request payload equals local twin");
            var publicValue = publicMethod.OutputType.FindFieldByNumber(2)!.MessageType;
            var localValue = localMethod.OutputType.FindFieldByNumber(2)!.MessageType;
            Require(Signature(publicValue).SequenceEqual(Signature(localValue)), publicMethod.Name + " value payload equals local twin");
            Require(Signature(publicMethod.OutputType).Where(item => item.Number <= 3).SequenceEqual(Signature(localMethod.OutputType).Where(item => item.Number <= 3)),
                publicMethod.Name + " response meta/value/error equals local twin");
        }
        ProveParityIsDiscriminating(Signature(messageByName["ConnectorConnection"]));
        ProveParityIsDiscriminating(Signature(messageByName["ConnectorProof"]));
        ProveParityIsDiscriminating(Signature(messageByName["ConnectorServiceListConnectionsValue"]));

        // Operation export.
        using var exportDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/operations/con-25.json")));
        var rows = exportDocument.RootElement.GetProperty("operations").EnumerateArray().ToArray();
        Require(rows.Length == 6, "exactly six exported connector operations");
        Require(rows.Select(row => row.GetProperty("operationId").GetString()).Order(StringComparer.Ordinal)
            .SequenceEqual(AuthTable.Select(row => row.OperationId).Order(StringComparer.Ordinal), StringComparer.Ordinal), "exported operation ids");
        foreach (var expected in AuthTable)
        {
            var row = rows.Single(item => item.GetProperty("operationId").GetString() == expected.OperationId);
            var authorization = row.GetProperty("authorization");
            Require(row.GetProperty("binding").GetString() == "arcforges.publicapi.v1.ConnectorService/" + expected.Method, expected.OperationId + " export binding");
            Require(row.GetProperty("kind").GetString() == "proto" && row.GetProperty("source").GetString() == "public/proto/arcforges/publicapi/v1/connector.proto", expected.OperationId + " export source");
            Require(row.GetProperty("scope").GetString() == "assistant" && row.GetProperty("surface").GetString() == "public" &&
                row.GetProperty("profile").GetString() == "human-owner", expected.OperationId + " export classification");
            Require(row.GetProperty("idempotency").GetString() == expected.Idempotency && authorization.GetProperty("risk").GetString() == expected.Risk &&
                authorization.GetProperty("approval").GetString() == expected.Approval && authorization.GetProperty("stepUp").GetBoolean() == expected.StepUp &&
                authorization.GetProperty("egress").GetString() == expected.Egress, expected.OperationId + " export idempotency/risk/approval/stepUp/egress");
            Require(authorization.GetProperty("capability").ValueKind == JsonValueKind.Null && !authorization.GetProperty("localPresence").GetBoolean() &&
                !authorization.GetProperty("patEligible").GetBoolean() && authorization.GetProperty("actorKinds").GetArrayLength() == 1 &&
                authorization.GetProperty("actorKinds")[0].GetString() == "human", expected.OperationId + " export actor kinds human only");
        }
        using var scopeManifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/operation-scope-manifest.json")));
        foreach (var entry in scopeManifest.RootElement.GetProperty("toolAllowlist").EnumerateArray())
        {
            var raw = entry.GetRawText();
            Require(!AuthTable.Any(expected => raw.Contains(expected.OperationId, StringComparison.Ordinal)), "no connector operation is tool-reachable: " + raw);
        }

        // Shape-validator vectors, consumed exactly once, with public/local validator agreement.
        var vectors = fixture.GetProperty("vectors").EnumerateArray().ToArray();
        ExactIds("connector", vectors.Select(vector => vector.GetProperty("id").GetString()!), ConnectorVectorIds);
        var consumed = new HashSet<string>(StringComparer.Ordinal);
        var positives = 0;
        var negatives = 0;
        foreach (var vector in vectors)
        {
            var id = vector.GetProperty("id").GetString()!;
            Require(consumed.Add(id), "no vector is consumed twice: " + id);
            var type = vector.GetProperty("type").GetString()!;
            var valid = vector.GetProperty("valid").GetBoolean();
            var result = EvaluateConnector(type, vector.GetProperty("value"), id);
            Require(result.WireRoundTrips, id + " protobuf round trip keeps presence");
            Require(result.Public == valid, id + " public shape validator " + (valid ? "accepts" : "rejects"));
            if (type == "ConnectorServiceListConnectionsValue")
            {
                // Only the page bound differs between the twins: 100 public versus 200 local items.
                Require(result.Local == (result.ItemCount <= 200 && result.ItemsValid), id + " local list page bound is 200");
                Require(valid == (result.ItemCount <= 100 && result.ItemsValid), id + " public list page bound is 100");
            }
            else
            {
                Require(result.Local == result.Public, id + " public and local validators agree");
            }
            if (valid) positives++; else negatives++;
        }
        Require(consumed.SetEquals(ConnectorVectorIds) && positives == 12 && negatives == 27, "every connector vector is consumed exactly once");
        Console.WriteLine("CON.25 connector: exact ConnectorService descriptors, authorization export, twin parity and all 39 shape vectors passed.");
    }

    private sealed record ConnectorResult(bool Public, bool Local, bool WireRoundTrips, int ItemCount, bool ItemsValid);

    private static ConnectorResult EvaluateConnector(string type, JsonElement value, string id)
    {
        switch (type)
        {
            case "ConnectorDefinition":
                {
                    var message = BuildDefinition(value);
                    var twin = Loc.ConnectorDefinition.Parser.ParseFrom(message.ToByteArray());
                    return new(PubShapes.IsValid(message), LocShapes.IsValid(twin), RoundTrips(message, Pub.ConnectorDefinition.Parser, twin), 0, true);
                }
            case "ConnectorConnection":
                {
                    var message = BuildConnection(value);
                    var twin = Loc.ConnectorConnection.Parser.ParseFrom(message.ToByteArray());
                    return new(PubShapes.IsValid(message), LocShapes.IsValid(twin), RoundTrips(message, Pub.ConnectorConnection.Parser, twin), 0, true);
                }
            case "ConnectorChallenge":
                {
                    var message = BuildChallenge(value);
                    var twin = Loc.ConnectorChallenge.Parser.ParseFrom(message.ToByteArray());
                    return new(PubShapes.IsValid(message), LocShapes.IsValid(twin), RoundTrips(message, Pub.ConnectorChallenge.Parser, twin), 0, true);
                }
            case "ConnectorProof":
                {
                    var message = BuildProof(value);
                    var twin = Loc.ConnectorProof.Parser.ParseFrom(message.ToByteArray());
                    return new(PubShapes.IsValid(message), LocShapes.IsValid(twin), RoundTrips(message, Pub.ConnectorProof.Parser, twin), 0, true);
                }
            case "ConnectorServiceBeginConnectionRequest":
                {
                    Keys(value, id, "connectionIdHex", "definitionId", "name");
                    var message = new Pub.ConnectorServiceBeginConnectionRequest { Meta = ValidMeta() };
                    if (value.TryGetProperty("connectionIdHex", out var connectionId)) message.ConnectionId = IdFromHex(connectionId.GetString()!);
                    if (value.TryGetProperty("definitionId", out var definitionId)) message.DefinitionId = definitionId.GetString()!;
                    if (value.TryGetProperty("name", out var name)) message.Name = name.GetString()!;
                    var twin = Loc.ConnectorBrokerServiceBeginConnectionRequest.Parser.ParseFrom(message.ToByteArray());
                    var withoutMeta = message.Clone();
                    withoutMeta.Meta = null;
                    Require(!PubShapes.IsValid(withoutMeta) && !LocShapes.IsValid(Loc.ConnectorBrokerServiceBeginConnectionRequest.Parser.ParseFrom(withoutMeta.ToByteArray())), id + " request meta is required");
                    return new(PubShapes.IsValid(message), LocShapes.IsValid(twin), RoundTrips(message, Pub.ConnectorServiceBeginConnectionRequest.Parser, twin), 0, true);
                }
            case "ConnectorServiceCompleteConnectionRequest":
                {
                    Keys(value, id, "flowIdHex", "proof");
                    var message = new Pub.ConnectorServiceCompleteConnectionRequest { Meta = ValidMeta() };
                    if (value.TryGetProperty("flowIdHex", out var flowId)) message.FlowId = IdFromHex(flowId.GetString()!);
                    if (value.TryGetProperty("proof", out var proof)) message.Proof = BuildProof(proof);
                    var twin = Loc.ConnectorBrokerServiceCompleteConnectionRequest.Parser.ParseFrom(message.ToByteArray());
                    var withoutMeta = message.Clone();
                    withoutMeta.Meta = null;
                    Require(!PubShapes.IsValid(withoutMeta) && !LocShapes.IsValid(Loc.ConnectorBrokerServiceCompleteConnectionRequest.Parser.ParseFrom(withoutMeta.ToByteArray())), id + " request meta is required");
                    return new(PubShapes.IsValid(message), LocShapes.IsValid(twin), RoundTrips(message, Pub.ConnectorServiceCompleteConnectionRequest.Parser, twin), 0, true);
                }
            case "ConnectorServiceRevokeConnectionRequest":
                {
                    Keys(value, id, "connectionIdHex");
                    var message = new Pub.ConnectorServiceRevokeConnectionRequest { Meta = ValidMeta() };
                    if (value.TryGetProperty("connectionIdHex", out var connectionId)) message.ConnectionId = IdFromHex(connectionId.GetString()!);
                    var twin = Loc.ConnectorBrokerServiceRevokeConnectionRequest.Parser.ParseFrom(message.ToByteArray());
                    var withoutMeta = message.Clone();
                    withoutMeta.Meta = null;
                    Require(!PubShapes.IsValid(withoutMeta) && !LocShapes.IsValid(Loc.ConnectorBrokerServiceRevokeConnectionRequest.Parser.ParseFrom(withoutMeta.ToByteArray())), id + " request meta is required");
                    return new(PubShapes.IsValid(message), LocShapes.IsValid(twin), RoundTrips(message, Pub.ConnectorServiceRevokeConnectionRequest.Parser, twin), 0, true);
                }
            case "ConnectorServiceListConnectionsValue":
                {
                    Keys(value, id, "items", "page");
                    var message = new Pub.ConnectorServiceListConnectionsValue();
                    foreach (var item in value.GetProperty("items").EnumerateArray()) message.Items.Add(BuildConnection(item));
                    if (value.TryGetProperty("page", out var page))
                    {
                        Keys(page, id, "hasMore", "nextCursor");
                        var state = new PageState();
                        if (page.TryGetProperty("hasMore", out var hasMore)) state.HasMore = hasMore.GetBoolean();
                        if (page.TryGetProperty("nextCursor", out var cursor)) state.NextCursor = cursor.GetString()!;
                        message.Page = state;
                    }
                    var twin = Loc.ConnectorBrokerServiceListConnectionsValue.Parser.ParseFrom(message.ToByteArray());
                    var itemsValid = message.Items.All(item => PubShapes.IsValid(item));
                    Require(itemsValid == twin.Items.All(item => LocShapes.IsValid(item)), id + " item validators agree");
                    return new(PubShapes.IsValid(message), LocShapes.IsValid(twin), RoundTrips(message, Pub.ConnectorServiceListConnectionsValue.Parser, twin), message.Items.Count, itemsValid);
                }
            default:
                throw new InvalidOperationException("Unknown CON.25 connector vector type " + type + " in " + id);
        }
    }

    // The fixture request models carry payload fields only; every request gets the same minimal valid RequestMeta (correlationId).
    private static RequestMeta ValidMeta() => new() { CorrelationId = IdFromHex("00000000000000000000000000000abc") };

    private static bool RoundTrips<T, TTwin>(T message, MessageParser<T> parser, TTwin twin)
        where T : IMessage<T>
        where TTwin : IMessage
    {
        var bytes = message.ToByteArray();
        var parsed = parser.ParseFrom(bytes);
        return parsed.Equals(message) && parsed.ToByteArray().SequenceEqual(bytes) && twin.ToByteArray().SequenceEqual(bytes);
    }

    private static Pub.ConnectorDefinition BuildDefinition(JsonElement e)
    {
        Keys(e, "definition", "definitionId", "packageId", "packageVersion", "manifestHash", "authKind", "origins", "scopes", "capabilities");
        var message = new Pub.ConnectorDefinition();
        if (e.TryGetProperty("definitionId", out var definitionId)) message.DefinitionId = definitionId.GetString()!;
        if (e.TryGetProperty("packageId", out var packageId)) message.PackageId = packageId.GetString()!;
        if (e.TryGetProperty("packageVersion", out var packageVersion)) message.PackageVersion = packageVersion.GetString()!;
        if (e.TryGetProperty("manifestHash", out var manifestHash)) message.ManifestHash = manifestHash.GetString()!;
        if (e.TryGetProperty("authKind", out var authKind)) message.AuthKind = authKind.GetString()!;
        if (e.TryGetProperty("origins", out var origins)) foreach (var item in origins.EnumerateArray()) message.Origins.Add(item.GetString()!);
        if (e.TryGetProperty("scopes", out var scopes)) foreach (var item in scopes.EnumerateArray()) message.Scopes.Add(item.GetString()!);
        if (e.TryGetProperty("capabilities", out var capabilities)) foreach (var item in capabilities.EnumerateArray()) message.Capabilities.Add(item.GetString()!);
        return message;
    }

    private static Pub.ConnectorConnection BuildConnection(JsonElement e)
    {
        Keys(e, "connection", "connectionIdHex", "definitionId", "name", "state", "scopes", "revision", "expiresAt", "reason");
        var message = new Pub.ConnectorConnection();
        if (e.TryGetProperty("connectionIdHex", out var connectionId)) message.ConnectionId = IdFromHex(connectionId.GetString()!);
        if (e.TryGetProperty("definitionId", out var definitionId)) message.DefinitionId = definitionId.GetString()!;
        if (e.TryGetProperty("name", out var name)) message.Name = name.GetString()!;
        if (e.TryGetProperty("state", out var state)) message.State = state.GetString()!;
        if (e.TryGetProperty("scopes", out var scopes)) foreach (var item in scopes.EnumerateArray()) message.Scopes.Add(item.GetString()!);
        if (e.TryGetProperty("revision", out var revision)) message.Revision = new Revision { Value = ModelS64(revision) };
        if (e.TryGetProperty("expiresAt", out var expiresAt)) message.ExpiresAt = BuildInstant(expiresAt);
        if (e.TryGetProperty("reason", out var reason)) message.Reason = reason.GetString()!;
        return message;
    }

    private static Pub.ConnectorChallenge BuildChallenge(JsonElement e)
    {
        Keys(e, "challenge", "flowIdHex", "connectionIdHex", "authorizationUrl", "expiresAt");
        var message = new Pub.ConnectorChallenge();
        if (e.TryGetProperty("flowIdHex", out var flowId)) message.FlowId = IdFromHex(flowId.GetString()!);
        if (e.TryGetProperty("connectionIdHex", out var connectionId)) message.ConnectionId = IdFromHex(connectionId.GetString()!);
        if (e.TryGetProperty("authorizationUrl", out var url)) message.AuthorizationUrl = url.GetString()!;
        if (e.TryGetProperty("expiresAt", out var expiresAt)) message.ExpiresAt = BuildInstant(expiresAt);
        return message;
    }

    private static Pub.ConnectorProof BuildProof(JsonElement e)
    {
        Keys(e, "proof", "callbackReceipt", "personalToken");
        var message = new Pub.ConnectorProof();
        if (e.TryGetProperty("callbackReceipt", out var receipt)) message.CallbackReceipt = receipt.GetString()!;
        if (e.TryGetProperty("personalToken", out var token)) message.PersonalToken = token.GetString()!;
        return message;
    }

    private static Instant BuildInstant(JsonElement e)
    {
        Keys(e, "instant", "unixSeconds", "nanos");
        var instant = new Instant();
        if (e.TryGetProperty("unixSeconds", out var seconds)) instant.UnixSeconds = ModelS64(seconds);
        if (e.TryGetProperty("nanos", out var nanos)) instant.Nanos = ModelU32(nanos);
        return instant;
    }

    private readonly record struct FieldSig(int Number, string Name, string JsonName, FieldType Type, bool Repeated, string Presence, string TypeName);

    // The four records and ConnectorService* payloads live in two packages; twin record and service-message names are normalised
    // to one spelling so only the real shape (numbers, names, kinds, presence, oneof membership) is compared.
    private static string NormalizeType(string fullName)
    {
        const string publicPackage = "arcforges.publicapi.v1.";
        const string localPackage = "arcforges.local.platform.v1.";
        string? shortName = null;
        if (fullName.StartsWith(publicPackage, StringComparison.Ordinal)) shortName = fullName[publicPackage.Length..];
        else if (fullName.StartsWith(localPackage, StringComparison.Ordinal)) shortName = fullName[localPackage.Length..];
        if (shortName is null || !shortName.StartsWith("Connector", StringComparison.Ordinal)) return fullName;
        return "twin:" + shortName.Replace("ConnectorBrokerService", "ConnectorService", StringComparison.Ordinal);
    }

    private static FieldSig[] Signature(MessageDescriptor descriptor) => descriptor.Fields.InFieldNumberOrder().Select(field => new FieldSig(
        field.FieldNumber, field.Name, field.JsonName, field.FieldType, field.IsRepeated,
        field.ContainingOneof is { IsSynthetic: false } oneof ? "oneof:" + oneof.Name
            : field.ContainingOneof is { IsSynthetic: true } ? "optional"
            : field.HasPresence ? "presence" : "none",
        field.FieldType == FieldType.Message ? NormalizeType(field.MessageType.FullName)
            : field.FieldType == FieldType.Enum ? field.EnumType.FullName : "")).ToArray();

    private static void ProveParityIsDiscriminating(FieldSig[] source)
    {
        Require(source.Length > 0 && source.SequenceEqual(source.ToArray()), "parity baseline equals an identical copy");
        for (var index = 0; index < source.Length; index++)
        {
            var field = source[index];
            var mismatches = new[]
            {
                field with { Number = field.Number + 1 },
                field with { Name = field.Name + "_x" },
                field with { JsonName = field.JsonName + "X" },
                field with { Type = field.Type == FieldType.String ? FieldType.Bytes : FieldType.String },
                field with { Repeated = !field.Repeated },
                field with { Presence = field.Presence + "!" },
                field with { TypeName = field.TypeName + ".other" }
            };
            foreach (var mismatch in mismatches)
            {
                var copy = source.ToArray();
                copy[index] = mismatch;
                Require(!source.SequenceEqual(copy), "a mismatched field-list copy must fail the parity comparison");
            }
        }
        Require(!source.SequenceEqual(source.Take(source.Length - 1)), "a truncated field list fails the parity comparison");
        Require(!source.SequenceEqual(source.Concat([new FieldSig(999, "extra", "extra", FieldType.String, false, "none", "")])), "an extended field list fails the parity comparison");
    }

    private static bool FieldList(MessageDescriptor descriptor, JsonElement expected, int minimumNumber, int maximumNumber)
    {
        var actual = descriptor.Fields.InFieldNumberOrder().Where(field => field.FieldNumber >= minimumNumber && field.FieldNumber <= maximumNumber)
            .Select(field => (field.JsonName, field.FieldNumber)).ToArray();
        var wanted = expected.EnumerateArray().Select(item => (item[0].GetString()!, ParseInt(item[1]))).ToArray();
        return actual.SequenceEqual(wanted);
    }

    private static JsonElement ExpectedList(params (string Name, int Number)[] items)
    {
        var builder = new StringBuilder("[");
        for (var index = 0; index < items.Length; index++)
        {
            if (index > 0) builder.Append(',');
            builder.Append("[\"").Append(items[index].Name).Append("\",").Append(items[index].Number.ToString(CultureInfo.InvariantCulture)).Append(']');
        }
        builder.Append(']');
        using var document = JsonDocument.Parse(builder.ToString());
        return document.RootElement.Clone();
    }

    // ------------------------------------------------------------------------------------------------------------
    // Part 2: LocalCallContext
    // ------------------------------------------------------------------------------------------------------------

    private static void RunLocalCallContext(string root)
    {
        using var fixtureDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/internal/con-25-local-call-context.json")));
        var fixture = fixtureDocument.RootElement;
        Require(fixture.GetProperty("schemaVersion").GetString() == "con-25-local-call-context.v1", "context fixture schema");
        Require(fixture.GetProperty("evidenceClass").GetString() == "offline-contract-only-no-binding-or-forwarding-behavior", "context fixture boundary");
        var record = fixture.GetProperty("record");
        var maxBytes = ParseInt(record.GetProperty("maxSerializedBytes"));
        var maxRoots = ParseInt(record.GetProperty("maxScopeRoots"));
        Require(maxBytes == 4096 && maxRoots == 32 && record.GetProperty("message").GetString() == "arcforges.local.platform.v1.LocalCallContext", "context limits and identity");

        var descriptor = Loc.LocalCallContext.Descriptor;
        Require(descriptor.FullName == "arcforges.local.platform.v1.LocalCallContext" && descriptor.File.Package == "arcforges.local.platform.v1", "LocalCallContext lives in the local platform package");
        var dependencies = descriptor.File.Dependencies.Select(dependency => dependency.Name).ToArray();
        Require(dependencies.Contains("arcforges/publicapi/v1/chat.proto") && dependencies.Contains("arcforges/foundation/v1/foundation.proto"), "platform.proto imports public chat and foundation");
        var specs = record.GetProperty("fields").EnumerateArray().ToArray();
        var fields = descriptor.Fields.InFieldNumberOrder().ToArray();
        Require(fields.Length == specs.Length && fields.Length == 6, "LocalCallContext field count");
        for (var index = 0; index < specs.Length; index++)
        {
            var typeText = specs[index][2].GetString()!;
            var repeated = typeText.StartsWith("repeated ", StringComparison.Ordinal);
            var typeName = repeated ? typeText["repeated ".Length..] : typeText;
            Require(fields[index].JsonName == specs[index][0].GetString() && fields[index].FieldNumber == ParseInt(specs[index][1]) && fields[index].IsRepeated == repeated &&
                fields[index].FieldType == FieldType.Message && fields[index].MessageType.FullName == typeName && fields[index].ContainingOneof is null, "LocalCallContext field " + index);
        }
        Require(fields[0].MessageType.FullName == "arcforges.foundation.v1.ActorChain" && fields[1].MessageType.FullName == "arcforges.foundation.v1.AggregateRef" &&
            fields[5].MessageType.FullName == "arcforges.publicapi.v1.ExecutionOwner", "LocalCallContext imports public ActorChain, AggregateRef and ExecutionOwner");
        var definitions = 0;
        foreach (var protoRoot in new[] { "public/proto", "internal/proto" })
        {
            foreach (var path in Directory.EnumerateFiles(Path.Combine(root, protoRoot), "*.proto", SearchOption.AllDirectories))
            {
                foreach (var line in File.ReadAllLines(path))
                {
                    if (line.TrimStart().StartsWith("message LocalCallContext", StringComparison.Ordinal))
                    {
                        definitions++;
                        Require(path.Replace('\\', '/').EndsWith("internal/proto/arcforges/local/platform/v1/platform.proto", StringComparison.Ordinal), "LocalCallContext is defined only in the local platform proto");
                    }
                }
            }
        }
        Require(definitions == 1, "exactly one LocalCallContext definition");

        var vectors = fixture.GetProperty("vectors").EnumerateArray().ToArray();
        ExactIds("local call context", vectors.Select(vector => vector.GetProperty("id").GetString()!), ContextVectorIds);
        var consumed = new HashSet<string>(StringComparer.Ordinal);
        foreach (var vector in vectors)
        {
            var id = vector.GetProperty("id").GetString()!;
            Require(consumed.Add(id), "no vector is consumed twice: " + id);
            var valid = vector.GetProperty("valid").GetBoolean();
            var context = BuildContext(vector.GetProperty("context"), id);
            var wire = context.ToByteArray();
            var wireHex = vector.GetProperty("wireHex").GetString()!;
            Require(ToHex(wire) == wireHex, id + " exact wire bytes");
            Require(ParseInt(vector.GetProperty("wireBytes")) == wire.Length && wire.Length == wireHex.Length / 2 && context.CalculateSize() == wire.Length, id + " wire length");
            var parsed = Loc.LocalCallContext.Parser.ParseFrom(HexToBytes(wireHex));
            Require(parsed.Equals(context) && parsed.ToByteArray().SequenceEqual(wire), id + " fixture wire bytes parse back to the same message");

            var shapeOk = LocShapes.IsValid(parsed);
            Require(shapeOk == LocShapes.IsValid(context), id + " validator agrees on built and parsed messages");
            var sizeOk = parsed.CalculateSize() <= maxBytes;
            var countOk = parsed.Scope.Count <= maxRoots;
            Require((shapeOk && sizeOk && countOk) == valid, id + " validity = shape validator and <= 4096 bytes and <= 32 roots");
            switch (id)
            {
                case "refuse-thirty-three-scope-roots":
                    Require(parsed.Scope.Count == 33 && sizeOk && !shapeOk, id + " rejected by the 32-root count although it is well under 4 KiB");
                    break;
                case "refuse-over-four-kib":
                    Require(parsed.Scope.Count == 32 && shapeOk && countOk && !sizeOk && wire.Length == 4997, id + " rejected only by the 4096-byte bound with 32 roots");
                    break;
                case "thirty-two-scope-roots-within-four-kib":
                    Require(parsed.Scope.Count == 32 && shapeOk && sizeOk, id + " accepted at exactly 32 roots");
                    break;
                default:
                    Require(valid || (!shapeOk && sizeOk && countOk), id + " negative vector is rejected by the shape validator itself");
                    break;
            }
        }
        Require(consumed.SetEquals(ContextVectorIds), "every context vector is consumed exactly once");
        Console.WriteLine("CON.25 local call context: descriptor facts and all 12 exact-wire vectors passed.");
    }

    private static Loc.LocalCallContext BuildContext(JsonElement e, string id)
    {
        Keys(e, id, "actor", "scope", "invocationIdHex", "approvalIdHex", "leaseIdHex", "executionOwner");
        var context = new Loc.LocalCallContext();
        if (e.TryGetProperty("actor", out var actor))
        {
            Keys(actor, id, "initiatorHex", "ownerHex", "actorKind", "deviceIdHex", "delegationIdHex");
            var chain = new ActorChain();
            if (actor.TryGetProperty("initiatorHex", out var initiator)) chain.Initiator = IdFromHex(initiator.GetString()!);
            if (actor.TryGetProperty("ownerHex", out var owner)) chain.Owner = IdFromHex(owner.GetString()!);
            if (actor.TryGetProperty("actorKind", out var kind)) chain.ActorKind = kind.GetString()!;
            if (actor.TryGetProperty("deviceIdHex", out var device)) chain.DeviceId = IdFromHex(device.GetString()!);
            if (actor.TryGetProperty("delegationIdHex", out var delegation)) chain.DelegationId = IdFromHex(delegation.GetString()!);
            context.Actor = chain;
        }
        if (e.TryGetProperty("scope", out var scope))
        {
            foreach (var item in scope.EnumerateArray())
            {
                Keys(item, id, "kind", "idHex");
                var reference = new AggregateRef();
                if (item.TryGetProperty("kind", out var kind)) reference.Kind = kind.GetString()!;
                if (item.TryGetProperty("idHex", out var idHex)) reference.Id = IdFromHex(idHex.GetString()!);
                context.Scope.Add(reference);
            }
        }
        if (e.TryGetProperty("invocationIdHex", out var invocation)) context.InvocationId = IdFromHex(invocation.GetString()!);
        if (e.TryGetProperty("approvalIdHex", out var approval)) context.ApprovalId = IdFromHex(approval.GetString()!);
        if (e.TryGetProperty("leaseIdHex", out var lease)) context.LeaseId = IdFromHex(lease.GetString()!);
        if (e.TryGetProperty("executionOwner", out var executionOwner))
        {
            Keys(executionOwner, id, "taskIdHex", "turnIdHex");
            var ownerMessage = new Pub.ExecutionOwner();
            if (executionOwner.TryGetProperty("taskIdHex", out var task)) ownerMessage.TaskId = IdFromHex(task.GetString()!);
            if (executionOwner.TryGetProperty("turnIdHex", out var turn)) ownerMessage.TurnId = IdFromHex(turn.GetString()!);
            context.ExecutionOwner = ownerMessage;
        }
        return context;
    }

    // ------------------------------------------------------------------------------------------------------------
    // Part 3: canonical af-segment.v1
    // ------------------------------------------------------------------------------------------------------------

    private static void RunAfSegment(string root)
    {
        using var fixtureDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-25-af-segment.json")));
        var fixture = fixtureDocument.RootElement;
        Require(fixture.GetProperty("schemaVersion").GetString() == "con-25-af-segment.v1", "segment fixture schema");
        Require(fixture.GetProperty("evidenceClass").GetString() == "offline-contract-only-no-simulator-or-native-reader", "segment fixture boundary");
        var profile = fixture.GetProperty("profile");
        Require(profile.GetProperty("id").GetString() == "af-segment.v1" && profile.GetProperty("executionProfile").GetString() == "af-sim.v1", "segment profile identity");

        var vectors = fixture.GetProperty("vectors").EnumerateArray().ToArray();
        var refusals = fixture.GetProperty("refusals").EnumerateArray().ToArray();
        ExactIds("segment", vectors.Select(vector => vector.GetProperty("id").GetString()!), SegmentVectorIds);
        ExactIds("segment refusal", refusals.Select(refusal => refusal.GetProperty("id").GetString()!), SegmentRefusals.Keys.ToArray());

        var consumed = new HashSet<string>(StringComparer.Ordinal);
        var canonicalTexts = new List<string>();
        foreach (var vector in vectors)
        {
            var id = vector.GetProperty("id").GetString()!;
            Require(consumed.Add(id), "no segment vector is consumed twice: " + id);
            var canonical = vector.GetProperty("canonicalJson").GetString()!;
            canonicalTexts.Add(canonical);
            var segment = BuildSegmentModel(vector.GetProperty("segment"));

            // (a) ENCODE: in-test canonical encoder over the generated message.
            var encoded = EncodeSegment(segment);
            Require(encoded == canonical, id + " canonical JSON text");
            var bytes = StrictUtf8().GetBytes(encoded);
            Require(bytes.Length == ParseInt(vector.GetProperty("utf8Bytes")), id + " UTF-8 byte length");
            Require(Convert.ToHexStringLower(SHA256.HashData(bytes)) == vector.GetProperty("sha256").GetString(), id + " SHA-256");
            Require(bytes.Length >= 3 && !(bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF), id + " no byte order mark");
            Require(PubShapes.IsValid(segment), id + " generated shape validator accepts the segment");

            // Protobuf round trip keeps optional presence, oneof arm and repeated order.
            var parsed = SimulationDataSegment.Parser.ParseFrom(segment.ToByteArray());
            Require(parsed.Equals(segment) && EncodeSegment(parsed) == canonical && PubShapes.IsValid(parsed), id + " protobuf round trip");
            AssertPresence(id, segment, parsed);

            // (b) STRICT READ of the canonical text must rebuild the identical message and re-encode byte for byte.
            var read = ReadStrict(canonical);
            Require(read.Equals(segment) && EncodeSegment(read) == canonical, id + " strict read re-encodes identically");
        }
        Require(consumed.SetEquals(SegmentVectorIds), "every segment vector is consumed exactly once");

        var consumedRefusals = new HashSet<string>(StringComparer.Ordinal);
        foreach (var refusal in refusals)
        {
            var id = refusal.GetProperty("id").GetString()!;
            Require(consumedRefusals.Add(id), "no refusal is consumed twice: " + id);
            var text = refusal.GetProperty("canonicalJson").GetString()!;
            Require(!canonicalTexts.Contains(text, StringComparer.Ordinal), id + " differs from every positive text");
            string? code = null;
            try { ReadStrict(text); }
            catch (Refused refused) { code = refused.Code; }
            Require(code is not null, id + " must be refused by the strict reader");
            Require(code == SegmentRefusals[id], id + " refused for the intended reason (expected " + SegmentRefusals[id] + ", got " + code + ")");
        }
        Require(consumedRefusals.SetEquals(SegmentRefusals.Keys), "every refusal is consumed exactly once");
        Require(Refuses("{}", "member") && Refuses("[]", "type") && Refuses("", "json"), "reader refuses structurally wrong documents");

        // Generated shape validator catches what the encoder cannot express, and the reader refuses the matching text.
        var positive = BuildSegmentModel(vectors.Single(vector => vector.GetProperty("id").GetString() == "gap-and-fault-markers-with-and-without-channel").GetProperty("segment"));
        Require(PubShapes.IsValid(positive), "validator baseline");
        var badKind = positive.Clone();
        badKind.Gaps[0].Kind = "lost";
        Require(!PubShapes.IsValid(badKind) && Refuses(EncodeSegment(badKind), "gapKind"), "unknown gap kind: validator and reader refuse");
        var badEncodingProfile = positive.Clone();
        badEncodingProfile.EncodingProfile = "af-segment.v2";
        Require(!PubShapes.IsValid(badEncodingProfile) && Refuses(EncodeSegment(badEncodingProfile), "profile"), "wrong encodingProfile: validator and reader refuse");
        var badExecutionProfile = positive.Clone();
        badExecutionProfile.ExecutionProfile = "af-sim.v2";
        Require(!PubShapes.IsValid(badExecutionProfile) && Refuses(EncodeSegment(badExecutionProfile), "profile"), "wrong executionProfile: validator and reader refuse");
        var zeroId = positive.Clone();
        zeroId.Records[0].ChannelId = new Id { Value = ByteString.CopyFrom(new byte[16]) };
        Require(!PubShapes.IsValid(zeroId) && Refuses(EncodeSegment(zeroId), "id"), "zero Id: validator and reader refuse");
        var missingOneof = positive.Clone();
        missingOneof.Records[0].ClearValue();
        Require(!PubShapes.IsValid(missingOneof), "missing oneof arm: validator refuses");
        Require(RefusesEncode(missingOneof, "oneof"), "missing oneof arm: encoder refuses");

        // The encoder itself refuses what af-segment.v1 cannot represent.
        var nonFinite = positive.Clone();
        nonFinite.Records[0].ClearValue();
        nonFinite.Records[0].Numeric = double.NaN;
        Require(RefusesEncode(nonFinite, "double"), "NaN numeric is refused by the encoder");
        nonFinite.Records[0].Numeric = double.PositiveInfinity;
        Require(RefusesEncode(nonFinite, "double"), "infinite numeric is refused by the encoder");
        var surrogate = positive.Clone();
        surrogate.Events[0].Kind = "bad\ud800";
        Require(RefusesEncode(surrogate, "surrogate"), "an unpaired surrogate is refused by the encoder");
        var shortId = positive.Clone();
        shortId.Records[0].ChannelId = new Id { Value = ByteString.CopyFrom(new byte[15]) };
        Require(RefusesEncode(shortId, "id"), "a malformed Id is refused by the encoder");
        var resource = positive.Clone();
        resource.Events[0].Fields.Add(new Pub.MetadataEntry { Name = "r", Value = new Pub.MetadataScalar { Resource = new ResourceRef() } });
        Require(RefusesEncode(resource, "metadata"), "the resource metadata arm is refused by the encoder");

        Console.WriteLine("CON.25 af-segment.v1: 7 vectors encode/strict-read/round-trip, 28 refusals refused for their reasons, validator parity passed.");
    }

    private static bool Refuses(string text, string code)
    {
        try { ReadStrict(text); return false; }
        catch (Refused refused) { return refused.Code == code; }
    }

    private static bool RefusesEncode(SimulationDataSegment segment, string code)
    {
        try { EncodeSegment(segment); return false; }
        catch (Refused refused) { return refused.Code == code; }
    }

    private static void AssertPresence(string id, SimulationDataSegment original, SimulationDataSegment parsed)
    {
        foreach (var segment in new[] { original, parsed })
        {
            Require(segment.HasEncodingProfile && segment.HasExecutionProfile && segment.HasStartTick && segment.HasTickCount, id + " optional scalars have presence");
            switch (id)
            {
                case "empty-segment-keeps-every-ordered-repeated-field":
                    Require(segment.StartTick == 0 && segment.TickCount == 0 && segment.Records.Count == 0 && segment.Events.Count == 0 && segment.Gaps.Count == 0, id + " zero presence and empty repeated members");
                    break;
                case "numeric-digital-and-event-samples-in-delivered-order":
                    Require(segment.Records.Select(record => record.ValueCase).SequenceEqual(
                        [SimulationSample.ValueOneofCase.Numeric, SimulationSample.ValueOneofCase.Digital, SimulationSample.ValueOneofCase.EventId]), id + " oneof arms");
                    Require(segment.Events[0].Duration is not null && segment.Events[1].Duration is null && segment.Events[0].FaultId is null && segment.Events[1].FaultId is null, id + " optional duration and faultId presence");
                    Require(segment.Events[0].Fields.Select(field => field.Value.ValueCase).SequenceEqual(
                        [Pub.MetadataScalar.ValueOneofCase.Text, Pub.MetadataScalar.ValueOneofCase.Boolean, Pub.MetadataScalar.ValueOneofCase.Integer,
                            Pub.MetadataScalar.ValueOneofCase.Number, Pub.MetadataScalar.ValueOneofCase.Decimal, Pub.MetadataScalar.ValueOneofCase.Instant]), id + " metadata scalar arms");
                    break;
                case "duplicate-delivery-differs-only-by-ordinal-and-fault-marker":
                    Require(segment.Records.Count == 2 && segment.Records[0].FaultIds.Count == 0 && segment.Records[1].FaultIds.Count == 1 &&
                        segment.Records[0].Tick == segment.Records[1].Tick && segment.Records[0].DeliveredOrdinal + 1 == segment.Records[1].DeliveredOrdinal, id + " duplicate delivery");
                    break;
                case "gap-and-fault-markers-with-and-without-channel":
                    Require(segment.Records[0].ValueCase == SimulationSample.ValueOneofCase.Digital && !segment.Records[0].Digital &&
                        segment.Records[1].ValueCase == SimulationSample.ValueOneofCase.Digital && segment.Records[1].Digital, id + " explicit digital false keeps its arm");
                    Require(segment.Gaps[0].ChannelId is not null && segment.Gaps[1].ChannelId is null && segment.Gaps[2].ChannelId is not null &&
                        segment.Events[0].FaultId is not null, id + " optional channel and fault presence");
                    break;
                case "binary64-bit-words-preserve-sign-and-extremes":
                    Require(BitConverter.DoubleToInt64Bits(segment.Records[0].Numeric) == long.MinValue && BitConverter.DoubleToInt64Bits(segment.Records[1].Numeric) == 0 &&
                        segment.Records[0].ValueCase == SimulationSample.ValueOneofCase.Numeric && segment.Records[1].ValueCase == SimulationSample.ValueOneofCase.Numeric, id + " signed zero and explicit zero arm");
                    Require(BitConverter.DoubleToInt64Bits(segment.Records[2].Numeric) == 1, id + " subnormal");
                    break;
                case "integral-extremes-use-exact-strings":
                    Require(segment.Records[1].Tick == ulong.MaxValue && segment.Records[0].Time.Ticks == long.MinValue && segment.Records[1].Time.Ticks == long.MaxValue, id + " extremes");
                    break;
                case "text-metadata-escapes-and-unicode":
                    Require(segment.Events[0].Fields[0].Value.Text == "a\"b\\c\n\t\u0001\u001b\u007fé中😀", id + " text scalar");
                    break;
                default:
                    break;
            }
        }
    }

    // ---- model (fixture notation) -> generated message ------------------------------------------------------------

    private static SimulationDataSegment BuildSegmentModel(JsonElement m)
    {
        Keys(m, "segment", "encodingProfile", "executionProfile", "startTick", "tickCount", "records", "events", "gaps");
        var segment = new SimulationDataSegment
        {
            EncodingProfile = m.GetProperty("encodingProfile").GetString()!,
            ExecutionProfile = m.GetProperty("executionProfile").GetString()!,
            StartTick = ModelU64(m.GetProperty("startTick")),
            TickCount = ModelU64(m.GetProperty("tickCount"))
        };
        foreach (var item in m.GetProperty("records").EnumerateArray()) segment.Records.Add(BuildSampleModel(item));
        foreach (var item in m.GetProperty("events").EnumerateArray()) segment.Events.Add(BuildEventModel(item));
        foreach (var item in m.GetProperty("gaps").EnumerateArray()) segment.Gaps.Add(BuildGapModel(item));
        return segment;
    }

    private static SimulationSample BuildSampleModel(JsonElement e)
    {
        Keys(e, "sample", "channelId", "tick", "deliveredOrdinal", "time", "value", "faultIds");
        var sample = new SimulationSample
        {
            ChannelId = ModelId(e.GetProperty("channelId")),
            Tick = ModelU64(e.GetProperty("tick")),
            DeliveredOrdinal = ModelU64(e.GetProperty("deliveredOrdinal")),
            Time = BuildTimeModel(e.GetProperty("time"))
        };
        var value = e.GetProperty("value");
        Keys(value, "sample value", "numeric", "digital", "eventId");
        Require(value.EnumerateObject().Count() == 1, "sample model value has exactly one arm");
        if (value.TryGetProperty("numeric", out var numeric)) sample.Numeric = ModelDouble(numeric);
        else if (value.TryGetProperty("digital", out var digital)) sample.Digital = digital.GetBoolean();
        else sample.EventId = ModelId(value.GetProperty("eventId"));
        foreach (var fault in e.GetProperty("faultIds").EnumerateArray()) sample.FaultIds.Add(ModelId(fault));
        return sample;
    }

    private static SimulationEvent BuildEventModel(JsonElement e)
    {
        Keys(e, "event", "eventId", "channelId", "kind", "start", "duration", "fields", "faultId");
        var evt = new SimulationEvent
        {
            EventId = ModelId(e.GetProperty("eventId")),
            ChannelId = ModelId(e.GetProperty("channelId")),
            Kind = e.GetProperty("kind").GetString()!,
            Start = BuildTimeModel(e.GetProperty("start"))
        };
        if (e.TryGetProperty("duration", out var duration)) evt.Duration = BuildTimeModel(duration);
        if (e.TryGetProperty("faultId", out var fault)) evt.FaultId = ModelId(fault);
        foreach (var field in e.GetProperty("fields").EnumerateArray())
        {
            Keys(field, "metadata entry", "name", "value");
            var entry = new Pub.MetadataEntry { Name = field.GetProperty("name").GetString()! };
            var scalar = field.GetProperty("value");
            Keys(scalar, "metadata scalar", "text", "boolean", "integer", "number", "decimal", "instant");
            Require(scalar.EnumerateObject().Count() == 1, "metadata model scalar has exactly one arm");
            var metadata = new Pub.MetadataScalar();
            if (scalar.TryGetProperty("text", out var text)) metadata.Text = text.GetString()!;
            else if (scalar.TryGetProperty("boolean", out var boolean)) metadata.Boolean = boolean.GetBoolean();
            else if (scalar.TryGetProperty("integer", out var integer)) metadata.Integer = ModelS64(integer);
            else if (scalar.TryGetProperty("number", out var number)) metadata.Number = ModelDouble(number);
            else if (scalar.TryGetProperty("decimal", out var dec)) metadata.Decimal = new FDecimal { Value = dec.GetString()! };
            else metadata.Instant = BuildInstant(scalar.GetProperty("instant"));
            entry.Value = metadata;
            evt.Fields.Add(entry);
        }
        return evt;
    }

    private static SimulationGap BuildGapModel(JsonElement e)
    {
        Keys(e, "gap", "channelId", "startTick", "tickCount", "faultId", "kind");
        var gap = new SimulationGap
        {
            StartTick = ModelU64(e.GetProperty("startTick")),
            TickCount = ModelU64(e.GetProperty("tickCount")),
            FaultId = ModelId(e.GetProperty("faultId")),
            Kind = e.GetProperty("kind").GetString()!
        };
        if (e.TryGetProperty("channelId", out var channel)) gap.ChannelId = ModelId(channel);
        return gap;
    }

    private static Pub.ScopeTime BuildTimeModel(JsonElement e)
    {
        Keys(e, "scope time", "ticks", "rate");
        var rate = e.GetProperty("rate");
        Keys(rate, "rational", "numerator", "denominator");
        return new Pub.ScopeTime
        {
            Ticks = ModelS64(e.GetProperty("ticks")),
            Rate = new Rational { Numerator = ModelS64(rate.GetProperty("numerator")), Denominator = ModelU64(rate.GetProperty("denominator")) }
        };
    }

    // ---- canonical encoder (generated message -> af-segment.v1 text) ----------------------------------------------

    private static string EncodeSegment(SimulationDataSegment s)
    {
        Need(s.HasEncodingProfile && s.HasExecutionProfile && s.HasStartTick && s.HasTickCount);
        return JObject(
            ("encodingProfile", JString(s.EncodingProfile)),
            ("events", JArray(s.Events.Select(EncodeEvent))),
            ("executionProfile", JString(s.ExecutionProfile)),
            ("gaps", JArray(s.Gaps.Select(EncodeGap))),
            ("records", JArray(s.Records.Select(EncodeSample))),
            ("startTick", JString(U64(s.StartTick))),
            ("tickCount", JString(U64(s.TickCount))));
    }

    private static string EncodeSample(SimulationSample s)
    {
        Need(s.HasTick && s.HasDeliveredOrdinal && s.Time is not null);
        var props = new List<(string, string)>
        {
            ("channelId", EncodeId(s.ChannelId)),
            ("deliveredOrdinal", JString(U64(s.DeliveredOrdinal))),
            ("faultIds", JArray(s.FaultIds.Select(EncodeId))),
            ("tick", JString(U64(s.Tick))),
            ("time", EncodeTime(s.Time!))
        };
        switch (s.ValueCase)
        {
            case SimulationSample.ValueOneofCase.Numeric: props.Add(("numeric", JString(DoubleHex(s.Numeric)))); break;
            case SimulationSample.ValueOneofCase.Digital: props.Add(("digital", s.Digital ? "true" : "false")); break;
            case SimulationSample.ValueOneofCase.EventId: props.Add(("eventId", EncodeId(s.EventId))); break;
            default: throw new Refused("oneof");
        }
        return JObject(props.ToArray());
    }

    private static string EncodeEvent(SimulationEvent e)
    {
        Need(e.HasKind && e.Start is not null);
        var props = new List<(string, string)>
        {
            ("channelId", EncodeId(e.ChannelId)),
            ("eventId", EncodeId(e.EventId)),
            ("fields", JArray(e.Fields.Select(EncodeEntry))),
            ("kind", JString(e.Kind)),
            ("start", EncodeTime(e.Start!))
        };
        if (e.Duration is not null) props.Add(("duration", EncodeTime(e.Duration)));
        if (e.FaultId is not null) props.Add(("faultId", EncodeId(e.FaultId)));
        return JObject(props.ToArray());
    }

    private static string EncodeGap(SimulationGap g)
    {
        Need(g.HasStartTick && g.HasTickCount && g.HasKind);
        var props = new List<(string, string)>
        {
            ("faultId", EncodeId(g.FaultId)),
            ("kind", JString(g.Kind)),
            ("startTick", JString(U64(g.StartTick))),
            ("tickCount", JString(U64(g.TickCount)))
        };
        if (g.ChannelId is not null) props.Add(("channelId", EncodeId(g.ChannelId)));
        return JObject(props.ToArray());
    }

    private static string EncodeEntry(Pub.MetadataEntry entry)
    {
        Need(entry.HasName && entry.Value is not null);
        return JObject(("name", JString(entry.Name)), ("value", EncodeScalar(entry.Value!)));
    }

    private static string EncodeScalar(Pub.MetadataScalar scalar)
    {
        switch (scalar.ValueCase)
        {
            case Pub.MetadataScalar.ValueOneofCase.Text: return JObject(("text", JString(scalar.Text)));
            case Pub.MetadataScalar.ValueOneofCase.Boolean: return JObject(("boolean", scalar.Boolean ? "true" : "false"));
            case Pub.MetadataScalar.ValueOneofCase.Integer: return JObject(("integer", JString(S64(scalar.Integer))));
            case Pub.MetadataScalar.ValueOneofCase.Number: return JObject(("number", JString(DoubleHex(scalar.Number))));
            case Pub.MetadataScalar.ValueOneofCase.Decimal:
                Need(scalar.Decimal.HasValue);
                return JObject(("decimal", JObject(("value", JString(scalar.Decimal.Value)))));
            case Pub.MetadataScalar.ValueOneofCase.Instant:
                Need(scalar.Instant.HasUnixSeconds && scalar.Instant.HasNanos);
                return JObject(("instant", JObject(("nanos", JString(U32(scalar.Instant.Nanos))), ("unixSeconds", JString(S64(scalar.Instant.UnixSeconds))))));
            case Pub.MetadataScalar.ValueOneofCase.Resource: throw new Refused("metadata");
            default: throw new Refused("oneof");
        }
    }

    private static string EncodeTime(Pub.ScopeTime time)
    {
        var rate = time.Rate;
        if (!time.HasTicks || rate is null || !rate.HasNumerator || !rate.HasDenominator) throw new Refused("required");
        if (rate.Numerator <= 0 || rate.Denominator < 1) throw new Refused("rate");
        return JObject(
            ("rate", JObject(("denominator", JString(U64(rate.Denominator))), ("numerator", JString(S64(rate.Numerator))))),
            ("ticks", JString(S64(time.Ticks))));
    }

    private static string EncodeId(Id? id)
    {
        if (id is null) throw new Refused("required");
        if (!id.HasValue || id.Value.Length != 16) throw new Refused("id");
        var hex = ToHex(id.Value.ToByteArray());
        return JString(hex[..8] + "-" + hex[8..12] + "-" + hex[12..16] + "-" + hex[16..20] + "-" + hex[20..]);
    }

    private static void Need(bool present)
    {
        if (!present) throw new Refused("required");
    }

    private static string JObject(params (string Name, string Json)[] members) =>
        "{" + string.Join(",", members.OrderBy(member => member.Name, StringComparer.Ordinal).Select(member => JString(member.Name) + ":" + member.Json)) + "}";

    private static string JArray(IEnumerable<string> items) => "[" + string.Join(",", items) + "]";

    private static string JString(string value)
    {
        var builder = new StringBuilder(value.Length + 2);
        builder.Append('"');
        for (var index = 0; index < value.Length; index++)
        {
            var c = value[index];
            if (char.IsHighSurrogate(c))
            {
                if (index + 1 >= value.Length || !char.IsLowSurrogate(value[index + 1])) throw new Refused("surrogate");
                builder.Append(c).Append(value[index + 1]);
                index++;
                continue;
            }
            if (char.IsLowSurrogate(c)) throw new Refused("surrogate");
            switch (c)
            {
                case '"': builder.Append("\\\""); break;
                case '\\': builder.Append("\\\\"); break;
                case '\b': builder.Append("\\b"); break;
                case '\t': builder.Append("\\t"); break;
                case '\n': builder.Append("\\n"); break;
                case '\f': builder.Append("\\f"); break;
                case '\r': builder.Append("\\r"); break;
                default:
                    if (c < 0x20) builder.Append("\\u00").Append(((int)c).ToString("x2", CultureInfo.InvariantCulture));
                    else builder.Append(c);
                    break;
            }
        }
        return builder.Append('"').ToString();
    }

    private static string U64(ulong value) => value.ToString(CultureInfo.InvariantCulture);
    private static string S64(long value) => value.ToString(CultureInfo.InvariantCulture);
    private static string U32(uint value) => value.ToString(CultureInfo.InvariantCulture);

    private static string DoubleHex(double value)
    {
        if (!double.IsFinite(value)) throw new Refused("double");
        return ((ulong)BitConverter.DoubleToInt64Bits(value)).ToString("x16", CultureInfo.InvariantCulture);
    }

    // ---- strict reader (text -> generated message), duplicate-detecting ------------------------------------------

    private sealed class Refused : Exception
    {
        internal Refused(string code) : base(code) { Code = code; }
        internal string Code { get; }
    }

    private enum JKind { Object, Array, String, Number, Bool, Null }

    private sealed class JNode
    {
        internal JKind Kind;
        internal string Text = "";
        internal List<KeyValuePair<string, JNode>> Members = [];
        internal List<JNode> Items = [];
    }

    private static UTF8Encoding StrictUtf8() => new(false, true);

    private static SimulationDataSegment ReadStrict(string text)
    {
        var root = ParseTree(text);
        var m = Members(root, ["encodingProfile", "events", "executionProfile", "gaps", "records", "startTick", "tickCount"],
            ["encodingProfile", "events", "executionProfile", "gaps", "records", "startTick", "tickCount"]);
        var encodingProfile = GetString(m["encodingProfile"]);
        var executionProfile = GetString(m["executionProfile"]);
        if (encodingProfile != "af-segment.v1" || executionProfile != "af-sim.v1") throw new Refused("profile");
        var segment = new SimulationDataSegment
        {
            EncodingProfile = encodingProfile,
            ExecutionProfile = executionProfile,
            StartTick = ReadU64(m["startTick"]),
            TickCount = ReadU64(m["tickCount"])
        };
        foreach (var node in GetArray(m["records"])) segment.Records.Add(ReadSample(node));
        foreach (var node in GetArray(m["events"])) segment.Events.Add(ReadEvent(node));
        foreach (var node in GetArray(m["gaps"])) segment.Gaps.Add(ReadGap(node));
        for (var index = 1; index < segment.Records.Count; index++)
        {
            if (segment.Records[index].DeliveredOrdinal <= segment.Records[index - 1].DeliveredOrdinal) throw new Refused("ordinal");
        }
        if (EncodeSegment(segment) != text) throw new Refused("form");
        return segment;
    }

    private static JNode ParseTree(string text)
    {
        if (text.Length > 0 && text[0] == '﻿') throw new Refused("bom");
        byte[] bytes;
        try { bytes = StrictUtf8().GetBytes(text); }
        catch (EncoderFallbackException) { throw new Refused("surrogate"); }
        try
        {
            var reader = new Utf8JsonReader(bytes, new JsonReaderOptions());
            if (!reader.Read()) throw new Refused("json");
            var node = ReadNode(ref reader);
            if (reader.Read()) throw new Refused("json");
            return node;
        }
        catch (JsonException) { throw new Refused("json"); }
        catch (InvalidOperationException) { throw new Refused("json"); }
    }

    private static JNode ReadNode(ref Utf8JsonReader reader)
    {
        switch (reader.TokenType)
        {
            case JsonTokenType.StartObject:
                {
                    var node = new JNode { Kind = JKind.Object };
                    var seen = new HashSet<string>(StringComparer.Ordinal);
                    while (true)
                    {
                        if (!reader.Read()) throw new Refused("json");
                        if (reader.TokenType == JsonTokenType.EndObject) return node;
                        if (reader.TokenType != JsonTokenType.PropertyName) throw new Refused("json");
                        var name = reader.GetString() ?? throw new Refused("json");
                        CheckScalars(name);
                        if (!seen.Add(name)) throw new Refused("duplicate");
                        if (!reader.Read()) throw new Refused("json");
                        node.Members.Add(new KeyValuePair<string, JNode>(name, ReadNode(ref reader)));
                    }
                }
            case JsonTokenType.StartArray:
                {
                    var node = new JNode { Kind = JKind.Array };
                    while (true)
                    {
                        if (!reader.Read()) throw new Refused("json");
                        if (reader.TokenType == JsonTokenType.EndArray) return node;
                        node.Items.Add(ReadNode(ref reader));
                    }
                }
            case JsonTokenType.String:
                {
                    var text = reader.GetString() ?? throw new Refused("json");
                    CheckScalars(text);
                    return new JNode { Kind = JKind.String, Text = text };
                }
            case JsonTokenType.Number: return new JNode { Kind = JKind.Number };
            case JsonTokenType.True: return new JNode { Kind = JKind.Bool, Text = "true" };
            case JsonTokenType.False: return new JNode { Kind = JKind.Bool, Text = "false" };
            case JsonTokenType.Null: return new JNode { Kind = JKind.Null };
            default: throw new Refused("json");
        }
    }

    private static void CheckScalars(string text)
    {
        for (var index = 0; index < text.Length; index++)
        {
            if (char.IsHighSurrogate(text[index]))
            {
                if (index + 1 >= text.Length || !char.IsLowSurrogate(text[index + 1])) throw new Refused("surrogate");
                index++;
            }
            else if (char.IsLowSurrogate(text[index])) throw new Refused("surrogate");
        }
    }

    private static string GetString(JNode node) => node.Kind == JKind.String ? node.Text : throw new Refused("type");
    private static bool GetBool(JNode node) => node.Kind == JKind.Bool ? node.Text == "true" : throw new Refused("type");
    private static List<JNode> GetArray(JNode node) => node.Kind == JKind.Array ? node.Items : throw new Refused("type");

    // The closed set is checked first, then required members, then the oneof arm count, then member order (last, so a text that
    // is wrong in several ways is classified by its semantic defect before its layout).
    private static Dictionary<string, JNode> Members(JNode node, string[] allowed, string[] required, string[]? oneof = null)
    {
        if (node.Kind != JKind.Object) throw new Refused("type");
        foreach (var member in node.Members)
        {
            if (!allowed.Contains(member.Key, StringComparer.Ordinal)) throw new Refused("member");
        }
        var result = node.Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
        foreach (var name in required)
        {
            if (!result.ContainsKey(name)) throw new Refused("member");
        }
        if (oneof is not null && oneof.Count(result.ContainsKey) != 1) throw new Refused("oneof");
        for (var index = 1; index < node.Members.Count; index++)
        {
            if (string.CompareOrdinal(node.Members[index - 1].Key, node.Members[index].Key) >= 0) throw new Refused("order");
        }
        return result;
    }

    private static SimulationSample ReadSample(JNode node)
    {
        var m = Members(node, ["channelId", "deliveredOrdinal", "digital", "eventId", "faultIds", "numeric", "tick", "time"],
            ["channelId", "deliveredOrdinal", "faultIds", "tick", "time"], ["digital", "eventId", "numeric"]);
        var sample = new SimulationSample
        {
            ChannelId = ReadId(m["channelId"]),
            Tick = ReadU64(m["tick"]),
            DeliveredOrdinal = ReadU64(m["deliveredOrdinal"]),
            Time = ReadTime(m["time"])
        };
        if (m.TryGetValue("numeric", out var numeric)) sample.Numeric = ReadDouble(numeric);
        else if (m.TryGetValue("digital", out var digital)) sample.Digital = GetBool(digital);
        else sample.EventId = ReadId(m["eventId"]);
        foreach (var fault in GetArray(m["faultIds"])) sample.FaultIds.Add(ReadId(fault));
        return sample;
    }

    private static SimulationEvent ReadEvent(JNode node)
    {
        var m = Members(node, ["channelId", "duration", "eventId", "faultId", "fields", "kind", "start"],
            ["channelId", "eventId", "fields", "kind", "start"]);
        var evt = new SimulationEvent
        {
            ChannelId = ReadId(m["channelId"]),
            EventId = ReadId(m["eventId"]),
            Kind = GetString(m["kind"]),
            Start = ReadTime(m["start"])
        };
        if (m.TryGetValue("duration", out var duration)) evt.Duration = ReadTime(duration);
        if (m.TryGetValue("faultId", out var fault)) evt.FaultId = ReadId(fault);
        foreach (var field in GetArray(m["fields"]))
        {
            var entry = Members(field, ["name", "value"], ["name", "value"]);
            evt.Fields.Add(new Pub.MetadataEntry { Name = GetString(entry["name"]), Value = ReadScalar(entry["value"]) });
        }
        return evt;
    }

    private static Pub.MetadataScalar ReadScalar(JNode node)
    {
        if (node.Kind == JKind.Object && node.Members.Any(member => member.Key == "resource")) throw new Refused("metadata");
        var m = Members(node, ["boolean", "decimal", "instant", "integer", "number", "text"], [], ["boolean", "decimal", "instant", "integer", "number", "text"]);
        var scalar = new Pub.MetadataScalar();
        if (m.TryGetValue("text", out var text)) scalar.Text = GetString(text);
        else if (m.TryGetValue("boolean", out var boolean)) scalar.Boolean = GetBool(boolean);
        else if (m.TryGetValue("integer", out var integer)) scalar.Integer = ReadS64(integer);
        else if (m.TryGetValue("number", out var number)) scalar.Number = ReadDouble(number);
        else if (m.TryGetValue("decimal", out var dec))
        {
            var d = Members(dec, ["value"], ["value"]);
            scalar.Decimal = new FDecimal { Value = GetString(d["value"]) };
        }
        else
        {
            var i = Members(m["instant"], ["nanos", "unixSeconds"], ["nanos", "unixSeconds"]);
            scalar.Instant = new Instant { UnixSeconds = ReadS64(i["unixSeconds"]), Nanos = ReadU32(i["nanos"]) };
        }
        return scalar;
    }

    private static SimulationGap ReadGap(JNode node)
    {
        var m = Members(node, ["channelId", "faultId", "kind", "startTick", "tickCount"], ["faultId", "kind", "startTick", "tickCount"]);
        var kind = GetString(m["kind"]);
        if (kind is not ("drop" or "disconnect" or "malformed")) throw new Refused("gapKind");
        var gap = new SimulationGap
        {
            FaultId = ReadId(m["faultId"]),
            Kind = kind,
            StartTick = ReadU64(m["startTick"]),
            TickCount = ReadU64(m["tickCount"])
        };
        if (m.TryGetValue("channelId", out var channel)) gap.ChannelId = ReadId(channel);
        return gap;
    }

    private static Pub.ScopeTime ReadTime(JNode node)
    {
        var m = Members(node, ["rate", "ticks"], ["rate", "ticks"]);
        var rate = Members(m["rate"], ["denominator", "numerator"], ["denominator", "numerator"]);
        var denominator = ReadU64(rate["denominator"]);
        var numerator = ReadS64(rate["numerator"]);
        if (denominator < 1 || numerator <= 0) throw new Refused("rate");
        return new Pub.ScopeTime { Ticks = ReadS64(m["ticks"]), Rate = new Rational { Numerator = numerator, Denominator = denominator } };
    }

    private static Id ReadId(JNode node)
    {
        var text = GetString(node);
        if (text.Length != 36) throw new Refused("id");
        var hex = new StringBuilder(32);
        for (var index = 0; index < 36; index++)
        {
            var c = text[index];
            if (index is 8 or 13 or 18 or 23)
            {
                if (c != '-') throw new Refused("id");
            }
            else if ((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) hex.Append(c);
            else throw new Refused("id");
        }
        var bytes = HexToBytes(hex.ToString());
        if (bytes.All(b => b == 0)) throw new Refused("id");
        return new Id { Value = ByteString.CopyFrom(bytes) };
    }

    private static ulong ReadU64(JNode node)
    {
        var text = GetString(node);
        if (!TryU64(text, out var value)) throw new Refused("int");
        return value;
    }

    private static uint ReadU32(JNode node)
    {
        var text = GetString(node);
        if (!TryU32(text, out var value)) throw new Refused("int");
        return value;
    }

    private static long ReadS64(JNode node)
    {
        var text = GetString(node);
        if (!TryS64(text, out var value)) throw new Refused("int");
        return value;
    }

    private static double ReadDouble(JNode node)
    {
        var text = GetString(node);
        if (text.Length != 16) throw new Refused("double");
        foreach (var c in text)
        {
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) throw new Refused("double");
        }
        var bits = ulong.Parse(text, NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture);
        var value = BitConverter.Int64BitsToDouble((long)bits);
        if (!double.IsFinite(value)) throw new Refused("double");
        return value;
    }

    // ------------------------------------------------------------------------------------------------------------
    // Shared exact-string helpers
    // ------------------------------------------------------------------------------------------------------------

    private static bool AllDigits(string text, int start)
    {
        if (start >= text.Length) return false;
        for (var index = start; index < text.Length; index++)
        {
            if (text[index] < '0' || text[index] > '9') return false;
        }
        return !(text[start] == '0' && text.Length - start > 1);
    }

    private static bool TryU64(string text, out ulong value)
    {
        value = 0;
        return AllDigits(text, 0) && ulong.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out value);
    }

    private static bool TryU32(string text, out uint value)
    {
        value = 0;
        return AllDigits(text, 0) && uint.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out value);
    }

    private static bool TryS64(string text, out long value)
    {
        value = 0;
        if (text == "-0") return false;
        var start = text.StartsWith('-') ? 1 : 0;
        return AllDigits(text, start) && long.TryParse(text, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out value);
    }

    private static string NumberText(JsonElement element) => element.ValueKind switch
    {
        JsonValueKind.String => element.GetString()!,
        JsonValueKind.Number => element.GetRawText(),
        _ => throw new InvalidOperationException("CON.25 fixture failed: expected a string or number")
    };

    private static int ParseInt(JsonElement element)
    {
        var text = NumberText(element);
        Require(AllDigits(text, 0) && int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out _), "exact integer " + text);
        return int.Parse(text, NumberStyles.None, CultureInfo.InvariantCulture);
    }

    private static ulong ModelU64(JsonElement element)
    {
        Require(TryU64(NumberText(element), out var value), "exact uint64 " + NumberText(element));
        return value;
    }

    private static uint ModelU32(JsonElement element)
    {
        Require(TryU32(NumberText(element), out var value), "exact uint32 " + NumberText(element));
        return value;
    }

    private static long ModelS64(JsonElement element)
    {
        Require(TryS64(NumberText(element), out var value), "exact sint64 " + NumberText(element));
        return value;
    }

    // Model doubles are decimal text; the exact bit word is asserted against the fixture canonical text by the encoder.
    private static double ModelDouble(JsonElement element) =>
        double.Parse(element.GetString()!, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint | NumberStyles.AllowExponent, CultureInfo.InvariantCulture);

    private static Id ModelId(JsonElement element) => ReadId(new JNode { Kind = JKind.String, Text = element.GetString()! });

    private static Id IdFromHex(string hex)
    {
        Require(hex.Length == 32, "Id hex has 32 digits: " + hex);
        return new Id { Value = ByteString.CopyFrom(HexToBytes(hex)) };
    }

    private static byte[] HexToBytes(string hex)
    {
        Require(hex.Length % 2 == 0 && hex.All(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')), "lower-case hex text");
        return Convert.FromHexString(hex);
    }

    private static string ToHex(byte[] bytes) => Convert.ToHexStringLower(bytes);

    private static void Keys(JsonElement element, string label, params string[] allowed)
    {
        Require(element.ValueKind == JsonValueKind.Object, label + " is an object");
        foreach (var property in element.EnumerateObject())
            Require(allowed.Contains(property.Name, StringComparer.Ordinal), label + " has unknown member " + property.Name);
    }

    private static void ExactIds(string label, IEnumerable<string> actual, string[] expected)
    {
        var ids = actual.ToArray();
        Require(ids.Length == expected.Length && ids.Distinct(StringComparer.Ordinal).Count() == ids.Length &&
            ids.Order(StringComparer.Ordinal).SequenceEqual(expected.Order(StringComparer.Ordinal), StringComparer.Ordinal), label + " exact unique fixture vector ids");
    }

    private static void Require(bool valid, string reason)
    {
        if (!valid) throw new InvalidOperationException("CON.25 fixture failed: " + reason);
    }
}
