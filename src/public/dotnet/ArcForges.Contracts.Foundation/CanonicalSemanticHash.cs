// SPDX-License-Identifier: Apache-2.0
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace ArcForges.Contracts.Foundation;

/// <summary>Registry04 semantic JSON for new owner profiles, never protobuf byte hashing.</summary>
public static class CanonicalSemanticHash
{
    /// <summary>
    /// Canonicalizes an owner-projected JSON object with an explicit schemaVersion.
    /// Exact numeric values, UUIDs, hashes and bytes must already use the owner's
    /// canonical string adapters. Numbers are rejected rather than rounded.
    /// NFC is applied only at the supplied RFC6901 string paths. Existing native
    /// content and content-origin hash formats are not routed through this API.
    /// </summary>
    public static string Canonicalize(string json, IReadOnlySet<string>? nfcPaths = null)
    {
        ArgumentNullException.ThrowIfNull(json);
        ValidateScalars(json);
        if (Encoding.UTF8.GetByteCount(json) > 4 * 1024 * 1024)
            throw new ArgumentException("Semantic input exceeds 4 MiB.", nameof(json));
        using var document = JsonDocument.Parse(json, new JsonDocumentOptions { MaxDepth = 32 });
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("schemaVersion", out var profile)
            || profile.ValueKind != JsonValueKind.String || string.IsNullOrEmpty(profile.GetString()))
            throw new ArgumentException("An explicit owner schemaVersion is required.", nameof(json));
        var normalized = new HashSet<string>(StringComparer.Ordinal);
        var output = new StringBuilder();
        Write(root, "", output, nfcPaths, normalized);
        if (nfcPaths is not null && !normalized.SetEquals(nfcPaths))
            throw new ArgumentException("Every normalization path must identify a present string.", nameof(nfcPaths));
        return output.ToString();
    }

    /// <summary>Returns lower-case SHA-256 of the canonical UTF-8 JSON.</summary>
    public static string Hash(string json, IReadOnlySet<string>? nfcPaths = null) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(Canonicalize(json, nfcPaths))));

    private static void Write(JsonElement value, string path, StringBuilder output,
        IReadOnlySet<string>? nfcPaths, HashSet<string> normalized)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                var properties = value.EnumerateObject().ToArray();
                var names = new HashSet<string>(StringComparer.Ordinal);
                foreach (var property in properties)
                {
                    if (!names.Add(property.Name) || property.Name.Any(c => c > 127))
                        throw new ArgumentException("Duplicate or non-ASCII semantic property name.");
                }
                Array.Sort(properties, (left, right) => StringComparer.Ordinal.Compare(left.Name, right.Name));
                output.Append('{');
                for (var index = 0; index < properties.Length; index++)
                {
                    if (index != 0) output.Append(',');
                    var property = properties[index];
                    Quote(property.Name, output);
                    output.Append(':');
                    Write(property.Value, path + "/" + property.Name.Replace("~", "~0", StringComparison.Ordinal)
                        .Replace("/", "~1", StringComparison.Ordinal), output, nfcPaths, normalized);
                }
                output.Append('}');
                break;
            case JsonValueKind.Array:
                output.Append('[');
                var itemIndex = 0;
                foreach (var item in value.EnumerateArray())
                {
                    if (itemIndex != 0) output.Append(',');
                    Write(item, path + "/" + itemIndex.ToString(System.Globalization.CultureInfo.InvariantCulture), output, nfcPaths, normalized);
                    itemIndex++;
                }
                output.Append(']');
                break;
            case JsonValueKind.String:
                var text = value.GetString()!;
                ValidateScalars(text);
                if (nfcPaths?.Contains(path) == true)
                {
                    text = text.Normalize(NormalizationForm.FormC);
                    normalized.Add(path);
                }
                Quote(text, output);
                break;
            case JsonValueKind.True: output.Append("true"); break;
            case JsonValueKind.False: output.Append("false"); break;
            case JsonValueKind.Null: output.Append("null"); break;
            default: throw new ArgumentException("Semantic numbers must use exact canonical strings.");
        }
    }

    private static void ValidateScalars(string value)
    {
        for (var index = 0; index < value.Length; index++)
        {
            if (!char.IsSurrogate(value[index])) continue;
            if (!char.IsHighSurrogate(value[index]) || index + 1 >= value.Length || !char.IsLowSurrogate(value[index + 1]))
                throw new ArgumentException("Unpaired surrogate in semantic input.");
            index++;
        }
    }

    private static void Quote(string value, StringBuilder output)
    {
        ValidateScalars(value);
        output.Append('"');
        foreach (var character in value)
        {
            switch (character)
            {
                case '"': output.Append("\\\""); break;
                case '\\': output.Append("\\\\"); break;
                case '\b': output.Append("\\b"); break;
                case '\f': output.Append("\\f"); break;
                case '\n': output.Append("\\n"); break;
                case '\r': output.Append("\\r"); break;
                case '\t': output.Append("\\t"); break;
                default:
                    if (character < 32) output.Append("\\u").Append(((int)character).ToString("x4", System.Globalization.CultureInfo.InvariantCulture));
                    else output.Append(character);
                    break;
            }
        }
        output.Append('"');
    }
}
