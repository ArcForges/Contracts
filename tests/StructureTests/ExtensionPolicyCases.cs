// SPDX-License-Identifier: Apache-2.0
using System.Text;
using System.Text.Json;
using ArcForges.Contracts.Validation;
using ArcForges.Contracts.CloudInternal.Http.V1;

// Executes independently authored fixtures against generated, source-generated codecs.
internal static class ExtensionPolicyCases
{
    private static readonly HashSet<string> ExpectedSchemas = new(StringComparer.Ordinal)
    {
        "ExtensionManifest", "ExtensionWorkflow", "DeclarativePanel", "PolicyBody", "ConfigurationDocument",
    };

    public static void Run(string root)
    {
        using var fixture = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/public/con-12-extension-policy.json")));
        using var privateFixture = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "fixtures/internal/con-12-configuration.json")));
        var publicCases = fixture.RootElement.GetProperty("codecCases").EnumerateArray().ToArray();
        var privateCases = privateFixture.RootElement.GetProperty("codecCases").EnumerateArray().ToArray();
        if (publicCases.Any(item => item.GetProperty("schema").GetString() == "ConfigurationDocument")
            || privateCases.Any(item => item.GetProperty("schema").GetString() != "ConfigurationDocument"))
            throw new InvalidOperationException("Public/private extension-policy fixture boundary is invalid.");
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var count = 0;
        foreach (var item in publicCases.Concat(privateCases))
        {
            var id = item.GetProperty("id").GetString()!;
            var schema = item.GetProperty("schema").GetString()!;
            var value = item.GetProperty("value");
            var bytes = Encoding.UTF8.GetBytes(value.GetRawText());
            var valid = item.GetProperty("valid").GetBoolean();
            seen.Add(schema);
            switch (schema)
            {
                case "ExtensionManifest":
                    Check(id, value, bytes, valid, input => ExtensionManifestJson.TryParse(input, out var parsed, out _)
                        ? (true, ExtensionManifestJson.Serialize(parsed!)) : (false, null));
                    break;
                case "ExtensionWorkflow":
                    Check(id, value, bytes, valid, input => ExtensionWorkflowJson.TryParse(input, out var parsed, out _)
                        ? (true, ExtensionWorkflowJson.Serialize(parsed!)) : (false, null));
                    break;
                case "DeclarativePanel":
                    Check(id, value, bytes, valid, input => DeclarativePanelJson.TryParse(input, out var parsed, out _)
                        ? (true, DeclarativePanelJson.Serialize(parsed!)) : (false, null));
                    break;
                case "PolicyBody":
                    Check(id, value, bytes, valid, input => PolicyBodyJson.TryParse(input, out var parsed, out _)
                        ? (true, PolicyBodyJson.Serialize(parsed!)) : (false, null));
                    break;
                case "ConfigurationDocument":
                    Check(id, value, bytes, valid, input => ConfigurationDocumentJson.TryParse(input, out var parsed, out _)
                        ? (true, ConfigurationDocumentJson.Serialize(parsed!)) : (false, null));
                    break;
                default:
                    throw new InvalidOperationException($"Unknown extension/policy fixture schema: {schema}");
            }
            count++;
        }
        if (!seen.SetEquals(ExpectedSchemas)) throw new InvalidOperationException("Extension/policy codec fixtures must exercise all five roots.");
        Console.WriteLine($"Extension/policy generated C# codecs passed {count} independent cases across {seen.Count} roots.");
    }

    private static void Check(string id, JsonElement original, byte[] input, bool valid,
        Func<ReadOnlyMemory<byte>, (bool Accepted, byte[]? Bytes)> parseAndSerialize)
    {
        var result = parseAndSerialize(input);
        if (result.Accepted != valid)
            throw new InvalidOperationException($"Extension/policy case {id}: expected accepted={valid}, actual={result.Accepted}.");
        if (!valid) return;
        if (result.Bytes is null) throw new InvalidOperationException($"Extension/policy case {id}: accepted codec emitted no bytes.");
        using var output = JsonDocument.Parse(result.Bytes);
        if (!JsonElement.DeepEquals(original, output.RootElement))
            throw new InvalidOperationException($"Extension/policy case {id}: typed roundtrip changed the independent document.");
        var second = parseAndSerialize(result.Bytes);
        if (!second.Accepted || second.Bytes is null || !second.Bytes.AsSpan().SequenceEqual(result.Bytes))
            throw new InvalidOperationException($"Extension/policy case {id}: generated serialization is not stable.");
    }
}

