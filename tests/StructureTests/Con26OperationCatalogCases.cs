// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using ArcForges.Contracts.PublicApi.Operations;
using ArcForges.Contracts.Events.Operations;

internal static class Con26OperationCatalogCases
{
    public static void Run(string root)
    {
        var policies = PublicOperationCatalog.All.Concat(EventOperationCatalog.All).ToArray();
        var byId = policies.ToDictionary(policy => policy.OperationId, StringComparer.Ordinal);
        Require(PublicOperationCatalog.All.Count == 200 && EventOperationCatalog.All.Count == 7, "complete current producer ownership");
        var expectedBindings = ArcForges.Contracts.PublicApi.ContractServices.All.Concat(ArcForges.Contracts.Events.ContractServices.All)
            .Where(service => !service.FullName.StartsWith("arcforges.hello.", StringComparison.Ordinal))
            .SelectMany(service => service.Methods.Select(method => service.FullName + "/" + method.Name)).Order(StringComparer.Ordinal);
        Require(policies.Select(policy => policy.Binding).Order(StringComparer.Ordinal).SequenceEqual(expectedBindings), "compiled descriptor equality");
        var observed = new HashSet<string>(StringComparer.Ordinal);
        foreach (var path in Directory.EnumerateFiles(Path.Combine(root, "eng", "operations"), "*.json"))
        {
            using var document = JsonDocument.Parse(File.ReadAllBytes(path));
            foreach (var row in document.RootElement.GetProperty("operations").EnumerateArray())
            {
                if (row.GetProperty("surface").GetString() != "public") continue;
                var operation = row.GetProperty("operationId").GetString()!;
                Require(observed.Add(operation) && byId.ContainsKey(operation), "unique complete authored public row " + operation);
                var policy = byId[operation];
                var authorization = row.GetProperty("authorization");
                Require(policy.Surface == "public" && policy.Binding == Text(row, "binding") && policy.Scope == Text(row, "scope") &&
                    policy.Idempotency == Text(row, "idempotency") && policy.Profile == Text(row, "profile") && policy.SourceRule == Text(row, "sourceRule"), operation + " operation fields");
                Require(policy.Capability == Text(authorization, "capability") && policy.Approval == Text(authorization, "approval") &&
                    policy.Egress == Text(authorization, "egress") && policy.PatEligible == authorization.GetProperty("patEligible").GetBoolean() &&
                    policy.ActorKinds.SequenceEqual(authorization.GetProperty("actorKinds").EnumerateArray().Select(actor => actor.GetString()!)), operation + " authorization fields");
                Compare(authorization.GetProperty("risk"), policy.Risk, policy.RiskSource, operation + " risk");
                Compare(authorization.GetProperty("stepUp"), policy.StepUp, policy.StepUpSource, operation + " step-up");
                Compare(authorization.GetProperty("localPresence"), policy.LocalPresence, policy.LocalPresenceSource, operation + " local-presence");
                Require(policy.PatScopes.SequenceEqual(policy.PatEligible ? new[] { operation } : Array.Empty<string>()), operation + " exact PAT scopes");
            }
        }
        Require(observed.SetEquals(byId.Keys), "no helper/operator/internal/HTTP catalog leakage");
        var expectedPat = new[] { "workspace.list", "workspace.get", "catalog.search", "catalog.getPackage", "catalog.listVersions",
            "catalog.submitVersion", "catalog.getSubmission", "resource.beginUpload", "resource.completeUpload",
            "resource.getUploadStatus", "resource.renewUploadTicket", "support.listCases" };
        Require(policies.Where(policy => policy.PatEligible).Select(policy => policy.OperationId).ToHashSet(StringComparer.Ordinal).SetEquals(expectedPat), "exact closed twelve-operation PAT allowlist");
        Require(PublicOperationCatalog.TryGet("approval.decide", out var approval) && approval.Risk is null && approval.StepUp is null &&
            approval.LocalPresence is null && approval.RiskSource == "verifiedApprovalProposal.effectiveRisk" &&
            approval.StepUpSource == "verifiedApprovalProposal.stepUp" && approval.LocalPresenceSource == "verifiedApprovalProposal.localPresence" && !approval.PatEligible,
            "derived proposal requirements never silently become false");
        Require(!PublicOperationCatalog.TryGet("WORKSPACE.LIST", out _) && !PublicOperationCatalog.TryGet("unknown", out _) &&
            !PublicOperationCatalog.TryGet("operator.listCases", out _) && !PublicOperationCatalog.TryGet("events.poll", out _), "ordinal unknown and cross-owner lookup denial");
        Require(EventOperationCatalog.TryGet("events.poll", out var polling) && !polling.PatEligible, "event lookup preserves explicit denial");
        Expect<ArgumentNullException>(() => PublicOperationCatalog.TryGet(null!, out _));
        Expect<NotSupportedException>(() => ((IList<PublicOperationPolicy>)PublicOperationCatalog.All)[0] = policies[0]);
        Expect<NotSupportedException>(() => ((IList<string>)policies[0].ActorKinds)[0] = "agent");
        var actors = new[] { "human" };
        var copy = new PublicOperationPolicy("example.read", "example.Service/Read", "account", "Q", "human-owner", "rule#read",
            null, "R1", null, "none", false, null, false, null, "none", true, actors);
        actors[0] = "agent";
        Require(copy.ActorKinds.SequenceEqual(new[] { "human" }) && copy.PatScopes.SequenceEqual(new[] { "example.read" }), "caller arrays are copied");
        Expect<NotSupportedException>(() => ((IList<string>)copy.PatScopes)[0] = "operator.listCases");
        Parallel.For(0, 1_000, index =>
        {
            var policy = PublicOperationCatalog.All[index % PublicOperationCatalog.All.Count];
            Require(PublicOperationCatalog.TryGet(policy.OperationId, out var found) && ReferenceEquals(policy, found), "concurrent immutable lookup");
        });
        Console.WriteLine($"CON.26 validated {policies.Length} compiled operation bindings, complete authored fields, PAT/source negatives and immutable concurrent lookup.");
    }

    private static string? Text(JsonElement row, string field) => row.GetProperty(field).GetString();
    private static void Compare(JsonElement expected, string? literal, string? source, string name) =>
        Require(expected.ValueKind == JsonValueKind.Object ? literal is null && source == Text(expected, "from") : source is null && literal == expected.GetString(), name);
    private static void Compare(JsonElement expected, bool? literal, string? source, string name) =>
        Require(expected.ValueKind == JsonValueKind.Object ? literal is null && source == Text(expected, "from") : source is null && literal == expected.GetBoolean(), name);
    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("CON.26: " + name);
    }
    private static void Expect<T>(Action action) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new InvalidOperationException("CON.26 expected " + typeof(T).Name);
    }
}
