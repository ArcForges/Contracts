// SPDX-License-Identifier: Apache-2.0
// CON.40 C# parity suite: the C# replacements for the TypeScript (tests/public/*.mjs, *.ts) and Kotlin
// (tests/public/KotlinConnectClient) consumer cases that had no same-named C# case, or whose C# case lacked
// an assertion or a negative fixture. eng/policy/con-40-test-map.json maps every retired case to the C#
// case that keeps its negative fixture. Everything here is offline and reads only committed fixtures.
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using ArcForges.Contracts.Foundation.Serialization;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using Grpc.Core;
using Browser = ArcForges.Contracts.PublicApi.Http.V1.Browser;
using E = ArcForges.Contracts.Events.V1;
using F = ArcForges.Contracts.Foundation.V1;
using Hello = ArcForges.Contracts.Hello.V1;
using Native = ArcForges.Contracts.PublicApi.Http.V1.NativeAuth;
using Op = ArcForges.Contracts.CloudInternal.Operator.V1;
using P = ArcForges.Contracts.PublicApi.V1;
using Shapes = ArcForges.Contracts.Validation.ContractShapeValidation;
using Sim = ArcForges.Contracts.Simulation.V1;
using V = ArcForges.Contracts.Foundation.Values;
using Val = ArcForges.Contracts.Validation;

internal static class Con40SdkCases
{
    public static void Run(string root)
    {
        // CON.03 had a complete C# port that the default StructureTests run never executed; the
        // retired con-03-sync-allowlist.test.mjs cases are carried by running it here.
        Con03Cases.Run(root);
        Wire(root);
        Serialization(root);
        Con10(root);
        FoundationIndependentEncoding(root);
        FoundationCoverage(root);
        FoundationRetirement(root);
        FoundationValues();
        ValueDomains();
        CatalogExport(root);
        Con02Admission();
        Con07(root);
        Con07Jvm();
        Con11(root);
        Con24(root);
        Con25Connector(root);
        Con25ConnectorClient();
        GeneratedClients(root);
        AfSegment(root);
        SemanticHash();
        Support(root);
        OperatorVisibility();
        SimulationCatalogue(root);
        TestMap(root);
        Console.WriteLine("CON.40 C# parity: wire, serialization, CON.10, independent foundation encoding and coverage, values, "
            + "catalog, CON.02, CON.07, CON.11, CON.24, CON.25, af-segment oracle, semantic hash, support and operator cases passed.");
    }

    // ---------------------------------------------------------------------------------------------- wire.test.mjs

    private static void Wire(string root)
    {
        using var fixture = Load(root, "fixtures/public/hello.json");
        var service = Hello.HelloReflection.Descriptor.Services.Single();
        Require(service == Hello.HelloService.Descriptor && service.FullName == "arcforges.hello.v1.HelloService"
            && service.Methods.Select(method => method.Name).SequenceEqual(["SayHello"]), "wire: the generated service preserves the public wire identity");
        var cases = 0;
        foreach (var item in fixture.RootElement.GetProperty("cases").EnumerateArray())
        {
            var name = item.GetProperty("name").GetString()!;
            var message = new Hello.SayHelloRequest { Name = name };
            Require(Hello.SayHelloRequest.Parser.ParseFrom(message.ToByteArray()).Name == name, "wire: protobuf round trip of " + name);
            cases++;
        }
        Require(cases > 1, "wire: shared ASCII and Unicode fixtures are present");
        Require(new Hello.SayHelloRequest { Name = "A" }.ToByteArray().SequenceEqual(new byte[] { 0x0a, 0x01, 0x41 }), "wire: field number 1 bytes");
        Throws<InvalidProtocolBufferException>(() => Hello.SayHelloRequest.Parser.ParseFrom(new byte[] { 0x0a, 0x05, 0x41 }), "wire: truncated payload refuses");
    }

    // ------------------------------------------------------------------------------------- serialization.test.mjs

    private static void Serialization(string root)
    {
        using var document = Load(root, "fixtures/public/wp03-02.json");
        var fixture = document.RootElement;
        var limits = fixture.GetProperty("limits");
        Require(WireLimits.UnaryMessageBytes == limits.GetProperty("unaryMessage").GetInt32()
            && WireLimits.HelperMessageBytes == limits.GetProperty("helperMessage").GetInt32()
            && WireLimits.InlinePageBytes == limits.GetProperty("inlinePage").GetInt32()
            && WireLimits.StreamFrameBytes == limits.GetProperty("streamFrame").GetInt32()
            && WireLimits.LargeProjectionBytes == limits.GetProperty("largeProjection").GetInt32()
            && WireLimits.NestedMessageLevels == limits.GetProperty("nestedMessageLevels").GetInt32(), "serialization: fixed limits match the independent vectors");

        // Text input: the C# codecs take UTF-8 bytes, so the same byte bound and text checks apply to the encoded string.
        var text = fixture.GetProperty("json").EnumerateArray().Single(item => item.GetProperty("id").GetString() == "part-canonical").GetProperty("text").GetString()!;
        Require(Val.PartReceiptJson.Parse(Encoding.UTF8.GetBytes(text)).PartNumber == 1, "serialization: canonical text parses");
        var padded = text + new string(' ', 65536 - text.Length + 1);
        Require(!Val.PartReceiptJson.TryParse(Encoding.UTF8.GetBytes(padded), out _, out var tooLarge) && tooLarge == ContractSerializationFailure.TooLarge,
            "serialization: one byte over the 64 KiB document bound is tooLarge");
        var at = text.IndexOf("\"e1", StringComparison.Ordinal);
        Require(at > 0, "serialization: lone-surrogate splice point");
        // A lone UTF-16 surrogate has no UTF-8 form; its generalized (WTF-8) bytes ED A0 80 are malformed input.
        var lone = Encoding.UTF8.GetBytes(text[..(at + 1)]).Concat(new byte[] { 0xED, 0xA0, 0x80 }).Concat(Encoding.UTF8.GetBytes(text[(at + 2)..])).ToArray();
        Require(!Val.PartReceiptJson.TryParse(lone, out _, out var malformed) && malformed == ContractSerializationFailure.Malformed, "serialization: lone surrogate is malformed");
        RefusesWith(() => Val.PartReceiptJson.Parse("{}"u8.ToArray()), ContractSerializationFailure.Invalid, "serialization: empty object is invalid");
        // The typed model cannot hold 1.5 for partNumber; the schema-refused typed values are the C# equivalent.
        RefusesWith(() => Val.PartReceiptJson.Serialize(new ArcForges.Contracts.PublicApi.Http.V1.PartReceipt { PartNumber = -1, Size = "1", Sha256 = new string('a', 64), Etag = "x" }),
            ContractSerializationFailure.Invalid, "serialization: serializer refuses a value the closed schema rejects (partNumber)");
        RefusesWith(() => Val.PartReceiptJson.Serialize(new ArcForges.Contracts.PublicApi.Http.V1.PartReceipt { PartNumber = 1, Size = "01", Sha256 = new string('a', 64), Etag = "x" }),
            ContractSerializationFailure.Invalid, "serialization: serializer refuses a value the closed schema rejects (size)");

        // Generated service catalogue: the C# public packages own exactly the authored services and methods.
        var con08 = new Dictionary<string, string[]>(StringComparer.Ordinal)
        {
            ["arcforges.publicapi.v1.EntitlementService"] = ["GetSnapshot", "GetServiceTerm", "GetCapacity", "ListGrants", "GetUsage", "Check"],
            ["arcforges.publicapi.v1.CommerceService"] = ["AuthoriseExtraUsage", "RevokeExtraUsage", "ExplainCharge", "GetCatalogue", "CreatePurchaseIntent",
                "CreateCheckoutAttempt", "GetPurchaseState", "GetSubscription", "CancelSubscription", "ReactivateSubscription", "GetCredits", "ListBillingHistory",
                "RequestRefund", "ExportEvidence"],
            ["arcforges.publicapi.v1.TaskService"] = ["List", "Get", "Create", "Cancel", "Pause", "Resume", "RetryAttempt", "Steer", "GetDetails"],
            ["arcforges.publicapi.v1.ApprovalService"] = ["List", "Decide"],
            ["arcforges.publicapi.v1.BridgeService"] = ["PullRequests", "SubmitResult", "GetRequestState"],
            ["arcforges.publicapi.v1.ChatService"] = ["ListConversations", "GetConversation", "AppendMessage", "CreateBranch", "RequestExport", "CreateConversation",
                "PutProject", "DeleteProject", "PutMemory", "DeleteMemory", "GetTurn", "CancelTurn", "PreviewPromotion", "PromoteTurn", "CloseTemporary",
                "SaveTemporary", "UpdateConversation", "ListProjects", "GetProject", "ListMemories", "GetMemory"],
            ["arcforges.publicapi.v1.AgentService"] = ["ListModels", "ListProfiles", "GetUsage", "PutProfile", "DeleteProfile", "PutSkill", "DeleteSkill"],
            ["arcforges.publicapi.v1.SearchService"] = ["Query"],
            ["arcforges.publicapi.v1.AutomationService"] = ["List", "Get", "Create", "Update", "SetEnabled", "Delete", "RunNow", "SubmitEvent", "ResolveMissed"],
            ["arcforges.publicapi.v1.SourceService"] = ["CreateConsent", "RevokeConsent", "GetPolicy", "SetPolicy", "ClearPolicy"],
            ["arcforges.publicapi.v1.SyncService"] = ["ListScopes", "SetScope", "PullChanges", "PushChange", "PushBatch", "GetAggregate", "ListConflicts",
                "ResolveConflict", "RequestFullResync", "GetBootstrapPage"],
            ["arcforges.publicapi.v1.ResourceService"] = ["BeginUpload", "CompleteUpload", "GetDownloadTicket", "GetMetadata", "Release", "GetUploadStatus", "RenewUploadTicket"],
            ["arcforges.publicapi.v1.TransferService"] = ["RequestExport", "PreviewImport", "CommitImport", "Get", "List", "Cancel"],
            ["arcforges.publicapi.v1.SupportService"] = ["CreateCase", "ListCases", "AppendMessage", "DecideAccess"],
            ["arcforges.publicapi.v1.NotificationService"] = ["List", "Acknowledge", "RegisterPush", "UnregisterPush"],
            ["arcforges.publicapi.v1.PreferenceService"] = ["Put"],
            ["arcforges.publicapi.v1.PolicyService"] = ["GetBundle"],
            ["arcforges.publicapi.v1.DataService"] = ["RequestExport", "GetExportState"],
            ["arcforges.publicapi.v1.ExportService"] = ["GetStatus", "Cancel", "GetDownload"],
            ["arcforges.simulation.v1.SimulationService"] = ["ListDefinitions", "GetDefinition", "CreateDefinition", "PublishScenarioVersion", "StartRun", "PauseRun",
                "ResumeRun", "CancelRun", "GetRun", "ListRuns", "ListSegments", "GetSegmentTicket", "PollState"],
            ["arcforges.publicapi.v1.ScopeService"] = ["ListProjects", "ListSessions", "GetSession"],
            ["arcforges.publicapi.v1.ConnectorService"] = ["ListDefinitions", "ListConnections", "BeginConnection", "CompleteConnection", "GetConnection", "RevokeConnection"],
        };
        var fixtureMethods = fixture.GetProperty("services").GetProperty("methods");
        foreach (var (service, count) in new[] { ("arcforges.events.v1.ExecutionService", 5), ("arcforges.events.v1.EventService", 2),
            ("arcforges.publicapi.v1.ApplicationService", 3), ("arcforges.publicapi.v1.HistoryService", 4) })
            Require(fixtureMethods.TryGetProperty(service, out var methods) && methods.GetArrayLength() == count, "serialization: CON.11 method count " + service);
        string[] expectedServices = ["arcforges.hello.v1.HelloService", "arcforges.events.v1.ExecutionService", "arcforges.events.v1.EventService",
            "arcforges.catalog.v1.CatalogService", .. con08.Keys, "arcforges.publicapi.v1.ApplicationService", "arcforges.publicapi.v1.HistoryService",
            "arcforges.publicapi.v1.IdentityService", "arcforges.publicapi.v1.WorkspaceService", "arcforges.publicapi.v1.DeviceService"];
        var actual = ArcForges.Contracts.PublicApi.ContractServices.All.Concat(ArcForges.Contracts.Events.ContractServices.All).ToArray();
        Require(actual.Select(service => service.FullName).Order(StringComparer.Ordinal).SequenceEqual(expectedServices.Order(StringComparer.Ordinal), StringComparer.Ordinal),
            "serialization: generated public catalogues list exactly the authored services");
        foreach (var service in actual)
        {
            var expected = con08.TryGetValue(service.FullName, out var named)
                ? named.Select(method => "/" + service.FullName + "/" + method)
                : fixtureMethods.GetProperty(service.FullName).EnumerateArray().Select(value => value.GetString()!);
            Require(service.Methods.Select(method => "/" + service.FullName + "/" + method.Name).SequenceEqual(expected, StringComparer.Ordinal),
                "serialization: exact authored methods of " + service.FullName);
        }
    }

    // ---------------------------------------------------------------------------- con-10-chat-task-agent.test.mjs

    private static void Con10(string root)
    {
        using var publicDocument = Load(root, "fixtures/public/con-10-chat-task-agent.json");
        using var internalDocument = Load(root, "fixtures/internal/con-10-ai-internal.json");
        using var exportDocument = Load(root, "eng/operations/con-10.json");
        var publicFixture = publicDocument.RootElement;
        foreach (var vector in publicFixture.GetProperty("contractShapeVectors").EnumerateArray())
        {
            var id = vector.GetProperty("id").GetString()!;
            var input = vector.GetProperty("input");
            bool actual;
            try
            {
                actual = vector.GetProperty("shape").GetString() switch
                {
                    // uint64 keeps the decimal-string JSON spelling; a JSON number is refused before parsing,
                    // because protobuf JSON parsing would otherwise erase the forbidden spelling.
                    "ApplicationTarget" => !(input.TryGetProperty("instanceEpoch", out var epoch) && epoch.ValueKind == JsonValueKind.Number)
                        && Shapes.IsValid(JsonParser.Default.Parse<P.ApplicationTarget>(input.GetRawText())),
                    "ChatTurnView" => Shapes.IsValid(JsonParser.Default.Parse<P.ChatTurnView>(input.GetRawText())),
                    var shape => throw new InvalidOperationException("CON.10 unknown shape " + shape),
                };
            }
            catch (Exception exception) when (exception is InvalidProtocolBufferException or InvalidJsonException or FormatException) { actual = false; }
            Require(actual == vector.GetProperty("valid").GetBoolean(), "CON.10 shape vector " + id);
        }

        var journeys = publicFixture.GetProperty("journeyVectors").EnumerateArray().ToDictionary(vector => vector.GetProperty("id").GetString()!, StringComparer.Ordinal);
        Require(journeys.Count == publicFixture.GetProperty("journeyVectors").GetArrayLength(), "CON.10 journey vector IDs are unique");
        Require(journeys.Keys.Order(StringComparer.Ordinal).SequenceEqual(new[] { "agent-mode", "agent-retry-reconciles-uncertainty", "cancel-pause-turn-reconciles-uncertainty",
            "explicit-promotion-creates-agent-task", "ordinary-generated-reply", "ordinary-write-proposal-awaits-promotion", "plain-append-no-generation",
            "save-temporary-content", "temporary-reply" }.Order(StringComparer.Ordinal), StringComparer.Ordinal), "CON.10 exact journey inventory");
        (string Journey, string Property, string Json)[] expectations =
        [
            ("plain-append-no-generation", "taskCreated", "false"), ("plain-append-no-generation", "userMessageCommitCount", "1"),
            ("ordinary-generated-reply", "taskCreated", "false"), ("ordinary-generated-reply", "runWorkflowCount", "1"),
            ("ordinary-generated-reply", "resourcePinsRequired", "true"), ("ordinary-generated-reply", "sharedEntitlementCommerceAdmission", "true"),
            ("ordinary-generated-reply", "reconcilePorts", "[\"chat.getTurn\",\"canonical-conversation\"]"),
            ("ordinary-generated-reply", "readOnlyToolsAllowed", "true"), ("ordinary-generated-reply", "writeToolsAllowed", "false"),
            ("ordinary-generated-reply", "outputCommitCount", "1"),
            ("agent-mode", "taskReadPorts", "[\"task.get\",\"task.getDetails\"]"), ("agent-mode", "ordinaryTaskPoliciesApply", "true"),
            ("agent-mode", "approvalRequiredForEffects", "true"),
            ("ordinary-write-proposal-awaits-promotion", "promotionPreviewStored", "true"),
            ("ordinary-write-proposal-awaits-promotion", "waitingReason", "\"promotion.required\""),
            ("ordinary-write-proposal-awaits-promotion", "writeToolDispatchAllowed", "false"),
            ("explicit-promotion-creates-agent-task", "writeToolDispatchAllowed", "false"),
            ("explicit-promotion-creates-agent-task", "matchingPreviewAndRevisionRequired", "true"),
            ("explicit-promotion-creates-agent-task", "linkedToSourceTurn", "true"),
            ("explicit-promotion-creates-agent-task", "ordinaryApprovalAndAuthorizationRequiredForEffects", "true"),
            ("temporary-reply", "historyListed", "false"), ("temporary-reply", "ordinaryListProjectionVisible", "false"),
            ("temporary-reply", "searchable", "false"), ("temporary-reply", "knowledgeProjectionVisible", "false"),
            ("temporary-reply", "absoluteBodyRetentionHours", "24"), ("temporary-reply", "explicitCloseCancelsWork", "true"),
            ("temporary-reply", "closePurgesTextWithinHours", "1"), ("temporary-reply", "temporaryDraftsVolatile", "true"),
            ("temporary-reply", "compactionSummaryVolatile", "true"), ("temporary-reply", "crashCanInterrupt", "true"),
            ("temporary-reply", "metadataOnlyFinancialSecurityReceiptSurvives", "true"),
            ("save-temporary-content", "selectedMessagesCurrentlyAuthorized", "true"), ("save-temporary-content", "newConversationId", "true"),
            ("save-temporary-content", "durableOriginRecorded", "true"), ("save-temporary-content", "copiesExecutionIdentity", "false"),
            ("save-temporary-content", "copiesChargeIdentity", "false"), ("save-temporary-content", "rerunsExecution", "false"),
            ("save-temporary-content", "missingOrExpiredContentRefuses", "true"),
            ("cancel-pause-turn-reconciles-uncertainty", "knownCompletedUsageSettlesNormally", "true"),
            ("cancel-pause-turn-reconciles-uncertainty", "controlReceiptSeparateFromEffectOutcome", "true"),
            ("cancel-pause-turn-reconciles-uncertainty", "unknownEffectTreatedAsZero", "false"),
            ("cancel-pause-turn-reconciles-uncertainty", "reconcileBeforeResume", "true"),
            ("cancel-pause-turn-reconciles-uncertainty", "duplicateDispatch", "false"),
            ("agent-retry-reconciles-uncertainty", "controlReceiptSeparateFromEffectOutcome", "true"),
            ("agent-retry-reconciles-uncertainty", "unknownEffectTreatedAsZero", "false"),
            ("agent-retry-reconciles-uncertainty", "reconcileBeforeRetry", "true"),
            ("agent-retry-reconciles-uncertainty", "duplicateDispatch", "false"),
        ];
        foreach (var (journey, property, json) in expectations)
            Require(Same(journeys[journey].GetProperty(property), json), "CON.10 journey " + journey + "." + property);
        Require(journeys["ordinary-generated-reply"].GetProperty("owner").TryGetProperty("turnId", out _), "CON.10 ordinary reply is turn-owned");
        Require(journeys["agent-mode"].GetProperty("owner").TryGetProperty("taskId", out _), "CON.10 agent mode is task-owned");
        var negatives = publicFixture.GetProperty("negativeVectors").EnumerateArray().ToArray();
        var negativeIds = negatives.Select(vector => vector.GetProperty("id").GetString()!).ToArray();
        Require(negativeIds.Distinct(StringComparer.Ordinal).Count() == negativeIds.Length, "CON.10 negative vector IDs are unique");
        Require(negativeIds.Order(StringComparer.Ordinal).SequenceEqual(new[] { "agent-mode-forges-turn-owner", "ordinary-turn-forges-task-owner",
            "ordinary-write-dispatched-before-promotion", "retry-unknown-dispatch-without-reconciliation", "save-copies-prior-execution-or-charge",
            "save-expired-temporary-content-refuses", "temporary-body-in-history-or-search" }.Order(StringComparer.Ordinal), StringComparer.Ordinal), "CON.10 exact negative inventory");
        var expired = negatives.Single(vector => vector.GetProperty("id").GetString() == "save-expired-temporary-content-refuses");
        var expiredInput = expired.GetProperty("input");
        Require(!expired.GetProperty("valid").GetBoolean() && expiredInput.GetProperty("temporaryContentExpired").GetBoolean()
            && expiredInput.GetProperty("saveAccepted").GetBoolean() && expiredInput.GetProperty("fabricatedReplacementCreated").GetBoolean(), "CON.10 expired save refusal vector");
        Require(journeys.Values.All(vector => vector.GetProperty("valid").GetBoolean()) && negatives.All(vector => !vector.GetProperty("valid").GetBoolean()),
            "CON.10 journeys are positive and negatives are negative");

        // Exactly the modelled Chat, Task and Agent proto method bindings, all unary, equal the operation export.
        var rows = exportDocument.RootElement.GetProperty("operations").EnumerateArray().ToArray();
        string[] chatServices = ["TaskService", "ApprovalService", "BridgeService", "ChatService", "AgentService", "SearchService", "AutomationService", "SourceService"];
        var services = chatServices.Select(name => P.ChatReflection.Descriptor.Services.Single(service => service.Name == name)).ToArray();
        var bindings = services.SelectMany(service => service.Methods.Select(method => "arcforges.publicapi.v1." + service.Name + "/" + method.Name)).ToArray();
        var registered = rows.Where(row => row.GetProperty("kind").GetString() == "proto" && row.GetProperty("source").GetString() == "public/proto/arcforges/publicapi/v1/chat.proto")
            .Select(row => row.GetProperty("binding").GetString()!).ToArray();
        Require(bindings.Length == 57 && registered.Order(StringComparer.Ordinal).SequenceEqual(bindings.Order(StringComparer.Ordinal), StringComparer.Ordinal), "CON.10 exact 57 chat.proto bindings");
        Require(services.SelectMany(service => service.Methods).All(method => !method.IsClientStreaming && !method.IsServerStreaming), "CON.10 chat.proto methods are unary");

        var approval = rows.Single(row => row.GetProperty("operationId").GetString() == "approval.decide");
        Require(Same(approval, """
            {"operationId":"approval.decide","binding":"arcforges.publicapi.v1.ApprovalService/Decide","kind":"proto","source":"public/proto/arcforges/publicapi/v1/chat.proto",
             "scope":"assistant","surface":"public","profile":"public-human-approval-decision","sourceRule":"docs/architecture/contracts/01-public-api-operations.md#rule-tk-02",
             "idempotency":"IW","authorization":{"capability":null,"risk":{"from":"verifiedApprovalProposal.effectiveRisk"},"approval":"foregroundProposal",
             "stepUp":{"from":"verifiedApprovalProposal.stepUp"},"localPresence":{"from":"verifiedApprovalProposal.localPresence"},"egress":"none","patEligible":false,"actorKinds":["human"]}}
            """), "CON.10 exact public approval profile");
        var retry = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["authorize"] = "Q", ["claim"] = "IW", ["renew"] = "IW", ["reconcile"] = "Q", ["context"] = "Q", ["model-intent"] = "IW", ["model-outcome"] = "IW",
            ["settle"] = "IW", ["prepare-tools"] = "IW", ["cloud-tool"] = "IW", ["wait"] = "IW", ["finalize"] = "IW", ["stream-state"] = "IW", ["late-outcome"] = "IW",
        };
        var aiRows = rows.Where(row => row.GetProperty("operationId").GetString()!.StartsWith("cf.ai.", StringComparison.Ordinal)).ToArray();
        var ports = internalDocument.RootElement.GetProperty("ports").EnumerateArray().ToArray();
        Require(aiRows.Length == 14 && ports.Length == 14, "CON.10 exactly 14 CF transport rows and ports");
        foreach (var port in ports)
        {
            var path = port.GetProperty("path").GetString()!;
            var route = path.Split('/')[^1];
            var row = aiRows.SingleOrDefault(candidate => candidate.GetProperty("operationId").GetString() == "cf.ai." + route);
            Require(row.ValueKind == JsonValueKind.Object, "CON.10 operation row for " + path);
            Require(row.GetProperty("binding").GetString() == path && row.GetProperty("kind").GetString() == "http"
                && row.GetProperty("source").GetString() == "internal/ai-http/v1/schema.json"
                && row.GetProperty("scope").GetString() == (route == "authorize" ? "resource-owner" : "assistant")
                && row.GetProperty("surface").GetString() == "cf-internal" && row.GetProperty("profile").GetString() == "cf-service"
                && row.GetProperty("sourceRule").GetString() == "docs/architecture/contracts/05-cloudflare-integration.md#3-exact-internal-ports"
                && row.GetProperty("idempotency").GetString() == retry[route], "CON.10 closed CF row " + path);
            Require(Same(row.GetProperty("authorization"), """{"capability":null,"risk":"R1","approval":"none","stepUp":false,"localPresence":false,"egress":"none","patEligible":false,"actorKinds":["service"]}"""),
                "CON.10 CF row authorization " + path);
        }
    }

    // ------------------------------------------------- foundation.test.mjs: independent encoding replaces --exchange

    private sealed record FoundationFixture(JsonObject Fixture, JsonObject Samples, HashSet<string> FoundationTypes);

    private static FoundationFixture LoadFoundation(string root)
    {
        var fixture = JsonNode.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/public/wp03-01.json")))!.AsObject();
        var additions = JsonNode.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/public/con-02-descriptors.json")))!["exchange"]!.AsObject();
        var samples = fixture["samples"]!.AsObject();
        foreach (var (name, sample) in additions["samples"]!.AsObject())
        {
            Require(!samples.ContainsKey(name), "foundation: duplicate independent fixture " + name);
            samples[name] = sample!.DeepClone();
        }
        foreach (var item in additions["cases"]!.AsArray()) fixture["cases"]!.AsArray().Add(item!.DeepClone());
        var types = fixture["foundationTypes"]!.AsArray().Select(node => node!.GetValue<string>()).ToHashSet(StringComparer.Ordinal);
        foreach (var name in additions["foundationTypes"]!.AsArray()) types.Add(name!.GetValue<string>());
        var transfer = JsonNode.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/public/con-09-sync-transfer.json")))!["transferTicket"]!.AsObject();
        Require(!samples.ContainsKey("TransferTicket"), "foundation: duplicate independent fixture TransferTicket");
        samples["TransferTicket"] = transfer["sample"]!.DeepClone();
        foreach (var item in transfer["cases"]!.AsArray()) fixture["cases"]!.AsArray().Add(item!.DeepClone());
        types.Add("TransferTicket");
        return new FoundationFixture(fixture, samples, types);
    }

    private static MessageDescriptor FoundationDescriptor(FoundationFixture fixture, string name)
    {
        Require(fixture.Samples.ContainsKey(name) && !name.StartsWith('$'), "foundation: unregistered fixture target " + name);
        FileDescriptor[] files = fixture.FoundationTypes.Contains(name)
            ? [F.FoundationReflection.Descriptor]
            : [P.ContentReflection.Descriptor, P.DescriptorsReflection.Descriptor];
        return files.SelectMany(file => file.MessageTypes).SingleOrDefault(message => message.Name == name)
            ?? throw new InvalidOperationException("foundation: missing generated descriptor " + name);
    }

    private static void FoundationIndependentEncoding(string root)
    {
        var fixture = LoadFoundation(root);
        var positives = 0;
        var records = new HashSet<string>(StringComparer.Ordinal);
        foreach (var node in fixture.Fixture["cases"]!.AsArray())
        {
            var item = node!.AsObject();
            if (!item["valid"]!.GetValue<bool>()) continue;
            var id = item["id"]!.GetValue<string>();
            var target = item["target"]!.GetValue<string>();
            var descriptor = FoundationDescriptor(fixture, target);
            var json = Materialize(item, fixture.Samples);
            var generated = JsonParser.Default.Parse(json.ToJsonString(), descriptor);
            var independent = ProtoWire.Encode(json, descriptor);
            Require(independent.AsSpan().SequenceEqual(generated.ToByteArray()), id + ": independent encoder bytes equal the generated C# bytes");
            var decoded = descriptor.Parser.ParseFrom(independent);
            Require(JsonFormatter.Default.Format(decoded) == JsonFormatter.Default.Format(generated), id + ": independent bytes decode to the authored value");
            records.Add(target);
            positives++;
        }
        Require(records.SetEquals(fixture.Samples.Select(pair => pair.Key).Where(name => !name.StartsWith('$'))), "foundation: every selected record is independently encoded");
        var vectors = 0;
        foreach (var node in fixture.Fixture["wireVectors"]!.AsArray())
        {
            var item = node!.AsObject();
            var descriptor = FoundationDescriptor(fixture, item["target"]!.GetValue<string>());
            var bytes = ProtoWire.Encode(Expand(item["value"]!, fixture.Samples), descriptor);
            Require(Convert.ToHexStringLower(bytes) == item["hex"]!.GetValue<string>(), item["id"]!.GetValue<string>() + ": independent encoder equals the published wire oracle");
            vectors++;
        }
        Require(positives == fixture.Fixture["cases"]!.AsArray().Count(node => node!["valid"]!.GetValue<bool>()) && positives > 200 && vectors == 10,
            "foundation: the complete positive and wire-oracle sets were exercised");
        Console.WriteLine($"Independently encoded {positives} positive foundation cases and {vectors} wire oracles; bytes equal the generated C# encoding.");
    }

    private static void FoundationCoverage(string root)
    {
        var fixture = LoadFoundation(root);
        var output = new List<(string Target, JsonNode Json, string Id)>();
        foreach (var node in fixture.Fixture["cases"]!.AsArray())
        {
            var item = node!.AsObject();
            if (!item["valid"]!.GetValue<bool>()) continue;
            var target = item["target"]!.GetValue<string>();
            var message = JsonParser.Default.Parse(Materialize(item, fixture.Samples).ToJsonString(), FoundationDescriptor(fixture, target));
            output.Add((target, JsonNode.Parse(JsonFormatter.Default.Format(message))!, item["id"]!.GetValue<string>()));
        }

        // The two authorized CON.22 positive content cases extend coverage.
        using var con22 = Load(root, "fixtures/public/con-22-account-support.json");
        var con22Expected = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["support-case-valid"] = "SupportCase",
            ["support-message-forward-compatible-actor-key"] = "SupportMessage",
        };
        var con22Cases = con22.RootElement.GetProperty("cases").EnumerateArray().Where(item => con22Expected.ContainsKey(item.GetProperty("id").GetString()!)).ToArray();
        Require(con22Cases.Select(item => item.GetProperty("id").GetString()!).Order(StringComparer.Ordinal).SequenceEqual(con22Expected.Keys.Order(StringComparer.Ordinal), StringComparer.Ordinal),
            "foundation coverage: only the two authorized CON.22 positive cases");
        foreach (var item in con22Cases)
        {
            var id = item.GetProperty("id").GetString()!;
            var target = con22Expected[id];
            Require(item.GetProperty("target").GetString() == target && item.GetProperty("valid").GetBoolean(), id + ": exact positive content.proto target");
            IMessage message = target == "SupportCase"
                ? CheckedRoundTrip(JsonParser.Default.Parse<P.SupportCase>(item.GetProperty("value").GetRawText()), P.SupportCase.Parser, Shapes.IsValid, id)
                : CheckedRoundTrip(JsonParser.Default.Parse<P.SupportMessage>(item.GetProperty("value").GetRawText()), P.SupportMessage.Parser, Shapes.IsValid, id);
            output.Add((target, JsonNode.Parse(JsonFormatter.Default.Format(message))!, id));
        }

        // The two authorized CON.24 positive scope vectors extend coverage.
        using var con24 = Load(root, "fixtures/public/con-24-scope-library.json");
        var con24Expected = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["projects-use-project-metadata-and-visible-live-sessions-in-one-snapshot"] = "ScopeProjectSummary",
            ["sessions-count-findings-and-reports-from-committed-owner-filtered-aggregate"] = "ScopeSessionSummary",
        };
        var con24Vectors = con24.RootElement.GetProperty("vectors").EnumerateArray().Where(item => con24Expected.ContainsKey(item.GetProperty("id").GetString()!)).ToArray();
        Require(con24Vectors.Length == 2, "foundation coverage: only the two authorized CON.24 positive vectors");
        foreach (var item in con24Vectors)
        {
            var id = item.GetProperty("id").GetString()!;
            var hasExpected = item.TryGetProperty("expected", out var expected);
            var hasItems = item.TryGetProperty("expectedItems", out var expectedItems);
            Require(hasExpected != hasItems, id + ": exactly one expected protobuf shape is present");
            if (con24Expected[id] == "ScopeProjectSummary")
            {
                Require(item.GetProperty("operationId").GetString() == "scope.listProjects", id + ": exact producer operation");
                Require(expected.EnumerateObject().Select(member => member.Name).Order(StringComparer.Ordinal)
                    .SequenceEqual(["mustNotUse", "name", "projectIdHex", "revision", "sessionCount", "updatedAt"], StringComparer.Ordinal), id + ": exact expected keys");
                Require(Same(expected.GetProperty("mustNotUse"), """["session.name","max(session.revision)"]"""), id + ": no session-derived identity or revision");
                var json = new JsonObject
                {
                    ["projectId"] = new JsonObject { ["value"] = ScopeBytes(expected.GetProperty("projectIdHex").GetString()!, id) },
                    ["name"] = expected.GetProperty("name").GetString(),
                    ["sessionCount"] = JsonNode.Parse(expected.GetProperty("sessionCount").GetRawText()),
                    ["updatedAt"] = JsonNode.Parse(expected.GetProperty("updatedAt").GetRawText()),
                    ["revision"] = new JsonObject { ["value"] = JsonNode.Parse(expected.GetProperty("revision").GetRawText()) },
                };
                var message = CheckedRoundTrip(JsonParser.Default.Parse<P.ScopeProjectSummary>(json.ToJsonString()), P.ScopeProjectSummary.Parser, Shapes.IsValid, id);
                output.Add(("ScopeProjectSummary", JsonNode.Parse(JsonFormatter.Default.Format(message))!, id));
            }
            else
            {
                Require(item.GetProperty("operationId").GetString() == "scope.listSessions", id + ": exact producer operation");
                Require(expectedItems.GetArrayLength() == 1, id + ": exact single visible positive item");
                var row = expectedItems[0];
                Require(row.EnumerateObject().Select(member => member.Name).Order(StringComparer.Ordinal).SequenceEqual(
                    ["findingCount", "name", "projectIdHex", "reportCount", "revision", "sessionIdHex", "tagsHex", "updatedAt"], StringComparer.Ordinal), id + ": exact expected keys");
                var tags = new JsonArray();
                foreach (var tag in row.GetProperty("tagsHex").EnumerateArray()) tags.Add((JsonNode)new JsonObject { ["value"] = ScopeBytes(tag.GetString()!, id) });
                var json = new JsonObject
                {
                    ["sessionId"] = new JsonObject { ["value"] = ScopeBytes(row.GetProperty("sessionIdHex").GetString()!, id) },
                    ["projectId"] = new JsonObject { ["value"] = ScopeBytes(row.GetProperty("projectIdHex").GetString()!, id) },
                    ["name"] = row.GetProperty("name").GetString(),
                    ["findingCount"] = JsonNode.Parse(row.GetProperty("findingCount").GetRawText()),
                    ["reportCount"] = JsonNode.Parse(row.GetProperty("reportCount").GetRawText()),
                    ["tags"] = tags,
                    ["updatedAt"] = JsonNode.Parse(row.GetProperty("updatedAt").GetRawText()),
                    ["revision"] = new JsonObject { ["value"] = JsonNode.Parse(row.GetProperty("revision").GetRawText()) },
                };
                var message = CheckedRoundTrip(JsonParser.Default.Parse<P.ScopeSessionSummary>(json.ToJsonString()), P.ScopeSessionSummary.Parser, Shapes.IsValid, id);
                output.Add(("ScopeSessionSummary", JsonNode.Parse(JsonFormatter.Default.Format(message))!, id));
            }
        }

        // foundation-coverage.mjs: every inventory record has a positive decoded example and every oneof branch survives.
        using var inventory = Load(root, "eng/foundation-inventory.json");
        var records = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        foreach (var record in inventory.RootElement.GetProperty("records").EnumerateArray())
            Require(records.TryAdd(record.GetProperty("name").GetString()!, record), "foundation coverage: duplicate inventory record");
        Require(output.Select(entry => entry.Target).ToHashSet(StringComparer.Ordinal).SetEquals(records.Keys),
            "foundation coverage: every selected message has a positive decoded example");
        var expectedBranches = new HashSet<string>(StringComparer.Ordinal);
        foreach (var (name, record) in records)
            foreach (var field in record.GetProperty("fields").EnumerateArray())
                if (field.GetProperty("oneof").ValueKind == JsonValueKind.String)
                    expectedBranches.Add(name + "." + field.GetProperty("oneof").GetString() + "." + field.GetProperty("name").GetString());
        var observed = new HashSet<string>(StringComparer.Ordinal);
        void Visit(string name, JsonNode? value, string path)
        {
            Require(value is JsonObject, path + ": decoded record expected");
            Require(records.TryGetValue(name, out var record), path + ": unknown selected record " + name);
            foreach (var field in record.GetProperty("fields").EnumerateArray())
            {
                var fieldName = field.GetProperty("name").GetString()!;
                if (!value!.AsObject().TryGetPropertyValue(fieldName, out var child) || child is null) continue;
                if (field.GetProperty("oneof").ValueKind == JsonValueKind.String) observed.Add(name + "." + field.GetProperty("oneof").GetString() + "." + fieldName);
                var wireType = field.GetProperty("wireType").GetString()!;
                if (!records.ContainsKey(wireType)) continue;
                if (field.GetProperty("presence").GetString() == "repeated")
                {
                    Require(child is JsonArray, path + "." + fieldName + ": decoded repeated field expected");
                    var index = 0;
                    foreach (var element in child.AsArray()) Visit(wireType, element, path + "." + fieldName + "[" + index++ + "]");
                }
                else Visit(wireType, child, path + "." + fieldName);
            }
        }
        foreach (var (target, json, id) in output) Visit(target, json, id);
        Require(observed.SetEquals(expectedBranches), "foundation coverage: every selected oneof branch survives a positive semantic round trip: missing "
            + string.Join(",", expectedBranches.Except(observed)));
    }

    private static void FoundationRetirement(string root)
    {
        // foundation-links.test.mjs: every retired inventory message stays out of the generated public content and foundation exports.
        using var inventory = Load(root, "eng/foundation-inventory.json");
        var retired = inventory.RootElement.GetProperty("retirement").GetProperty("messages").EnumerateArray().Select(name => name.GetString()!).ToArray();
        Require(retired.Length > 0, "foundation retirement: retired message inventory");
        foreach (var name in retired)
            Require(!P.ContentReflection.Descriptor.MessageTypes.Any(message => message.Name == name)
                && !F.FoundationReflection.Descriptor.MessageTypes.Any(message => message.Name == name), "foundation retirement: retired message reappeared " + name);
        Require(P.ContentReflection.Descriptor.MessageTypes.Any(message => message.Name == "StructuredValue"), "foundation retirement: StructuredValue remains");
    }

    // ------------------------------------------------------------- foundation.test.mjs values and foundation-types.ts

    private static void FoundationValues()
    {
        // The C# identity boundary takes System.Guid, so textual UUID spellings have no C# parser; the zero UUID refusal is the shared negative.
        Throws<ArgumentException>(() => new ArcForges.Contracts.PublicApi.Values.ScopeProjectId(Guid.Empty), "values: zero UUID identity refuses");
        Require(new ArcForges.Contracts.PublicApi.Values.ScopeProjectId(Guid.Parse("00112233-4455-6677-8899-aabbccddeeff")).Value
            == ArcForges.Contracts.PublicApi.Values.ScopeProjectId.FromWire(new F.Id { Value = ByteString.FromBase64("ABEiM0RVZneImaq7zN3u/w==") }).Value,
            "values: wire identity decodes from the canonical base64 bytes");
        var owned = new ArcForges.Contracts.PublicApi.Values.ScopeProjectId(Guid.Parse("00112233-4455-6677-8899-aabbccddeeff"));
        var first = owned.ToWire();
        Require(Convert.ToHexStringLower(first.Value.Span) == "00112233445566778899aabbccddeeff" && !ReferenceEquals(first, owned.ToWire()), "values: wire output owns its bytes");
        Throws<ArgumentException>(() => new V.OpaqueCursor("\ud800"), "values: cursor refuses an unpaired surrogate");
        Require(new V.OpaqueCursor(string.Concat(Enumerable.Repeat("😀", 1024))).Value.Length == 2048, "values: cursor byte bound");
        Throws<ArgumentOutOfRangeException>(() => new V.OpaqueCursor(string.Concat(Enumerable.Repeat("😀", 1025))), "values: cursor over its byte bound");
    }

    private static void ValueDomains()
    {
        // foundation-types.ts asserted with the compiler that identity and revision domains never convert into each other.
        Type[] domains = [typeof(ArcForges.Contracts.PublicApi.Values.ScopeProjectId), typeof(V.ResourceId), typeof(ArcForges.Contracts.PublicApi.Values.RunId),
            typeof(V.CloudRevision), typeof(V.NativeRevision), typeof(V.DeliverySequence)];
        Require(domains.Distinct().Count() == domains.Length, "domains: distinct types");
        Require(!typeof(ArcForges.Contracts.PublicApi.Values.ScopeProjectId).GetMethods().Any(method => method.Name is "op_Implicit" or "op_Explicit"), "domains: ScopeProjectId has no conversion operator");
        Require(!typeof(V.ResourceId).GetMethods().Any(method => method.Name is "op_Implicit" or "op_Explicit"), "domains: ResourceId has no conversion operator");
        Require(!typeof(ArcForges.Contracts.PublicApi.Values.RunId).GetMethods().Any(method => method.Name is "op_Implicit" or "op_Explicit"), "domains: RunId has no conversion operator");
        Require(!typeof(V.CloudRevision).GetMethods().Any(method => method.Name is "op_Implicit" or "op_Explicit"), "domains: CloudRevision has no conversion operator");
        Require(!typeof(V.NativeRevision).GetMethods().Any(method => method.Name is "op_Implicit" or "op_Explicit"), "domains: NativeRevision has no conversion operator");
        Require(!typeof(V.DeliverySequence).GetMethods().Any(method => method.Name is "op_Implicit" or "op_Explicit"), "domains: DeliverySequence has no conversion operator");
        // An exact Cloud revision is constructed from a 64-bit integer only; no floating-point constructor exists.
        Require(typeof(V.CloudRevision).GetConstructors().All(constructor => constructor.GetParameters().All(parameter => parameter.ParameterType == typeof(long))),
            "domains: CloudRevision takes an exact integer only");
        Require(new V.CloudRevision(9007199254740993).ToWire().Value == 9007199254740993, "domains: exact Cloud revision beyond 2^53");
    }

    // --------------------------------------------------------------------------------------------- catalog.test.mjs

    private static void CatalogExport(string root)
    {
        using var fixture = Load(root, "fixtures/public/con-13-package-catalog.json");
        using var export = Load(root, "eng/operations/con-13.json");
        var rows = export.RootElement.GetProperty("operations").EnumerateArray().ToArray();
        Require(rows.Length == 7, "catalog: exactly seven exported operations");
        Require(rows.Where(row => row.GetProperty("authorization").GetProperty("patEligible").GetBoolean()).Select(row => row.GetProperty("operationId").GetString()!)
            .Order(StringComparer.Ordinal).SequenceEqual(fixture.RootElement.GetProperty("patEligible").EnumerateArray().Select(value => value.GetString()!).Order(StringComparer.Ordinal), StringComparer.Ordinal),
            "catalog: closed PAT subset equals the fixture");
        foreach (var row in rows)
            Require(row.GetProperty("scope").GetString() == "account" && row.GetProperty("profile").GetString() == "human-owner"
                && Same(row.GetProperty("authorization").GetProperty("actorKinds"), "[\"human\"]")
                && row.GetProperty("authorization").GetProperty("capability").ValueKind == JsonValueKind.Null, "catalog: human account operation " + row.GetProperty("operationId").GetString());
    }

    // ------------------------------------------------------------------------------------ con-02-descriptors.test.mjs

    private static void Con02Admission()
    {
        var malformed = new byte[] { 255 };
        RefusesWith(() => ReadEncoded(EncodedReference(malformed), malformed), ContractSerializationFailure.Malformed,
            "CON.02: a complete matching reference over malformed protobuf refuses as malformed");
        var bytes = new Hello.SayHelloResponse { Message = "A" }.ToByteArray();
        var reference = EncodedReference(bytes);
        var read = ReadEncoded(reference, bytes);
        Array.Fill(bytes, (byte)255);
        reference.Resource.ContentHash = new string('0', 64);
        reference.ExpiresAt.Nanos = 0;
        Require(read.Message == "A", "CON.02: the read owns an immutable byte and reference snapshot");
    }

    private static Hello.SayHelloResponse ReadEncoded(F.EncodedBodyRef reference, byte[] bytes) =>
        Val.EncodedBodyReader.Read(reference, bytes, "arcforges.hello.v1.SayHelloResponse", new string('a', 64), "bound-snapshot",
            new F.Instant { UnixSeconds = 200, Nanos = 0 }, Hello.SayHelloResponse.Parser);

    private static F.EncodedBodyRef EncodedReference(byte[] bytes)
    {
        var id = new F.Id { Value = ByteString.CopyFrom(Convert.FromHexString("00112233445566778899aabbccddeeff")) };
        return new F.EncodedBodyRef
        {
            Resource = new F.ResourceVersionRef
            {
                Resource = new F.ResourceRef { RealmId = id, ResourceId = id.Clone(), OwnerAppId = "arcscope", ResourceKind = "projection", Availability = (F.ResourceAvailability)1 },
                Cloud = new F.Revision { Value = 1 },
                ContentHash = Convert.ToHexStringLower(SHA256.HashData(bytes)),
            },
            MessageType = "arcforges.hello.v1.SayHelloResponse",
            DescriptorHash = new string('a', 64),
            ByteLength = (ulong)bytes.Length,
            SnapshotToken = "bound-snapshot",
            ExpiresAt = new F.Instant { UnixSeconds = 200, Nanos = 1 },
        };
    }

    // -------------------------------------------------------------------------------------- con-07-identity.test.mjs

    private static void Con07(string root)
    {
        using var fixtureDocument = Load(root, "fixtures/public/con-07-identity.json");
        using var exportDocument = Load(root, "eng/operations/con-07.json");
        var fixture = fixtureDocument.RootElement;
        var operations = fixture.GetProperty("operations").EnumerateArray().ToArray();
        foreach (var row in exportDocument.RootElement.GetProperty("operations").EnumerateArray())
            Require(row.GetProperty("source").GetString() == "public/proto/arcforges/publicapi/v1/identity.proto", "CON.07: export source " + row.GetProperty("operationId").GetString());
        Require(operations.Where(row => row.GetProperty("patEligible").GetBoolean()).Select(row => row.GetProperty("id").GetString()).SequenceEqual(["workspace.list", "workspace.get"]),
            "CON.07: exact PAT-eligible operations");
        Require(operations.Where(row => row.GetProperty("risk").GetString() == "R4").Select(row => row.GetProperty("id").GetString())
            .SequenceEqual(["identity.requestAccountDeletion", "workspace.requestDataDeletion"]), "CON.07: exact R4 operations");

        var vectors = fixture.GetProperty("httpVectors").EnumerateArray().ToArray();
        var form = vectors.Single(item => item.GetProperty("id").GetString() == "native-token-desktop").GetProperty("text").GetString()!;
        Require(Val.NativeTokenRequestForm.TryParse(Encoding.UTF8.GetBytes(form), out _, out _), "CON.07: desktop token form parses");
        Require(!Val.NativeTokenRequestForm.TryParse(Encoding.UTF8.GetBytes(form.Replace("&", "\n", StringComparison.Ordinal)), out _, out var control) && control == ContractSerializationFailure.Malformed,
            "CON.07: a raw control separator is malformed");
        RefusesWith(() => Val.NativeTokenRequestForm.Parse("grant_type=authorization_code"u8.ToArray()), ContractSerializationFailure.Invalid, "CON.07: incomplete form is invalid");
        RefusesWith(() => Val.NativeTokenRequestForm.Serialize(new Native.NativeTokenRequest { GrantType = "password", Code = "", CodeVerifier = "", ClientId = "", RedirectUri = "", InstallationId = "" }),
            ContractSerializationFailure.Invalid, "CON.07: serializer refuses an undeclared grant");
        Require(!Val.NativeTokenRequestForm.TryParse("__proto__=x&grant_type=authorization_code"u8.ToArray(), out _, out var proto) && proto == ContractSerializationFailure.Invalid,
            "CON.07: an undeclared prototype-named form key is invalid");

        var challenge = vectors.Single(item => item.GetProperty("id").GetString() == "browser-auth-challenge-valid").GetProperty("text").GetString()!;
        var parsed = Val.BrowserAuthChallengeJson.Parse(Encoding.UTF8.GetBytes(challenge));
        using (var written = JsonDocument.Parse(Val.BrowserAuthChallengeJson.Serialize(parsed)))
            Require(written.RootElement.EnumerateObject().Select(member => member.Name).SequenceEqual(["flowId", "method", "challenge", "rpId", "expiresAt", "options", "purpose"]),
                "CON.07: browser challenge keeps its declared member order");
        Require(!Val.BrowserAuthChallengeJson.TryParse(new byte[65537], out _, out var large) && large == ContractSerializationFailure.TooLarge, "CON.07: 64 KiB JSON bound");
        Require(!Val.BrowserAuthChallengeJson.TryParse(Encoding.UTF8.GetBytes("{\"__proto__\":{}," + challenge[1..]), out _, out _), "CON.07: prototype member refused");
        Require(!Val.BrowserSessionViewJson.TryParse(Encoding.UTF8.GetBytes(challenge), out _, out _), "CON.07: a challenge is not a session view");

        var routes = Browser.BrowserSessionRoutes.All.Select(route => (route.Id, route.SetCookie, route.ResponseRoots))
            .Concat(Native.NativeAuthRoutes.All.Select(route => (route.Id, route.SetCookie, route.ResponseRoots))).ToArray();
        Require(routes.Single(route => route.Id == "browser.logout").SetCookie == "clear", "CON.07: browser logout clears the session cookie");
        Require(!routes.Any(route => route.Id.StartsWith("browser.", StringComparison.Ordinal) && route.ResponseRoots.Contains("NativeTokenResponse")),
            "CON.07: no browser route returns a native token");
        Require(fixture.GetProperty("journeys").EnumerateArray().Select(journey => journey.GetProperty("id").GetString()).SequenceEqual(["account-creation", "email-login",
            "passkey-login", "passkey-management", "self-host-password-enrollment", "oidc-login-enrollment-link", "recovery", "step-up", "refresh", "logout",
            "native-browser-authorization", "api-token", "account-deletion", "browser-session"]), "CON.07: exact ordered journey inventory");
    }

    private static void Con07Jvm()
    {
        // KotlinConnectClient IdentityCases.kt: client operations, enum numbers, presence, oneofs and challenge rules, in C#.
        var total = ClientMethods(typeof(P.IdentityService.IdentityServiceClient), P.IdentityService.Descriptor)
            + ClientMethods(typeof(P.WorkspaceService.WorkspaceServiceClient), P.WorkspaceService.Descriptor)
            + ClientMethods(typeof(P.DeviceService.DeviceServiceClient), P.DeviceService.Descriptor);
        Require(total == 49, "CON.07 client: exact 49 Registry04 operations");
        foreach (var (name, count) in new[] { ("AuthMethod", 5), ("AuthPurpose", 6), ("RecoveryMethod", 5), ("TrustLevel", 4), ("ProtectionProfile", 2) })
            Require(P.IdentityReflection.Descriptor.EnumTypes.Single(type => type.Name == name).Values.Select(value => value.Number).SequenceEqual(Enumerable.Range(0, count)),
                "CON.07 client: " + name + " numbers");
        Require(!new P.AuthChallenge().HasPurpose && new P.AuthChallenge { Purpose = P.AuthPurpose.Enroll }.HasPurpose, "CON.07 client: AuthChallenge.purpose presence");
        Require(!new P.NativeSession().HasPurpose && new P.NativeSession { Purpose = P.AuthPurpose.Enroll }.HasPurpose, "CON.07 client: NativeSession.purpose presence");
        Require(!new P.SessionView().HasPurpose && new P.SessionView { Purpose = P.AuthPurpose.Enroll }.HasPurpose, "CON.07 client: SessionView.purpose presence");
        Require(!new P.AuthProviderView().HasMethod && new P.AuthProviderView { Method = P.AuthMethod.Oidc }.HasMethod, "CON.07 client: AuthProviderView.method presence");
        Require(!new P.WorkspaceView().HasProtection && new P.WorkspaceView { Protection = P.ProtectionProfile.Standard }.HasProtection, "CON.07 client: WorkspaceView.protection presence");
        Require(!new P.DeviceView().HasTrust && new P.DeviceView { Trust = P.TrustLevel.Trusted }.HasTrust, "CON.07 client: DeviceView.trust presence");
        var begin = new P.IdentityServiceBeginAuthenticationRequest { Method = P.AuthMethod.Email, Purpose = P.AuthPurpose.Enroll };
        Require(!new P.IdentityServiceBeginAuthenticationRequest().HasMethod && !new P.IdentityServiceBeginAuthenticationRequest().HasPurpose && begin.HasMethod && begin.HasPurpose,
            "CON.07 client: BeginAuthentication method and purpose presence");
        Require(!new P.IdentityServiceRequestEmailCodeRequest().HasPurpose && new P.IdentityServiceRequestEmailCodeRequest { Purpose = P.AuthPurpose.Enroll }.HasPurpose, "CON.07 client: RequestEmailCode presence");
        Require(!new P.IdentityServiceBeginStepUpRequest().HasMethod && new P.IdentityServiceBeginStepUpRequest { Method = P.AuthMethod.Passkey }.HasMethod, "CON.07 client: BeginStepUp presence");
        Require(!new P.IdentityServiceBeginRecoveryRequest().HasMethod && new P.IdentityServiceBeginRecoveryRequest { Method = P.RecoveryMethod.EmailCode }.HasMethod, "CON.07 client: BeginRecovery presence");
        Require(!new P.DeviceServiceSetTrustRequest().HasTrust && new P.DeviceServiceSetTrustRequest { Trust = P.TrustLevel.Trusted }.HasTrust, "CON.07 client: SetTrust presence");

        var passkey = new P.WebAuthnAssertion
        {
            CredentialId = ByteString.CopyFromUtf8("credential"),
            ClientDataJson = ByteString.CopyFromUtf8("{}"),
            AuthenticatorData = ByteString.CopyFromUtf8("data"),
            Signature = ByteString.CopyFromUtf8("signature"),
        };
        (P.AuthProof Proof, P.AuthProof.ProofOneofCase Case)[] proofs =
        [
            (new P.AuthProof { Passkey = passkey }, P.AuthProof.ProofOneofCase.Passkey),
            (new P.AuthProof { EmailCode = "123456" }, P.AuthProof.ProofOneofCase.EmailCode),
            (new P.AuthProof { RecoveryCode = "recovery" }, P.AuthProof.ProofOneofCase.RecoveryCode),
            (new P.AuthProof { Password = "correct horse battery staple" }, P.AuthProof.ProofOneofCase.Password),
            (new P.AuthProof { ProviderReceipt = "receipt" }, P.AuthProof.ProofOneofCase.ProviderReceipt),
            (new P.AuthProof { AdminGrant = "grant" }, P.AuthProof.ProofOneofCase.AdminGrant),
        ];
        foreach (var (proof, expected) in proofs)
            Require(proof.ProofCase == expected && P.AuthProof.Parser.ParseFrom(proof.ToByteArray()).Equals(proof), "CON.07 client: AuthProof variant " + expected);
        var replaced = new P.AuthProof { EmailCode = "1", Password = "2" };
        Require(replaced.ProofCase == P.AuthProof.ProofOneofCase.Password && replaced.EmailCode.Length == 0, "CON.07 client: a second proof variant replaces the first");
        Require(new P.AuthProof().ProofCase == P.AuthProof.ProofOneofCase.None, "CON.07 client: an absent proof is not set");

        // The Kotlin case used a test-local predicate; here the generated C# validator enforces the same bounds.
        Require(Shapes.IsValid(new P.CredentialReplacement { Password = string.Concat(Enumerable.Repeat("😀", 15)) }), "CON.07 client: 15-scalar password accepted");
        Require(!Shapes.IsValid(new P.CredentialReplacement { Password = string.Concat(Enumerable.Repeat("😀", 14)) }), "CON.07 client: 14-scalar password refused");
        Require(!Shapes.IsValid(new P.CredentialReplacement { Password = new string('a', 129) }), "CON.07 client: 129-scalar password refused");
        Require(new P.CredentialReplacement { Password = new string('p', 15) }.ReplacementCase == P.CredentialReplacement.ReplacementOneofCase.Password, "CON.07 client: password variant retained");

        var id = new F.Id { Value = ByteString.CopyFrom(Convert.FromHexString("112233445566478899aabbccddeeff00")) };
        var now = new F.Instant { UnixSeconds = 1, Nanos = 0 };
        var recover = new P.AuthChallenge { FlowId = id, Challenge = ByteString.CopyFrom(new byte[32]), ExpiresAt = now, Purpose = P.AuthPurpose.Recover, RecoveryMethod = P.RecoveryMethod.EmailCode };
        Require(Shapes.IsValid(recover), "CON.07 client: recovery challenge with recoveryMethod accepted");
        var recoverWithMethod = recover.Clone(); recoverWithMethod.Method = P.AuthMethod.Email;
        Require(!Shapes.IsValid(recoverWithMethod), "CON.07 client: recovery challenge carrying method refused");
        var recoverWithout = recover.Clone(); recoverWithout.ClearRecoveryMethod();
        Require(!Shapes.IsValid(recoverWithout), "CON.07 client: recovery challenge without recoveryMethod refused");
        var authenticate = recover.Clone(); authenticate.Purpose = P.AuthPurpose.Authenticate; authenticate.ClearRecoveryMethod(); authenticate.Method = P.AuthMethod.Passkey;
        Require(Shapes.IsValid(authenticate), "CON.07 client: authenticate challenge with method accepted");
        var authenticateWithRecovery = authenticate.Clone(); authenticateWithRecovery.RecoveryMethod = P.RecoveryMethod.Passkey;
        Require(!Shapes.IsValid(authenticateWithRecovery), "CON.07 client: authenticate challenge carrying recoveryMethod refused");
        var oversized = authenticate.Clone(); oversized.Challenge = ByteString.CopyFrom(new byte[33]);
        Require(!Shapes.IsValid(oversized), "CON.07 client: 33-byte challenge refused");

        var device = new P.DeviceView { DeviceId = id, Name = "Workstation", Platform = "windows", Trust = P.TrustLevel.Trusted, RemoteEnabled = false, Revision = new F.Revision { Value = 1 } };
        var session = new P.NativeSession
        {
            SessionId = id, AccessToken = "access", AccessExpiresAt = now, RefreshToken = "refresh", RefreshExpiresAt = now, Device = device,
            RecoveryGeneration = 1, Purpose = P.AuthPurpose.Authenticate,
        };
        Require(P.NativeSession.Parser.ParseFrom(session.ToByteArray()).Equals(session), "CON.07 client: NativeSession round trip");
        var noRefresh = session.Clone(); noRefresh.ClearRefreshToken();
        Require(!P.NativeSession.Parser.ParseFrom(noRefresh.ToByteArray()).HasRefreshToken, "CON.07 client: absent refresh token stays absent");
        var cleared = new P.ProfileUpdate { ClearAvatar = true };
        Require(cleared.ChangeCase == P.ProfileUpdate.ChangeOneofCase.ClearAvatar && cleared.ClearAvatar && P.ProfileUpdate.Parser.ParseFrom(cleared.ToByteArray()).Equals(cleared),
            "CON.07 client: clearAvatar variant retained");
        Require(new P.ProfileUpdate().ChangeCase == P.ProfileUpdate.ChangeOneofCase.None, "CON.07 client: an unchanged avatar is the unset oneof");
    }

    private static int ClientMethods([System.Diagnostics.CodeAnalysis.DynamicallyAccessedMembers(System.Diagnostics.CodeAnalysis.DynamicallyAccessedMemberTypes.PublicMethods)] Type client, ServiceDescriptor descriptor)
    {
        var service = descriptor.FullName;
        var methods = descriptor.Methods.Select(method => method.Name).ToArray();
        var declared = client.GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.DeclaredOnly)
            .Select(method => method.Name).ToHashSet(StringComparer.Ordinal);
        Require(declared.SetEquals(methods.Concat(methods.Select(method => method + "Async"))), "CON.07 client: generated " + service + " client methods");
        return methods.Length;
    }

    // ---------------------------------------------------------------------------- con-11-application-streams.test.mjs

    private static void Con11(string root)
    {
        var services = P.ApplicationReflection.Descriptor.Services.Concat(E.EventsReflection.Descriptor.Services).ToDictionary(service => service.FullName, StringComparer.Ordinal);
        var expected = new Dictionary<string, string[]>(StringComparer.Ordinal)
        {
            ["arcforges.publicapi.v1.ApplicationService"] = ["List", "Heartbeat", "Disconnect"],
            ["arcforges.publicapi.v1.HistoryService"] = ["BeginImport", "FinalizeImport", "GetImport", "CancelImport"],
            ["arcforges.events.v1.ExecutionService"] = ["StartTransientTurn", "ReadOutput", "WatchOutput", "AcknowledgeOutput", "PurgeTransient"],
            ["arcforges.events.v1.EventService"] = ["Poll", "Watch"],
        };
        Require(services.Keys.Order(StringComparer.Ordinal).SequenceEqual(expected.Keys.Order(StringComparer.Ordinal), StringComparer.Ordinal), "CON.11: exact independent service set");
        foreach (var (name, methods) in expected)
            Require(services[name].Methods.Select(method => method.Name).Order(StringComparer.Ordinal).SequenceEqual(methods.Order(StringComparer.Ordinal), StringComparer.Ordinal),
                "CON.11: exact independent method set " + name);

        using var fixture = Load(root, "fixtures/public/con-11-application-streams.json");
        var presence = fixture.RootElement.GetProperty("presenceBoundaryVectors").EnumerateArray().ToDictionary(vector => vector.GetProperty("id").GetString()!, StringComparer.Ordinal);
        byte[] Bytes(IMessage message) => message.ToByteArray();
        Require(Bytes(new P.ApplicationTarget { ProductId = presence["application-target-empty-product-presence"].GetProperty("value").GetString()! }).SequenceEqual(new byte[] { 0x0a, 0x00 }),
            "CON.11: explicit empty productId bytes");
        Require(Bytes(new P.ApplicationTarget { InstanceEpoch = ulong.Parse(presence["application-target-zero-epoch-presence"].GetProperty("value").ToString(), CultureInfo.InvariantCulture) })
            .SequenceEqual(new byte[] { 0x20, 0x00 }), "CON.11: explicit zero instanceEpoch bytes");
        Require(presence.ContainsKey("request-meta-empty-application-scope-presence")
            && Bytes(new F.RequestMeta { ApplicationScope = new F.ApplicationScope() }).SequenceEqual(new byte[] { 0x42, 0x00 }), "CON.11: empty RequestMeta applicationScope bytes");
        Require(presence.ContainsKey("conversation-view-empty-application-scope-presence")
            && Bytes(new P.ConversationView { ApplicationScope = new F.ApplicationScope() }).SequenceEqual(new byte[] { 0x52, 0x00 }), "CON.11: empty ConversationView applicationScope bytes");
        Require(Bytes(new P.ConversationView { HistoryMode = (P.HistoryMode)presence["conversation-view-unspecified-history-mode-presence"].GetProperty("value").GetInt32() })
            .SequenceEqual(new byte[] { 0x58, 0x00 }), "CON.11: explicit unspecified historyMode bytes");
    }

    // ---------------------------------------------------------------------------------- con-24-scope-library.test.mjs

    private static void Con24(string root)
    {
        using var fixture = Load(root, "fixtures/public/con-24-scope-library.json");
        var vectors = fixture.RootElement.GetProperty("vectors").EnumerateArray().ToDictionary(vector => vector.GetProperty("id").GetString()!, StringComparer.Ordinal);
        var first = vectors["projects-use-project-metadata-and-visible-live-sessions-in-one-snapshot"].GetProperty("expected");
        Require(first.GetProperty("sessionCount").GetInt32() == 2 && Same(first.GetProperty("mustNotUse"), """["session.name","max(session.revision)"]"""), "CON.24: project summary facts");
        var aggregate = vectors["sessions-count-findings-and-reports-from-committed-owner-filtered-aggregate"].GetProperty("expectedItems")[0];
        Require(aggregate.GetProperty("findingCount").GetInt32() == 2 && aggregate.GetProperty("reportCount").GetInt32() == 1
            && Same(aggregate.GetProperty("tagsHex"), """["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]"""), "CON.24: session aggregate facts");
        Require(Same(vectors["sessions-missing-or-hidden-project-returns-not-found"].GetProperty("expected"), """{"errorCode":"state.not_found","itemsExposed":false}"""), "CON.24: hidden project disposition");
        Require(Same(vectors["sessions-next-page-rechecks-current-access"].GetProperty("expected"), """{"accessRecheckedOnThisRequest":true,"priorSnapshotDoesNotRestoreRevokedAccess":true}"""),
            "CON.24: next page access disposition");
        Require(vectors["sessions-next-page-rechecks-current-access"].GetProperty("source").GetProperty("cursorBoundToPriorAuthorizedSnapshot").GetBoolean(), "CON.24: cursor bound to the prior snapshot");
        Require(Same(vectors["get-session-returns-only-committed-metadata-with-cloud-revision-and-time"].GetProperty("expected").GetProperty("committedAt"),
            """{"unixSeconds":"1790593200","nanos":500000000}"""), "CON.24: committed time");
        var unresolved = vectors["get-session-unresolved-parent-is-not-reassigned-or-exposed"];
        Require(!unresolved.GetProperty("source").GetProperty("parentProjectTombstoned").GetBoolean()
            && Same(unresolved.GetProperty("expected"), """{"visible":false,"errorCode":"state.not_found","reassigned":false}"""), "CON.24: unresolved parent disposition");
        Require(Same(vectors["get-session-tombstone-returns-gone"].GetProperty("expected"), """{"visible":false,"errorCode":"state.gone"}"""), "CON.24: tombstone disposition");
        Require(vectors["projects-order-equal-commit-times-by-project-id-descending"].GetProperty("source").GetProperty("projects").EnumerateArray()
            .Count(project => project.GetProperty("hasVisibleLiveSessions").GetBoolean()) == 2, "CON.24: two visible tie-order projects");
    }

    // ------------------------------------------------------------------------------------ con-25-connector.test.mjs

    private static readonly (string Id, string Type, bool Valid)[] ConnectorVectors =
    [
        ("definition-valid-oauth", "ConnectorDefinition", true), ("definition-valid-minimal-no-origins", "ConnectorDefinition", true),
        ("definition-bad-id-characters", "ConnectorDefinition", false), ("definition-uppercase-manifest-hash", "ConnectorDefinition", false),
        ("definition-short-manifest-hash", "ConnectorDefinition", false), ("definition-unknown-auth-kind", "ConnectorDefinition", false),
        ("definition-http-origin", "ConnectorDefinition", false), ("definition-origin-with-path", "ConnectorDefinition", false),
        ("definition-origin-with-credentials", "ConnectorDefinition", false), ("definition-too-many-origins", "ConnectorDefinition", false),
        ("definition-duplicate-scope", "ConnectorDefinition", false), ("definition-missing-package-version", "ConnectorDefinition", false),
        ("connection-valid-connected", "ConnectorConnection", true), ("connection-valid-failed-with-reason", "ConnectorConnection", true),
        ("connection-unknown-state", "ConnectorConnection", false), ("connection-empty-name", "ConnectorConnection", false),
        ("connection-name-too-long", "ConnectorConnection", false), ("connection-zero-connection-id", "ConnectorConnection", false),
        ("connection-missing-revision", "ConnectorConnection", false), ("connection-duplicate-scope", "ConnectorConnection", false),
        ("challenge-valid-oauth-url", "ConnectorChallenge", true), ("challenge-valid-personal-token-no-url", "ConnectorChallenge", true),
        ("challenge-http-url", "ConnectorChallenge", false), ("challenge-missing-expiry", "ConnectorChallenge", false),
        ("challenge-zero-flow-id", "ConnectorChallenge", false), ("proof-valid-callback-receipt", "ConnectorProof", true),
        ("proof-valid-personal-token", "ConnectorProof", true), ("proof-no-arm", "ConnectorProof", false), ("proof-empty-secret", "ConnectorProof", false),
        ("proof-oversize-secret", "ConnectorProof", false), ("begin-request-valid", "ConnectorServiceBeginConnectionRequest", true),
        ("begin-request-missing-name", "ConnectorServiceBeginConnectionRequest", false), ("begin-request-bad-definition-id", "ConnectorServiceBeginConnectionRequest", false),
        ("complete-request-valid", "ConnectorServiceCompleteConnectionRequest", true), ("complete-request-missing-proof", "ConnectorServiceCompleteConnectionRequest", false),
        ("revoke-request-valid", "ConnectorServiceRevokeConnectionRequest", true), ("revoke-request-zero-connection-id", "ConnectorServiceRevokeConnectionRequest", false),
        ("list-connections-value-valid", "ConnectorServiceListConnectionsValue", true), ("list-connections-value-over-page-bound", "ConnectorServiceListConnectionsValue", false),
    ];

    private static void Con25Connector(string root)
    {
        using var fixtureDocument = Load(root, "fixtures/public/con-25-connector.json");
        using var manifest = Load(root, "eng/operation-scope-manifest.json");
        var fixture = fixtureDocument.RootElement;
        Require(fixture.GetProperty("source").GetString() == "public/proto/arcforges/publicapi/v1/connector.proto", "CON.25: fixture source");
        Require(fixture.GetProperty("decisions").EnumerateArray().Select(decision => decision.GetProperty("id").GetString()).SequenceEqual(["revoke-expected-revision",
            "public-records-in-public-package", "foreground-and-tool-reachability", "idempotency-compatibility-classes", "no-owner-runtime"]), "CON.25: exact recorded decisions");
        var allowlist = manifest.RootElement.GetProperty("toolAllowlist");
        Require(allowlist.ValueKind == JsonValueKind.Array && allowlist.GetArrayLength() == 0, "CON.25: the tool allowlist stays empty");
        Require(P.ConnectorService.Descriptor.Methods.All(method => method.InputType.Oneofs.All(oneof => oneof.IsSynthetic)), "CON.25: requests have no oneof");
        Require(F.RequestMeta.Descriptor.FindFieldByNumber(2) is { Name: "expected_rev", JsonName: "expectedRev" }, "CON.25: RequestMeta tag 2 is expected_rev");
        var vectors = fixture.GetProperty("vectors").EnumerateArray().Select(vector => (vector.GetProperty("id").GetString()!, vector.GetProperty("type").GetString()!, vector.GetProperty("valid").GetBoolean())).ToArray();
        Require(vectors.Length == ConnectorVectors.Length && vectors.ToHashSet().SetEquals(ConnectorVectors), "CON.25: exact authorized vector id, type and validity table");
    }

    private sealed class CapturedCall : Exception
    {
        public CapturedCall() : base("captured") { }
    }

    private sealed class CapturingInvoker : CallInvoker
    {
        public List<(string Path, MethodType Type, Type Request, Type Response, string Kind)> Calls { get; } = [];

        public override AsyncUnaryCall<TResponse> AsyncUnaryCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options, TRequest request)
        {
            Calls.Add((method.FullName, method.Type, typeof(TRequest), typeof(TResponse), "unary"));
            throw new CapturedCall();
        }
        public override TResponse BlockingUnaryCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options, TRequest request) => throw new NotSupportedException();
        public override AsyncServerStreamingCall<TResponse> AsyncServerStreamingCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options, TRequest request)
        {
            Calls.Add((method.FullName, method.Type, typeof(TRequest), typeof(TResponse), "serverStream"));
            throw new CapturedCall();
        }
        public override AsyncClientStreamingCall<TRequest, TResponse> AsyncClientStreamingCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options) => throw new NotSupportedException();
        public override AsyncDuplexStreamingCall<TRequest, TResponse> AsyncDuplexStreamingCall<TRequest, TResponse>(Method<TRequest, TResponse> method, string? host, CallOptions options) => throw new NotSupportedException();
    }

    private static void Con25ConnectorClient()
    {
        // Con25Cases.kt verifyRpcRecorder: the generated client binds each RPC to its exact path, types and unary kind before any I/O.
        var invoker = new CapturingInvoker();
        var client = new P.ConnectorService.ConnectorServiceClient(invoker);
        var meta = new F.RequestMeta();
        var id = new F.Id { Value = ByteString.CopyFrom(Convert.FromHexString("00112233445566778899aabbccddeeff")) };
        Action[] calls =
        [
            () => client.ListDefinitionsAsync(new P.ConnectorServiceListDefinitionsRequest { Meta = meta, Page = new F.PageRequest() }),
            () => client.ListConnectionsAsync(new P.ConnectorServiceListConnectionsRequest { Meta = meta, Page = new F.PageRequest() }),
            () => client.BeginConnectionAsync(new P.ConnectorServiceBeginConnectionRequest { Meta = meta, ConnectionId = id, DefinitionId = "github.oauth", Name = "n" }),
            () => client.CompleteConnectionAsync(new P.ConnectorServiceCompleteConnectionRequest { Meta = meta, FlowId = id, Proof = new P.ConnectorProof { CallbackReceipt = "r" } }),
            () => client.GetConnectionAsync(new P.ConnectorServiceGetConnectionRequest { Meta = meta, ConnectionId = id }),
            () => client.RevokeConnectionAsync(new P.ConnectorServiceRevokeConnectionRequest { Meta = meta, ConnectionId = id }),
        ];
        foreach (var call in calls) Throws<CapturedCall>(call, "CON.25 client: generated call reaches the recorder");
        string[] methods = ["ListDefinitions", "ListConnections", "BeginConnection", "CompleteConnection", "GetConnection", "RevokeConnection"];
        Require(invoker.Calls.Select(call => call.Path).SequenceEqual(methods.Select(method => "/arcforges.publicapi.v1.ConnectorService/" + method)), "CON.25 client: exact RPC paths");
        Require(invoker.Calls.All(call => call.Type == MethodType.Unary), "CON.25 client: unary RPCs");
        Require(invoker.Calls.Select(call => call.Request.Name).SequenceEqual(methods.Select(method => "ConnectorService" + method + "Request"))
            && invoker.Calls.Select(call => call.Response.Name).SequenceEqual(methods.Select(method => "ConnectorService" + method + "Response")), "CON.25 client: exact request and response types");

        // Con25Cases.kt verifyOutcomes: each closed outcome arm survives a round trip with only meta and that arm on the wire.
        var responseMeta = new F.ResponseMeta();
        var error = new F.ArcError();
        var encoded = new F.EncodedBodyRef();
        var page = new F.PageState { HasMore = false };
        var connection = new P.ConnectorConnection { ConnectionId = id, DefinitionId = "github.oauth", Name = "n", State = "connected", Scopes = { "a" }, Revision = new F.Revision { Value = 1 } };
        (IMessage Message, MessageParser Parser, int Arm)[] cases =
        [
            (new P.ConnectorServiceListDefinitionsResponse { Meta = responseMeta, Value = new P.ConnectorServiceListDefinitionsValue { Items = { new P.ConnectorDefinition() }, Page = page } }, P.ConnectorServiceListDefinitionsResponse.Parser, 2),
            (new P.ConnectorServiceListDefinitionsResponse { Meta = responseMeta, Error = error }, P.ConnectorServiceListDefinitionsResponse.Parser, 3),
            (new P.ConnectorServiceListDefinitionsResponse { Meta = responseMeta, EncodedBody = encoded }, P.ConnectorServiceListDefinitionsResponse.Parser, 4),
            (new P.ConnectorServiceListConnectionsResponse { Meta = responseMeta, Value = new P.ConnectorServiceListConnectionsValue { Items = { connection }, Page = page } }, P.ConnectorServiceListConnectionsResponse.Parser, 2),
            (new P.ConnectorServiceListConnectionsResponse { Meta = responseMeta, Error = error }, P.ConnectorServiceListConnectionsResponse.Parser, 3),
            (new P.ConnectorServiceListConnectionsResponse { Meta = responseMeta, EncodedBody = encoded }, P.ConnectorServiceListConnectionsResponse.Parser, 4),
            (new P.ConnectorServiceBeginConnectionResponse { Meta = responseMeta, Value = new P.ConnectorServiceBeginConnectionValue { Challenge = new P.ConnectorChallenge() } }, P.ConnectorServiceBeginConnectionResponse.Parser, 2),
            (new P.ConnectorServiceBeginConnectionResponse { Meta = responseMeta, Error = error }, P.ConnectorServiceBeginConnectionResponse.Parser, 3),
            (new P.ConnectorServiceCompleteConnectionResponse { Meta = responseMeta, Value = new P.ConnectorServiceCompleteConnectionValue { Connection = connection } }, P.ConnectorServiceCompleteConnectionResponse.Parser, 2),
            (new P.ConnectorServiceCompleteConnectionResponse { Meta = responseMeta, Error = error }, P.ConnectorServiceCompleteConnectionResponse.Parser, 3),
            (new P.ConnectorServiceGetConnectionResponse { Meta = responseMeta, Value = new P.ConnectorServiceGetConnectionValue { Connection = connection } }, P.ConnectorServiceGetConnectionResponse.Parser, 2),
            (new P.ConnectorServiceGetConnectionResponse { Meta = responseMeta, Error = error }, P.ConnectorServiceGetConnectionResponse.Parser, 3),
            (new P.ConnectorServiceGetConnectionResponse { Meta = responseMeta, EncodedBody = encoded }, P.ConnectorServiceGetConnectionResponse.Parser, 4),
            (new P.ConnectorServiceRevokeConnectionResponse { Meta = responseMeta, Value = new P.ConnectorServiceRevokeConnectionValue { Connection = connection } }, P.ConnectorServiceRevokeConnectionResponse.Parser, 2),
            (new P.ConnectorServiceRevokeConnectionResponse { Meta = responseMeta, Error = error }, P.ConnectorServiceRevokeConnectionResponse.Parser, 3),
        ];
        Require(cases.Length == 15, "CON.25 client: fifteen outcome cases");
        foreach (var (message, parser, arm) in cases)
        {
            var decoded = parser.ParseFrom(message.ToByteArray());
            Require(decoded.Equals(message), "CON.25 client: outcome round trip " + message.Descriptor.Name);
            var outcome = decoded.Descriptor.Oneofs.Single(oneof => oneof.Name == "outcome");
            Require(outcome.Accessor.GetCaseFieldDescriptor(decoded)?.FieldNumber == arm, "CON.25 client: selected outcome arm " + message.Descriptor.Name + " " + arm);
            Require(TopLevelTags(decoded.ToByteArray()).SequenceEqual([1, arm]), "CON.25 client: only meta and the selected arm are on the wire " + message.Descriptor.Name);
        }
    }

    private static void GeneratedClients(string root)
    {
        // Con11ApplicationStreamsCases.kt verifyPublicRpcCalls: each generated client method reaches the transport with its exact
        // path, request and response types and call kind, before any I/O.
        using var fixture = Load(root, "fixtures/public/con-11-application-streams.json");
        var invoker = new CapturingInvoker();
        var application = new P.ApplicationService.ApplicationServiceClient(invoker);
        var history = new P.HistoryService.HistoryServiceClient(invoker);
        var execution = new E.ExecutionService.ExecutionServiceClient(invoker);
        var events = new E.EventService.EventServiceClient(invoker);
        var calls = new Dictionary<string, Action>(StringComparer.Ordinal)
        {
            ["application.list"] = () => application.ListAsync(new P.ApplicationServiceListRequest()),
            ["application.heartbeat"] = () => application.HeartbeatAsync(new P.ApplicationServiceHeartbeatRequest()),
            ["application.disconnect"] = () => application.DisconnectAsync(new P.ApplicationServiceDisconnectRequest()),
            ["history.beginImport"] = () => history.BeginImportAsync(new P.HistoryServiceBeginImportRequest()),
            ["history.finalizeImport"] = () => history.FinalizeImportAsync(new P.HistoryServiceFinalizeImportRequest()),
            ["history.getImport"] = () => history.GetImportAsync(new P.HistoryServiceGetImportRequest()),
            ["history.cancelImport"] = () => history.CancelImportAsync(new P.HistoryServiceCancelImportRequest()),
            ["execution.startTransientTurn"] = () => execution.StartTransientTurnAsync(new E.ExecutionServiceStartTransientTurnRequest()),
            ["execution.readOutput"] = () => execution.ReadOutputAsync(new E.ExecutionServiceReadOutputRequest()),
            ["execution.watchOutput"] = () => execution.WatchOutput(new E.ExecutionServiceWatchOutputRequest()),
            ["execution.acknowledgeOutput"] = () => execution.AcknowledgeOutputAsync(new E.ExecutionServiceAcknowledgeOutputRequest()),
            ["execution.purgeTransient"] = () => execution.PurgeTransientAsync(new E.ExecutionServicePurgeTransientRequest()),
            ["events.poll"] = () => events.PollAsync(new E.EventServicePollRequest()),
            ["events.watch"] = () => events.Watch(new E.EventServiceWatchRequest()),
        };
        var vectors = fixture.RootElement.GetProperty("rpcVectors").EnumerateArray().ToArray();
        Require(vectors.Length == 14 && calls.Count == 14, "CON.11 client: exactly the 14 public RPCs");
        foreach (var vector in vectors)
        {
            var id = vector.GetProperty("id").GetString()!;
            var before = invoker.Calls.Count;
            Throws<CapturedCall>(calls[id], "CON.11 client: generated call reaches the transport " + id);
            Require(invoker.Calls.Count == before + 1, "CON.11 client: one call captured for " + id);
            var captured = invoker.Calls[^1];
            var streaming = vector.GetProperty("streamType").GetString() switch
            {
                "unary" => false,
                "serverStreaming" => true,
                var other => throw new InvalidOperationException("CON.11 client: unknown stream type " + other),
            };
            Require(captured.Kind == (streaming ? "serverStream" : "unary") && captured.Type == (streaming ? MethodType.ServerStreaming : MethodType.Unary),
                "CON.11 client: call kind for " + id);
            Require(captured.Path == "/" + vector.GetProperty("service").GetString() + "/" + vector.GetProperty("method").GetString(), "CON.11 client: method path for " + id);
            Require(captured.Request.Name == vector.GetProperty("input").GetString() && captured.Response.Name == vector.GetProperty("output").GetString()!.Split('.')[^1],
                "CON.11 client: request and response types for " + id);
        }
        Require(invoker.Calls.Count == 14, "CON.11 client: all 14 generated client methods invoked once");

        // Con24ScopeLibraryCases.kt: Scope client binding, request wire tags and closed outcome arms.
        Require(P.ScopeServiceListProjectsRequest.MetaFieldNumber == 1 && P.ScopeServiceListProjectsRequest.PageFieldNumber == 10
            && P.ScopeServiceListSessionsRequest.ProjectIdFieldNumber == 10 && P.ScopeServiceListSessionsRequest.PageFieldNumber == 11
            && P.ScopeServiceGetSessionRequest.SessionIdFieldNumber == 10 && P.ScopeServiceGetSessionRequest.MinRevisionFieldNumber == 11
            && P.ScopeServiceGetSessionValue.SessionFieldNumber == 10 && P.ScopeServiceGetSessionValue.RevisionFieldNumber == 11 && P.ScopeServiceGetSessionValue.CommittedAtFieldNumber == 12
            && P.ScopeServiceGetSessionResponse.EncodedBodyFieldNumber == 4, "CON.24 client: generated field-number constants");
        using var scopeFixture = Load(root, "fixtures/public/con-24-scope-library.json");
        var sessionVector = scopeFixture.RootElement.GetProperty("vectors").EnumerateArray()
            .Single(vector => vector.GetProperty("id").GetString() == "sessions-count-findings-and-reports-from-committed-owner-filtered-aggregate").GetProperty("expectedItems")[0];
        var sessionId = new F.Id { Value = ByteString.CopyFrom(Convert.FromHexString(sessionVector.GetProperty("sessionIdHex").GetString()!)) };
        var projectId = new F.Id { Value = ByteString.CopyFrom(Convert.FromHexString(sessionVector.GetProperty("projectIdHex").GetString()!)) };
        var revision = new F.Revision { Value = long.Parse(sessionVector.GetProperty("revision").ToString(), CultureInfo.InvariantCulture) };
        var projectsRequest = new P.ScopeServiceListProjectsRequest { Meta = new F.RequestMeta(), Page = new F.PageRequest() };
        var sessionsRequest = new P.ScopeServiceListSessionsRequest { Meta = new F.RequestMeta(), ProjectId = projectId, Page = new F.PageRequest() };
        var getSessionRequest = new P.ScopeServiceGetSessionRequest { Meta = new F.RequestMeta(), SessionId = sessionId, MinRevision = revision };
        Require(TopLevelTags(projectsRequest.ToByteArray()).SequenceEqual([1, 10]) && TopLevelTags(sessionsRequest.ToByteArray()).SequenceEqual([1, 10, 11])
            && TopLevelTags(getSessionRequest.ToByteArray()).SequenceEqual([1, 10, 11]), "CON.24 client: request wire tags");
        Require(P.ScopeServiceGetSessionRequest.Parser.ParseFrom(getSessionRequest.ToByteArray()).MinRevision.Equals(revision), "CON.24 client: minRevision round trip");
        var scope = new P.ScopeService.ScopeServiceClient(invoker);
        var start = invoker.Calls.Count;
        Throws<CapturedCall>(() => scope.ListProjectsAsync(projectsRequest), "CON.24 client: ListProjects reaches the transport");
        Throws<CapturedCall>(() => scope.ListSessionsAsync(sessionsRequest), "CON.24 client: ListSessions reaches the transport");
        Throws<CapturedCall>(() => scope.GetSessionAsync(getSessionRequest), "CON.24 client: GetSession reaches the transport");
        var scopeCalls = invoker.Calls.Skip(start).ToArray();
        string[] scopeMethods = ["ListProjects", "ListSessions", "GetSession"];
        Require(scopeCalls.Select(call => call.Path).SequenceEqual(scopeMethods.Select(method => "/arcforges.publicapi.v1.ScopeService/" + method))
            && scopeCalls.All(call => call.Type == MethodType.Unary && call.Kind == "unary")
            && scopeCalls.Select(call => call.Request.Name).SequenceEqual(scopeMethods.Select(method => "ScopeService" + method + "Request"))
            && scopeCalls.Select(call => call.Response.Name).SequenceEqual(scopeMethods.Select(method => "ScopeService" + method + "Response")), "CON.24 client: exact Scope bindings");
        var errorResponse = P.ScopeServiceGetSessionResponse.Parser.ParseFrom(new P.ScopeServiceGetSessionResponse { Error = new F.ArcError() }.ToByteArray());
        var encodedResponse = P.ScopeServiceGetSessionResponse.Parser.ParseFrom(new P.ScopeServiceGetSessionResponse { EncodedBody = new F.EncodedBodyRef() }.ToByteArray());
        var valueResponse = P.ScopeServiceGetSessionResponse.Parser.ParseFrom(new P.ScopeServiceGetSessionResponse
        {
            Meta = new F.ResponseMeta(),
            Value = new P.ScopeServiceGetSessionValue { Session = new P.ScopeMetadata(), Revision = revision, CommittedAt = new F.Instant { UnixSeconds = 1, Nanos = 0 } },
        }.ToByteArray());
        Require(errorResponse.OutcomeCase == P.ScopeServiceGetSessionResponse.OutcomeOneofCase.Error
            && encodedResponse.OutcomeCase == P.ScopeServiceGetSessionResponse.OutcomeOneofCase.EncodedBody
            && valueResponse.OutcomeCase == P.ScopeServiceGetSessionResponse.OutcomeOneofCase.Value && valueResponse.Value.Revision.Equals(revision), "CON.24 client: closed outcome arms");

        // SimulationCases.kt: the generated simulation client exposes exactly the 13 fixture operations.
        using var simulation = Load(root, "fixtures/public/con-21-simulation.json");
        var operations = simulation.RootElement.GetProperty("operations").EnumerateArray().Select(item => item.GetProperty("method").GetString()!).ToArray();
        Require(operations.Length == simulation.RootElement.GetProperty("operationCount").GetInt32() && operations.Length == 13, "simulation client: thirteen operations");
        Require(ClientMethods(typeof(Sim.SimulationService.SimulationServiceClient), Sim.SimulationService.Descriptor) == 13
            && Sim.SimulationService.Descriptor.Methods.Select(method => method.Name).SequenceEqual(operations, StringComparer.Ordinal), "simulation client: generated client methods");
    }

    // --------------------------------------------------------------------------------- con-25-af-segment.test.mjs

    private static void AfSegment(string root)
    {
        using var document = Load(root, "fixtures/public/con-25-af-segment.json");
        var fixture = document.RootElement;
        var vectors = fixture.GetProperty("vectors").EnumerateArray().ToDictionary(vector => vector.GetProperty("id").GetString()!, vector => vector.GetProperty("canonicalJson").GetString()!, StringComparer.Ordinal);
        var refusals = fixture.GetProperty("refusals").EnumerateArray().ToDictionary(refusal => refusal.GetProperty("id").GetString()!, refusal => refusal.GetProperty("canonicalJson").GetString()!, StringComparer.Ordinal);
        Require(vectors.Values.Distinct(StringComparer.Ordinal).Count() == 7, "af-segment: seven distinct golden texts");
        Require(fixture.GetProperty("refusals").EnumerateArray().All(refusal => refusal.GetProperty("reason").ValueKind == JsonValueKind.String), "af-segment: every refusal states its reason");

        // The independent C# oracle accepts every golden text, refuses every refusal text, and re-emits golden texts byte for byte.
        foreach (var (id, golden) in vectors)
        {
            Require(AfAccepts(golden), "af-segment: golden text accepted " + id);
            Require(AfEmit(AfParse(golden), default) == golden, "af-segment: parse tree re-emits the golden text " + id);
            Require(golden[0] == '{' && Encoding.UTF8.GetByteCount(golden) == fixture.GetProperty("vectors").EnumerateArray().Single(vector => vector.GetProperty("id").GetString() == id).GetProperty("utf8Bytes").GetInt32(),
                "af-segment: no byte order mark and exact UTF-8 length " + id);
        }
        foreach (var (id, refused) in refusals)
        {
            Require(!AfAccepts(refused), "af-segment: refusal refused " + id);
            Require(!vectors.ContainsValue(refused), "af-segment: refusal is not a golden text " + id);
        }

        // Reader discrimination: without the byte comparison only the lexical-only refusals slip through.
        var slipped = refusals.Where(pair => AfAccepts(pair.Value, skipReencode: true)).Select(pair => pair.Key).Order(StringComparer.Ordinal).ToArray();
        Require(slipped.SequenceEqual(new[] { "refuse-insignificant-whitespace", "refuse-non-minimal-escape", "refuse-uppercase-escape-digits" }.Order(StringComparer.Ordinal), StringComparer.Ordinal),
            "af-segment: the re-encode comparison is load bearing for exactly the lexical-only refusals: " + string.Join(",", slipped));
        Require(vectors.Values.Any(text => !AfAccepts(text, options: new AfEmitOptions(NoSort: true))), "af-segment: an unsorted encoder makes the comparison refuse a golden text");
        Require(!AfAccepts(refusals["refuse-insignificant-whitespace"]) && AfAccepts(refusals["refuse-insignificant-whitespace"], skipReencode: true),
            "af-segment: the whitespace text is refused only by the comparison");

        // Flipping a refusal to canonical form makes it accepted (and it is then a golden text).
        var repairs = new Dictionary<string, Func<string, string>>(StringComparer.Ordinal)
        {
            ["refuse-uppercase-uuid"] = text => Regex.Replace(text, "[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}", match => match.Value.ToLowerInvariant()),
            ["refuse-uppercase-hex-double"] = text => Regex.Replace(text, "\"(?:numeric|number)\":\"([0-9A-F]{16})\"", match => match.Value.ToLowerInvariant()),
            ["refuse-uppercase-escape-digits"] = text => Regex.Replace(text, @"\\u00[0-9A-F]{2}", match => match.Value.ToLowerInvariant()),
            ["refuse-insignificant-whitespace"] = RemoveSpaceOutsideStrings,
            ["refuse-unsorted-members"] = text => text.Replace("{\"events\":[],\"encodingProfile\":\"af-segment.v1\",", "{\"encodingProfile\":\"af-segment.v1\",\"events\":[],", StringComparison.Ordinal),
            ["refuse-wrong-encoding-profile"] = text => text.Replace("af-segment.v2", "af-segment.v1", StringComparison.Ordinal),
            ["refuse-wrong-execution-profile"] = text => text.Replace("af-sim.v2", "af-sim.v1", StringComparison.Ordinal),
            ["refuse-duplicate-member"] = text => text.Replace("\"gaps\":[],\"gaps\":[],", "\"gaps\":[],", StringComparison.Ordinal),
            ["refuse-unknown-member"] = text => text.Replace("\"zzz\":\"1\",", "", StringComparison.Ordinal),
            ["refuse-missing-empty-repeated"] = text => text.Replace("\"executionProfile\":\"af-sim.v1\",", "\"executionProfile\":\"af-sim.v1\",\"gaps\":[],", StringComparison.Ordinal),
            ["refuse-null-for-absent-optional"] = text => text.Replace("\"duration\":null,", "", StringComparison.Ordinal),
            ["refuse-leading-zero-uint64"] = text => new Regex("\"(0)(\\d+)\"").Replace(text, "\"$2\"", 1),
        };
        foreach (var (id, repair) in repairs)
        {
            var published = refusals[id];
            var fixedText = repair(published);
            Require(!AfAccepts(published) && fixedText != published && AfAccepts(fixedText) && vectors.ContainsValue(fixedText), "af-segment: repaired refusal is accepted " + id);
        }
        Require(repairs.Count == 12, "af-segment: twelve lexical repairs");
        // As in the TypeScript case: drop the first ",digital" arm, then the first "digital," arm.
        var twoArms = new Regex("\"digital\":(true|false),").Replace(new Regex(",\"digital\":(true|false)").Replace(refusals["refuse-two-oneof-arms"], "", 1), "", 1);
        Require(!AfAccepts(refusals["refuse-two-oneof-arms"]) && AfAccepts(twoArms) && vectors.ContainsValue(twoArms), "af-segment: the oneof pair repaired structurally is accepted");

        // The strict parser refuses non-canonical JSON on its own.
        Throws<AfRefused>(() => AfParse("{\"a\":\"1\",\"a\":\"2\"}"), "af-segment parser: duplicate member");
        Require(AfParse("{\"a\":\"1\",\"a\":\"2\"}", allowDuplicates: true).Members.Count == 2, "af-segment parser: duplicates tolerated only on request");
        foreach (var bad in new[] { "\uFEFF{}", "{}x", "{'a':1}", "{\"a\":01}", "{\"a\":NaN}", "{\"a\":\"\\ud800\"}", "{\"a\":\"\\x\"}", "{\"a\":\"\u0001\"}", "{\"a\":\"x}", "{\"a\":[1,]}" })
            Throws<AfRefused>(() => AfParse(bad), "af-segment parser refuses " + bad);
        AfParse("{} ");
        Require(!AfAccepts("{} "), "af-segment: trailing whitespace is refused by the byte comparison");
        var empty = vectors["empty-segment-keeps-every-ordered-repeated-field"];
        Require(AfAccepts(empty), "af-segment: empty segment accepted");
        foreach (var replacement in new[] { "\"startTick\":0", "\"startTick\":null", "\"startTick\":\"+0\"", "\"startTick\":\"-0\"", "\"startTick\":\"18446744073709551616\"" })
            Require(!AfAccepts(empty.Replace("\"startTick\":\"0\"", replacement, StringComparison.Ordinal)), "af-segment: refused startTick " + replacement);
        Require(!AfAccepts(empty.Replace("\"events\":[]", "\"events\":{}", StringComparison.Ordinal)), "af-segment: refused object for a repeated member");
        var numeric = vectors["duplicate-delivery-differs-only-by-ordinal-and-fault-marker"];
        Require(AfAccepts(numeric), "af-segment: numeric segment accepted");
        foreach (var word in new[] { "7ff8000000000000", "fff0000000000000", "7ff0000000000001" })
            Require(!AfAccepts(numeric.Replace("400a000000000000", word, StringComparison.Ordinal)), "af-segment: nonfinite bit word refused " + word);

        // Encoder mutations are caught by the golden bytes, and the faithful emission matches every golden text.
        foreach (var (name, options) in new[] { ("members left unsorted", new AfEmitOptions(NoSort: true)), ("double printed as decimal text", new AfEmitOptions(DoubleToString: true)),
            ("non-ASCII escaped", new AfEmitOptions(EscapeNonAscii: true)), ("empty repeated members omitted", new AfEmitOptions(OmitEmpty: true)) })
        {
            Require(vectors.Values.Any(text => AfEmit(AfParse(text), options) != text), "af-segment: golden bytes catch the mutation " + name);
            Require(vectors.Values.All(text => AfEmit(AfParse(text), default) == text), "af-segment: faithful emission after " + name);
        }
        var binary = vectors["binary64-bit-words-preserve-sign-and-extremes"];
        Require(binary.Contains("\"numeric\":\"8000000000000000\"", StringComparison.Ordinal) && binary.Contains("\"numeric\":\"0000000000000001\"", StringComparison.Ordinal)
            && binary.Contains("\"numeric\":\"7fefffffffffffff\"", StringComparison.Ordinal), "af-segment: binary64 bit words in the golden text");
        Require(double.IsNegative(BitConverter.Int64BitsToDouble(unchecked((long)0x8000000000000000UL))) && BitConverter.Int64BitsToDouble(1) == 5e-324, "af-segment: bit words decode to -0 and the smallest subnormal");
        // A signed zero collapsed to +0 is a different, still well-formed text: the faithful encoder never conflates them.
        var collapsed = binary.Replace("\"numeric\":\"8000000000000000\"", "\"numeric\":\"0000000000000000\"", StringComparison.Ordinal);
        Require(collapsed != binary && AfAccepts(collapsed) && AfEmit(AfParse(collapsed), default) != binary, "af-segment: a signed zero collapsed to +0 is caught by the golden bytes");
        Require(vectors["gap-and-fault-markers-with-and-without-channel"].Contains("\"digital\":false", StringComparison.Ordinal), "af-segment: explicit digital false is a selected arm");
        Require(empty == "{\"encodingProfile\":\"af-segment.v1\",\"events\":[],\"executionProfile\":\"af-sim.v1\",\"gaps\":[],\"records\":[],\"startTick\":\"0\",\"tickCount\":\"0\"}",
            "af-segment: exact empty segment text");
        var unicode = vectors["text-metadata-escapes-and-unicode"];
        Require(unicode.Contains("\\u0001\\u001b\u007fé中😀", StringComparison.Ordinal) && unicode.Contains("\\\"b\\\\c\\n\\t", StringComparison.Ordinal)
            && Encoding.UTF8.GetByteCount(unicode) > unicode.Length, "af-segment: minimal escapes and literal multi-byte UTF-8");
        var gapsText = vectors["gap-and-fault-markers-with-and-without-channel"];
        var noArm = new Regex("\"digital\":false,").Replace(gapsText, "", 1);
        Require(noArm != gapsText && !AfAccepts(noArm), "af-segment: a digital false that lost its arm is not representable");
        var resourceArm = new Regex("\"value\":\\{\"(boolean|decimal|instant|integer|number|text)\":").Replace(vectors["numeric-digital-and-event-samples-in-delivered-order"], "\"value\":{\"resource\":{},\"$1\":", 1);
        Require(resourceArm != vectors["numeric-digital-and-event-samples-in-delivered-order"] && !AfAccepts(resourceArm), "af-segment: the resource scalar arm is not representable");
        Throws<AfRefused>(() => AfEmit(new AfNode { Kind = AfKind.String, Text = "\ud800" }, default), "af-segment: the encoder refuses an unpaired surrogate");

        // The generated validator rejects invalid built messages (built from the strict reading of a golden text).
        var baseSegment = AfModel(AfParse(vectors["gap-and-fault-markers-with-and-without-channel"]));
        Require(Shapes.IsValid(baseSegment), "af-segment model: unmodified message is valid");
        Require(Sim.SimulationDataSegment.Parser.ParseFrom(baseSegment.ToByteArray()).Equals(baseSegment), "af-segment model: protobuf round trip");
        bool Mutated(Action<Sim.SimulationDataSegment> change) { var copy = baseSegment.Clone(); change(copy); return Shapes.IsValid(copy); }
        Require(!Mutated(m => m.Gaps[0].Kind = "explode"), "af-segment model: unknown gap kind");
        Require(Mutated(m => m.Gaps[0].Kind = "drop"), "af-segment model: known gap kind");
        Require(!Mutated(m => m.EncodingProfile = "af-segment.v2"), "af-segment model: wrong encoding profile");
        Require(!Mutated(m => m.ExecutionProfile = "af-sim.v2"), "af-segment model: wrong execution profile");
        Require(!Mutated(m => m.Records[0].ChannelId = new F.Id { Value = ByteString.CopyFrom(new byte[16]) }), "af-segment model: zero Id");
        Require(!Mutated(m => m.Records[0].ClearValue()), "af-segment model: missing oneof arm");
        Require(!Mutated(m => m.Records[0].Numeric = double.NaN), "af-segment model: NaN numeric");
        Require(!Mutated(m => m.Records[0].Numeric = double.PositiveInfinity), "af-segment model: infinite numeric");
        Require(!Mutated(m => m.ClearStartTick()), "af-segment model: missing startTick");
        Require(!Mutated(m => m.Events[0].Kind = ""), "af-segment model: empty event kind");
        Require(!Mutated(m => m.Gaps[0].FaultId = null), "af-segment model: gap without faultId");
        Require(!Mutated(m => m.Records[0].ClearDeliveredOrdinal()), "af-segment model: missing ordinal");
        var emptySegment = AfModel(AfParse(empty));
        var emptyRound = Sim.SimulationDataSegment.Parser.ParseFrom(emptySegment.ToByteArray());
        Require(emptyRound.HasStartTick && emptyRound.StartTick == 0 && emptyRound.Records.Count == 0 && emptyRound.Events.Count == 0 && emptyRound.Gaps.Count == 0,
            "af-segment model: explicit zero startTick keeps presence");
        var binaryRound = Sim.SimulationDataSegment.Parser.ParseFrom(AfModel(AfParse(binary)).ToByteArray());
        Require(double.IsNegative(binaryRound.Records[0].Numeric) && binaryRound.Records[0].Numeric == 0 && binaryRound.Records[2].Numeric == 5e-324,
            "af-segment model: negative zero and subnormal survive protobuf bytes");
        var gaps = Sim.SimulationDataSegment.Parser.ParseFrom(baseSegment.ToByteArray());
        Require(gaps.Records[0].ValueCase == Sim.SimulationSample.ValueOneofCase.Digital && !gaps.Records[0].Digital, "af-segment model: explicit digital false arm survives");
        Require(gaps.Gaps[1].ChannelId is null && gaps.Events[0].Duration is null, "af-segment model: absent optional members stay absent");
        var integral = AfModel(AfParse(vectors["integral-extremes-use-exact-strings"]));
        Require(integral.Records[1].Tick == ulong.MaxValue && integral.Records[0].Time.Ticks == long.MinValue && integral.Records[1].Time.Ticks == long.MaxValue,
            "af-segment model: integral extremes stay exact");
        var metadataText = AfModel(AfParse(unicode)).Events[0].Fields[0].Value.Text;
        Require(metadataText == "a\"b\\c\n\t\u0001\u001b\u007fé中😀", "af-segment model: text metadata escapes and Unicode");
    }

    private static string RemoveSpaceOutsideStrings(string text)
    {
        var output = new StringBuilder(text.Length);
        var inString = false;
        for (var index = 0; index < text.Length; index++)
        {
            var c = text[index];
            if (inString)
            {
                output.Append(c);
                if (c == '\\') output.Append(text[++index]);
                else if (c == '"') inString = false;
            }
            else if (c == '"') { inString = true; output.Append(c); }
            else if (c != ' ') output.Append(c);
        }
        return output.ToString();
    }

    // --------------------------------------------------------------------------------- semantic-hash.test.mjs

    private static void SemanticHash()
    {
        var empty = new HashSet<string>(StringComparer.Ordinal);
        Require(Refused(() => ArcForges.Contracts.Foundation.CanonicalSemanticHash.Canonicalize("{\"schemaVersion\":\"example.v1\",\"value\":\"" + '\ud800' + "\"}", empty)),
            "semantic hash: a raw unpaired surrogate is refused");
        Require(Refused(() => ArcForges.Contracts.Foundation.CanonicalSemanticHash.Canonicalize("{\"schemaVersion\":\"example.v1\",\"value\":" + new string('[', 33) + "null" + new string(']', 33) + "}", empty)),
            "semantic hash: nesting beyond the depth bound is refused");
    }

    private static bool Refused(Action action)
    {
        try { action(); return false; }
        catch (Exception exception) when (exception is ArgumentException or JsonException or InvalidOperationException or FormatException) { return true; }
    }

    // ---------------------------------------------------------------------------------------- support.test.mjs

    private static void Support(string root)
    {
        using var fixture = Load(root, "fixtures/public/con-22-account-support.json");
        foreach (var item in fixture.RootElement.GetProperty("cases").EnumerateArray())
        {
            if (!item.GetProperty("valid").GetBoolean()) continue;
            var id = item.GetProperty("id").GetString()!;
            var json = item.GetProperty("value").GetRawText();
            var ok = item.GetProperty("target").GetString() switch
            {
                "SupportCase" => Shapes.IsValid(P.SupportCase.Parser.ParseFrom(JsonParser.Default.Parse<P.SupportCase>(json).ToByteArray())),
                "SupportMessage" => Shapes.IsValid(P.SupportMessage.Parser.ParseFrom(JsonParser.Default.Parse<P.SupportMessage>(json).ToByteArray())),
                "NotificationView" => Shapes.IsValid(P.NotificationView.Parser.ParseFrom(JsonParser.Default.Parse<P.NotificationView>(json).ToByteArray())),
                "PolicyBundle" => Shapes.IsValid(P.PolicyBundle.Parser.ParseFrom(JsonParser.Default.Parse<P.PolicyBundle>(json).ToByteArray())),
                var target => throw new InvalidOperationException("CON.22 unknown target " + target),
            };
            Require(ok, "CON.22: " + id + " binary round trip stays valid");
        }
        var id16 = new F.Id { Value = ByteString.CopyFrom(Convert.FromHexString("112233445566478899aabbccddeeff00")) };
        P.NotificationView Notice(string kind) => new()
        {
            NotificationId = id16, Kind = kind, Durability = "durable", MessageKey = "future.message-key", State = "unread",
            CreatedAt = new F.Instant { UnixSeconds = 1, Nanos = 0 },
        };
        Require(Shapes.IsValid(Notice("future.notification-kind")), "CON.22: forward-compatible notification kind accepted");
        Require(!Shapes.IsValid(Notice("bad key")), "CON.22: notification kind enforces Key syntax");
        var missingTime = Notice("notice.kind"); missingTime.CreatedAt = null;
        Require(!Shapes.IsValid(missingTime), "CON.22: notification createdAt presence");
        var forward = new P.SupportMessage { MessageId = id16, ActorKind = "future.actor-kind", Text = "explicit support text", CreatedAt = new F.Instant { UnixSeconds = 1, Nanos = 0 } };
        Require(Shapes.IsValid(forward), "CON.22: forward-compatible actor kind with explicit text");
    }

    // --------------------------------------------------------------------------------- operator-contract.test.mjs

    private static void OperatorVisibility()
    {
        const string service = "arcforges.operator.v1.OperatorService";
        IReadOnlyList<ServiceDescriptor>[] publicCatalogues = [ArcForges.Contracts.PublicApi.ContractServices.All, ArcForges.Contracts.Events.ContractServices.All,
            ArcForges.Sdk.Contracts.ContractServices.All];
        Require(publicCatalogues.SelectMany(catalogue => catalogue).All(candidate => candidate.FullName != service), "operator: no public C# catalogue lists OperatorService");
        Require(ArcForges.Contracts.CloudInternal.ContractServices.All.Any(candidate => candidate.FullName == service), "operator: the internal CloudInternal catalogue owns OperatorService");
        foreach (var type in new[] { typeof(Op.OperatorService), typeof(Op.OperatorCallContext), typeof(Op.OperatorProposalRef) })
            Require(type.Assembly.GetName().Name == "ArcForges.Contracts.CloudInternal", "operator: " + type.Name + " is internal-package only");
        FileDescriptor[] publicFiles = [F.FoundationReflection.Descriptor, P.ContentReflection.Descriptor, P.ChatReflection.Descriptor, P.ConnectorReflection.Descriptor,
            P.IdentityReflection.Descriptor, P.ApplicationReflection.Descriptor, E.EventsReflection.Descriptor, Sim.SimulationReflection.Descriptor];
        Require(publicFiles.All(file => file.Package != Op.OperatorReflection.Descriptor.Package && file.Dependencies.All(dependency => dependency.Package != Op.OperatorReflection.Descriptor.Package)),
            "operator: no public schema defines or imports the operator package");
        Require(Op.OperatorReflection.Descriptor.MessageTypes.Any(message => message.Name == "OperatorCallContext")
            && Op.OperatorReflection.Descriptor.MessageTypes.Any(message => message.Name == "OperatorProposalRef"), "operator: operator records stay in the internal package");

        // AdjustCredit delta is sint64 ZigZag on the wire: ZigZag(-1) = 1; an int64 encoding would be a 10-byte varint.
        Require(Op.OperatorAdjustCreditInput.Descriptor.FindFieldByNumber(2) is { FieldType: FieldType.SInt64 }, "operator: AdjustCredit delta is sint64");
        var adjust = JsonParser.Default.Parse<Op.OperatorAdjustCreditInput>("{\"deltaMicro\":\"-1\"}");
        Require(adjust.ToByteArray().SequenceEqual(new byte[] { 0x10, 0x01 }) && Op.OperatorAdjustCreditInput.Parser.ParseFrom(new byte[] { 0x10, 0x01 }).DeltaMicro == -1,
            "operator: AdjustCredit delta ZigZag wire bytes");
    }

    // ------------------------------------------------------------------------------------- simulation.test.mjs

    private static void SimulationCatalogue(string root)
    {
        using var fixture = Load(root, "fixtures/public/con-21-simulation.json");
        var name = fixture.RootElement.GetProperty("service").GetString()!;
        var service = ArcForges.Contracts.PublicApi.ContractServices.All.SingleOrDefault(candidate => candidate.FullName == name);
        Require(service is not null, "simulation: SimulationService is registered in the generated C# package catalogue");
        Require(service!.Methods.Select(method => method.Name).SequenceEqual(fixture.RootElement.GetProperty("operations").EnumerateArray().Select(item => item.GetProperty("method").GetString()!)),
            "simulation: catalogue methods equal the fixture operations");
    }

    // ------------------------------------------------------------------------------ eng/policy/con-40-test-map.json

    private static void TestMap(string root)
    {
        // The map is load bearing: every C# anchor must exist, and every test() title of a TypeScript file that is still
        // present must be mapped. Removed TypeScript and Kotlin files keep their rows as migration evidence.
        using var document = Load(root, "eng/policy/con-40-test-map.json");
        var map = document.RootElement;
        Require(map.GetProperty("schemaVersion").GetString() == "con-40-test-map.v1" && map.GetProperty("task").GetString() == "CON.40", "test map: identity");
        var mapped = new HashSet<(string, string)>();
        var anchors = 0;
        foreach (var entry in map.GetProperty("cases").EnumerateArray())
        {
            var source = entry.GetProperty("source").GetString()!;
            var name = entry.GetProperty("case").GetString()!;
            Require(source.StartsWith("tests/public/", StringComparison.Ordinal) && mapped.Add((source, name)), "test map: unique case " + source + " " + name);
            var csharp = entry.GetProperty("csharp").EnumerateArray().Select(anchor => anchor.GetString()!).ToArray();
            Require(csharp.Length > 0 || entry.TryGetProperty("node", out _), "test map: a C# case or the retained Node assertion for " + name);
            Require(entry.GetProperty("negativeFixtures").GetArrayLength() > 0, "test map: negative fixtures recorded for " + name);
            foreach (var anchor in csharp)
            {
                var separator = anchor.IndexOf('#', StringComparison.Ordinal);
                Require(separator > 0, "test map: anchor form " + anchor);
                var path = Path.Combine(root, anchor[..separator]);
                var token = anchor[(separator + 1)..];
                Require(File.Exists(path), "test map: anchor file " + anchor);
                var text = File.ReadAllText(path);
                var defined = Regex.IsMatch(token, "^[A-Z][A-Za-z0-9]*$") && anchor.StartsWith("tests/StructureTests/", StringComparison.Ordinal)
                    ? Regex.IsMatch(text, @"\b(?:void|bool)\s+" + token + @"\(")
                    : text.Contains(token, StringComparison.Ordinal);
                Require(defined, "test map: anchor target " + anchor);
                anchors++;
            }
        }
        var titles = new Regex(@"^\s*test\(\s*([""`])((?:\\.|(?!\1).)*)\1", RegexOptions.Multiline | RegexOptions.CultureInvariant, TimeSpan.FromSeconds(5));
        foreach (var file in Directory.EnumerateFiles(Path.Combine(root, "tests/public"), "*.mjs").Order(StringComparer.Ordinal))
        {
            var source = Path.GetRelativePath(root, file).Replace('\\', '/');
            if (source == "tests/public/ai-internal.test.mjs") continue;
            foreach (Match match in titles.Matches(File.ReadAllText(file)))
                Require(mapped.Contains((source, match.Groups[2].Value)), "test map: unmapped TypeScript case " + source + " " + match.Groups[2].Value);
        }
        Console.WriteLine($"CON.40 test map: {mapped.Count} retired TypeScript and Kotlin cases, {anchors} C# anchors verified.");
    }

    // ================================================================================================ shared helpers

    private static JsonDocument Load(string root, string path) => JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, path)));

    private static bool Same(JsonElement actual, string expectedJson) => JsonNode.DeepEquals(JsonNode.Parse(actual.GetRawText()), JsonNode.Parse(expectedJson));

    private static string ScopeBytes(string hex, string id)
    {
        Require(Regex.IsMatch(hex, "^(?:[0-9a-f]{2})+$"), id + ": expected lowercase even-length hex bytes");
        return Convert.ToBase64String(Convert.FromHexString(hex));
    }

    private static T CheckedRoundTrip<T>(T message, MessageParser<T> parser, Func<T, bool> validate, string id) where T : IMessage<T>
    {
        Require(validate(message), id + ": generated validator");
        var decoded = parser.ParseFrom(message.ToByteArray());
        Require(JsonFormatter.Default.Format(decoded) == JsonFormatter.Default.Format(message) && validate(decoded), id + ": semantic round trip");
        return decoded;
    }

    private static int[] TopLevelTags(byte[] bytes)
    {
        var input = new CodedInputStream(bytes);
        var tags = new List<int>();
        uint tag;
        while ((tag = input.ReadTag()) != 0)
        {
            tags.Add(WireFormat.GetTagFieldNumber(tag));
            input.SkipLastField();
        }
        return [.. tags];
    }

    private static JsonNode Expand(JsonNode node, JsonObject samples, HashSet<string>? stack = null)
    {
        stack ??= new HashSet<string>(StringComparer.Ordinal);
        if (node is JsonObject record && record.TryGetPropertyValue("$ref", out var reference))
        {
            var name = reference!.GetValue<string>();
            Require(record.Count == 1 && samples.ContainsKey(name) && stack.Add(name), "foundation: invalid or recursive fixture reference " + name);
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
                Require(parent is JsonObject obj && obj.Remove(key), "foundation: unknown fixture removal path");
            }
        }
        return value;
    }

    private static (JsonNode Parent, string Key) Parent(JsonNode node, string path)
    {
        var parts = path.Split('.');
        for (var index = 0; index < parts.Length - 1; index++)
            node = node is JsonArray array ? array[int.Parse(parts[index], CultureInfo.InvariantCulture)]! : node[parts[index]]!;
        return (node, parts[^1]);
    }

    private static void RefusesWith(Action action, ContractSerializationFailure failure, string message)
    {
        try { action(); }
        catch (ContractSerializationException error) when (error.Failure == failure) { return; }
        throw new InvalidOperationException("CON.40 parity failed: " + message);
    }

    private static void Throws<T>(Action action, string message) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new InvalidOperationException("CON.40 parity failed: " + message);
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException("CON.40 parity failed: " + message);
    }

    // ============================================================= independent protobuf encoder (replaces --exchange)

    /// <summary>
    /// A descriptor-driven proto3 binary encoder written only for this test. It reads protobuf JSON from the committed,
    /// independently authored fixtures and never calls generated serialization, so equality with the generated C# bytes
    /// is a second-implementation check, as the TypeScript exchange was.
    /// </summary>
    private static class ProtoWire
    {
        public static byte[] Encode(JsonNode? json, MessageDescriptor descriptor)
        {
            var output = new List<byte>();
            WriteMessage(output, json as JsonObject ?? throw new InvalidOperationException("ProtoWire: object expected for " + descriptor.FullName), descriptor);
            return [.. output];
        }

        private static void WriteMessage(List<byte> output, JsonObject json, MessageDescriptor descriptor)
        {
            foreach (var member in json)
                Require(descriptor.Fields.InDeclarationOrder().Any(field => field.JsonName == member.Key || field.Name == member.Key), "ProtoWire: unknown member " + descriptor.FullName + "." + member.Key);
            foreach (var field in descriptor.Fields.InFieldNumberOrder())
            {
                var value = json.TryGetPropertyValue(field.JsonName, out var byJson) ? byJson : json.TryGetPropertyValue(field.Name, out var byName) ? byName : null;
                if (value is null) continue;
                Require(!field.IsMap, "ProtoWire: map fields are not used by the foundation fixtures");
                if (field.IsRepeated)
                {
                    var items = value.AsArray();
                    if (items.Count == 0) continue;
                    if (field.IsPacked && field.FieldType is not (FieldType.String or FieldType.Bytes or FieldType.Message or FieldType.Group))
                    {
                        var payload = new List<byte>();
                        foreach (var item in items) WriteScalar(payload, field, item!);
                        Tag(output, field.FieldNumber, 2);
                        Varint(output, (ulong)payload.Count);
                        output.AddRange(payload);
                    }
                    else foreach (var item in items) WriteSingle(output, field, item!);
                    continue;
                }
                if (!field.HasPresence && IsDefault(field, value)) continue;
                WriteSingle(output, field, value);
            }
        }

        private static void WriteSingle(List<byte> output, FieldDescriptor field, JsonNode value)
        {
            switch (field.FieldType)
            {
                case FieldType.Message:
                    var inner = new List<byte>();
                    WriteMessage(inner, value.AsObject(), field.MessageType);
                    Tag(output, field.FieldNumber, 2);
                    Varint(output, (ulong)inner.Count);
                    output.AddRange(inner);
                    break;
                case FieldType.String:
                    var text = new UTF8Encoding(false, true).GetBytes(value.GetValue<string>());
                    Tag(output, field.FieldNumber, 2);
                    Varint(output, (ulong)text.Length);
                    output.AddRange(text);
                    break;
                case FieldType.Bytes:
                    var bytes = Base64(value.GetValue<string>());
                    Tag(output, field.FieldNumber, 2);
                    Varint(output, (ulong)bytes.Length);
                    output.AddRange(bytes);
                    break;
                default:
                    Tag(output, field.FieldNumber, field.FieldType switch
                    {
                        FieldType.Fixed64 or FieldType.SFixed64 or FieldType.Double => 1,
                        FieldType.Fixed32 or FieldType.SFixed32 or FieldType.Float => 5,
                        _ => 0,
                    });
                    WriteScalar(output, field, value);
                    break;
            }
        }

        private static void WriteScalar(List<byte> output, FieldDescriptor field, JsonNode value)
        {
            switch (field.FieldType)
            {
                case FieldType.Int32: Varint(output, unchecked((ulong)(long)checked((int)Integer(value)))); break;
                case FieldType.Int64: Varint(output, unchecked((ulong)checked((long)Integer(value)))); break;
                case FieldType.UInt32: Varint(output, checked((uint)Integer(value))); break;
                case FieldType.UInt64: Varint(output, checked((ulong)Integer(value))); break;
                case FieldType.SInt32: var s32 = checked((int)Integer(value)); Varint(output, unchecked((uint)((s32 << 1) ^ (s32 >> 31)))); break;
                case FieldType.SInt64: var s64 = checked((long)Integer(value)); Varint(output, unchecked((ulong)((s64 << 1) ^ (s64 >> 63)))); break;
                case FieldType.Bool: Varint(output, value.GetValue<bool>() ? 1UL : 0UL); break;
                case FieldType.Enum: Varint(output, unchecked((ulong)(long)EnumNumber(field, value))); break;
                case FieldType.Fixed32: output.AddRange(BitConverter.GetBytes(checked((uint)Integer(value)))); break;
                case FieldType.SFixed32: output.AddRange(BitConverter.GetBytes(checked((int)Integer(value)))); break;
                case FieldType.Fixed64: output.AddRange(BitConverter.GetBytes(checked((ulong)Integer(value)))); break;
                case FieldType.SFixed64: output.AddRange(BitConverter.GetBytes(checked((long)Integer(value)))); break;
                case FieldType.Float: output.AddRange(BitConverter.GetBytes((float)Floating(value))); break;
                case FieldType.Double: output.AddRange(BitConverter.GetBytes(Floating(value))); break;
                default: throw new InvalidOperationException("ProtoWire: unsupported scalar " + field.FieldType);
            }
        }

        private static bool IsDefault(FieldDescriptor field, JsonNode value) => field.FieldType switch
        {
            FieldType.String => value.GetValue<string>().Length == 0,
            FieldType.Bytes => Base64(value.GetValue<string>()).Length == 0,
            FieldType.Bool => !value.GetValue<bool>(),
            FieldType.Enum => EnumNumber(field, value) == 0,
            FieldType.Float or FieldType.Double => BitConverter.DoubleToInt64Bits(Floating(value)) == 0,
            FieldType.Message => false,
            _ => Integer(value) == 0,
        };

        private static System.Numerics.BigInteger Integer(JsonNode value)
        {
            var text = value.GetValueKind() == JsonValueKind.String ? value.GetValue<string>() : value.ToJsonString();
            Require(Regex.IsMatch(text, "^-?(0|[1-9][0-9]*)$"), "ProtoWire: integral JSON value expected: " + text);
            return System.Numerics.BigInteger.Parse(text, CultureInfo.InvariantCulture);
        }

        private static double Floating(JsonNode value)
        {
            if (value.GetValueKind() == JsonValueKind.String)
            {
                return value.GetValue<string>() switch
                {
                    "NaN" => double.NaN,
                    "Infinity" => double.PositiveInfinity,
                    "-Infinity" => double.NegativeInfinity,
                    var text => double.Parse(text, NumberStyles.Float, CultureInfo.InvariantCulture),
                };
            }
            return double.Parse(value.ToJsonString(), NumberStyles.Float, CultureInfo.InvariantCulture);
        }

        private static int EnumNumber(FieldDescriptor field, JsonNode value)
        {
            if (value.GetValueKind() == JsonValueKind.String)
                return field.EnumType.FindValueByName(value.GetValue<string>())?.Number ?? throw new InvalidOperationException("ProtoWire: unknown enum name " + value.GetValue<string>());
            return checked((int)Integer(value));
        }

        private static byte[] Base64(string text)
        {
            var standard = text.Replace('-', '+').Replace('_', '/');
            return Convert.FromBase64String(standard.PadRight((standard.Length + 3) / 4 * 4, '='));
        }

        private static void Tag(List<byte> output, int number, int wireType) => Varint(output, ((ulong)number << 3) | (uint)wireType);

        private static void Varint(List<byte> output, ulong value)
        {
            do
            {
                var low = (byte)(value & 0x7f);
                value >>= 7;
                output.Add(value != 0 ? (byte)(low | 0x80) : low);
            } while (value != 0);
        }
    }

    // ===================================================== independent af-segment.v1 canonical-text oracle (C# port)

    private sealed class AfRefused : Exception
    {
        public AfRefused(string code) : base("af-segment refused: " + code) => Code = code;
        public string Code { get; }
    }

    private enum AfKind { Object, Array, String, Number, True, False, Null }

    private sealed class AfNode
    {
        public AfKind Kind { get; init; }
        public string Text { get; init; } = "";
        public List<KeyValuePair<string, AfNode>> Members { get; } = [];
        public List<AfNode> Items { get; } = [];
    }

    private readonly record struct AfEmitOptions(bool NoSort = false, bool DoubleToString = false, bool EscapeNonAscii = false, bool OmitEmpty = false);

    private static bool AfAccepts(string text, bool skipReencode = false, AfEmitOptions options = default)
    {
        try
        {
            var tree = AfParse(text);
            AfValidateSegment(tree);
            if (!skipReencode && AfEmit(tree, options) != text) throw new AfRefused("form");
            return true;
        }
        catch (AfRefused) { return false; }
    }

    private static AfNode AfParse(string text, bool allowDuplicates = false)
    {
        if (text.Length > 0 && text[0] == '\uFEFF') throw new AfRefused("bom");
        byte[] bytes;
        try { bytes = new UTF8Encoding(false, true).GetBytes(text); }
        catch (EncoderFallbackException) { throw new AfRefused("surrogate"); }
        try
        {
            var reader = new Utf8JsonReader(bytes, new JsonReaderOptions { AllowTrailingCommas = false, CommentHandling = JsonCommentHandling.Disallow, MaxDepth = 64 });
            if (!reader.Read()) throw new AfRefused("json");
            var node = AfRead(ref reader, allowDuplicates);
            if (reader.Read()) throw new AfRefused("json");
            return node;
        }
        catch (JsonException) { throw new AfRefused("json"); }
        catch (InvalidOperationException) { throw new AfRefused("json"); }
    }

    private static AfNode AfRead(ref Utf8JsonReader reader, bool allowDuplicates)
    {
        switch (reader.TokenType)
        {
            case JsonTokenType.StartObject:
            {
                var node = new AfNode { Kind = AfKind.Object };
                var seen = new HashSet<string>(StringComparer.Ordinal);
                while (true)
                {
                    if (!reader.Read()) throw new AfRefused("json");
                    if (reader.TokenType == JsonTokenType.EndObject) return node;
                    var name = reader.GetString() ?? throw new AfRefused("json");
                    if (!seen.Add(name) && !allowDuplicates) throw new AfRefused("duplicate");
                    if (!reader.Read()) throw new AfRefused("json");
                    node.Members.Add(new KeyValuePair<string, AfNode>(name, AfRead(ref reader, allowDuplicates)));
                }
            }
            case JsonTokenType.StartArray:
            {
                var node = new AfNode { Kind = AfKind.Array };
                while (true)
                {
                    if (!reader.Read()) throw new AfRefused("json");
                    if (reader.TokenType == JsonTokenType.EndArray) return node;
                    node.Items.Add(AfRead(ref reader, allowDuplicates));
                }
            }
            case JsonTokenType.String: return new AfNode { Kind = AfKind.String, Text = reader.GetString() ?? throw new AfRefused("json") };
            case JsonTokenType.Number: return new AfNode { Kind = AfKind.Number, Text = Encoding.UTF8.GetString(reader.ValueSpan) };
            case JsonTokenType.True: return new AfNode { Kind = AfKind.True };
            case JsonTokenType.False: return new AfNode { Kind = AfKind.False };
            case JsonTokenType.Null: return new AfNode { Kind = AfKind.Null };
            default: throw new AfRefused("json");
        }
    }

    private static Dictionary<string, AfNode> AfMembers(AfNode node, string[] allowed, string[] required, string[]? oneof = null)
    {
        if (node.Kind != AfKind.Object) throw new AfRefused("type");
        if (node.Members.Any(member => !allowed.Contains(member.Key, StringComparer.Ordinal))) throw new AfRefused("member");
        var result = node.Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
        if (required.Any(name => !result.ContainsKey(name))) throw new AfRefused("member");
        if (oneof is not null && oneof.Count(result.ContainsKey) != 1) throw new AfRefused("oneof");
        for (var index = 1; index < node.Members.Count; index++)
            if (string.CompareOrdinal(node.Members[index - 1].Key, node.Members[index].Key) >= 0) throw new AfRefused("order");
        return result;
    }

    private static void AfValidateSegment(AfNode root)
    {
        string[] names = ["encodingProfile", "events", "executionProfile", "gaps", "records", "startTick", "tickCount"];
        var m = AfMembers(root, names, names);
        if (AfString(m["encodingProfile"]) != "af-segment.v1" || AfString(m["executionProfile"]) != "af-sim.v1") throw new AfRefused("profile");
        AfU64(m["startTick"]);
        AfU64(m["tickCount"]);
        ulong? previous = null;
        foreach (var record in AfArray(m["records"]))
        {
            var sample = AfMembers(record, ["channelId", "deliveredOrdinal", "digital", "eventId", "faultIds", "numeric", "tick", "time"],
                ["channelId", "deliveredOrdinal", "faultIds", "tick", "time"], ["digital", "eventId", "numeric"]);
            AfId(sample["channelId"]);
            var ordinal = AfU64(sample["deliveredOrdinal"]);
            if (previous is not null && ordinal <= previous) throw new AfRefused("ordinal");
            previous = ordinal;
            AfU64(sample["tick"]);
            AfTime(sample["time"]);
            if (sample.TryGetValue("numeric", out var numeric)) AfDouble(numeric);
            else if (sample.TryGetValue("digital", out var digital)) AfBool(digital);
            else AfId(sample["eventId"]);
            foreach (var fault in AfArray(sample["faultIds"])) AfId(fault);
        }
        foreach (var node in AfArray(m["events"]))
        {
            var evt = AfMembers(node, ["channelId", "duration", "eventId", "faultId", "fields", "kind", "start"], ["channelId", "eventId", "fields", "kind", "start"]);
            AfId(evt["channelId"]);
            AfId(evt["eventId"]);
            AfString(evt["kind"]);
            AfTime(evt["start"]);
            if (evt.TryGetValue("duration", out var duration)) AfTime(duration);
            if (evt.TryGetValue("faultId", out var faultId)) AfId(faultId);
            foreach (var field in AfArray(evt["fields"]))
            {
                var entry = AfMembers(field, ["name", "value"], ["name", "value"]);
                AfString(entry["name"]);
                AfScalar(entry["value"]);
            }
        }
        foreach (var node in AfArray(m["gaps"]))
        {
            var gap = AfMembers(node, ["channelId", "faultId", "kind", "startTick", "tickCount"], ["faultId", "kind", "startTick", "tickCount"]);
            if (AfString(gap["kind"]) is not ("drop" or "disconnect" or "malformed")) throw new AfRefused("gapKind");
            AfId(gap["faultId"]);
            AfU64(gap["startTick"]);
            AfU64(gap["tickCount"]);
            if (gap.TryGetValue("channelId", out var channel)) AfId(channel);
        }
    }

    private static void AfScalar(AfNode node)
    {
        if (node.Kind == AfKind.Object && node.Members.Any(member => member.Key == "resource")) throw new AfRefused("metadata");
        string[] arms = ["boolean", "decimal", "instant", "integer", "number", "text"];
        var m = AfMembers(node, arms, [], arms);
        if (m.TryGetValue("text", out var text)) AfString(text);
        else if (m.TryGetValue("boolean", out var boolean)) AfBool(boolean);
        else if (m.TryGetValue("integer", out var integer)) AfS64(integer);
        else if (m.TryGetValue("number", out var number)) AfDouble(number);
        else if (m.TryGetValue("decimal", out var dec)) AfString(AfMembers(dec, ["value"], ["value"])["value"]);
        else
        {
            var instant = AfMembers(m["instant"], ["nanos", "unixSeconds"], ["nanos", "unixSeconds"]);
            AfS64(instant["unixSeconds"]);
            AfU32(instant["nanos"]);
        }
    }

    private static void AfTime(AfNode node)
    {
        var m = AfMembers(node, ["rate", "ticks"], ["rate", "ticks"]);
        var rate = AfMembers(m["rate"], ["denominator", "numerator"], ["denominator", "numerator"]);
        if (AfU64(rate["denominator"]) < 1 || AfS64(rate["numerator"]) <= 0) throw new AfRefused("rate");
        AfS64(m["ticks"]);
    }

    private static string AfString(AfNode node) => node.Kind == AfKind.String ? node.Text : throw new AfRefused("type");
    private static bool AfBool(AfNode node) => node.Kind switch { AfKind.True => true, AfKind.False => false, _ => throw new AfRefused("type") };
    private static List<AfNode> AfArray(AfNode node) => node.Kind == AfKind.Array ? node.Items : throw new AfRefused("type");

    private static bool AfDigits(string text, int start) =>
        start < text.Length && text.Skip(start).All(char.IsAsciiDigit) && !(text[start] == '0' && text.Length - start > 1);

    private static ulong AfU64(AfNode node)
    {
        var text = AfString(node);
        return AfDigits(text, 0) && ulong.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out var value) ? value : throw new AfRefused("int");
    }

    private static uint AfU32(AfNode node)
    {
        var text = AfString(node);
        return AfDigits(text, 0) && uint.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out var value) ? value : throw new AfRefused("int");
    }

    private static long AfS64(AfNode node)
    {
        var text = AfString(node);
        if (text == "-0") throw new AfRefused("int");
        var start = text.StartsWith('-') ? 1 : 0;
        return AfDigits(text, start) && long.TryParse(text, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var value) ? value : throw new AfRefused("int");
    }

    private static double AfDouble(AfNode node)
    {
        var text = AfString(node);
        if (text.Length != 16 || !text.All(c => char.IsAsciiDigit(c) || c is >= 'a' and <= 'f')) throw new AfRefused("double");
        var value = BitConverter.Int64BitsToDouble(unchecked((long)ulong.Parse(text, NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture)));
        return double.IsFinite(value) ? value : throw new AfRefused("double");
    }

    private static F.Id AfId(AfNode node)
    {
        var text = AfString(node);
        if (text.Length != 36) throw new AfRefused("id");
        var hex = new StringBuilder(32);
        for (var index = 0; index < 36; index++)
        {
            var c = text[index];
            if (index is 8 or 13 or 18 or 23) { if (c != '-') throw new AfRefused("id"); }
            else if (char.IsAsciiDigit(c) || c is >= 'a' and <= 'f') hex.Append(c);
            else throw new AfRefused("id");
        }
        var bytes = Convert.FromHexString(hex.ToString());
        if (bytes.All(b => b == 0)) throw new AfRefused("id");
        return new F.Id { Value = ByteString.CopyFrom(bytes) };
    }

    private static string AfEmit(AfNode node, AfEmitOptions options, string? member = null)
    {
        switch (node.Kind)
        {
            case AfKind.Object:
            {
                var members = node.Members.Where(pair => !(options.OmitEmpty && pair.Value.Kind == AfKind.Array && pair.Value.Items.Count == 0)).ToList();
                members = options.NoSort ? members.AsEnumerable().Reverse().ToList() : members.OrderBy(pair => pair.Key, StringComparer.Ordinal).ToList();
                return "{" + string.Join(",", members.Select(pair => AfEmitString(pair.Key, options) + ":" + AfEmit(pair.Value, options, pair.Key))) + "}";
            }
            case AfKind.Array: return "[" + string.Join(",", node.Items.Select(item => AfEmit(item, options, member))) + "]";
            case AfKind.String:
                if (options.DoubleToString && (member is "numeric" or "number") && node.Text.Length == 16)
                    return "\"" + BitConverter.Int64BitsToDouble(unchecked((long)ulong.Parse(node.Text, NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture))).ToString("R", CultureInfo.InvariantCulture) + "\"";
                return AfEmitString(node.Text, options);
            case AfKind.True: return "true";
            case AfKind.False: return "false";
            case AfKind.Null: return "null";
            default: return node.Text;
        }
    }

    private static string AfEmitString(string value, AfEmitOptions options)
    {
        for (var index = 0; index < value.Length; index++)
        {
            if (char.IsHighSurrogate(value[index]) && index + 1 < value.Length && char.IsLowSurrogate(value[index + 1])) { index++; continue; }
            if (char.IsSurrogate(value[index])) throw new AfRefused("surrogate");
        }
        var output = new StringBuilder("\"");
        foreach (var c in value)
        {
            if (c == '"') output.Append("\\\"");
            else if (c == '\\') output.Append("\\\\");
            else if (c == '\b') output.Append("\\b");
            else if (c == '\t') output.Append("\\t");
            else if (c == '\n') output.Append("\\n");
            else if (c == '\f') output.Append("\\f");
            else if (c == '\r') output.Append("\\r");
            else if (c < 0x20) output.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
            else if (options.EscapeNonAscii && c > 0x7e) output.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
            else output.Append(c);
        }
        return output.Append('"').ToString();
    }

    private static Sim.SimulationDataSegment AfModel(AfNode root)
    {
        AfValidateSegment(root);
        var m = root.Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
        var segment = new Sim.SimulationDataSegment
        {
            EncodingProfile = AfString(m["encodingProfile"]),
            ExecutionProfile = AfString(m["executionProfile"]),
            StartTick = AfU64(m["startTick"]),
            TickCount = AfU64(m["tickCount"]),
        };
        foreach (var node in AfArray(m["records"]))
        {
            var r = node.Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
            var sample = new Sim.SimulationSample { ChannelId = AfId(r["channelId"]), Tick = AfU64(r["tick"]), DeliveredOrdinal = AfU64(r["deliveredOrdinal"]), Time = AfModelTime(r["time"]) };
            if (r.TryGetValue("numeric", out var numeric)) sample.Numeric = AfDouble(numeric);
            else if (r.TryGetValue("digital", out var digital)) sample.Digital = AfBool(digital);
            else sample.EventId = AfId(r["eventId"]);
            foreach (var fault in AfArray(r["faultIds"])) sample.FaultIds.Add(AfId(fault));
            segment.Records.Add(sample);
        }
        foreach (var node in AfArray(m["events"]))
        {
            var e = node.Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
            var evt = new Sim.SimulationEvent { ChannelId = AfId(e["channelId"]), EventId = AfId(e["eventId"]), Kind = AfString(e["kind"]), Start = AfModelTime(e["start"]) };
            if (e.TryGetValue("duration", out var duration)) evt.Duration = AfModelTime(duration);
            if (e.TryGetValue("faultId", out var faultId)) evt.FaultId = AfId(faultId);
            foreach (var field in AfArray(e["fields"]))
            {
                var entry = field.Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
                evt.Fields.Add(new P.MetadataEntry { Name = AfString(entry["name"]), Value = AfModelScalar(entry["value"]) });
            }
            segment.Events.Add(evt);
        }
        foreach (var node in AfArray(m["gaps"]))
        {
            var g = node.Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
            var gap = new Sim.SimulationGap { FaultId = AfId(g["faultId"]), Kind = AfString(g["kind"]), StartTick = AfU64(g["startTick"]), TickCount = AfU64(g["tickCount"]) };
            if (g.TryGetValue("channelId", out var channel)) gap.ChannelId = AfId(channel);
            segment.Gaps.Add(gap);
        }
        return segment;
    }

    private static P.ScopeTime AfModelTime(AfNode node)
    {
        var m = node.Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
        var rate = m["rate"].Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
        return new P.ScopeTime { Ticks = AfS64(m["ticks"]), Rate = new F.Rational { Numerator = AfS64(rate["numerator"]), Denominator = AfU64(rate["denominator"]) } };
    }

    private static P.MetadataScalar AfModelScalar(AfNode node)
    {
        var m = node.Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
        if (m.TryGetValue("text", out var text)) return new P.MetadataScalar { Text = AfString(text) };
        if (m.TryGetValue("boolean", out var boolean)) return new P.MetadataScalar { Boolean = AfBool(boolean) };
        if (m.TryGetValue("integer", out var integer)) return new P.MetadataScalar { Integer = AfS64(integer) };
        if (m.TryGetValue("number", out var number)) return new P.MetadataScalar { Number = AfDouble(number) };
        if (m.TryGetValue("decimal", out var dec)) return new P.MetadataScalar { Decimal = new F.Decimal { Value = AfString(dec.Members.Single().Value) } };
        var instant = m["instant"].Members.ToDictionary(member => member.Key, member => member.Value, StringComparer.Ordinal);
        return new P.MetadataScalar { Instant = new F.Instant { UnixSeconds = AfS64(instant["unixSeconds"]), Nanos = AfU32(instant["nanos"]) } };
    }
}
