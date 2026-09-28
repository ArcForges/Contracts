// SPDX-License-Identifier: Apache-2.0
using System.Text.RegularExpressions;

// Repository policy checks for the level-2 extension boundary. The allowed PublicApi
// occurrences are the pre-existing generic gateway and the recursively closed value model.
internal static class ExtensionBoundaryCases
{
    private const string PublicApiContent = "public/proto/arcforges/publicapi/v1/content.proto";
    private const string NegativeFixture = "tests/StructureTests/Fixtures/structured-value-first-party-domain.proto";
    private static readonly HashSet<string> ExistingBoundaryFields = new(StringComparer.Ordinal)
    {
        "CapabilityArguments.value", "CapabilityResult.value", "ValueList.items", "ValueEntry.value",
    };

    public static void Run(string root)
    {
        var contractRoots = new[]
        {
            Path.Combine(root, "public", "proto", "arcforges"),
            Path.Combine(root, "internal", "proto", "arcforges"),
        };
        var scanned = 0;
        var violations = new List<string>();
        foreach (var contractRoot in contractRoots)
        {
            if (!Directory.Exists(contractRoot)) throw new DirectoryNotFoundException(contractRoot);
            foreach (var file in Directory.EnumerateFiles(contractRoot, "*.proto", SearchOption.AllDirectories))
            {
                var relative = Path.GetRelativePath(root, file).Replace('\\', '/');
                // The extension protocol is the intended dynamic boundary, not an inward leak.
                if (relative.StartsWith("public/proto/arcforges/extensions/", StringComparison.Ordinal)) continue;
                scanned++;
                violations.AddRange(FindReferences(File.ReadAllText(file), relative));
            }
        }

        if (scanned == 0) throw new InvalidOperationException("No first-party proto contracts were scanned.");
        if (violations.Count != 0)
            throw new InvalidOperationException("StructuredValue leaked into first-party domain/product contracts: " + string.Join(", ", violations));

        var fixturePath = Path.Combine(root, NegativeFixture.Replace('/', Path.DirectorySeparatorChar));
        var fixtureRelative = NegativeFixture;
        var fixtureViolations = FindReferences(File.ReadAllText(fixturePath), fixtureRelative);
        if (fixtureViolations.Count != 1 || !fixtureViolations[0].Contains("FirstPartyDomainCommand", StringComparison.Ordinal))
            throw new InvalidOperationException("The executable first-party-domain negative fixture was not rejected by the containment policy.");

        Console.WriteLine($"StructuredValue containment passed across {scanned} first-party proto files and rejected the negative fixture.");
    }

    private static List<string> FindReferences(string source, string relativePath)
    {
        var code = Regex.Replace(source, @"/\*[\s\S]*?\*/|//[^\r\n]*", string.Empty, RegexOptions.CultureInvariant);
        var tokens = Regex.Matches(code, @"\bmessage\s+([A-Za-z_]\w*)\s*\{|\{|\}|(?:[A-Za-z_]\w*\.)*StructuredValue\b", RegexOptions.CultureInvariant);
        var messages = new Stack<(string Name, int Depth)>();
        var depth = 0;
        var failures = new List<string>();

        foreach (Match token in tokens)
        {
            if (token.Groups[1].Success)
            {
                depth++;
                messages.Push((token.Groups[1].Value, depth));
            }
            else if (token.Value == "{")
            {
                depth++;
            }
            else if (token.Value == "}")
            {
                if (messages.TryPeek(out var message) && message.Depth == depth) messages.Pop();
                depth--;
            }
            else if (relativePath != PublicApiContent
                || !messages.TryPeek(out var owner)
                || !TryGetFieldName(code, token.Index, out var fieldName)
                || !ExistingBoundaryFields.Contains(owner.Name + "." + fieldName))
            {
                failures.Add(relativePath + ":" + (messages.TryPeek(out var current) ? current.Name : "<top-level>"));
            }
        }

        return failures;
    }

    private static bool TryGetFieldName(string source, int typeIndex, out string fieldName)
    {
        var lineStart = source.LastIndexOf('\n', Math.Max(0, typeIndex - 1)) + 1;
        var statementEnd = source.IndexOf(';', typeIndex);
        if (statementEnd < 0)
        {
            fieldName = string.Empty;
            return false;
        }

        var statement = source[lineStart..(statementEnd + 1)];
        var match = Regex.Match(statement, @"\bStructuredValue\s+([A-Za-z_]\w*)\s*=", RegexOptions.CultureInvariant);
        fieldName = match.Success ? match.Groups[1].Value : string.Empty;
        return match.Success;
    }
}
