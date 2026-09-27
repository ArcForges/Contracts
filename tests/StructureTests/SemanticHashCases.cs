// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using ArcForges.Contracts.Foundation;

internal static class SemanticHashCases
{
    internal static void Run(string root)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-17-compat-hash.json")));
        foreach (var vector in document.RootElement.GetProperty("vectors").EnumerateArray())
        {
            var paths = Paths(vector);
            var input = vector.GetProperty("input").GetString()!;
            if (CanonicalSemanticHash.Canonicalize(input, paths) != vector.GetProperty("canonical").GetString()
                || CanonicalSemanticHash.Hash(input, paths) != vector.GetProperty("sha256").GetString())
                throw new InvalidOperationException("Semantic golden mismatch: " + vector.GetProperty("id").GetString());
        }
        foreach (var vector in document.RootElement.GetProperty("invalid").EnumerateArray())
        {
            var refused = false;
            try { CanonicalSemanticHash.Canonicalize(vector.GetProperty("input").GetString()!, Paths(vector)); }
            catch (Exception exception) when (exception is ArgumentException or JsonException or InvalidOperationException) { refused = true; }
            if (!refused) throw new InvalidOperationException("Invalid semantic input accepted: " + vector.GetProperty("id").GetString());
        }
        const string command = """{"schemaVersion":"example-command.v1","operationId":"setValue","realm":"official","workspaceId":"00112233-4455-6677-8899-aabbccddeeff","actorId":"11223344-5566-7788-99aa-bbccddeeff00","revisionKind":"cloud","revisionValue":"1","fields":{"value":null}}""";
        if (CanonicalSemanticHash.Hash(command) == CanonicalSemanticHash.Hash(command.Replace("\"revisionValue\":\"1\"", "\"revisionValue\":\"2\"", StringComparison.Ordinal)))
            throw new InvalidOperationException("Owner revision must affect command identity.");
        Console.WriteLine("Validated shared C#/TypeScript canonical semantic hash golden vectors and refusals.");
    }

    private static HashSet<string> Paths(JsonElement vector) => vector.TryGetProperty("nfcPaths", out var paths)
        ? paths.EnumerateArray().Select(item => item.GetString()!).ToHashSet(StringComparer.Ordinal)
        : new HashSet<string>(StringComparer.Ordinal);
}
