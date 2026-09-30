// SPDX-License-Identifier: Apache-2.0
using System.Globalization;
using System.Linq;
using System.Text.Json;
using ArcForges.Contracts.PublicApi.V1;
using Google.Protobuf.Reflection;

internal static class Con24ScopeLibraryCases
{
    private static readonly string[] ExpectedIds =
    [
        "projects-use-project-metadata-and-visible-live-sessions-in-one-snapshot",
        "projects-order-equal-commit-times-by-project-id-descending",
        "sessions-count-findings-and-reports-from-committed-owner-filtered-aggregate",
        "sessions-missing-or-hidden-project-returns-not-found",
        "sessions-next-page-rechecks-current-access",
        "get-session-returns-only-committed-metadata-with-cloud-revision-and-time",
        "get-session-unresolved-parent-is-not-reassigned-or-exposed",
        "get-session-tombstone-returns-gone",
        "projects-order-updated-at-primary-before-project-id",
        "sessions-order-updated-at-then-session-id-descending"
    ];

    internal static void Run(string root)
    {
        using var fixtureDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-24-scope-library.json")));
        var fixture = fixtureDocument.RootElement;
        var auth = fixture.GetProperty("authorization");
        Require(fixture.GetProperty("evidenceClass").GetString() == "offline-contract-only-no-owner-service-or-live-workspace", "fixture boundary");
        Require(auth.GetProperty("scope").GetString() == "product-owner" && auth.GetProperty("risk").GetString() == "R1" &&
            auth.GetProperty("idempotency").GetString() == "Q" && auth.GetProperty("compatibility").GetString() == "AO", "fixture authorization facts");
        Require(auth.GetProperty("capability").ValueKind == JsonValueKind.Null && auth.GetProperty("approval").GetString() == "none" &&
            !auth.GetProperty("stepUp").GetBoolean() && !auth.GetProperty("localPresence").GetBoolean() &&
            auth.GetProperty("egress").GetString() == "none" && !auth.GetProperty("patEligible").GetBoolean() &&
            auth.GetProperty("actorKinds").GetArrayLength() == 1 && auth.GetProperty("actorKinds")[0].GetString() == "human", "closed product-owner authorization");

        var service = ScopeService.Descriptor;
        Require(service.FullName == "arcforges.publicapi.v1.ScopeService", "service identity");
        Require(service.Methods.Select(method => method.Name).SequenceEqual(new[] { "ListProjects", "ListSessions", "GetSession" }), "exact three method inventory");
        var operationSpecs = fixture.GetProperty("operations").EnumerateArray().ToArray();
        Require(operationSpecs.Length == 3, "exact fixture RPC inventory");
        foreach (var operation in operationSpecs)
        {
            var methodName = operation.GetProperty("rpc").GetString()!.Split('/').Last();
            var method = service.FindMethodByName(methodName) ?? throw new InvalidOperationException(methodName + " descriptor missing");
            Require(method.InputType.Name == operation.GetProperty("requestType").GetString() &&
                JsonNames(method.InputType, operation.GetProperty("requestFields"), minimumFieldNumber: 1), methodName + " request descriptor matches fixture");
            var value = method.OutputType.FindFieldByNumber(2)?.MessageType ?? throw new InvalidOperationException(methodName + " value descriptor missing");
            Require(value.Name == operation.GetProperty("valueType").GetString() &&
                JsonNames(value, operation.GetProperty("valueFields"), minimumFieldNumber: 10), methodName + " value descriptor matches fixture");
            Require(method.OutputType.Name == operation.GetProperty("responseType").GetString() &&
                JsonNames(method.OutputType, operation.GetProperty("outcomeFields"), minimumFieldNumber: 2), methodName + " response descriptor matches fixture");
        }
        foreach (var method in service.Methods)
        {
            Require(!method.IsClientStreaming && !method.IsServerStreaming, "unary method");
            Require(method.InputType.FindFieldByNumber(1)?.MessageType?.FullName == "arcforges.foundation.v1.RequestMeta", "request envelope");
            Require(method.OutputType.FindFieldByNumber(1)?.MessageType?.FullName == "arcforges.foundation.v1.ResponseMeta", "response envelope");
            Require(Enumerable.All<FieldDescriptor>(method.InputType.Fields.InDeclarationOrder(), field => field.FieldNumber == 1 || field.FieldNumber >= 10), "request payload tags");
            Require(Fields(method.OutputType, ("meta", 1), ("value", 2), ("error", 3), ("encodedBody", 4)), "response field tags");
            var outcome = Enumerable.Where<FieldDescriptor>(method.OutputType.Fields.InFieldNumberOrder(), field => field.FieldNumber >= 2).ToArray();
            Require(outcome.All(field => field.ContainingOneof?.Name == "outcome"), "exclusive response outcome");
            Require(method.OutputType.FindFieldByNumber(4)?.MessageType?.FullName == "arcforges.foundation.v1.EncodedBodyRef", "large read envelope");
        }
        Require(Fields(ScopeServiceListProjectsRequest.Descriptor, ("meta", 1), ("page", 10)), "ListProjects request");
        Require(Fields(ScopeServiceListSessionsRequest.Descriptor, ("meta", 1), ("projectId", 10), ("page", 11)), "ListSessions request");
        Require(Fields(ScopeServiceGetSessionRequest.Descriptor, ("meta", 1), ("sessionId", 10), ("minRevision", 11)), "GetSession request");
        Require(Fields(ScopeServiceListProjectsValue.Descriptor, ("items", 10), ("page", 11)), "ListProjects value");
        Require(Fields(ScopeServiceListSessionsValue.Descriptor, ("items", 10), ("page", 11)), "ListSessions value");
        Require(Fields(ScopeServiceGetSessionValue.Descriptor, ("session", 10), ("revision", 11), ("committedAt", 12)), "GetSession value");
        Require(ScopeServiceListProjectsRequest.Descriptor.FindFieldByNumber(10)?.MessageType?.FullName == "arcforges.foundation.v1.PageRequest", "project page type");
        Require(ScopeServiceListSessionsRequest.Descriptor.FindFieldByNumber(10)?.MessageType?.FullName == "arcforges.foundation.v1.Id", "session-list project identity");
        Require(ScopeServiceGetSessionValue.Descriptor.FindFieldByNumber(10)?.MessageType?.FullName == "arcforges.publicapi.v1.ScopeMetadata", "committed ScopeMetadata result");
        Require(ScopeServiceGetSessionValue.Descriptor.FindFieldByNumber(11)?.MessageType?.FullName == "arcforges.foundation.v1.Revision", "cloud revision result");
        Require(ScopeProjectSummary.Descriptor.FullName == "arcforges.publicapi.v1.ScopeProjectSummary" &&
            Fields(ScopeProjectSummary.Descriptor, ("projectId", 1), ("name", 2), ("sessionCount", 3), ("updatedAt", 4), ("revision", 5)), "project summary fields");
        Require(ScopeSessionSummary.Descriptor.FullName == "arcforges.publicapi.v1.ScopeSessionSummary" &&
            Fields(ScopeSessionSummary.Descriptor, ("sessionId", 1), ("projectId", 2), ("name", 3), ("findingCount", 4), ("reportCount", 5), ("tags", 6), ("updatedAt", 7), ("revision", 8)), "session summary fields");

        using var operationDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/operations/con-24.json")));
        var operationRows = operationDocument.RootElement.GetProperty("operations").EnumerateArray().ToArray();
        Require(operationRows.Length == 3, "exactly three exported operations");
        var operationIds = operationRows.Select(row => row.GetProperty("operationId").GetString()).Order().ToArray();
        Require(operationIds.SequenceEqual(new[] { "scope.getSession", "scope.listProjects", "scope.listSessions" }), "operation ids");
        foreach (var row in operationRows)
        {
            var spec = operationSpecs.Single(item => item.GetProperty("operationId").GetString() == row.GetProperty("operationId").GetString());
            var authorization = row.GetProperty("authorization");
            Require(row.GetProperty("binding").GetString() == "arcforges.publicapi.v1." + spec.GetProperty("rpc").GetString(), "exported RPC binding");
            Require(row.GetProperty("source").GetString() == "public/proto/arcforges/publicapi/v1/scope.proto", "owned operation source");
            Require(row.GetProperty("scope").GetString() == "product-owner" && row.GetProperty("surface").GetString() == "public" &&
                row.GetProperty("profile").GetString() == "human-owner" && row.GetProperty("idempotency").GetString() == "Q", "exported operation classification");
            Require(authorization.GetProperty("risk").GetString() == "R1" && authorization.GetProperty("approval").GetString() == "none" &&
                authorization.GetProperty("capability").ValueKind == JsonValueKind.Null && !authorization.GetProperty("stepUp").GetBoolean() &&
                !authorization.GetProperty("localPresence").GetBoolean() && authorization.GetProperty("egress").GetString() == "none" &&
                !authorization.GetProperty("patEligible").GetBoolean() && authorization.GetProperty("actorKinds").GetArrayLength() == 1 &&
                authorization.GetProperty("actorKinds")[0].GetString() == "human", "exported authorization values");
        }

        var vectors = fixture.GetProperty("vectors").EnumerateArray().ToArray();
        var ids = vectors.Select(vector => vector.GetProperty("id").GetString()!).ToArray();
        Require(ids.Length == ExpectedIds.Length && ids.Distinct(StringComparer.Ordinal).Count() == ids.Length &&
            ids.Order(StringComparer.Ordinal).SequenceEqual(ExpectedIds.Order(StringComparer.Ordinal)), "exact unique fixture vector ids");
        var consumed = new HashSet<string>(StringComparer.Ordinal);
        foreach (var vector in vectors)
        {
            var id = vector.GetProperty("id").GetString()!;
            Require(consumed.Add(id), "no vector is consumed twice: " + id);
            var operation = vector.GetProperty("operationId").GetString();
            switch (id)
            {
                case "projects-use-project-metadata-and-visible-live-sessions-in-one-snapshot":
                    {
                        Require(operation == "scope.listProjects", id + " operation");
                        var source = vector.GetProperty("source"); var expected = vector.GetProperty("expected");
                        Require(source.GetProperty("projectMetadata").GetProperty("projectIdHex").GetString() == expected.GetProperty("projectIdHex").GetString() &&
                            source.GetProperty("projectMetadata").GetProperty("name").GetString() == expected.GetProperty("name").GetString(), id + " metadata source");
                        Require(source.GetProperty("sessionsInListSnapshot").EnumerateArray().Count(session => session.GetProperty("live").GetBoolean() && session.GetProperty("visible").GetBoolean()) == expected.GetProperty("sessionCount").GetInt32(), id + " snapshot count");
                        Require(expected.GetProperty("revision").GetInt32() == source.GetProperty("projectRevision").GetInt32() && expected.GetProperty("updatedAt").GetRawText() == source.GetProperty("projectUpdatedAt").GetRawText(), id + " project-owned revision/time");
                        Require(expected.GetProperty("mustNotUse").GetArrayLength() == 2, id + " no session-derived identity/revision");
                        break;
                    }
                case "projects-order-equal-commit-times-by-project-id-descending":
                    {
                        Require(operation == "scope.listProjects", id + " operation");
                        var sourceProjects = vector.GetProperty("source").GetProperty("projects").EnumerateArray().ToArray();
                        Require(sourceProjects.Length == 3, id + " exact source project count");
                        var commitTimes = sourceProjects.Select(project => (
                            project.GetProperty("updatedAt").GetProperty("unixSeconds").GetString() ?? throw new InvalidOperationException(id + " missing commit time"),
                            project.GetProperty("updatedAt").GetProperty("nanos").GetInt32())).Distinct().ToArray();
                        Require(commitTimes.Length == 1, id + " equal commit times");
                        var derivedVisibleIds = sourceProjects
                            .Where(project => project.GetProperty("hasVisibleLiveSessions").GetBoolean())
                            .OrderByDescending(project => project.GetProperty("projectIdHex").GetString(), StringComparer.Ordinal)
                            .Select(project => project.GetProperty("projectIdHex").GetString() ?? throw new InvalidOperationException(id + " missing project id"))
                            .ToArray();
                        var expectedIds = vector.GetProperty("expectedProjectIdsHex").EnumerateArray().Select(value => value.GetString() ?? throw new InvalidOperationException(id + " missing expected project id")).ToArray();
                        Require(derivedVisibleIds.SequenceEqual(expectedIds, StringComparer.Ordinal), id + " source-derived tie order");
                        Require(expectedIds.SequenceEqual(new[] { "00000000000000000000000000000002", "00000000000000000000000000000001" }, StringComparer.Ordinal), id + " stable tie order");
                        break;
                    }
                case "sessions-count-findings-and-reports-from-committed-owner-filtered-aggregate":
                    {
                        Require(operation == "scope.listSessions", id + " operation");
                        var sourceRows = vector.GetProperty("source").GetProperty("sessionsInListSnapshot").EnumerateArray().Where(row => row.GetProperty("live").GetBoolean() && row.GetProperty("visible").GetBoolean()).ToArray();
                        var expectedRows = vector.GetProperty("expectedItems").EnumerateArray().ToArray();
                        Require(sourceRows.Length == 1 && expectedRows.Length == 1, id + " visible aggregate count");
                        foreach (var key in new[] { "sessionIdHex", "projectIdHex", "name", "findingCount", "reportCount", "tagsHex", "updatedAt", "revision" })
                            Require(sourceRows[0].GetProperty(key).GetRawText() == expectedRows[0].GetProperty(key).GetRawText(), id + " field " + key);
                        break;
                    }
                case "sessions-missing-or-hidden-project-returns-not-found":
                    Require(operation == "scope.listSessions" && !vector.GetProperty("source").GetProperty("projectVisibleToOwner").GetBoolean() &&
                        vector.GetProperty("expected").GetProperty("errorCode").GetString() == "state.not_found" && !vector.GetProperty("expected").GetProperty("itemsExposed").GetBoolean(), id + " hidden project refusal");
                    break;
                case "sessions-next-page-rechecks-current-access":
                    Require(operation == "scope.listSessions" && vector.GetProperty("source").GetProperty("accessRevokedAfterPreviousPage").GetBoolean() &&
                        vector.GetProperty("expected").GetProperty("accessRecheckedOnThisRequest").GetBoolean() &&
                        vector.GetProperty("expected").GetProperty("priorSnapshotDoesNotRestoreRevokedAccess").GetBoolean(), id + " current page authorization");
                    break;
                case "get-session-returns-only-committed-metadata-with-cloud-revision-and-time":
                    Require(operation == "scope.getSession" && vector.GetProperty("expected").GetProperty("sessionType").GetString() == "ScopeMetadata" &&
                        vector.GetProperty("expected").GetProperty("revision").GetInt32() == 9 && !vector.GetProperty("expected").GetProperty("rawCaptureBytesPresent").GetBoolean(), id + " committed read");
                    break;
                case "get-session-unresolved-parent-is-not-reassigned-or-exposed":
                    Require(operation == "scope.getSession" && !vector.GetProperty("source").GetProperty("parentProjectResolved").GetBoolean() &&
                        !vector.GetProperty("expected").GetProperty("visible").GetBoolean() && !vector.GetProperty("expected").GetProperty("reassigned").GetBoolean() &&
                        vector.GetProperty("expected").GetProperty("errorCode").GetString() == "state.not_found", id + " unresolved parent refusal");
                    break;
                case "get-session-tombstone-returns-gone":
                    Require(operation == "scope.getSession" && vector.GetProperty("source").GetProperty("sessionTombstoned").GetBoolean() &&
                        !vector.GetProperty("expected").GetProperty("visible").GetBoolean() && vector.GetProperty("expected").GetProperty("errorCode").GetString() == "state.gone", id + " tombstone disposition");
                    break;
                case "projects-order-updated-at-primary-before-project-id":
                    {
                        Require(operation == "scope.listProjects", id + " operation");
                        var sourceProjects = vector.GetProperty("source").GetProperty("projects").EnumerateArray().ToArray();
                        Require(sourceProjects.Length == 3 && sourceProjects.All(project => project.GetProperty("hasVisibleLiveSessions").GetBoolean()), id + " visible source projects");
                        var instants = sourceProjects.Select(project => (
                            project.GetProperty("updatedAt").GetProperty("unixSeconds").GetString() ?? throw new InvalidOperationException(id + " missing seconds"),
                            project.GetProperty("updatedAt").GetProperty("nanos").GetInt32())).Distinct().ToArray();
                        Require(instants.Length == 3, id + " exact distinct commit instants");
                        Require(instants.Select(instant => instant.Item1).Distinct(StringComparer.Ordinal).Count() == 2, id + " exercises nanosecond ordering within one second");
                        var actual = OrderByUpdatedAtThenIdDescending(sourceProjects, "projectIdHex")
                            .Select(project => project.GetProperty("projectIdHex").GetString() ?? throw new InvalidOperationException(id + " missing project id"))
                            .ToArray();
                        var expectedIds = vector.GetProperty("expectedProjectIdsHex").EnumerateArray().Select(value => value.GetString() ?? throw new InvalidOperationException(id + " missing expected id")).ToArray();
                        Require(actual.SequenceEqual(expectedIds, StringComparer.Ordinal), id + " source-derived primary order");
                        Require(actual.SequenceEqual(new[]
                        {
                            "00000000000000000000000000000001",
                            "00000000000000000000000000000002",
                            "00000000000000000000000000000003"
                        }, StringComparer.Ordinal), id + " fixed updatedAt-first order");
                        break;
                    }
                case "sessions-order-updated-at-then-session-id-descending":
                    {
                        Require(operation == "scope.listSessions", id + " operation");
                        var sourceRows = vector.GetProperty("source").GetProperty("sessionsInListSnapshot").EnumerateArray()
                            .Where(session => session.GetProperty("live").GetBoolean() && session.GetProperty("visible").GetBoolean()).ToArray();
                        Require(sourceRows.Length == 4, id + " visible source rows");
                        var instants = sourceRows.Select(session => (
                            session.GetProperty("updatedAt").GetProperty("unixSeconds").GetString() ?? throw new InvalidOperationException(id + " missing seconds"),
                            session.GetProperty("updatedAt").GetProperty("nanos").GetInt32())).ToArray();
                        Require(instants.Distinct().Count() == 3, id + " exact timestamp set");
                        Require(instants.Count(instant => instant == ("1790593200", 100000000)) == 2, id + " exact ID tie pair");
                        var actual = OrderByUpdatedAtThenIdDescending(sourceRows, "sessionIdHex")
                            .Select(session => session.GetProperty("sessionIdHex").GetString() ?? throw new InvalidOperationException(id + " missing session id"))
                            .ToArray();
                        var expectedIds = vector.GetProperty("expectedSessionIdsHex").EnumerateArray().Select(value => value.GetString() ?? throw new InvalidOperationException(id + " missing expected id")).ToArray();
                        Require(actual.SequenceEqual(expectedIds, StringComparer.Ordinal), id + " source-derived order");
                        Require(actual.SequenceEqual(new[]
                        {
                            "00000000000000000000000000000001",
                            "00000000000000000000000000000004",
                            "00000000000000000000000000000002",
                            "00000000000000000000000000000003"
                        }, StringComparer.Ordinal), id + " fixed timestamp-and-ID order");
                        break;
                    }
                default:
                    throw new InvalidOperationException("Unknown CON.24 vector " + id);
            }
        }
        Require(consumed.SetEquals(ExpectedIds), "every vector is consumed exactly once");
        Console.WriteLine("CON.24: exact ScopeService descriptors, operation scope and all ten independent summary/read vectors passed.");
    }

    private static bool Fields(MessageDescriptor descriptor, params (string JsonName, int Number)[] expected) =>
        Enumerable.OrderBy<FieldDescriptor, int>(descriptor.Fields.InFieldNumberOrder(), field => field.FieldNumber)
            .Select(field => (field.JsonName, field.FieldNumber)).SequenceEqual(expected);

    private static bool JsonNames(MessageDescriptor descriptor, JsonElement expected, int minimumFieldNumber) =>
        Enumerable.OrderBy<FieldDescriptor, int>(
            Enumerable.Where<FieldDescriptor>(descriptor.Fields.InFieldNumberOrder(), field => field.FieldNumber >= minimumFieldNumber),
            field => field.FieldNumber)
            .Select(field => field.JsonName).SequenceEqual(expected.EnumerateArray().Select(item => item.GetString()!));

    private static IOrderedEnumerable<JsonElement> OrderByUpdatedAtThenIdDescending(IEnumerable<JsonElement> rows, string idField) =>
        rows.OrderByDescending(row => long.Parse(row.GetProperty("updatedAt").GetProperty("unixSeconds").GetString()!, CultureInfo.InvariantCulture))
            .ThenByDescending(row => row.GetProperty("updatedAt").GetProperty("nanos").GetInt32())
            .ThenByDescending(row => row.GetProperty(idField).GetString()!, StringComparer.Ordinal);

    private static void Require(bool valid, string reason)
    {
        if (!valid) throw new InvalidOperationException("CON.24 fixture failed: " + reason);
    }
}
