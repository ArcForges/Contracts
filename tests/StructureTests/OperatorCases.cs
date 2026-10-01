// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using System.Text.Json.Nodes;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using ArcForges.Contracts.CloudInternal.Operator.V1;
using CloudShapes = ArcForges.Contracts.CloudInternal.Shapes.ContractShapeValidation;

internal static class OperatorCases
{
    private const string OperatorFile = "arcforges/operator/v1/operator.proto";
    private const string OperatorPackage = "arcforges.operator.v1";

    public static void Run(string root)
    {
        using var fixtureDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/internal/con-14-operator.json")));
        var fixture = fixtureDocument.RootElement;
        AssertProtocolExpectations(fixture.GetProperty("protocolExpectations"));
        AssertMutationOracle(fixture.GetProperty("mutationVectors"));
        var negativeVectors = fixture.GetProperty("negativeVectors");
        AssertVectorIds(negativeVectors, new[]
        {
            "non-operator-caller-refused",
            "same-identity-cannot-propose-and-approve",
            "changed-proposal-hash-refused",
            "stale-proposal-revision-refused",
            "stale-owner-revision-refused",
            "changed-configuration-invalidates-approval",
            "revoked-required-role-invalidates-approval",
            "expired-proposal-refused",
            "concurrent-consumption-happens-at-most-once",
            "changed-content-with-reused-command-refused"
        }, "negative refusal coverage");
        AssertNegativeOracle(negativeVectors);
        AssertRuntimeAcceptanceUnproven(negativeVectors, "negative vectors");

        var lostReceiptVectors = fixture.GetProperty("lostReceiptVectors");
        Require(lostReceiptVectors.GetArrayLength() == 1 &&
            lostReceiptVectors[0].GetProperty("id").GetString() == "lost-response-same-command-replays-original-receipt",
            "same-command lost-response idempotency vector");
        Require(lostReceiptVectors[0].GetProperty("scenario").GetString() ==
            "The owner batch committed but the response was lost; the original proposer retries the exact same commandId and canonical hash.",
            "lost-response retry scenario");
        Require(lostReceiptVectors[0].GetProperty("expectedBoundary").GetString() ==
            "return the original receipt and resulting proposal state without a second owner effect", "lost-response receipt boundary");
        AssertRuntimeAcceptanceUnproven(lostReceiptVectors, "lost-receipt vectors");

        var file = OperatorReflection.Descriptor;
        Require(file.Name == OperatorFile, "internal operator source file");
        Require(file.Package == OperatorPackage, "internal operator package");
        Require(file.Dependencies.Select(dependency => dependency.Name).SequenceEqual(new[]
        {
            "arcforges/foundation/v1/foundation.proto",
            "arcforges/catalog/v1/catalog.proto",
            "arcforges/publicapi/v1/commerce.proto",
            "arcforges/publicapi/v1/content.proto"
        }), "restricted operator imports");

        var publicClosure = new[]
            {
                ArcForges.Contracts.Foundation.V1.FoundationReflection.Descriptor,
                ArcForges.Contracts.Catalog.V1.CatalogReflection.Descriptor,
                ArcForges.Contracts.PublicApi.V1.CommerceReflection.Descriptor,
                ArcForges.Contracts.PublicApi.V1.ContentReflection.Descriptor
            }
            .SelectMany(DependencyClosure)
            .DistinctBy(dependency => dependency.Name);
        Require(publicClosure.All(dependency =>
            dependency.Name != OperatorFile && !dependency.Package.StartsWith("arcforges.operator.", StringComparison.Ordinal)),
            "public descriptor closure does not import the internal operator package");

        var service = file.Services.Single(candidate => candidate.Name == "OperatorService");
        var methodNames = new[]
        {
            "ListCases", "GetCase", "RequestAccess", "ApproveAccess", "EndAccess", "ReadDiagnostic",
            "ProposeEnforcement", "DecideEnforcement", "GetAppeal", "ResolveAppeal", "StageConfiguration",
            "ValidateConfiguration", "ApproveConfiguration", "ActivateConfiguration", "GetConfiguration",
            "SetKillSwitch", "StartBreakGlass", "EndBreakGlass", "ProposeAction", "ApproveAction",
            "GetProposal", "GrantEntitlement", "RevokeEntitlement", "IssueCompensation", "AdjustCompensation",
            "DecideRefund", "GetCatalogSubmission", "ReplyCase", "SetCaseState", "ReviewCatalogSubmission",
            "RevokeCatalogVersion"
        };
        Require(service.FullName == OperatorPackage + ".OperatorService", "internal OperatorService identity");
        Require(service.Methods.Select(method => method.Name).SequenceEqual(methodNames), "exact 31 OperatorService methods and order");
        var expectedPaths = methodNames.Select(name => $"/{OperatorPackage}.OperatorService/{name}");
        var actualPaths = service.Methods.Select(method => $"/{service.FullName}/{method.Name}");
        Require(actualPaths.SequenceEqual(expectedPaths), "exact 31 internal method paths");

        var proposalMethods = new HashSet<string>(StringComparer.Ordinal)
        {
            "ResolveAppeal", "SetKillSwitch", "ReviewCatalogSubmission", "RevokeCatalogVersion"
        };
        foreach (var method in service.Methods)
        {
            var path = $"/{service.FullName}/{method.Name}";
            var request = method.InputType;
            var response = method.OutputType;
            Require(path.StartsWith("/arcforges.operator.v1.OperatorService/", StringComparison.Ordinal), path + " internal path");
            Require(!method.IsClientStreaming && !method.IsServerStreaming, path + " unary");
            Require(request.File == file && response.File == file, path + " request/response stay in the internal file");
            Require(request.Name == "OperatorService" + method.Name + "Request", path + " request identity");
            Require(response.Name == "OperatorService" + method.Name + "Response", path + " response identity");
            Require(request.FindFieldByNumber(1)?.MessageType?.FullName == "arcforges.foundation.v1.RequestMeta", path + " request metadata");

            var context = request.FindFieldByNumber(100);
            Require(context is not null && context.Name == "context" &&
                context.MessageType.FullName == OperatorPackage + ".OperatorCallContext", path + " tag 100 context");

            var messages = request.FindFieldByNumber(102);
            Require((messages is not null) == (method.Name == "GetCase"), path + " tag 102 allowlist");
            if (messages is not null)
            {
                Require(messages.Name == "messages" &&
                    messages.MessageType.FullName == "arcforges.foundation.v1.PageRequest", path + " tag 102 message page");
            }

            var proposal = request.FindFieldByNumber(101);
            var requiresProposal = proposalMethods.Contains(method.Name);
            Require((proposal is not null) == requiresProposal, path + " tag 101 allowlist");
            if (proposal is not null)
            {
                Require(proposal.Name == "proposal" &&
                    proposal.MessageType.FullName == OperatorPackage + ".OperatorProposalRef", path + " tag 101 proposal reference");
            }

            Require(response.FindFieldByNumber(1)?.MessageType?.FullName == "arcforges.foundation.v1.ResponseMeta", path + " response metadata");
            Require(response.FindFieldByNumber(2)?.ContainingOneof?.Name == "outcome" &&
                response.FindFieldByNumber(3)?.ContainingOneof?.Name == "outcome" &&
                response.FindFieldByNumber(3)?.MessageType?.FullName == "arcforges.foundation.v1.ArcError", path + " typed response outcome");
        }

        AssertFields(file, "OperatorAccess", "1:access_id,2:operator_id,3:case_id,4:workspace_id,5:resources,6:purpose,7:expires_at,8:state,9:consent_ref,10:second_operator_id,11:revision");
        AssertFields(file, "OperatorAction", "1:action_id,2:proposer_id,3:approver_id,4:target,5:action,6:proposal_hash,7:reason,8:state,9:expires_at,10:revision");
        AssertFields(file, "OperatorCallContext", "1:case_id,2:incident_id,3:purpose");
        AssertFields(file, "OperatorProposalRef", "1:proposal_id,2:proposal_hash,3:expected_proposal_revision");
        AssertFields(file, "OperatorMutation", "1:grant,2:revoke_grant,3:issue_credit,4:adjust_credit,5:refund,6:catalog_review,7:catalog_revoke,8:appeal,9:kill");
        AssertFields(file, "OperatorProposal", "1:proposal_id,2:mutation,3:target_operation,4:context,5:reason,6:proposer_subject,7:approver_subject,8:proposal_hash,9:owner_revision,10:revision,11:state,12:expires_at,13:consumed_by_command_id,14:result_ref,15:recovery_generation,16:configuration_hash");
        AssertFields(file, "OperatorResult", "1:grant,2:credit,3:refund,4:submission,5:catalog_version,6:action");
        AssertFields(file, "ConfigValidation", "1:config_id,2:config_hash,3:schema_version,4:problems,5:worker_acknowledgement,6:compatible,7:revision");

        AssertOneof(file, "OperatorCallContext", "context", "case_id", "incident_id");
        AssertOneof(file, "OperatorMutation", "mutation", "grant", "revoke_grant", "issue_credit", "adjust_credit", "refund", "catalog_review", "catalog_revoke", "appeal", "kill");
        AssertOneof(file, "OperatorResult", "result", "grant", "credit", "refund", "submission", "catalog_version", "action");
        AssertFieldType(file, "OperatorCallContext", 1, "arcforges.foundation.v1.Id");
        AssertFieldType(file, "OperatorCallContext", 2, "arcforges.foundation.v1.Id");
        AssertFieldType(file, "OperatorProposalRef", 1, "arcforges.foundation.v1.Id");
        AssertScalarType(file, "OperatorProposalRef", 2, FieldType.String);
        AssertFieldType(file, "OperatorProposalRef", 3, "arcforges.foundation.v1.Revision");
        AssertFieldType(file, "OperatorMutation", 1, OperatorPackage + ".OperatorGrantInput");
        AssertFieldType(file, "OperatorMutation", 2, OperatorPackage + ".OperatorRevokeGrantInput");
        AssertFieldType(file, "OperatorMutation", 3, OperatorPackage + ".OperatorIssueCreditInput");
        AssertFieldType(file, "OperatorMutation", 4, OperatorPackage + ".OperatorAdjustCreditInput");
        AssertFieldType(file, "OperatorMutation", 5, OperatorPackage + ".OperatorRefundInput");
        AssertFieldType(file, "OperatorMutation", 6, OperatorPackage + ".OperatorCatalogReviewInput");
        AssertFieldType(file, "OperatorMutation", 7, OperatorPackage + ".OperatorCatalogRevokeInput");
        AssertFieldType(file, "OperatorMutation", 8, OperatorPackage + ".OperatorAppealInput");
        AssertFieldType(file, "OperatorMutation", 9, OperatorPackage + ".OperatorKillInput");
        AssertFieldType(file, "OperatorProposal", 2, OperatorPackage + ".OperatorMutation");
        AssertFieldType(file, "OperatorProposal", 4, OperatorPackage + ".OperatorCallContext");
        AssertFieldType(file, "OperatorResult", 1, "arcforges.publicapi.v1.Grant");
        AssertFieldType(file, "OperatorResult", 2, "arcforges.publicapi.v1.CreditLot");
        AssertFieldType(file, "OperatorResult", 3, "arcforges.publicapi.v1.RefundView");
        AssertFieldType(file, "OperatorResult", 4, "arcforges.catalog.v1.CatalogSubmissionView");
        AssertFieldType(file, "OperatorResult", 5, "arcforges.catalog.v1.CatalogVersionView");
        AssertFieldType(file, "OperatorResult", 6, OperatorPackage + ".OperatorAction");

        AssertOperationMatrix(root, fixture, service, methodNames);
        AssertShapeCases(fixture.GetProperty("shapeCases"));

        Console.WriteLine("CON.14: internal operator descriptor, exact methods, authorization matrix, shape vectors, context/proposal tags and Registry04 record shapes passed.");
    }

    // Independent Registry04 section 9.1 oracle: operation|method|class|risk|approval|stepUp|egress|roles.
    private static readonly string[] Matrix =
    {
            "operator.listCases|ListCases|Q|R1|none|false|none|CS,RS,TS,SE",
            "operator.getCase|GetCase|Q|R1|none|false|none|CS,RS,TS,SE",
            "operator.requestAccess|RequestAccess|CC|R3|foreground|true|none|CS,RS,TS",
            "operator.approveAccess|ApproveAccess|IW|R3|secondOperatorAndOwnerConsent|true|none|RS,SE",
            "operator.endAccess|EndAccess|IW|R2|foreground|false|none|CS,RS,TS,SE",
            "operator.readDiagnostic|ReadDiagnostic|Q|R3|activeAccessGrant|true|diagnosticToOperator|CS,RS,TS",
            "operator.proposeEnforcement|ProposeEnforcement|CC|R3|foreground|true|none|TS",
            "operator.decideEnforcement|DecideEnforcement|IW|R3|secondOperator|true|none|SE",
            "operator.getAppeal|GetAppeal|Q|R1|none|false|none|TS,SE",
            "operator.resolveAppeal|ResolveAppeal|IW|R3|approvedProposal|true|none|TS",
            "operator.stageConfiguration|StageConfiguration|CC|R3|foreground|true|none|OP",
            "operator.validateConfiguration|ValidateConfiguration|Q|R3|none|true|none|OP",
            "operator.approveConfiguration|ApproveConfiguration|IW|R3|secondOperator|true|none|SE",
            "operator.activateConfiguration|ActivateConfiguration|IW|R3|secondOperatorReceipt|true|none|OP",
            "operator.getConfiguration|GetConfiguration|Q|R2|none|false|none|OP,SE",
            "operator.setKillSwitch|SetKillSwitch|IW|R3|approvedProposal|true|none|OP",
            "operator.startBreakGlass|StartBreakGlass|CC|R4|alarmedIncident|true|caseBoundRecovery|SE",
            "operator.endBreakGlass|EndBreakGlass|IW|R2|foreground|false|none|SE",
            "operator.proposeAction|ProposeAction|CC|R3|foreground|true|none|proposer",
            "operator.approveAction|ApproveAction|IW|R3|secondOperator|true|none|approver",
            "operator.getProposal|GetProposal|Q|R2|none|false|none|proposerOrApprover",
            "operator.grantEntitlement|GrantEntitlement|CC|R3|approvedProposal|true|none|CS,RS",
            "operator.revokeEntitlement|RevokeEntitlement|DE|R3|approvedProposal|true|none|CS,RS",
            "operator.issueCompensation|IssueCompensation|CC|R3|approvedProposal|true|none|CS",
            "operator.adjustCompensation|AdjustCompensation|IW|R3|approvedProposal|true|none|CS",
            "operator.decideRefund|DecideRefund|IW|R3|approvedProposal|true|paymentProvider|CS",
            "operator.getCatalogSubmission|GetCatalogSubmission|Q|R2|none|false|none|TS,SE",
            "operator.replyCase|ReplyCase|CC|R2|foreground|false|caseOwnerNotification|CS,RS,TS,SE",
            "operator.setCaseState|SetCaseState|IW|R2|foreground|false|caseOwnerNotification|CS,RS,TS,SE",
            "catalog.review|ReviewCatalogSubmission|IW|R3|approvedProposal|true|none|TS",
            "catalog.revoke|RevokeCatalogVersion|DE|R3|approvedProposal|true|none|TS",
    };

    private static void AssertOperationMatrix(string root, JsonElement fixture, ServiceDescriptor service, string[] methodNames)
    {
        var abbreviations = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["CS"] = "customerSupport", ["RS"] = "recoverySpecialist", ["OP"] = "operations",
            ["TS"] = "trustSafety", ["SE"] = "security"
        };
        AssertStrings(fixture.GetProperty("roleVocabulary"), "customerSupport", "recoverySpecialist", "operations", "trustSafety", "security");
        var matrix = fixture.GetProperty("operationMatrix").EnumerateArray().ToArray();
        using var exportDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/operations/con-14.json")));
        var exports = exportDocument.RootElement.GetProperty("operations").EnumerateArray().ToArray();
        Require(Matrix.Length == 31 && matrix.Length == 31 && exports.Length == 31, "31 matrix, oracle and export rows");
        Require(Matrix.Count(row => row.StartsWith("operator.", StringComparison.Ordinal)) == 29 &&
            Matrix.Count(row => row.StartsWith("catalog.", StringComparison.Ordinal)) == 2, "29 operator.* plus 2 catalog.* operations");
        Require(Matrix.Select(row => row.Split("|")[1]).SequenceEqual(methodNames), "oracle methods follow the service order");
        for (var index = 0; index < Matrix.Length; index++)
        {
            var oracle = Matrix[index].Split("|");
            var row = matrix[index];
            var name = oracle[0];
            Require(row.GetProperty("operationId").GetString() == name, name + " matrix identity");
            Require(row.GetProperty("method").GetString() == oracle[1], name + " matrix method");
            Require(row.GetProperty("class").GetString() == oracle[2], name + " matrix class");
            Require(row.GetProperty("risk").GetString() == oracle[3], name + " matrix risk");
            Require(row.GetProperty("approval").GetString() == oracle[4], name + " matrix approval");
            Require(row.GetProperty("stepUp").GetBoolean() == (oracle[5] == "true"), name + " matrix step-up");
            Require(row.GetProperty("egress").GetString() == oracle[6], name + " matrix egress");
            if (abbreviations.ContainsKey(oracle[7].Split(",")[0]))
            {
                AssertStrings(row.GetProperty("roles"), oracle[7].Split(",").Select(role => abbreviations[role]).ToArray());
                Require(!row.TryGetProperty("payloadBoundRoles", out _), name + " fixed roles have no payload binding");
            }
            else
            {
                Require(row.GetProperty("roles").ValueKind == JsonValueKind.Null &&
                    row.GetProperty("payloadBoundRoles").GetString() == oracle[7], name + " payload-bound roles");
            }

            var exported = exports[index];
            Require(exported.GetProperty("operationId").GetString() == name, name + " export identity");
            Require(exported.GetProperty("binding").GetString() == OperatorPackage + ".OperatorService/" + oracle[1], name + " export binding");
            Require(exported.GetProperty("kind").GetString() == "proto" &&
                exported.GetProperty("source").GetString() == "internal/proto/arcforges/operator/v1/operator.proto" &&
                exported.GetProperty("scope").GetString() == "operator" && exported.GetProperty("surface").GetString() == "operator" &&
                exported.GetProperty("profile").GetString() == "operator", name + " operator boundary");
            Require(exported.GetProperty("idempotency").GetString() == oracle[2], name + " export class");
            var auth = exported.GetProperty("authorization");
            Require(auth.EnumerateObject().Count() == 8, name + " exactly eight authorization fields");
            Require(auth.GetProperty("capability").ValueKind == JsonValueKind.Null, name + " has no tool capability");
            Require(auth.GetProperty("risk").GetString() == oracle[3] && auth.GetProperty("approval").GetString() == oracle[4] &&
                auth.GetProperty("stepUp").GetBoolean() == (oracle[5] == "true") && auth.GetProperty("egress").GetString() == oracle[6],
                name + " export authorization metadata");
            Require(auth.GetProperty("localPresence").ValueKind == JsonValueKind.False &&
                auth.GetProperty("patEligible").ValueKind == JsonValueKind.False, name + " no local-presence or PAT reachability");
            AssertStrings(auth.GetProperty("actorKinds"), "operator");
            Require(service.Methods[index].Name == oracle[1], name + " method order");
        }
    }

    private static void AssertShapeCases(JsonElement cases)
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var positive = 0;
        var negative = 0;
        foreach (var item in cases.EnumerateArray())
        {
            var id = item.GetProperty("id").GetString()!;
            Require(seen.Add(id), "unique shape case " + id);
            var node = JsonNode.Parse(item.GetProperty("value").GetRawText())!;
            if (node is JsonObject obj && obj["canonicalJson"] is JsonObject generated)
                obj["canonicalJson"] = Convert.ToBase64String(new byte[generated["generatedBytes"]!.GetValue<int>()]);
            var json = node.ToJsonString();
            var target = item.GetProperty("target").GetString()!;
            var actual = target switch
            {
                "OperatorCallContext" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorCallContext>(json)),
                "OperatorProposalRef" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorProposalRef>(json)),
                "OperatorMutation" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorMutation>(json)),
                "OperatorProposal" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorProposal>(json)),
                "ConfigurationDocument" => CloudShapes.IsValid(JsonParser.Default.Parse<ConfigurationDocument>(json)),
                "ConfigValidation" => CloudShapes.IsValid(JsonParser.Default.Parse<ConfigValidation>(json)),
                "OperatorServiceApproveActionRequest" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorServiceApproveActionRequest>(json)),
                "OperatorServiceGrantEntitlementRequest" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorServiceGrantEntitlementRequest>(json)),
                "OperatorServiceReviewCatalogSubmissionRequest" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorServiceReviewCatalogSubmissionRequest>(json)),
                "OperatorServiceSetKillSwitchRequest" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorServiceSetKillSwitchRequest>(json)),
                "OperatorServiceSetCaseStateRequest" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorServiceSetCaseStateRequest>(json)),
                "OperatorServiceGetCaseRequest" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorServiceGetCaseRequest>(json)),
                "OperatorServiceListCasesRequest" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorServiceListCasesRequest>(json)),
                "OperatorServiceGetCaseResponse" => CloudShapes.IsValid(JsonParser.Default.Parse<OperatorServiceGetCaseResponse>(json)),
                _ => throw new InvalidOperationException("Unknown CON.14 shape target: " + target)
            };
            var expected = item.GetProperty("valid").GetBoolean();
            Require(actual == expected, "shape case " + id);
            if (expected) positive++; else negative++;
        }
        Require(positive >= 20 && negative >= 30, $"shape coverage positives={positive} negatives={negative}");
    }

    private static void AssertProtocolExpectations(JsonElement protocol)
    {
        Require(protocol.GetProperty("proposalLifetimeMinutes").GetInt32() == 15, "proposal lifetime");
        AssertStrings(protocol.GetProperty("proposalStates"), "pending", "approved", "rejected", "expired", "invalidated", "executed");
        AssertStrings(protocol.GetProperty("approvalBinds"),
            "distinct eligible operator identity", "exact proposal hash", "expected proposal revision", "current step-up",
            "unchanged owner and governing configuration");
        AssertStrings(protocol.GetProperty("executionBinds"),
            "original proposer", "exact executing operation and typed mutation body", "approved proposal reference and revision",
            "captured owner revision", "current permitted proposer and approver roles", "case or incident context", "recovery generation");
        AssertStrings(protocol.GetProperty("atomicExecutionEffects"),
            "owner write through the owner port", "approval consumption", "result receipt", "audit", "notification/outbox",
            "proposal state executed");
        Require(protocol.GetProperty("sameCommandAndHashAfterLostResponse").GetString() ==
            "return the original receipt without repeating the owner effect", "same-command retry idempotency expectation");
        Require(protocol.GetProperty("changedContentWithReusedCommand").GetString() ==
            "refuse with command.reused_identifier", "changed content command reuse refusal");
    }

    private static void AssertMutationOracle(JsonElement vectors)
    {
        var lifecycle = new[] { "pending", "approved", "executed" };
        var expected = new (string Variant, string Operation, string[] ProposerRoles, string ApproverRole, string RevisionGuard)[]
        {
            ("grant", "operator.grantEntitlement", new[] { "customerSupport", "recoverySpecialist" }, "operations", "absent grant=0 plus captured configuration/profile hash"),
            ("revokeGrant", "operator.revokeEntitlement", new[] { "customerSupport", "recoverySpecialist" }, "security", "entitlement snapshot version and exact unrevoked grant identity"),
            ("issueCredit", "operator.issueCompensation", new[] { "customerSupport" }, "operations", "absent lot=0 plus captured configuration hash"),
            ("adjustCredit", "operator.adjustCompensation", new[] { "customerSupport" }, "operations", "credit_lot.rev and current held/remaining balances"),
            ("refund", "operator.decideRefund", new[] { "customerSupport" }, "operations", "commerce.refund.rev and current payment/refundable balance"),
            ("catalogReview", "catalog.review", new[] { "trustSafety" }, "security", "PackageCatalog submission revision"),
            ("catalogRevoke", "catalog.revoke", new[] { "trustSafety" }, "security", "PackageCatalog published version revision"),
            ("appeal", "operator.resolveAppeal", new[] { "trustSafety" }, "security", "enforcement action revision and pending appeal"),
            ("kill", "operator.setKillSwitch", new[] { "operations" }, "security", "Policy control revision (0 for absent control)")
        };
        var actual = vectors.EnumerateArray().ToDictionary(vector => vector.GetProperty("variant").GetString()!, StringComparer.Ordinal);
        Require(actual.Count == expected.Length && actual.Count == 9, "exact nine unique mutation vectors");
        foreach (var item in expected)
        {
            var vector = actual[item.Variant];
            Require(vector.GetProperty("executingOperation").GetString() == item.Operation, item.Variant + " executing operation");
            Require(vector.GetProperty("distinctApproverRole").GetString() == item.ApproverRole, item.Variant + " distinct approver role");
            Require(vector.GetProperty("ownerRevisionGuard").GetString() == item.RevisionGuard, item.Variant + " owner revision guard");
            AssertStrings(vector.GetProperty("proposerRoles"), item.ProposerRoles);
            AssertStrings(vector.GetProperty("expectedProposalLifecycle"), lifecycle);
            AssertOptionalText(vector, "proposerMustDifferFrom",
                item.Variant == "appeal" ? "original enforcement proposer" : null, item.Variant + " proposer identity boundary");
            AssertOptionalText(vector, "approverMustDifferFrom",
                item.Variant == "appeal" ? "original enforcement approver" : null, item.Variant + " approver identity boundary");
            AssertOptionalText(vector, "ownerEffectBoundary",
                item.Variant == "refund" ? "approval commits a refund intent/hold/outbox; it does not assert that the provider refunded" : null,
                item.Variant + " external owner-effect boundary");
        }
        AssertRuntimeAcceptanceUnproven(vectors, "mutation vectors");
    }

    private static void AssertNegativeOracle(JsonElement vectors)
    {
        var expected = new (string Id, string? Scenario, string Boundary)[]
        {
            ("non-operator-caller-refused", null, "refuse; OperatorService is available only through its separate operator origin/session and CSRF binding"),
            ("same-identity-cannot-propose-and-approve", "The proposer and the claimed distinct approver resolve to the same operator identity.", "refuse approval; no proposal approval or owner effect"),
            ("changed-proposal-hash-refused", "ApproveAction supplies a proposalHash different from the immutable pending proposal hash.", "refuse approval; do not regenerate or silently rebind the proposal"),
            ("stale-proposal-revision-refused", "The approval or OperatorProposalRef expected proposal revision differs from the current proposal revision.", "refuse on revision mismatch; no owner effect"),
            ("stale-owner-revision-refused", "RequestMeta.expectedRev differs from the owner revision captured by the proposal.", "refuse on revision mismatch; do not rebase the approved mutation"),
            ("changed-configuration-invalidates-approval", "The governing configuration hash changes after proposal approval and before execution.", "invalidate the approval; require a new proposal and approval rather than silently regenerating consent"),
            ("revoked-required-role-invalidates-approval", "A required proposer or approver role is revoked after approval and before execution.", "refuse execution under the current role set; no owner effect"),
            ("expired-proposal-refused", "Execution is attempted after the pending proposal's 15-minute expiry.", "refuse as expired; no owner effect"),
            ("concurrent-consumption-happens-at-most-once", "Two distinct commands concurrently attempt to execute the same approved proposal.", "at most one command consumes approval and commits the owner effect; the competing command refuses and cannot repeat it"),
            ("changed-content-with-reused-command-refused", "After a response is lost, a retry reuses the original commandId with a different canonical request hash.", "refuse with command.reused_identifier; do not repeat or rebind the owner effect")
        };
        var actual = vectors.EnumerateArray().ToDictionary(vector => vector.GetProperty("id").GetString()!, StringComparer.Ordinal);
        Require(actual.Count == expected.Length, "exact negative vector set");
        foreach (var item in expected)
        {
            var vector = actual[item.Id];
            AssertOptionalText(vector, "scenario", item.Scenario, item.Id + " scenario");
            Require(vector.GetProperty("expectedBoundary").GetString() == item.Boundary, item.Id + " expected refusal boundary");
            if (item.Id == "non-operator-caller-refused")
            {
                AssertStrings(vector.GetProperty("callerClasses"), "customer cookie", "native session", "personal access token", "agent", "service credential", "public Web/Android origin");
            }
            else Require(!vector.TryGetProperty("callerClasses", out _), item.Id + " has no unrelated caller-class field");
        }
    }

    private static void AssertStrings(JsonElement actual, params string[] expected) =>
        Require(actual.EnumerateArray().Select(value => value.GetString()).SequenceEqual(expected), "exact fixture string vector");

    private static void AssertOptionalText(JsonElement value, string property, string? expected, string name)
    {
        var present = value.TryGetProperty(property, out var actual);
        Require(present == (expected is not null), name + " presence");
        if (expected is not null) Require(actual.GetString() == expected, name + " value");
    }

    private static void AssertVectorIds(JsonElement vectors, string[] expectedIds, string name)
    {
        var actualIds = vectors.EnumerateArray().Select(vector => vector.GetProperty("id").GetString()!).ToArray();
        Require(actualIds.Length >= 9 && actualIds.Distinct(StringComparer.Ordinal).Count() == actualIds.Length,
            name + " has at least nine unique cases");
        Require(actualIds.OrderBy(id => id, StringComparer.Ordinal).SequenceEqual(expectedIds.OrderBy(id => id, StringComparer.Ordinal)),
            name + " exact required case identities");
    }

    private static void AssertRuntimeAcceptanceUnproven(JsonElement vectors, string name)
    {
        foreach (var vector in vectors.EnumerateArray())
        {
            Require(vector.GetProperty("runtimeAcceptanceProven").ValueKind == JsonValueKind.False,
                name + " remain declarative, not runtime acceptance evidence");
        }
    }

    private static IEnumerable<FileDescriptor> DependencyClosure(FileDescriptor file)
    {
        yield return file;
        foreach (var dependency in file.Dependencies)
        foreach (var transitive in DependencyClosure(dependency))
            yield return transitive;
    }

    private static void AssertFields(FileDescriptor file, string messageName, string expected)
    {
        var message = file.MessageTypes.Single(candidate => candidate.Name == messageName);
        var actual = string.Join(",", message.Fields.InDeclarationOrder().Select(field => $"{field.FieldNumber}:{field.Name}"));
        Require(actual == expected, messageName + " Registry04 field identities");
    }

    private static void AssertOneof(FileDescriptor file, string messageName, string oneofName, params string[] fieldNames)
    {
        var message = file.MessageTypes.Single(candidate => candidate.Name == messageName);
        var oneof = message.Oneofs.SingleOrDefault(candidate => candidate.Name == oneofName);
        Require(oneof is not null && oneof.Fields.OrderBy(field => field.FieldNumber).Select(field => field.Name).SequenceEqual(fieldNames),
            messageName + "." + oneofName + " exact oneof members");
    }

    private static void AssertFieldType(FileDescriptor file, string messageName, int number, string typeName)
    {
        var message = file.MessageTypes.Single(candidate => candidate.Name == messageName);
        var field = message.FindFieldByNumber(number);
        Require(field?.MessageType?.FullName == typeName, messageName + " field " + number + " type");
    }

    private static void AssertScalarType(FileDescriptor file, string messageName, int number, FieldType type)
    {
        var message = file.MessageTypes.Single(candidate => candidate.Name == messageName);
        Require(message.FindFieldByNumber(number)?.FieldType == type, messageName + " field " + number + " scalar type");
    }

    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("CON.14 descriptor: " + name);
    }
}
