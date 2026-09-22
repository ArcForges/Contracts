# SPDX-License-Identifier: Apache-2.0
"""Emit the selected WP03.01 self-contained wire/profile relationships.

Field presence, scalar bounds and recursive shape checks run before these rules.
No helper performs owner lookup, query evaluation, authorization or computation
over acquisition data. Unknown response data is preserved by the wire codecs;
these checks describe records admitted for use under the supported profile.
"""
from __future__ import annotations


cs_rules = {
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
    "scalarValue": "if (!ScalarSemantics(value)) return false;",
    "scalarPredicate": "if (!PredicateSemantics(value)) return false;",
    "notesFilter": "if (!FilterBounds(value)) return false;",
    "filterGroup": "if (value.Operator == \"not\" ? value.Children.Count != 1 : value.Operator is not (\"all\" or \"any\") || value.Children.Count is < 1 or > 32) return false;",
    "notesQuery": "if (!QuerySemantics(value)) return false;",
    "propertyDefinition": "if (!DefinitionSemantics(value)) return false;",
    "savedView": "if (value.Query.Page.HasCursor || value.Query.HasDatasetToken || value.Query.SavedViewId is not null || value.Query.SavedViewRev is not null || !value.NotebookId.Value.Equals(value.Query.NotebookId.Value)) return false;",
    "notesSelectors": "if (!UniqueIds(value.TagIds.Select(x => x.Value)) || value.BlockKinds.Distinct(global::System.StringComparer.Ordinal).Count() != value.BlockKinds.Count) return false;",
    "notesSelection": "if ((value.LocalVersion is null) == (value.CloudRevision is null) || value.CloudRevision is { Value: <= 0 }) return false;",
    "structuredValue": "if (!StructuredBounds(value)) return false;",
    "valueRecord": "if (!OrderedKeys(value.Entries.Select(x => x.Name))) return false;",
    "tableBlock": "if (!TableSemantics(value)) return false;",
    "richText": "if (!RichTextSemantics(value)) return false;",
    "block": "if (!BlockSemantics(value)) return false;",
    "notesDocument": "if (!DocumentSemantics(value)) return false;",
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
    "linkSpec": "if ((value.TargetId is null) == !value.HasUrl || (value.HasUrl && !SafeLink(value.Url))) return false;",
    "generatedSource": "if ((value.Kind == \"title\") != (value.Text is not null) || (value.Kind == \"title\" && value.Parameters.Count != 0)) return false;",
    "sampleRange": "if (value.From > ulong.MaxValue - value.Count) return false;",
}


ts_rules = {
    "reducedRational": "if (!reduced(value.numerator as bigint, value.denominator as bigint)) return false;",
    "mediaTime": "if ((value.rate as Profile).numerator !== 705600000n || (value.rate as Profile).denominator !== 1n) return false;",
    "mediaRange": "if (!mediaRangeSemantics(value)) return false;",
    "byteRange": "if ((value.length as bigint) === 0n || (value.offset as bigint) + (value.length as bigint) > 18446744073709551615n) return false;",
    "timeRangeUtc": "if (compareInstant(value.from as Profile, value.until as Profile) > 0) return false;",
    "contentOrigin": "if (!originSemantics(value) || toBinary(ContentOriginSchema, value as never).length > 65536) return false;",
    "resourceVersionRef": "if (!resourceVersionSemantics(value)) return false;",
    "retryAdvice": "if ((value.mode === 3) !== (value.retryAt !== undefined) || (value.mode === 4) !== (value.reconciliationOperation !== undefined)) return false;",
    "arcError": "if (!errorSemantics(value)) return false;",
    "scalarValue": "if (!scalarSemantics(value)) return false;",
    "scalarPredicate": "if (!predicateSemantics(value)) return false;",
    "notesFilter": "if (!filterBounds(value)) return false;",
    "filterGroup": "if (value.operator === 'not' ? (value.children as unknown[]).length !== 1 : !['all','any'].includes(value.operator as string) || (value.children as unknown[]).length < 1 || (value.children as unknown[]).length > 32) return false;",
    "notesQuery": "if (!querySemantics(value) || toBinary(NotesQuerySchema, value as never).length > 65536) return false;",
    "propertyDefinition": "if (!definitionSemantics(value)) return false;",
    "savedView": "if (!savedViewSemantics(value)) return false;",
    "notesSelectors": "if (!uniqueIds((value.tagIds ?? []) as Profile[]) || new Set((value.blockKinds ?? []) as string[]).size !== ((value.blockKinds ?? []) as string[]).length) return false;",
    "notesSelection": "if ((value.localVersion === undefined) === (value.cloudRevision === undefined) || (value.cloudRevision !== undefined && (value.cloudRevision as Profile).value <= 0n)) return false;",
    "structuredValue": "if (!structuredBounds(value)) return false;",
    "valueRecord": "if (!orderedKeys(((value.entries ?? []) as Profile[]).map(v => v.name as string))) return false;",
    "tableBlock": "if (!tableSemantics(value)) return false;",
    "richText": "if (!richTextSemantics(value)) return false;",
    "block": "if (!blockSemantics(value)) return false;",
    "notesDocument": "if (!documentSemantics(value)) return false;",
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
    "linkSpec": "if ((value.targetId === undefined) === (value.url === undefined) || (value.url !== undefined && !safeLink(value.url as string))) return false;",
    "generatedSource": "if ((value.kind === 'title') !== (value.text !== undefined) || (value.kind === 'title' && ((value.parameters ?? []) as unknown[]).length !== 0)) return false;",
    "sampleRange": "if ((value.from as bigint) + (value.count as bigint) > 18446744073709551615n) return false;",
}


def ts_imports(names: set[str]) -> str:
    lines = []
    if "arcforges.foundation.v1.ContentOrigin" in names or "arcforges.publicapi.v1.NotesQuery" in names:
        lines.append('import { toBinary } from "@bufbuild/protobuf";')
    if "arcforges.foundation.v1.ContentOrigin" in names:
        lines.append('import { ContentOriginSchema } from "../../gen/arcforges/foundation/v1/foundation_pb.js";')
    if "arcforges.publicapi.v1.NotesQuery" in names:
        lines.append('import { NotesQuerySchema } from "../../gen/arcforges/publicapi/v1/content_pb.js";')
    return "\n".join(lines) + ("\n" if lines else "")


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
    private static bool ScalarSemantics(P.ScalarValue value)
    {
        switch ((int)value.ValueCase)
        {
            case 1: return value.Null;
            case 4: return !value.Number.Value.Contains('.') || !value.Number.Value.EndsWith('0');
            case 5: return value.Date.Length == 10 && global::System.DateOnly.TryParseExact(value.Date, "yyyy-MM-dd", global::System.Globalization.CultureInfo.InvariantCulture, global::System.Globalization.DateTimeStyles.None, out _);
            case 7: return value.MultiSelect.Items.Count <= 100 && OrderedIds(value.MultiSelect.Items.Select(x => x.Value));
            case 8: return value.DateTime.Nanos % 100 == 0;
            default: return true;
        }
    }
    private static bool PredicateSemantics(P.ScalarPredicate value)
    {
        if (value.Operator is "isMissing" or "isPresent") return value.Operands.Count == 0;
        var membership = value.Operator is "in" or "hasAny" or "hasAll";
        if (membership ? value.Operands.Count is < 1 or > 100 : value.Operands.Count != 1) return false;
        var kind = (int)value.Operands[0].ValueCase;
        if (kind == 1 || value.Operands.Any(x => (int)x.ValueCase != kind)) return false;
        if (value.Operands.Any(x => ((int)x.ValueCase == 2 && ScalarLength(x.Text) > 4096) || ((int)x.ValueCase == 9 && ScalarLength(x.Url) > 4096))) return false;
        if (value.Operator is "hasAny" or "hasAll") return kind == 6;
        if (value.Operator is "contains" or "startsWith" or "endsWith") return kind is 2 or 9;
        if (value.Operator is "eq" or "ne") return true;
        return kind != 7 && value.Operator is ("lt" or "le" or "gt" or "ge" or "in");
    }
    private static bool FilterBounds(P.NotesFilter root)
    {
        var pending = new global::System.Collections.Generic.Stack<(P.NotesFilter Node, int Depth)>();
        pending.Push((root, 1));
        var count = 0;
        while (pending.TryPop(out var next))
        {
            if (++count > 128 || next.Depth > 8) return false;
            if ((int)next.Node.ExpressionCase == 1)
                foreach (var child in next.Node.Group.Children) pending.Push((child, next.Depth + 1));
        }
        return true;
    }
    private static bool QuerySemantics(P.NotesQuery value)
    {
        if (value.CalculateSize() > 65536 || (value.SavedViewId is null) != (value.SavedViewRev is null) || value.SavedViewRev is { Value: <= 0 }) return false;
        if (!UniqueIds(value.Projection.Select(x => x.Value)) || !UniqueIds(value.Sorts.Select(x => x.PropertyId.Value)) || !UniqueIds(value.DefinitionVersions.Select(x => x.PropertyId.Value))) return false;
        var definitions = value.DefinitionVersions.Select(x => IdKey(x.PropertyId.Value)).ToHashSet(global::System.StringComparer.Ordinal);
        if (value.DefinitionVersions.Any(x => x.SemanticRevision.Value <= 0) || value.Projection.Any(x => !definitions.Contains(IdKey(x.Value))) || value.Sorts.Any(x => !definitions.Contains(IdKey(x.PropertyId.Value)))) return false;
        if (value.Filter is not null)
        {
            var pending = new global::System.Collections.Generic.Stack<P.NotesFilter>();
            pending.Push(value.Filter);
            var count = 0;
            while (pending.TryPop(out var filter))
            {
                if (++count > 128) return false;
                if ((int)filter.ExpressionCase == 2 && !definitions.Contains(IdKey(filter.Predicate.PropertyId.Value))) return false;
                if ((int)filter.ExpressionCase == 1) foreach (var child in filter.Group.Children) pending.Push(child);
            }
        }
        return true;
    }
    private static bool DefinitionSemantics(P.PropertyDefinition value)
    {
        if (value.SemanticRevision.Value <= 0 || value.Revision.Value <= 0) return false;
        if (value.HasNumberScale && value.Type != "number") return false;
        if (value.Type is not ("select" or "multiSelect") && value.Options.Count != 0) return false;
        return UniqueIds(value.Options.Select(x => x.OptionId.Value)) && value.Options.Select(x => x.Order).Distinct().Count() == value.Options.Count;
    }
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
    private static bool TableSemantics(P.TableBlock value)
    {
        if (value.Rows.Count == 0) return false;
        var width = value.Rows[0].Cells.Count;
        return width is >= 1 and <= 50 && value.Rows.All(x => x.Cells.Count == width) && UniqueIds(value.Rows.Select(x => x.RowId.Value)) && UniqueIds(value.Rows.SelectMany(x => x.Cells).Select(x => x.CellId.Value));
    }
    private static bool Boundary(string text, uint offset) => offset <= text.Length && (offset == 0 || offset == text.Length || !char.IsLowSurrogate(text[(int)offset]));
    private static bool RichTextSemantics(P.RichText value)
    {
        if (!value.Text.IsNormalized(global::System.Text.NormalizationForm.FormC)) return false;
        var length = (uint)value.Text.Length;
        if (length == 0) return value.Runs.Count == 1 && value.Runs[0].From == 0 && value.Runs[0].Until == 0 && value.Atoms.Count == 0 && value.Spans.Count == 0;
        if (!UniqueIds(value.Runs.Select(x => x.RunId.Value).Concat(value.Atoms.Select(x => x.InlineId.Value)))) return false;
        var intervals = new global::System.Collections.Generic.List<(uint From, uint Until)>();
        foreach (var run in value.Runs)
        {
            if (run.From >= run.Until || !Boundary(value.Text, run.From) || !Boundary(value.Text, run.Until)) return false;
            if (value.Text.AsSpan((int)run.From, (int)(run.Until - run.From)).Contains('\uFFFC')) return false;
            intervals.Add((run.From, run.Until));
        }
        foreach (var atom in value.Atoms)
        {
            if (atom.Offset >= length || value.Text[(int)atom.Offset] != '\uFFFC' || ((int)atom.ContentCase == 3 && atom.Math.Display)) return false;
            intervals.Add((atom.Offset, atom.Offset + 1));
        }
        intervals.Sort((a, b) => a.From.CompareTo(b.From));
        uint end = 0;
        foreach (var interval in intervals)
        {
            if (interval.From != end) return false;
            end = interval.Until;
        }
        if (end != length) return false;
        uint spanEnd = 0;
        foreach (var span in value.Spans)
        {
            if (span.From >= span.Until || span.From < spanEnd || !Boundary(value.Text, span.From) || !Boundary(value.Text, span.Until) || span.Marks.Distinct(global::System.StringComparer.Ordinal).Count() != span.Marks.Count) return false;
            spanEnd = span.Until;
        }
        return true;
    }
    private static bool BlockSemantics(P.Block value)
    {
        var body = (int)value.Body.ContentCase;
        var expected = value.Kind switch { "paragraph" or "heading" or "list" or "quote" or "callout" or "toggle" => 1, "code" => 2, "image" or "attachment" => 3, "embed" => 4, "table" => 5, "math" => 6, "divider" => 7, _ => 0 };
        if (expected == 0 || body != expected || (body == 7 && !value.Body.Empty) || (body == 6 && !value.Body.Math.Display)) return false;
        var p = value.Properties;
        if (p is null) return value.Kind is not ("heading" or "list" or "callout" or "image" or "attachment" or "embed");
        if (p.HasHeadingLevel != (value.Kind == "heading") || p.HasListStyle != (value.Kind == "list") || p.HasCalloutKind != (value.Kind == "callout") || p.HasAltText != (value.Kind == "image") || (p.ImageLayout is not null) != (value.Kind == "image") || p.HasAttachmentPresentation != (value.Kind == "attachment") || p.HasEmbedRenderMode != (value.Kind == "embed")) return false;
        return p.HasChecked == (value.Kind == "list" && p.ListStyle == "checklist");
    }
    private static bool DocumentSemantics(P.NotesDocument value)
    {
        if (!UniqueIds(value.Blocks.Select(x => x.BlockId.Value)) || !UniqueIds(value.Properties.Select(x => x.PropertyId.Value)) || !UniqueIds(value.Tags.Select(x => x.Value))) return false;
        var blocks = value.Blocks.ToDictionary(x => IdKey(x.BlockId.Value), global::System.StringComparer.Ordinal);
        var positions = new global::System.Collections.Generic.HashSet<string>(global::System.StringComparer.Ordinal);
        foreach (var block in value.Blocks)
        {
            if (!positions.Add((block.ParentId is null ? "root" : IdKey(block.ParentId.Value)) + ":" + block.OrderKey)) return false;
            var seen = new global::System.Collections.Generic.HashSet<string>(global::System.StringComparer.Ordinal) { IdKey(block.BlockId.Value) };
            var parent = block.ParentId;
            while (parent is not null)
            {
                var id = IdKey(parent.Value);
                if (!seen.Add(id) || !blocks.TryGetValue(id, out var parentBlock)) return false;
                parent = parentBlock.ParentId;
            }
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
function validDate(value: string): boolean {
  if (/^\d{4}-\d{2}-\d{2}$/.exec(value)?.[0] !== value) return false;
  const year = Number(value.slice(0,4)), month = Number(value.slice(5,7)), day = Number(value.slice(8,10));
  if (year < 1 || month < 1 || month > 12) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return day >= 1 && day <= [31,leap ? 29 : 28,31,30,31,30,31,31,30,31,30,31][month - 1]!;
}
function scalarSemantics(value: Profile): boolean {
  const scalar = value.value as Profile;
  switch (scalar.case) {
    case 'null': return scalar.value === true;
    case 'number': return !scalar.value.value.includes('.') || !scalar.value.value.endsWith('0');
    case 'date': return validDate(scalar.value);
    case 'multiSelect': return (scalar.value.items ?? []).length <= 100 && orderedIds(scalar.value.items ?? []);
    case 'dateTime': return scalar.value.nanos % 100 === 0;
    default: return true;
  }
}
function predicateSemantics(value: Profile): boolean {
  const operands = (value.operands ?? []) as Profile[];
  if (['isMissing','isPresent'].includes(value.operator)) return operands.length === 0;
  const membership = ['in','hasAny','hasAll'].includes(value.operator);
  if (membership ? operands.length < 1 || operands.length > 100 : operands.length !== 1) return false;
  const kind = operands[0]!.value.case;
  if (kind === 'null' || operands.some(v => v.value.case !== kind)) return false;
  if (operands.some(v => ['text','url'].includes(v.value.case) && [...v.value.value as string].length > 4096)) return false;
  if (['hasAny','hasAll'].includes(value.operator)) return kind === 'select';
  if (['contains','startsWith','endsWith'].includes(value.operator)) return ['text','url'].includes(kind);
  if (['eq','ne'].includes(value.operator)) return true;
  return kind !== 'multiSelect' && ['lt','le','gt','ge','in'].includes(value.operator);
}
function filterBounds(root: Profile): boolean {
  const pending: [Profile, number][] = [[root, 1]];
  let count = 0;
  while (pending.length) {
    const [node, depth] = pending.pop()!;
    if (++count > 128 || depth > 8) return false;
    if (node.expression.case === 'group') for (const child of node.expression.value.children ?? []) pending.push([child, depth + 1]);
  }
  return true;
}
function querySemantics(value: Profile): boolean {
  if ((value.savedViewId === undefined) !== (value.savedViewRev === undefined) || (value.savedViewRev !== undefined && value.savedViewRev.value <= 0n)) return false;
  const projection = (value.projection ?? []) as Profile[], sorts = (value.sorts ?? []) as Profile[], versions = (value.definitionVersions ?? []) as Profile[];
  if (!uniqueIds(projection) || !uniqueIds(sorts.map(v => v.propertyId)) || !uniqueIds(versions.map(v => v.propertyId))) return false;
  const definitions = new Set(versions.map(v => idKey(v.propertyId)));
  if (versions.some(v => v.semanticRevision.value <= 0n) || projection.some(v => !definitions.has(idKey(v))) || sorts.some(v => !definitions.has(idKey(v.propertyId)))) return false;
  const pending = value.filter === undefined ? [] : [value.filter as Profile];
  let count = 0;
  while (pending.length) {
    const node = pending.pop()!;
    if (++count > 128) return false;
    if (node.expression.case === 'predicate' && !definitions.has(idKey(node.expression.value.propertyId))) return false;
    if (node.expression.case === 'group') pending.push(...node.expression.value.children ?? []);
  }
  return true;
}
function definitionSemantics(value: Profile): boolean {
  const options = (value.options ?? []) as Profile[];
  return value.semanticRevision.value > 0n && value.revision.value > 0n && (value.numberScale === undefined || value.type === 'number') && (['select','multiSelect'].includes(value.type) || options.length === 0) && uniqueIds(options.map(v => v.optionId)) && new Set(options.map(v => v.order)).size === options.length;
}
function savedViewSemantics(value: Profile): boolean {
  return value.query.page.cursor === undefined && value.query.datasetToken === undefined && value.query.savedViewId === undefined && value.query.savedViewRev === undefined && idKey(value.notebookId) === idKey(value.query.notebookId);
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
function tableSemantics(value: Profile): boolean {
  const rows = (value.rows ?? []) as Profile[];
  if (!rows.length) return false;
  const width = (rows[0]!.cells ?? []).length;
  return width >= 1 && width <= 50 && rows.every(v => (v.cells ?? []).length === width) && uniqueIds(rows.map(v => v.rowId)) && uniqueIds(rows.flatMap(v => (v.cells ?? []).map((c: Profile) => c.cellId)));
}
function boundary(text: string, offset: number): boolean { return offset <= text.length && (offset === 0 || offset === text.length || text.charCodeAt(offset) < 0xdc00 || text.charCodeAt(offset) > 0xdfff); }
function richTextSemantics(value: Profile): boolean {
  const text = value.text as string, runs = (value.runs ?? []) as Profile[], atoms = (value.atoms ?? []) as Profile[], spans = (value.spans ?? []) as Profile[];
  if (text.normalize('NFC') !== text) return false;
  if (!text.length) return runs.length === 1 && runs[0]!.from === 0 && runs[0]!.until === 0 && atoms.length === 0 && spans.length === 0;
  if (!uniqueIds([...runs.map(v => v.runId), ...atoms.map(v => v.inlineId)])) return false;
  const intervals: [number, number][] = [];
  for (const run of runs) {
    if (run.from >= run.until || !boundary(text, run.from) || !boundary(text, run.until) || text.slice(run.from, run.until).includes('\uFFFC')) return false;
    intervals.push([run.from, run.until]);
  }
  for (const atom of atoms) {
    if (atom.offset >= text.length || text[atom.offset] !== '\uFFFC' || (atom.content.case === 'math' && atom.content.value.display)) return false;
    intervals.push([atom.offset, atom.offset + 1]);
  }
  intervals.sort((a,b) => a[0] - b[0]);
  let end = 0;
  for (const interval of intervals) { if (interval[0] !== end) return false; end = interval[1]; }
  if (end !== text.length) return false;
  let spanEnd = 0;
  for (const span of spans) {
    if (span.from >= span.until || span.from < spanEnd || !boundary(text, span.from) || !boundary(text, span.until) || new Set(span.marks ?? []).size !== (span.marks ?? []).length) return false;
    spanEnd = span.until;
  }
  return true;
}
function blockSemantics(value: Profile): boolean {
  const expected: Record<string, string> = {paragraph:'text',heading:'text',list:'text',quote:'text',callout:'text',toggle:'text',code:'code',image:'resource',attachment:'resource',embed:'link',table:'table',math:'math',divider:'empty'};
  const body = value.body.content;
  if (expected[value.kind] === undefined || body.case !== expected[value.kind] || (body.case === 'empty' && body.value !== true) || (body.case === 'math' && body.value.display !== true)) return false;
  const p = value.properties as Profile | undefined;
  if (p === undefined) return !['heading','list','callout','image','attachment','embed'].includes(value.kind);
  if ((p.headingLevel !== undefined) !== (value.kind === 'heading') || (p.listStyle !== undefined) !== (value.kind === 'list') || (p.calloutKind !== undefined) !== (value.kind === 'callout') || (p.altText !== undefined) !== (value.kind === 'image') || (p.imageLayout !== undefined) !== (value.kind === 'image') || (p.attachmentPresentation !== undefined) !== (value.kind === 'attachment') || (p.embedRenderMode !== undefined) !== (value.kind === 'embed')) return false;
  return (p.checked !== undefined) === (value.kind === 'list' && p.listStyle === 'checklist');
}
function documentSemantics(value: Profile): boolean {
  const rows = (value.blocks ?? []) as Profile[], properties = (value.properties ?? []) as Profile[];
  if (!uniqueIds(rows.map(v => v.blockId)) || !uniqueIds(properties.map(v => v.propertyId)) || !uniqueIds(value.tags ?? [])) return false;
  const blocks = new Map(rows.map(v => [idKey(v.blockId), v])), positions = new Set<string>();
  for (const block of rows) {
    const position = (block.parentId === undefined ? 'root' : idKey(block.parentId)) + ':' + block.orderKey;
    if (positions.has(position)) return false;
    positions.add(position);
    const seen = new Set([idKey(block.blockId)]);
    let parent = block.parentId as Profile | undefined;
    while (parent !== undefined) {
      const key = idKey(parent), parentBlock = blocks.get(key);
      if (seen.has(key) || parentBlock === undefined) return false;
      seen.add(key); parent = parentBlock.parentId;
    }
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
