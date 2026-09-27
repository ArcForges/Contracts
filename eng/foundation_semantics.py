# SPDX-License-Identifier: Apache-2.0
"""Emit the selected WP03.01 self-contained wire/profile relationships.

Field presence, scalar bounds and recursive shape checks run before these rules.
No helper performs owner lookup, query evaluation, authorization or computation
over acquisition data. Unknown response data is preserved by the wire codecs;
these checks describe records admitted for use under the supported profile.
"""
from __future__ import annotations


cs_rules = {
    "capabilityDescriptor": "if ((int)value.Effect == 1 && value.Writes.Count != 0) return false;",
    "contractVersion": "if (!DescriptorSemver(value.Version)) return false;",
    "contractCompatibility": "if (!DescriptorSemver(value.MinReadable) || !DescriptorSemver(value.MinWritable) || CompareDescriptorVersions(value.MinReadable, value.Contract.Version) > 0 || CompareDescriptorVersions(value.MinWritable, value.Contract.Version) > 0) return false;",
    "compatibilityDescriptor": "if (value.Contracts.Select(x => x.Contract.Key).Distinct(global::System.StringComparer.Ordinal).Count() != value.Contracts.Count || value.Capabilities.Select(x => x.Contract.Key).Distinct(global::System.StringComparer.Ordinal).Count() != value.Capabilities.Count) return false;",
    "encodedBodyRef": "if (!value.Resource.HasContentHash) return false;",
    "reducedRational": "if (!Reduced(value.Numerator, value.Denominator)) return false;",
    "mediaTime": "if (value.Rate.Numerator != 705600000L || value.Rate.Denominator != 1UL) return false;",
    "mediaRange": "if (value.Duration.Ticks < 0 || value.Start.Rate.Numerator != value.Duration.Rate.Numerator || value.Start.Rate.Denominator != value.Duration.Rate.Denominator || (global::System.Numerics.BigInteger)value.Start.Ticks + value.Duration.Ticks > long.MaxValue) return false;",
    "byteRange": "if (value.Length == 0 || value.Offset > ulong.MaxValue - value.Length) return false;",
    "timeRangeUtc": "if (value.From.UnixSeconds > value.Until.UnixSeconds || (value.From.UnixSeconds == value.Until.UnixSeconds && value.From.Nanos > value.Until.Nanos)) return false;",
    "contentOrigin": """if (value.CalculateSize() > 65536 || !OrderedKinds(value.Kinds) || !OrderedIds(value.ParentOriginIds.Select(x => x.Value))) return false;
        if (value.OmittedParentCount > 0 && value.ParentOriginIds.Count != 32) return false;
        if (value.ParentOriginIds.Any(x => x.Value.Equals(value.OriginId.Value))) return false;""",
    "resourceVersionRef": """if ((int)value.RevisionCase == 2 && value.Cloud.Value <= 0) return false;
        if (value.Blob is not null && (!value.HasContentHash || value.ContentHash != value.Blob.ContentHash)) return false;""",
    "retryAdvice": """if (((int)value.Mode == 3) != (value.RetryAt is not null)) return false;
        if (((int)value.Mode == 4) != value.HasReconciliationOperation) return false;""",
    "arcError": """var knownCategory = ErrorCategoryFor(value.Code);
        if (knownCategory != 0 && (int)value.Category != knownCategory) return false;
        if (knownCategory != 0 && value.Code is not ("dependency.unavailable" or "dependency.timeout" or "internal.unexpected" or "resource.parser_failed") && (int)value.Effect != 1) return false;
        if (value.Code == "dependency.timeout" && (int)value.Effect != 3) return false;
        if (value.Code is "entitlement.capacity_exhausted" or "capacity.rate_limited" or "capacity.busy" && (int)value.Retry.Mode != 3) return false;
        if (NoRetryCode(value.Code) && (int)value.Retry.Mode != 1) return false;
        if ((int)value.Effect == 3 && (int)value.Retry.Mode == 3) return false;""",
    "structuredValue": "if (!StructuredBounds(value)) return false;",
    "valueRecord": "if (!OrderedKeys(value.Entries.Select(x => x.Name))) return false;",
    "taskSnapshot": "if (((int)value.State == 3) != ((int)value.ReasonFacet != 1) || value.CompletedSteps > value.TotalSteps) return false;",
    "contextSelector": "if ((int)value.SelectionCase == 1 && !value.Whole) return false;",
    "contextRef": "if (value.Revision is { Value: <= 0 }) return false;",
    "messageView": "if (value.TaskId is not null && value.TurnId is not null) return false;",
    "scopeTime": "if (value.Rate.Numerator <= 0) return false;",
    "measurementWindow": "if (CompareScopeTime(value.Start, value.End) >= 0) return false;",
    "alignmentSpec": "if (!AlignmentSemantics(value)) return false;",
    "cursorResult": "if (!CursorSemantics(value)) return false;",
    "channelDefinition": "if (value.Rate.Numerator <= 0 || (value.Calibration is not null && value.Calibration.Unit != value.Unit)) return false;",
    "scopeConfiguration": "if (!ConfigurationSemantics(value)) return false;",
    "frameConfiguration": "if (!FrameSemantics(value)) return false;",
    "checksumSpec": "if (!ChecksumSemantics(value)) return false;",
    "triggerConfiguration": "if (!TriggerSemantics(value)) return false;",
    "measurementThreshold": "if (!ThresholdSemantics(value)) return false;",
    "measurementValue": "if ((value.Name is \"count\" or \"eventCount\") != ((int)value.ResultCase == 4) || ((int)value.ResultCase == 4 && value.Unit != \"1\")) return false;",
    "familyResult": "if (!FamilySemantics(value)) return false;",
    "measurementRequest": "if (!MeasurementRequestSemantics(value)) return false;",
    "measurementResult": "if (!MeasurementResultSemantics(value)) return false;",
    "pageState": "if (value.HasMore && (!value.HasNextCursor || value.NextCursor.Length == 0)) return false;",
    "sampleRange": "if (value.From > ulong.MaxValue - value.Count) return false;",
}


ts_rules = {
    "capabilityDescriptor": "if (value.effect === 1 && (value.writes as unknown[]).length !== 0) return false;",
    "contractVersion": "if (!descriptorSemver(value.version as string)) return false;",
    "contractCompatibility": "if (!descriptorSemver(value.minReadable as string) || !descriptorSemver(value.minWritable as string) || compareDescriptorVersions(value.minReadable as string, (value.contract as Profile).version) > 0 || compareDescriptorVersions(value.minWritable as string, (value.contract as Profile).version) > 0) return false;",
    "compatibilityDescriptor": "if (new Set((value.contracts as Profile[]).map(x => x.contract.key)).size !== (value.contracts as unknown[]).length || new Set((value.capabilities as Profile[]).map(x => x.contract.key)).size !== (value.capabilities as unknown[]).length) return false;",
    "encodedBodyRef": "if (typeof (value.resource as Profile).contentHash !== 'string') return false;",
    "reducedRational": "if (!reduced(value.numerator as bigint, value.denominator as bigint)) return false;",
    "mediaTime": "if ((value.rate as Profile).numerator !== 705600000n || (value.rate as Profile).denominator !== 1n) return false;",
    "mediaRange": "if (!mediaRangeSemantics(value)) return false;",
    "byteRange": "if ((value.length as bigint) === 0n || (value.offset as bigint) + (value.length as bigint) > 18446744073709551615n) return false;",
    "timeRangeUtc": "if (compareInstant(value.from as Profile, value.until as Profile) > 0) return false;",
    "contentOrigin": "if (!originSemantics(value) || toBinary(ContentOriginSchema, value as never).length > 65536) return false;",
    "resourceVersionRef": "if (!resourceVersionSemantics(value)) return false;",
    "retryAdvice": "if ((value.mode === 3) !== (value.retryAt !== undefined) || (value.mode === 4) !== (value.reconciliationOperation !== undefined)) return false;",
    "arcError": "if (!errorSemantics(value)) return false;",
    "structuredValue": "if (!structuredBounds(value)) return false;",
    "valueRecord": "if (!orderedKeys(((value.entries ?? []) as Profile[]).map(v => v.name as string))) return false;",
    "taskSnapshot": "if ((value.state === 3) !== (value.reasonFacet !== 1) || (value.completedSteps as number) > (value.totalSteps as number)) return false;",
    "contextSelector": "if ((value.selection as Profile).case === 'whole' && (value.selection as Profile).value !== true) return false;",
    "contextRef": "if (value.revision !== undefined && (value.revision as Profile).value <= 0n) return false;",
    "messageView": "if (value.taskId !== undefined && value.turnId !== undefined) return false;",
    "scopeTime": "if ((value.rate as Profile).numerator <= 0n) return false;",
    "measurementWindow": "if (compareScopeTime(value.start as Profile, value.end as Profile) >= 0) return false;",
    "alignmentSpec": "if (!alignmentSemantics(value)) return false;",
    "cursorResult": "if (!cursorSemantics(value)) return false;",
    "channelDefinition": "if ((value.rate as Profile).numerator <= 0n || (value.calibration !== undefined && (value.calibration as Profile).unit !== value.unit)) return false;",
    "scopeConfiguration": "if (!configurationSemantics(value)) return false;",
    "frameConfiguration": "if (!frameSemantics(value)) return false;",
    "checksumSpec": "if (!checksumSemantics(value)) return false;",
    "triggerConfiguration": "if (!triggerSemantics(value)) return false;",
    "measurementThreshold": "if (!thresholdSemantics(value)) return false;",
    "measurementValue": "if (['count','eventCount'].includes(value.name as string) !== ((value.result as Profile).case === 'count') || ((value.result as Profile).case === 'count' && value.unit !== '1')) return false;",
    "familyResult": "if (!familySemantics(value)) return false;",
    "measurementRequest": "if (!measurementRequestSemantics(value)) return false;",
    "measurementResult": "if (!measurementResultSemantics(value)) return false;",
    "pageState": "if (value.hasMore === true && (typeof value.nextCursor !== 'string' || value.nextCursor.length === 0)) return false;",
    "sampleRange": "if ((value.from as bigint) + (value.count as bigint) > 18446744073709551615n) return false;",
}


def ts_imports(names: set[str]) -> str:
    lines = []
    if "arcforges.foundation.v1.ContentOrigin" in names:
        lines.append('import { toBinary } from "@bufbuild/protobuf";')
    if "arcforges.foundation.v1.ContentOrigin" in names:
        lines.append('import { ContentOriginSchema } from "../../gen/arcforges/foundation/v1/foundation_pb.js";')
    return "\n".join(lines) + ("\n" if lines else "")


DESCRIPTOR_CS_HELPERS = r'''
    private static bool DescriptorSemver(string value)
    {
        if (value.Length is < 1 or > 128) return false;
        if (!Matches(value, @"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?")) return false;
        var core = value.Split('+')[0].Split('-', 2);
        return core.Length == 1 || core[1].Split('.').All(x => x.Length == 1 || x[0] != '0' || !x.All(char.IsAsciiDigit));
    }
    private static int CompareDescriptorVersions(string left, string right)
    {
        var a = left.Split('+')[0].Split('-', 2);
        var b = right.Split('+')[0].Split('-', 2);
        var ac = a[0].Split('.'); var bc = b[0].Split('.');
        for (var i = 0; i < 3; i++)
        {
            var result = global::System.Numerics.BigInteger.Parse(ac[i], global::System.Globalization.CultureInfo.InvariantCulture).CompareTo(global::System.Numerics.BigInteger.Parse(bc[i], global::System.Globalization.CultureInfo.InvariantCulture));
            if (result != 0) return result;
        }
        if (a.Length != b.Length) return a.Length == 1 ? 1 : -1;
        if (a.Length == 1) return 0;
        var ap = a[1].Split('.'); var bp = b[1].Split('.');
        for (var i = 0; i < global::System.Math.Min(ap.Length, bp.Length); i++)
        {
            var an = ap[i].All(char.IsAsciiDigit); var bn = bp[i].All(char.IsAsciiDigit);
            var result = an && bn ? global::System.Numerics.BigInteger.Parse(ap[i], global::System.Globalization.CultureInfo.InvariantCulture).CompareTo(global::System.Numerics.BigInteger.Parse(bp[i], global::System.Globalization.CultureInfo.InvariantCulture))
                : an != bn ? (an ? -1 : 1) : global::System.StringComparer.Ordinal.Compare(ap[i], bp[i]);
            if (result != 0) return result;
        }
        return ap.Length.CompareTo(bp.Length);
    }
'''

COMMON_CS_HELPERS = r'''
    private static bool Reduced(long numerator, ulong denominator) => denominator != 0 &&
        global::System.Numerics.BigInteger.GreatestCommonDivisor(global::System.Numerics.BigInteger.Abs(numerator), denominator) == 1;
    private static bool SafeLink(string value)
    {
        var mailto = value.StartsWith("mailto:", global::System.StringComparison.Ordinal);
        var start = mailto ? 7 : value.StartsWith("https://", global::System.StringComparison.Ordinal) ? 8 : value.StartsWith("http://", global::System.StringComparison.Ordinal) ? 7 : -1;
        if (start < 0 || value.Length <= start || (!mailto && value[start] is '/' or '?' or '#')) return false;
        // Share Unicode whitespace plus BOM rejection with TypeScript. A single
        // scan avoids overlapping authority/path quantifiers and backtracking.
        foreach (var character in value)
            if (char.IsWhiteSpace(character) || character == '\uFEFF') return false;
        return true;
    }
    private static string IdKey(global::Google.Protobuf.ByteString value) => global::System.Convert.ToHexString(value.Span);
    private static bool UniqueIds(global::System.Collections.Generic.IEnumerable<global::Google.Protobuf.ByteString> values)
    {
        var seen = new global::System.Collections.Generic.HashSet<global::Google.Protobuf.ByteString>();
        return values.All(seen.Add);
    }
    private static bool OrderedIds(global::System.Collections.Generic.IEnumerable<global::Google.Protobuf.ByteString> values)
    {
        global::Google.Protobuf.ByteString? previous = null;
        foreach (var item in values)
        {
            if (previous is not null && previous.Span.SequenceCompareTo(item.Span) >= 0) return false;
            previous = item;
        }
        return true;
    }
    private static bool OrderedKeys(global::System.Collections.Generic.IEnumerable<string> values)
    {
        string? previous = null;
        foreach (var item in values)
        {
            if (previous is not null && global::System.StringComparer.Ordinal.Compare(previous, item) >= 0) return false;
            previous = item;
        }
        return true;
    }
    private static bool OrderedKinds(global::System.Collections.Generic.IEnumerable<string> values)
    {
        var previous = -1;
        foreach (var item in values)
        {
            var position = item switch { "aiGenerated" => 0, "aiManipulated" => 1, "nonAi" => 2, "unknown" => 3, _ => -1 };
            if (position <= previous) return false;
            previous = position;
        }
        return previous >= 0;
    }
    private static int ErrorCategoryFor(string code) => code switch
    {
        "validation.invalid_request" or "validation.ast_bounds_exceeded" or "validation.unsupported_version" or "validation.invalid_offset" or "media.time_not_representable" => 1,
        "auth.unauthenticated" or "auth.session_expired" or "auth.step_up_required" => 2,
        "auth.local_presence_required" or "perm.capability_denied" or "perm.resource_denied" or "perm.egress_denied" or "perm.approval_required" or "perm.approval_expired" or "perm.lease_expired" => 3,
        "entitlement.no_service_term" or "entitlement.not_entitled" or "entitlement.quota_exceeded" or "entitlement.capacity_exhausted" or "entitlement.extra_credits_required" or "entitlement.credits_exhausted" or "entitlement.request_too_large" or "commerce.supplier_budget_exhausted" => 4,
        "conflict.revision_mismatch" or "conflict.local_changes_pending" or "conflict.duplicate_identifier" or "command.reused_identifier" => 5,
        "state.not_found" or "state.invalid_transition" or "state.gone" or "state.stale_fence" or "sync.cursor_expired" or "sync.bootstrap_expired" or "identity.last_credential" => 6,
        "resource.unavailable" or "resource.integrity_failed" or "resource.upload_expired" or "resource.parser_failed" or "capacity.rate_limited" or "capacity.busy" => 7,
        "dependency.unavailable" or "dependency.timeout" or "provider.declined" or "security.isolation_unavailable" => 8,
        "internal.unexpected" => 9,
        _ => 0,
    };
    private static bool NoRetryCode(string code) => code is
        "auth.unauthenticated" or "auth.session_expired" or "auth.step_up_required" or "auth.local_presence_required" or
        "perm.capability_denied" or "perm.resource_denied" or "perm.egress_denied" or "perm.approval_required" or "perm.approval_expired" or "perm.lease_expired" or
        "entitlement.no_service_term" or "entitlement.not_entitled" or "entitlement.extra_credits_required" or "entitlement.credits_exhausted" or
        "validation.invalid_request" or "validation.ast_bounds_exceeded" or "validation.unsupported_version" or "identity.last_credential" or
        "conflict.duplicate_identifier" or "command.reused_identifier" or "state.not_found" or "state.invalid_transition" or "state.gone" or "resource.integrity_failed";
'''


CS_HELPERS = r'''





    private static bool StructuredBounds(P.StructuredValue root)
    {
        var pending = new global::System.Collections.Generic.Stack<(P.StructuredValue Node, int Depth)>();
        pending.Push((root, 1));
        while (pending.TryPop(out var next))
        {
            if (next.Depth > 16) return false;
            if ((int)next.Node.ValueCase == 1 && !next.Node.Null) return false;
            if ((int)next.Node.ValueCase == 8) foreach (var item in next.Node.List.Items) pending.Push((item, next.Depth + 1));
            if ((int)next.Node.ValueCase == 9) foreach (var item in next.Node.Record.Entries) pending.Push((item.Value, next.Depth + 1));
        }
        return true;
    }





'''.replace("P.", "global::ArcForges.Contracts.PublicApi.V1.")

CS_HELPERS += r'''
    private static int CompareScopeTime(P.ScopeTime a, P.ScopeTime b) =>
        ((global::System.Numerics.BigInteger)a.Ticks * a.Rate.Denominator * b.Rate.Numerator).CompareTo((global::System.Numerics.BigInteger)b.Ticks * b.Rate.Denominator * a.Rate.Numerator);
    private static bool AlignmentSemantics(P.AlignmentSpec value) => value.Kind switch
    {
        "absoluteTime" => value.LeftAnchor is null && value.RightAnchor is null && value.Offset is null && value.EventId is null,
        "trigger" => value.LeftAnchor is not null && value.RightAnchor is not null && value.Offset is null && value.EventId is null,
        "event" => value.LeftAnchor is not null && value.RightAnchor is not null && value.Offset is null && value.EventId is not null,
        "manualOffset" => value.LeftAnchor is null && value.RightAnchor is null && value.Offset is not null && value.EventId is null,
        _ => false,
    };
    private static bool CursorSemantics(P.CursorResult value)
    {
        var a = value.A.Time; var b = value.B.Time; var d = value.DeltaTime;
        var left = (global::System.Numerics.BigInteger)d.Ticks * d.Rate.Denominator * a.Rate.Numerator * b.Rate.Numerator;
        var right = ((global::System.Numerics.BigInteger)b.Ticks * b.Rate.Denominator * a.Rate.Numerator - (global::System.Numerics.BigInteger)a.Ticks * a.Rate.Denominator * b.Rate.Numerator) * d.Rate.Numerator;
        var expected = value.B.Value - value.A.Value;
        return left == right && double.IsFinite(expected) && Math.Abs(value.DeltaValue - expected) <= 1e-12 + 1e-9 * Math.Abs(expected);
    }
    private static bool ConfigurationSemantics(P.ScopeConfiguration value)
    {
        if (!UniqueIds(value.Channels.Select(x => x.ChannelId.Value))) return false;
        var channels = value.Channels.Select(x => IdKey(x.ChannelId.Value)).ToHashSet(global::System.StringComparer.Ordinal);
        if (value.Framing.Fields.Any(x => !channels.Contains(IdKey(x.ChannelId.Value)))) return false;
        return value.Trigger?.ChannelId is null || channels.Contains(IdKey(value.Trigger.ChannelId.Value));
    }
    private static bool FrameSemantics(P.FrameConfiguration value)
    {
        if (!UniqueIds(value.Fields.Select(x => x.ChannelId.Value))) return false;
        var newline = value.End.Span.SequenceEqual(new byte[] { 10 }) || value.End.Span.SequenceEqual(new byte[] { 13, 10 });
        switch (value.Kind)
        {
            case "delimitedText":
                return value.Start.Length <= 16 && value.End.Length is >= 1 and <= 16 && !value.HasDelimiter && !value.HasFrameBytes && !value.Header && value.Fields.All(x => !x.HasOffset && x.JsonPath.Count == 0);
            case "csvLine":
                return value.Start.Length == 0 && newline && !value.HasEscapeByte && value.HasDelimiter && value.Delimiter is 44 or 59 or 9 && !value.HasFrameBytes && value.Fields.All(x => x.HasColumn && !x.HasOffset && x.JsonPath.Count == 0);
            case "jsonLine":
                return value.Start.Length == 0 && newline && !value.HasEscapeByte && !value.HasDelimiter && !value.HasFrameBytes && !value.Header && value.Fields.All(x => !x.HasColumn && !x.HasOffset && x.JsonPath.Count != 0);
            case "canonicalReplay":
                return value.Start.Length == 0 && value.End.Length == 0 && !value.HasEscapeByte && !value.HasDelimiter && !value.HasFrameBytes && !value.Header && value.Fields.Count == 0 && value.Checksum is null;
            case "fixedBinary":
                if (value.Start.Length != 0 || value.End.Length != 0 || value.HasEscapeByte || value.HasDelimiter || value.Header || !value.HasFrameBytes || value.FrameBytes is 0 or > 1048576 || value.ByteOrder is not ("little" or "big")) return false;
                var intervals = new global::System.Collections.Generic.List<(ulong From, ulong Until)>();
                foreach (var field in value.Fields)
                {
                    var width = field.ScalarType switch { "u8" or "i8" or "bool" => 1, "u16" or "i16" => 2, "u32" or "i32" or "f32" => 4, "u64" or "i64" or "f64" => 8, _ => 0 };
                    if (width == 0 || !field.HasOffset || field.HasColumn || field.JsonPath.Count != 0 || (ulong)field.Offset + (uint)width > value.FrameBytes) return false;
                    var end = (ulong)field.Offset + (uint)width;
                    if (intervals.Any(x => field.Offset < x.Until && x.From < end)) return false;
                    intervals.Add((field.Offset, end));
                }
                if (value.Checksum is not null)
                {
                    var width = value.Checksum.Algorithm switch { "xor8" => 1, "crc16CcittFalse" => 2, "crc32IsoHdlc" => 4, _ => -1 };
                    if (width < 0 || (ulong)value.Checksum.Offset + (uint)width > value.FrameBytes || value.Checksum.Input.Offset + value.Checksum.Input.Length > value.FrameBytes) return false;
                }
                return true;
            default: return false;
        }
    }
    private static bool ChecksumSemantics(P.ChecksumSpec value)
    {
        var width = value.Algorithm switch { "xor8" => 1UL, "crc16CcittFalse" => 2UL, "crc32IsoHdlc" => 4UL, _ => 0UL };
        return width != 0 && (value.ByteOrder is "little" or "big") &&
            (value.Input.Offset + value.Input.Length <= value.Offset || (ulong)value.Offset + width <= value.Input.Offset);
    }
    private static bool TriggerSemantics(P.TriggerConfiguration value)
    {
        if (value.Hysteresis < 0 || value.Holdoff.Ticks < 0 || value.Pre.Ticks < 0 || value.Post.Ticks < 0 || value.MaxOccurrences == 0 || (!value.Repeated && value.MaxOccurrences != 1)) return false;
        return value.Kind switch
        {
            "manual" => value.ChannelId is null && !value.HasThreshold && !value.HasDirection && value.Hysteresis == 0,
            "edge" => value.ChannelId is not null && value.HasThreshold && value.HasDirection && value.Direction is "rising" or "falling" or "either",
            _ => false,
        };
    }
    private static bool PulseFamily(string family) => family is "frequency" or "dutyCycle" or "riseTime" or "fallTime";
    private static bool ThresholdSemantics(P.MeasurementThreshold value)
    {
        if (!PulseFamily(value.Family)) return false;
        return value.Name switch
        {
            "low" or "high" => true,
            "fraction10" => value.Unit == "1" && value.Value == 0.1,
            "fraction50" => value.Unit == "1" && value.Value == 0.5,
            "fraction90" => value.Unit == "1" && value.Value == 0.9,
            _ => false,
        };
    }
    private static string? FixedUnit(string name) => name switch
    {
        "count" or "eventCount" or "dutyCycle" => "1",
        "duration" or "riseTime" or "fallTime" or "deltaTime" => "s",
        "frequency" => "Hz",
        _ => null,
    };
    private static bool FamilySemantics(P.FamilyResult value)
    {
        if (value.Status != "ok")
        {
            if (value.Values.Count != 0 || !value.HasReason) return false;
            if (value.Status == "invalid") return value.Reason is "invalidTimeOrder" or "invalidConfiguration" or "numericOverflow";
            return value.Status == "insufficient" && (value.Reason switch
            {
                "noFiniteSamples" => value.Family is not ("count" or "duration" or "eventCount"),
                "noCompleteCycle" => value.Family is "frequency" or "dutyCycle",
                "noCompleteEdge" => value.Family is "riseTime" or "fallTime",
                "cursorUnavailable" => value.Family == "cursorDelta",
                _ => false,
            });
        }
        if (value.HasReason) return false;
        if (value.ValidCount == 0 && value.Family is ("minimum" or "maximum" or "mean" or "rms" or "peakToPeak" or "standardDeviation")) return false;
        if (value.Family == "cursorDelta")
        {
            if (value.Values.Count != 2 || !value.Values.Select(x => x.Name).ToHashSet(global::System.StringComparer.Ordinal).SetEquals(new[] { "deltaTime", "deltaValue" })) return false;
        }
        else if (value.Values.Count != 1 || value.Values[0].Name != value.Family) return false;
        foreach (var item in value.Values)
        {
            if (FixedUnit(item.Name) is { } unit && item.Unit != unit) return false;
            if (item.Name == "dutyCycle" && (item.Value < 0 || item.Value > 1)) return false;
            if (item.Name is "duration" or "frequency" && item.Value <= 0) return false;
            if (item.Name is "rms" or "peakToPeak" or "standardDeviation" or "riseTime" or "fallTime" && item.Value < 0) return false;
            if (item.Name == "count" && item.Count != value.ValidCount) return false;
        }
        return true;
    }
    private static bool SourceSemantics(P.MeasurementSource value, P.ScopeConfiguration configuration)
    {
        if (!value.Capture.HasContentHash || !value.Configuration.HasContentHash) return false;
        if (value.Decoder is not null && !value.Decoder.HasContentHash || value.TimeMapping is not null && !value.TimeMapping.HasContentHash || value.EventSet is not null && !value.EventSet.HasContentHash) return false;
        if ((int)value.Configuration.RevisionCase == 3 && value.Configuration.Native.Value != configuration.Revision.Value) return false;
        return configuration.Channels.Any(x => x.ChannelId.Value.Equals(value.ChannelId.Value));
    }
    private static bool ThresholdBindings(global::System.Collections.Generic.IEnumerable<P.MeasurementThreshold> values,
        global::System.Collections.Generic.Dictionary<string, P.ChannelDefinition> channels,
        global::System.Collections.Generic.HashSet<string> families, bool result, bool levels, bool fractions,
        out global::System.Collections.Generic.Dictionary<string, P.MeasurementThreshold> resolved)
    {
        resolved = new(global::System.StringComparer.Ordinal);
        foreach (var threshold in values)
        {
            if (!families.Contains(threshold.Family) || (result && threshold.ChannelId is null)) return false;
            var level = threshold.Name is "low" or "high";
            if (level ? !levels : !fractions) return false;
            var targets = threshold.ChannelId is null ? channels.Where(x => !level || x.Value.Unit == threshold.Unit).Select(x => x.Key).ToArray() : new[] { IdKey(threshold.ChannelId.Value) };
            if (targets.Length == 0) return false;
            foreach (var target in targets)
            {
                if (!channels.TryGetValue(target, out var channel) || (level && threshold.Unit != channel.Unit) || !resolved.TryAdd(target + ":" + threshold.Family + ":" + threshold.Name, threshold)) return false;
            }
        }
        foreach (var (key, threshold) in resolved)
        {
            if (threshold.Name is not ("low" or "high")) continue;
            var prefix = key[..(key.LastIndexOf(':') + 1)];
            if (!resolved.TryGetValue(prefix + "low", out var low) || !resolved.TryGetValue(prefix + "high", out var high) || low.Value >= high.Value) return false;
        }
        return true;
    }
    private static bool MeasurementRequestSemantics(P.MeasurementRequest value)
    {
        if (value.Channels.Count == 0 || !UniqueIds(value.Channels.Select(x => x.Value)) || value.Families.Count == 0 || value.Families.Distinct(global::System.StringComparer.Ordinal).Count() != value.Families.Count) return false;
        if (!SourceSemantics(value.Source, value.Configuration) || !value.Channels.Any(x => x.Value.Equals(value.Source.ChannelId.Value))) return false;
        if ((int)value.Source.Capture.RevisionCase == 3 && value.Source.Capture.Native.Value != value.SourceRevision.Value) return false;
        var available = value.Configuration.Channels.ToDictionary(x => IdKey(x.ChannelId.Value), global::System.StringComparer.Ordinal);
        var channels = new global::System.Collections.Generic.Dictionary<string, P.ChannelDefinition>(global::System.StringComparer.Ordinal);
        foreach (var id in value.Channels)
        {
            if (!available.TryGetValue(IdKey(id.Value), out var channel)) return false;
            channels.Add(IdKey(id.Value), channel);
        }
        var families = value.Families.ToHashSet(global::System.StringComparer.Ordinal);
        if (!ThresholdBindings(value.ReferenceLevels, channels, families, false, true, false, out _) || !ThresholdBindings(value.Thresholds, channels, families, false, false, true, out _)) return false;
        if (families.Contains("cursorDelta") ? value.Cursors.Count != 2 : value.Cursors.Count != 0) return false;
        foreach (var cursor in value.Cursors)
            if (!channels.ContainsKey(IdKey(cursor.ChannelId.Value)) || CompareScopeTime(cursor.Time, value.Window.Start) < 0 || CompareScopeTime(cursor.Time, value.Window.End) >= 0) return false;
        return value.Cursors.Count != 2 || channels[IdKey(value.Cursors[0].ChannelId.Value)].Unit == channels[IdKey(value.Cursors[1].ChannelId.Value)].Unit;
    }
    private static bool MeasurementResultSemantics(P.MeasurementResult value)
    {
        if (!SourceSemantics(value.Source, value.Configuration) || value.RunCount > value.FiniteCount || value.RequestedDuration.Ticks <= 0 || value.CoveredDuration.Ticks < 0 || value.TimingUncertainty.Ticks < 0 || CompareScopeTime(value.CoveredDuration, value.RequestedDuration) > 0) return false;
        if (value.FiniteCount == 0 ? value.RunCount != 0 || value.CoveredDuration.Ticks != 0 : value.RunCount == 0) return false;
        var channels = value.Configuration.Channels.ToDictionary(x => IdKey(x.ChannelId.Value), global::System.StringComparer.Ordinal);
        var pairs = new global::System.Collections.Generic.HashSet<string>(global::System.StringComparer.Ordinal);
        var families = value.Families.Select(x => x.Family).ToHashSet(global::System.StringComparer.Ordinal);
        foreach (var family in value.Families)
        {
            if (!channels.TryGetValue(IdKey(family.ChannelId.Value), out var channel) || !pairs.Add(IdKey(family.ChannelId.Value) + ":" + family.Family)) return false;
            foreach (var item in family.Values)
                if (FixedUnit(item.Name) is null && item.Unit != channel.Unit) return false;
        }
        if (!ThresholdBindings(value.ResolvedThresholds, channels, families, true, true, true, out var resolved)) return false;
        if (resolved.Keys.Any(key => !pairs.Contains(key[..key.LastIndexOf(':')]))) return false;
        foreach (var family in value.Families.Where(x => x.Status == "ok" && PulseFamily(x.Family)))
        {
            var prefix = IdKey(family.ChannelId.Value) + ":" + family.Family + ":";
            if (new[] { "low", "high", "fraction10", "fraction50", "fraction90" }.Any(name => !resolved.ContainsKey(prefix + name))) return false;
        }
        var cursorFamilies = value.Families.Where(x => x.Family == "cursorDelta" && x.Status == "ok").ToArray();
        if ((value.Cursor is not null) != (cursorFamilies.Length != 0)) return false;
        if (value.Cursor is null) return true;
        if (!channels.TryGetValue(IdKey(value.Cursor.A.ChannelId.Value), out var left) || !channels.TryGetValue(IdKey(value.Cursor.B.ChannelId.Value), out var right) || left.Unit != right.Unit) return false;
        var seconds = (double)value.Cursor.DeltaTime.Ticks * value.Cursor.DeltaTime.Rate.Denominator / value.Cursor.DeltaTime.Rate.Numerator;
        foreach (var family in cursorFamilies)
        {
            if (channels[IdKey(family.ChannelId.Value)].Unit != left.Unit) return false;
            foreach (var item in family.Values)
            {
                var expected = item.Name == "deltaTime" ? seconds : value.Cursor.DeltaValue;
                if (Math.Abs(item.Value - expected) > 1e-12 + 1e-9 * Math.Abs(expected)) return false;
            }
        }
        return true;
    }
'''.replace("P.", "global::ArcForges.Contracts.PublicApi.V1.")


DESCRIPTOR_TS_HELPERS = r'''
function descriptorSemver(value: string): boolean {
  if (value.length < 1 || value.length > 128) return false;
  const pattern = /(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?/;
  if (pattern.exec(value)?.[0] !== value) return false;
  const core = value.split('+')[0]!.split(/-(.*)/s);
  return core.length === 1 || core[1]!.split('.').every(x => !/^0[0-9]+$/.test(x));
}
function compareDescriptorVersions(left: string, right: string): number {
  const a = left.split('+')[0]!.split(/-(.*)/s);
  const b = right.split('+')[0]!.split(/-(.*)/s);
  const ac = a[0]!.split('.'); const bc = b[0]!.split('.');
  for (let i = 0; i < 3; i++) {
    const x = BigInt(ac[i]!); const y = BigInt(bc[i]!);
    if (x !== y) return x < y ? -1 : 1;
  }
  if (a.length !== b.length) return a.length === 1 ? 1 : -1;
  if (a.length === 1) return 0;
  const ap = a[1]!.split('.'); const bp = b[1]!.split('.');
  for (let i = 0; i < Math.min(ap.length, bp.length); i++) {
    const x = ap[i]!; const y = bp[i]!;
    const an = /^[0-9]+$/.test(x); const bn = /^[0-9]+$/.test(y);
    if (an && bn) { if (BigInt(x) !== BigInt(y)) return BigInt(x) < BigInt(y) ? -1 : 1; }
    else if (an !== bn) return an ? -1 : 1;
    else if (x !== y) return x < y ? -1 : 1;
  }
  return ap.length - bp.length;
}
'''

TS_HELPERS = r'''
// These helpers follow successful recursive field checks. They never deserialize
// a second wire model or consult an owner store.
type Profile = Record<string, any>;
function reduced(numerator: bigint, denominator: bigint): boolean {
  if (denominator === 0n) return false;
  let a = numerator < 0n ? -numerator : numerator;
  let b = denominator;
  while (b !== 0n) { const r = a % b; a = b; b = r; }
  return a === 1n;
}
function safeLink(value: string): boolean {
  const mailto = value.startsWith('mailto:');
  const start = mailto ? 7 : value.startsWith('https://') ? 8 : value.startsWith('http://') ? 7 : -1;
  if (start < 0 || value.length <= start || (!mailto && '/?#'.includes(value[start]!))) return false;
  // ECMAScript whitespace plus NEL equals C# Unicode whitespace plus BOM.
  // This single-character search is linear; no authority/path backtracking.
  return !/[\s\u0085]/u.test(value);
}
function idKey(value: Profile): string { return Array.from(value.value as Uint8Array, x => x.toString(16).padStart(2, '0')).join(''); }
function uniqueIds(values: Profile[]): boolean { return new Set(values.map(idKey)).size === values.length; }
function orderedKeys(values: string[]): boolean { return values.every((v, i) => i === 0 || values[i - 1]! < v); }
function orderedIds(values: Profile[]): boolean { return orderedKeys(values.map(idKey)); }
function compareInstant(a: Profile, b: Profile): number { return a.unixSeconds < b.unixSeconds ? -1 : a.unixSeconds > b.unixSeconds ? 1 : Math.sign(a.nanos - b.nanos); }
function mediaRangeSemantics(value: Profile): boolean {
  return value.duration.ticks >= 0n && value.start.rate.numerator === value.duration.rate.numerator && value.start.rate.denominator === value.duration.rate.denominator && value.start.ticks + value.duration.ticks <= 9223372036854775807n;
}
function originSemantics(value: Profile): boolean {
  const kinds = ['aiGenerated','aiManipulated','nonAi','unknown'];
  const positions = (value.kinds ?? []).map((k: string) => kinds.indexOf(k)) as number[];
  const parents = (value.parentOriginIds ?? []) as Profile[];
  return positions.length > 0 && positions.every((v, i) => v >= 0 && (i === 0 || positions[i - 1]! < v)) && orderedIds(parents) && (value.omittedParentCount === 0 || parents.length === 32) && parents.every(v => idKey(v) !== idKey(value.originId));
}
function resourceVersionSemantics(value: Profile): boolean {
  return !(value.revision.case === 'cloud' && value.revision.value.value <= 0n) && (value.blob === undefined || (value.contentHash !== undefined && value.contentHash === value.blob.contentHash));
}
const errorCategories: Record<string, number> = {
  'validation.invalid_request':1,'validation.ast_bounds_exceeded':1,'validation.unsupported_version':1,'validation.invalid_offset':1,'media.time_not_representable':1,
  'auth.unauthenticated':2,'auth.session_expired':2,'auth.step_up_required':2,
  'auth.local_presence_required':3,'perm.capability_denied':3,'perm.resource_denied':3,'perm.egress_denied':3,'perm.approval_required':3,'perm.approval_expired':3,'perm.lease_expired':3,
  'entitlement.no_service_term':4,'entitlement.not_entitled':4,'entitlement.quota_exceeded':4,'entitlement.capacity_exhausted':4,'entitlement.extra_credits_required':4,'entitlement.credits_exhausted':4,'entitlement.request_too_large':4,'commerce.supplier_budget_exhausted':4,
  'conflict.revision_mismatch':5,'conflict.local_changes_pending':5,'conflict.duplicate_identifier':5,'command.reused_identifier':5,
  'state.not_found':6,'state.invalid_transition':6,'state.gone':6,'state.stale_fence':6,'sync.cursor_expired':6,'sync.bootstrap_expired':6,'identity.last_credential':6,
  'resource.unavailable':7,'resource.integrity_failed':7,'resource.upload_expired':7,'resource.parser_failed':7,'capacity.rate_limited':7,'capacity.busy':7,
  'dependency.unavailable':8,'dependency.timeout':8,'provider.declined':8,'security.isolation_unavailable':8,'internal.unexpected':9,
};
const noRetryCodes = new Set(['auth.unauthenticated','auth.session_expired','auth.step_up_required','auth.local_presence_required','perm.capability_denied','perm.resource_denied','perm.egress_denied','perm.approval_required','perm.approval_expired','perm.lease_expired','entitlement.no_service_term','entitlement.not_entitled','entitlement.extra_credits_required','entitlement.credits_exhausted','validation.invalid_request','validation.ast_bounds_exceeded','validation.unsupported_version','identity.last_credential','conflict.duplicate_identifier','command.reused_identifier','state.not_found','state.invalid_transition','state.gone','resource.integrity_failed']);
function errorSemantics(value: Profile): boolean {
  const category = Object.hasOwn(errorCategories, value.code as string) ? errorCategories[value.code as string] : undefined;
  if (category !== undefined && value.category !== category) return false;
  if (category !== undefined && !['dependency.unavailable','dependency.timeout','internal.unexpected','resource.parser_failed'].includes(value.code) && value.effect !== 1) return false;
  if (value.code === 'dependency.timeout' && value.effect !== 3) return false;
  if (['entitlement.capacity_exhausted','capacity.rate_limited','capacity.busy'].includes(value.code) && value.retry.mode !== 3) return false;
  if (noRetryCodes.has(value.code) && value.retry.mode !== 1) return false;
  return !(value.effect === 3 && value.retry.mode === 3);
}







function structuredBounds(root: Profile): boolean {
  const pending: [Profile, number][] = [[root,1]];
  while (pending.length) {
    const [node, depth] = pending.pop()!;
    if (depth > 16) return false;
    if (node.value.case === 'null' && node.value.value !== true) return false;
    if (node.value.case === 'list') for (const child of node.value.value.items ?? []) pending.push([child, depth + 1]);
    if (node.value.case === 'record') for (const entry of node.value.value.entries ?? []) pending.push([entry.value, depth + 1]);
  }
  return true;
}





function compareScopeTime(a: Profile, b: Profile): number {
  const left = (a.ticks as bigint) * (a.rate.denominator as bigint) * (b.rate.numerator as bigint);
  const right = (b.ticks as bigint) * (b.rate.denominator as bigint) * (a.rate.numerator as bigint);
  return left < right ? -1 : left > right ? 1 : 0;
}
function alignmentSemantics(value: Profile): boolean {
  const left = value.leftAnchor !== undefined, right = value.rightAnchor !== undefined, offset = value.offset !== undefined, event = value.eventId !== undefined;
  switch (value.kind) {
    case 'absoluteTime': return !left && !right && !offset && !event;
    case 'trigger': return left && right && !offset && !event;
    case 'event': return left && right && !offset && event;
    case 'manualOffset': return !left && !right && offset && !event;
    default: return false;
  }
}
function cursorSemantics(value: Profile): boolean {
  const a = value.a.time, b = value.b.time, d = value.deltaTime;
  const left = (d.ticks as bigint) * (d.rate.denominator as bigint) * (a.rate.numerator as bigint) * (b.rate.numerator as bigint);
  const right = ((b.ticks as bigint) * (b.rate.denominator as bigint) * (a.rate.numerator as bigint) - (a.ticks as bigint) * (a.rate.denominator as bigint) * (b.rate.numerator as bigint)) * (d.rate.numerator as bigint);
  const expected = value.b.value - value.a.value;
  return left === right && Number.isFinite(expected) && Math.abs(value.deltaValue - expected) <= 1e-12 + 1e-9 * Math.abs(expected);
}
function configurationSemantics(value: Profile): boolean {
  const rows = (value.channels ?? []) as Profile[];
  if (!uniqueIds(rows.map(v => v.channelId))) return false;
  const channels = new Set(rows.map(v => idKey(v.channelId)));
  if ((value.framing.fields ?? []).some((v: Profile) => !channels.has(idKey(v.channelId)))) return false;
  return value.trigger?.channelId === undefined || channels.has(idKey(value.trigger.channelId));
}
function frameSemantics(value: Profile): boolean {
  const fields = (value.fields ?? []) as Profile[];
  if (!uniqueIds(fields.map(v => v.channelId))) return false;
  const start = value.start as Uint8Array, end = value.end as Uint8Array;
  const newline = end.length === 1 && end[0] === 10 || end.length === 2 && end[0] === 13 && end[1] === 10;
  switch (value.kind) {
    case 'delimitedText': return start.length <= 16 && end.length >= 1 && end.length <= 16 && value.delimiter === undefined && value.frameBytes === undefined && !value.header && fields.every(v => v.offset === undefined && (v.jsonPath ?? []).length === 0);
    case 'csvLine': return start.length === 0 && newline && value.escapeByte === undefined && [44,59,9].includes(value.delimiter) && value.frameBytes === undefined && fields.every(v => v.column !== undefined && v.offset === undefined && (v.jsonPath ?? []).length === 0);
    case 'jsonLine': return start.length === 0 && newline && value.escapeByte === undefined && value.delimiter === undefined && value.frameBytes === undefined && !value.header && fields.every(v => v.column === undefined && v.offset === undefined && (v.jsonPath ?? []).length !== 0);
    case 'canonicalReplay': return start.length === 0 && end.length === 0 && value.escapeByte === undefined && value.delimiter === undefined && value.frameBytes === undefined && !value.header && fields.length === 0 && value.checksum === undefined;
    case 'fixedBinary': {
      if (start.length || end.length || value.escapeByte !== undefined || value.delimiter !== undefined || value.header || value.frameBytes === undefined || value.frameBytes < 1 || value.frameBytes > 1048576 || !['little','big'].includes(value.byteOrder)) return false;
      const widths: Record<string, number> = {u8:1,i8:1,bool:1,u16:2,i16:2,u32:4,i32:4,f32:4,u64:8,i64:8,f64:8};
      const intervals: [number, number][] = [];
      for (const field of fields) {
        const width = widths[field.scalarType as string];
        if (width === undefined || field.offset === undefined || field.column !== undefined || (field.jsonPath ?? []).length || field.offset + width > value.frameBytes) return false;
        const end = field.offset + width;
        if (intervals.some(([from, until]) => field.offset < until && from < end)) return false;
        intervals.push([field.offset, end]);
      }
      if (value.checksum !== undefined) {
        const checksumWidths: Record<string, number> = {xor8:1,crc16CcittFalse:2,crc32IsoHdlc:4};
        const checksum = value.checksum, width = checksumWidths[checksum.algorithm as string];
        if (width === undefined || checksum.offset + width > value.frameBytes || checksum.input.offset + checksum.input.length > BigInt(value.frameBytes)) return false;
      }
      return true;
    }
    default: return false;
  }
}
function checksumSemantics(value: Profile): boolean {
  const widths: Record<string, bigint> = {xor8:1n,crc16CcittFalse:2n,crc32IsoHdlc:4n};
  const width = widths[value.algorithm as string];
  return width !== undefined && ['little','big'].includes(value.byteOrder) &&
    (value.input.offset + value.input.length <= BigInt(value.offset) || BigInt(value.offset) + width <= value.input.offset);
}
function triggerSemantics(value: Profile): boolean {
  if (value.hysteresis < 0 || value.holdoff.ticks < 0n || value.pre.ticks < 0n || value.post.ticks < 0n || value.maxOccurrences === 0 || (!value.repeated && value.maxOccurrences !== 1)) return false;
  return value.kind === 'manual' ? value.channelId === undefined && value.threshold === undefined && value.direction === undefined && value.hysteresis === 0 : value.kind === 'edge' && value.channelId !== undefined && value.threshold !== undefined && ['rising','falling','either'].includes(value.direction);
}
function pulseFamily(family: string): boolean { return ['frequency','dutyCycle','riseTime','fallTime'].includes(family); }
function thresholdSemantics(value: Profile): boolean {
  if (!pulseFamily(value.family)) return false;
  switch (value.name) {
    case 'low': case 'high': return true;
    case 'fraction10': return value.unit === '1' && value.value === 0.1;
    case 'fraction50': return value.unit === '1' && value.value === 0.5;
    case 'fraction90': return value.unit === '1' && value.value === 0.9;
    default: return false;
  }
}
function fixedUnit(name: string): string | undefined {
  if (['count','eventCount','dutyCycle'].includes(name)) return '1';
  if (['duration','riseTime','fallTime','deltaTime'].includes(name)) return 's';
  return name === 'frequency' ? 'Hz' : undefined;
}
function familySemantics(value: Profile): boolean {
  const values = (value.values ?? []) as Profile[];
  if (value.status !== 'ok') {
    if (values.length || value.reason === undefined) return false;
    if (value.status === 'invalid') return ['invalidTimeOrder','invalidConfiguration','numericOverflow'].includes(value.reason);
    if (value.status !== 'insufficient') return false;
    switch (value.reason) {
      case 'noFiniteSamples': return !['count','duration','eventCount'].includes(value.family);
      case 'noCompleteCycle': return ['frequency','dutyCycle'].includes(value.family);
      case 'noCompleteEdge': return ['riseTime','fallTime'].includes(value.family);
      case 'cursorUnavailable': return value.family === 'cursorDelta';
      default: return false;
    }
  }
  if (value.reason !== undefined) return false;
  if (value.validCount === 0n && ['minimum','maximum','mean','rms','peakToPeak','standardDeviation'].includes(value.family)) return false;
  if (value.family === 'cursorDelta') {
    if (values.length !== 2 || !values.some(v => v.name === 'deltaTime') || !values.some(v => v.name === 'deltaValue')) return false;
  } else if (values.length !== 1 || values[0]!.name !== value.family) return false;
  for (const item of values) {
    const unit = fixedUnit(item.name);
    if (unit !== undefined && item.unit !== unit) return false;
    if (item.name === 'dutyCycle' && (item.result.value < 0 || item.result.value > 1)) return false;
    if (['duration','frequency'].includes(item.name) && item.result.value <= 0) return false;
    if (['rms','peakToPeak','standardDeviation','riseTime','fallTime'].includes(item.name) && item.result.value < 0) return false;
    if (item.name === 'count' && item.result.value !== value.validCount) return false;
  }
  return true;
}
function sourceSemantics(value: Profile, configuration: Profile): boolean {
  if (value.capture.contentHash === undefined || value.configuration.contentHash === undefined) return false;
  if ([value.decoder,value.timeMapping,value.eventSet].some(v => v !== undefined && v.contentHash === undefined)) return false;
  if (value.configuration.revision.case === 'native' && value.configuration.revision.value.value !== configuration.revision.value) return false;
  return (configuration.channels ?? []).some((v: Profile) => idKey(v.channelId) === idKey(value.channelId));
}
function thresholdBindings(values: Profile[], channels: Map<string, Profile>, families: Set<string>, result: boolean, levels: boolean, fractions: boolean): Map<string, Profile> | undefined {
  const resolved = new Map<string, Profile>();
  for (const threshold of values) {
    if (!families.has(threshold.family) || (result && threshold.channelId === undefined)) return undefined;
    const level = ['low','high'].includes(threshold.name);
    if (level ? !levels : !fractions) return undefined;
    const targets = threshold.channelId === undefined ? [...channels].filter(([, channel]) => !level || channel.unit === threshold.unit).map(([key]) => key) : [idKey(threshold.channelId)];
    if (!targets.length) return undefined;
    for (const target of targets) {
      const channel = channels.get(target), key = target + ':' + threshold.family + ':' + threshold.name;
      if (channel === undefined || (level && threshold.unit !== channel.unit) || resolved.has(key)) return undefined;
      resolved.set(key, threshold);
    }
  }
  for (const [key, threshold] of resolved) {
    if (!['low','high'].includes(threshold.name)) continue;
    const prefix = key.slice(0,key.lastIndexOf(':') + 1), low = resolved.get(prefix + 'low'), high = resolved.get(prefix + 'high');
    if (low === undefined || high === undefined || low.value >= high.value) return undefined;
  }
  return resolved;
}
function measurementRequestSemantics(value: Profile): boolean {
  const ids = (value.channels ?? []) as Profile[], requested = (value.families ?? []) as string[], cursors = (value.cursors ?? []) as Profile[];
  if (!ids.length || !uniqueIds(ids) || !requested.length || new Set(requested).size !== requested.length) return false;
  if (!sourceSemantics(value.source, value.configuration) || !ids.some(v => idKey(v) === idKey(value.source.channelId))) return false;
  if (value.source.capture.revision.case === 'native' && value.source.capture.revision.value.value !== value.sourceRevision.value) return false;
  const available = new Map<string, Profile>(((value.configuration.channels ?? []) as Profile[]).map(v => [idKey(v.channelId),v])), channels = new Map<string, Profile>();
  for (const id of ids) { const key = idKey(id), channel = available.get(key); if (channel === undefined) return false; channels.set(key,channel); }
  const families = new Set(requested);
  if (thresholdBindings(value.referenceLevels ?? [], channels, families, false,true,false) === undefined || thresholdBindings(value.thresholds ?? [], channels, families, false,false,true) === undefined) return false;
  if (families.has('cursorDelta') ? cursors.length !== 2 : cursors.length !== 0) return false;
  for (const cursor of cursors) if (!channels.has(idKey(cursor.channelId)) || compareScopeTime(cursor.time,value.window.start) < 0 || compareScopeTime(cursor.time,value.window.end) >= 0) return false;
  return cursors.length !== 2 || channels.get(idKey(cursors[0]!.channelId))!.unit === channels.get(idKey(cursors[1]!.channelId))!.unit;
}
function measurementResultSemantics(value: Profile): boolean {
  if (!sourceSemantics(value.source,value.configuration) || value.runCount > value.finiteCount || value.requestedDuration.ticks <= 0n || value.coveredDuration.ticks < 0n || value.timingUncertainty.ticks < 0n || compareScopeTime(value.coveredDuration,value.requestedDuration) > 0) return false;
  if (value.finiteCount === 0n ? value.runCount !== 0n || value.coveredDuration.ticks !== 0n : value.runCount === 0n) return false;
  const channels = new Map<string, Profile>(((value.configuration.channels ?? []) as Profile[]).map(v => [idKey(v.channelId),v])), pairs = new Set<string>(), rows = (value.families ?? []) as Profile[], families = new Set<string>(rows.map(v => v.family));
  for (const family of rows) {
    const channel = channels.get(idKey(family.channelId)), pair = idKey(family.channelId) + ':' + family.family;
    if (channel === undefined || pairs.has(pair)) return false;
    pairs.add(pair);
    for (const item of (family.values ?? []) as Profile[]) if (fixedUnit(item.name) === undefined && item.unit !== channel.unit) return false;
  }
  const resolved = thresholdBindings(value.resolvedThresholds ?? [],channels,families,true,true,true);
  if (resolved === undefined || [...resolved.keys()].some(key => !pairs.has(key.slice(0,key.lastIndexOf(':'))))) return false;
  for (const family of rows.filter(v => v.status === 'ok' && pulseFamily(v.family))) {
    const prefix = idKey(family.channelId) + ':' + family.family + ':';
    if (['low','high','fraction10','fraction50','fraction90'].some(name => !resolved.has(prefix + name))) return false;
  }
  const cursorFamilies = rows.filter(v => v.family === 'cursorDelta' && v.status === 'ok');
  if ((value.cursor !== undefined) !== (cursorFamilies.length !== 0)) return false;
  if (value.cursor === undefined) return true;
  const left = channels.get(idKey(value.cursor.a.channelId)), right = channels.get(idKey(value.cursor.b.channelId));
  if (left === undefined || right === undefined || left.unit !== right.unit) return false;
  const seconds = Number(value.cursor.deltaTime.ticks) * Number(value.cursor.deltaTime.rate.denominator) / Number(value.cursor.deltaTime.rate.numerator);
  for (const family of cursorFamilies) {
    if (channels.get(idKey(family.channelId))!.unit !== left.unit) return false;
    for (const item of family.values as Profile[]) {
      const expected = item.name === 'deltaTime' ? seconds : value.cursor.deltaValue;
      if (Math.abs(item.result.value - expected) > 1e-12 + 1e-9 * Math.abs(expected)) return false;
    }
  }
  return true;
}
'''
