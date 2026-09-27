// SPDX-License-Identifier: Apache-2.0
using System.Text.RegularExpressions;
using ArcForges.Contracts.Catalog.V1;
using ArcForges.Contracts.Foundation.V1;
using Google.Protobuf;

namespace ArcForges.Contracts.Validation;

/// <summary>Offline catalog facts only; never DNS, authorization, archive inspection or publication.</summary>
public static class CatalogProfile
{
    /// <summary>The public catalog archive limit, independent of the general package ZIP limit.</summary>
    public const ulong MaximumArchiveBytes = 100UL * 1024 * 1024;

    /// <summary>Catalog's exact subset of the operation catalogue PAT allowlist.</summary>
    public static bool PatEligible(string operation) => operation is "catalog.search" or "catalog.getPackage"
        or "catalog.listVersions" or "catalog.submitVersion" or "catalog.getSubmission";

    /// <summary>Checks canonical unpadded encoding of exactly 32 bytes; does not establish entropy or freshness.</summary>
    public static bool IsChallenge(string value) => Match(value, "arcforges=[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]");

    /// <summary>Checks already-normalized ASCII DNS syntax; registrable suffix and ownership require the server resolver.</summary>
    public static bool IsDomain(string value) => value.Length + "_arcforges-publisher.".Length <= 253
        && Match(value, "[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")
        && !Match(value, "[0-9.]+") && !value.EndsWith(".localhost", StringComparison.Ordinal)
        && !value.EndsWith(".local", StringComparison.Ordinal) && !value.EndsWith(".internal", StringComparison.Ordinal);

    /// <summary>Checks the DNS name binding and optional owner challenge of a generated publisher projection.</summary>
    public static bool IsPublisher(PublisherView value) => ContractShapeValidation.IsValid(value)
        && IsDomain(value.Domain) && value.DnsName == "_arcforges-publisher." + value.Domain
        && (!value.HasChallenge || IsChallenge(value.Challenge)) && value.Revision.Value > 0;

    /// <summary>Absent limit means 50; explicit limits must lie in 1..100.</summary>
    public static bool IsPage(PageRequest value) => ContractShapeValidation.IsValid(value)
        && (!value.HasLimit || value.Limit is >= 1 and <= 100);

    /// <summary>Checks generated catalog requests and the declared cloud-revision posture without authenticating a caller.</summary>
    public static bool IsRequest(IMessage value) => value switch
    {
        CatalogServiceSearchRequest v => ContractShapeValidation.IsValid(v) && Read(v.Meta) && IsPage(v.Page),
        CatalogServiceGetPackageRequest v => ContractShapeValidation.IsValid(v) && Read(v.Meta),
        CatalogServiceListVersionsRequest v => ContractShapeValidation.IsValid(v) && Read(v.Meta) && IsPage(v.Page),
        CatalogServiceRegisterPublisherRequest v => ContractShapeValidation.IsValid(v) && Create(v.Meta) && IsDomain(v.Domain),
        CatalogServiceVerifyPublisherRequest v => ContractShapeValidation.IsValid(v) && Write(v.Meta) && v.Meta.ExpectedRev.Value > 0,
        CatalogServiceSubmitVersionRequest v => ContractShapeValidation.IsValid(v) && Create(v.Meta) && IsArchive(v.Archive),
        CatalogServiceGetSubmissionRequest v => ContractShapeValidation.IsValid(v) && Read(v.Meta),
        _ => false
    };

    /// <summary>Compares independently inspected archive/manifest projections with the request; caller must separately verify ownership, signatures and bytes.</summary>
    public static bool MatchesSubmission(CatalogServiceSubmitVersionRequest request, string manifestPackageId,
        string manifestVersion, string manifestHash, string archiveDigest, ulong archiveBytes,
        IReadOnlyDictionary<string, string> manifestLicences, IReadOnlyDictionary<string, string> archiveLicences)
    {
        if (!IsRequest(request) || request.PackageId != manifestPackageId || request.Version != manifestVersion
            || request.ManifestHash != manifestHash || request.Archive.ContentHash != archiveDigest
            || archiveBytes > MaximumArchiveBytes || request.Archive.Blob is { } blob && blob.SizeBytes != archiveBytes)
            return false;
        // Root licence/NOTICE and full payload provenance remain archive-owner responsibilities.
        // This compares every manifest-referenced licence, including content paths; extra archive files do not grant trust.
        foreach (var (path, licence) in manifestLicences)
            if (string.IsNullOrWhiteSpace(path) || string.IsNullOrWhiteSpace(licence)
                || !archiveLicences.TryGetValue(path, out var actual) || actual != licence) return false;
        return true;
    }

    /// <summary>Exact bounded SemVer2 field profile; build metadata is retained in identity comparisons.</summary>
    public static bool IsVersion(string value) => value.Length <= 128 && Match(value,
        @"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?");
    private static bool IsArchive(ResourceVersionRef archive) => archive.RevisionCase == ResourceVersionRef.RevisionOneofCase.Cloud
        && archive.Cloud.Value > 0 && archive.HasContentHash && Match(archive.ContentHash, "[0-9a-f]{64}")
        && (archive.Blob is null || archive.Blob.SizeBytes <= MaximumArchiveBytes && archive.Blob.ContentHash == archive.ContentHash);
    private static bool Read(RequestMeta meta) => meta.ExpectedNative is null;
    private static bool Write(RequestMeta meta) => Read(meta) && meta.CommandId is not null && meta.ExpectedRev is not null;
    private static bool Create(RequestMeta meta) => Write(meta) && meta.ExpectedRev.Value == 0;
    private static bool Match(string value, string pattern)
    {
        var match = Regex.Match(value, pattern, RegexOptions.CultureInvariant | RegexOptions.NonBacktracking, TimeSpan.FromMilliseconds(100));
        return match.Success && match.Index == 0 && match.Length == value.Length;
    }
}
