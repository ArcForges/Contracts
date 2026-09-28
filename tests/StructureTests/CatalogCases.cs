// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using Google.Protobuf;
using ArcForges.Contracts.Catalog.V1;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.Validation;

internal static class CatalogCases
{
    public static void Run(string root)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-13-package-catalog.json")));
        var fixture = document.RootElement;
        foreach (var value in fixture.GetProperty("patEligible").EnumerateArray()) Require(CatalogProfile.PatEligible(value.GetString()!), "PAT allowlist");
        foreach (var value in fixture.GetProperty("patDenied").EnumerateArray()) Require(!CatalogProfile.PatEligible(value.GetString()!), "PAT deny");
        foreach (var value in fixture.GetProperty("challenge").EnumerateArray()) Require(CatalogProfile.IsChallenge(value.GetProperty("value").GetString()!) == value.GetProperty("valid").GetBoolean(), "challenge");
        foreach (var value in fixture.GetProperty("domains").EnumerateArray()) Require(CatalogProfile.IsDomain(value.GetProperty("value").GetString()!) == value.GetProperty("valid").GetBoolean(), "domain");

        foreach (var value in fixture.GetProperty("versions").EnumerateArray()) Require(CatalogProfile.IsVersion(value.GetProperty("value").GetString()!) == value.GetProperty("valid").GetBoolean(), "SemVer2");
        var methods = CatalogReflection.Descriptor.Services.Single().Methods;
        var expected = new[] { "Search", "GetPackage", "ListVersions", "RegisterPublisher", "VerifyPublisher", "SubmitVersion", "GetSubmission" };
        Require(methods.Select(m => m.Name).SequenceEqual(expected), "exact seven methods");
        foreach (var method in methods)
        {
            Require(!method.IsClientStreaming && !method.IsServerStreaming, "unary");
            Require(method.InputType.Name == "CatalogService" + method.Name + "Request", "unique input");
            Require(method.OutputType.Name == "CatalogService" + method.Name + "Response", "unique output");
            Require(method.InputType.FindFieldByNumber(1).MessageType == RequestMeta.Descriptor, "request metadata");
            Require(method.OutputType.FindFieldByNumber(1).MessageType == ResponseMeta.Descriptor, "response metadata");
            Require(method.InputType.Fields.InDeclarationOrder().All(f => f.FieldNumber == 1 || f.FieldNumber >= 10), "request business tags");
            var read = method.Name is "Search" or "GetPackage" or "ListVersions" or "GetSubmission";
            Require((method.OutputType.FindFieldByNumber(4) is not null) == read, "encoded-body read-only tag");
            Require(method.OutputType.FindFieldByNumber(2).ContainingOneof.Name == "outcome" && method.OutputType.FindFieldByNumber(3).ContainingOneof.Name == "outcome", "success/error oneof");
        }
        var request = Submit();
        Require(CatalogProfile.IsRequest(request), "typed submit");
        Require(CatalogProfile.IsRequest(CatalogServiceSubmitVersionRequest.Parser.ParseFrom(request.ToByteArray())), "binary roundtrip");
        var baseline = fixture.GetProperty("integrityBase");
        foreach (var item in fixture.GetProperty("integrity").EnumerateArray())
        {
            var field = item.GetProperty("field").GetString();
            string Text(string key) => field == key ? item.GetProperty("value").GetString()! : baseline.GetProperty(key).GetString()!;
            var manifestLicences = Map(baseline.GetProperty("manifestLicences"));
            var archiveLicences = Map(field == "archiveLicences" ? item.GetProperty("value") : baseline.GetProperty("archiveLicences"));
            Require(CatalogProfile.MatchesSubmission(request, Text("packageId"), Text("version"), Text("manifestHash"), Text("archiveDigest"), ulong.Parse(Text("archiveBytes"), System.Globalization.CultureInfo.InvariantCulture), manifestLicences, archiveLicences) == item.GetProperty("valid").GetBoolean(), item.GetProperty("id").GetString()!);
        }
        var noCommand = request.Clone(); noCommand.Meta.CommandId = null;
        Require(!CatalogProfile.MatchesSubmission(request, request.PackageId, request.Version, request.ManifestHash,
            request.Archive.ContentHash, request.Archive.Blob.SizeBytes,
            new Dictionary<string, string>(StringComparer.Ordinal) { ["licences/a.txt"] = "MIT" },
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) { ["LICENCES/A.TXT"] = "MIT" }), "archive paths stay ordinal regardless of caller comparer");
        Require(!CatalogProfile.IsRequest(noCommand), "mutation command required");
        var wrongRevision = request.Clone(); wrongRevision.Meta.ExpectedRev.Value = 1;
        Require(!CatalogProfile.IsRequest(wrongRevision), "new submission absent root revision");
        var native = request.Clone(); native.Archive.Native = new NativeContentRev { Value = 1 };
        Require(!CatalogProfile.IsRequest(native), "archive cloud ownership");
        var hashMismatch = request.Clone(); hashMismatch.Archive.Blob.ContentHash = new string('c', 64);
        Require(!CatalogProfile.IsRequest(hashMismatch), "blob digest consistency");
        Require(CatalogProfile.IsPage(new PageRequest()) && CatalogProfile.IsPage(new PageRequest { Limit = 100 }), "page boundaries");
        Require(!CatalogProfile.IsPage(new PageRequest { Limit = 0 }) && !CatalogProfile.IsPage(new PageRequest { Limit = 101 }), "page refusals");
        var search = new CatalogServiceSearchRequest { Meta = Meta(), Query = string.Concat(Enumerable.Repeat("😀", 256)), Page = new PageRequest() };
        Require(CatalogProfile.IsRequest(search), "256 Unicode scalars"); search.Query += "x";
        Require(!CatalogProfile.IsRequest(search), "257 Unicode scalars");
        search.Query = "\ud800"; Require(!CatalogProfile.IsRequest(search), "unpaired surrogate");
        var publisher = new PublisherView { PublisherId = Id(), Domain = "publisher.example.com", DnsName = "_arcforges-publisher.publisher.example.com", State = "pending", Challenge = "arcforges=" + new string('A', 43), Revision = new Revision { Value = 1 } };
        Require(CatalogProfile.IsPublisher(publisher), "publisher challenge binding"); publisher.DnsName = "attacker.example.com";
        Require(!CatalogProfile.IsPublisher(publisher), "wrong DNS target");
        Require(!ContractShapeValidation.IsValid(new CatalogServiceSearchResponse { Meta = new ResponseMeta { CorrelationId = Id() } }), "missing outcome");
        Console.WriteLine("Catalog: exact 7 unary methods, shared fixture profiles and independent typed boundary cases passed.");
    }
    private static Dictionary<string, string> Map(JsonElement value) => value.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.GetString()!, StringComparer.Ordinal);
    private static Id Id() => new() { Value = ByteString.CopyFrom(Convert.FromHexString("112233445566478899AABBCCDDEEFF00")) };
    private static RequestMeta Meta() => new() { CorrelationId = Id(), CommandId = Id(), ExpectedRev = new Revision { Value = 0 } };
    private static CatalogServiceSubmitVersionRequest Submit() => new()
    {
        Meta = Meta(), SubmissionId = Id(), PublisherId = Id(), PackageId = "com.example.fixture", Version = "1.2.3", ManifestHash = new string('a', 64),
        Archive = new ResourceVersionRef
        {
            Resource = new ResourceRef { RealmId = Id(), OwnerAppId = "catalog", ResourceKind = "package", ResourceId = Id(), Availability = (ResourceAvailability)4 },
            Cloud = new Revision { Value = 1 }, ContentHash = new string('b', 64),
            Blob = new BlobRef { BlobId = Id(), ContentHash = new string('b', 64), SizeBytes = 104857600 }
        }
    };
    private static void Require(bool condition, string name) { if (!condition) throw new InvalidOperationException("Catalog fixture: " + name); }
}
