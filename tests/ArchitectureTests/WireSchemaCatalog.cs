// SPDX-License-Identifier: Apache-2.0

using System.Text.Json;
using System.Text.RegularExpressions;

namespace ArcForges.Contracts.ArchitectureTests;

/// <summary>
/// Resolves the authored schema that owns a generated C# source file of a contract package, using only the
/// complete package inventory and the authored schema files it lists. A file whose owner cannot be derived
/// exactly resolves to nothing, so its public types stay unbound and the shared AT-12 rule keeps reporting them.
/// </summary>
internal sealed class WireSchemaCatalog
{
    private const string ValueBoundaries = "public/proto/value-boundaries.json";

    private readonly string _root;
    private readonly Dictionary<string, PackageRow> _packagesByProject;
    private readonly Dictionary<string, List<string>> _schemasByTitle;

    private sealed record PackageRow(string Access, string[] Protos, string[] JsonSchemas);

    private WireSchemaCatalog(string root, Dictionary<string, PackageRow> packagesByProject,
        Dictionary<string, List<string>> schemasByTitle)
    {
        _root = root;
        _packagesByProject = packagesByProject;
        _schemasByTitle = schemasByTitle;
    }

    public static WireSchemaCatalog Read(string root)
    {
        using var manifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/contract-packages.json")));
        var packages = new Dictionary<string, PackageRow>(StringComparer.Ordinal);
        var titles = new Dictionary<string, List<string>>(StringComparer.Ordinal);
        foreach (var row in manifest.RootElement.GetProperty("packages").EnumerateArray()
            .Where(row => row.GetProperty("kind").GetString() == "nuget"))
        {
            string project = Normalize(Path.Combine(row.GetProperty("sourceRoot").GetString()!,
                row.GetProperty("id").GetString() + ".csproj"));
            var package = new PackageRow(row.GetProperty("access").GetString()!,
                Strings(row.GetProperty("proto")), Strings(row.GetProperty("jsonSchemas")));
            packages.Add(project, package);
            foreach (string schema in package.JsonSchemas)
            {
                foreach (string title in GeneratedRootTitles(Path.Combine(root, schema)))
                {
                    if (!titles.TryGetValue(title, out var owners)) titles.Add(title, owners = []);
                    owners.Add(Normalize(schema));
                }
            }
        }

        return new WireSchemaCatalog(root, packages, titles);
    }

    /// <summary>The owning authored schema path (repository relative), or null when it cannot be derived exactly.</summary>
    public string? SchemaFor(string projectPath, string sourcePath, string sourceText)
    {
        if (!_packagesByProject.TryGetValue(Normalize(projectPath), out var package)) return null;
        string relative = Normalize(Path.GetRelativePath(_root, sourcePath));
        string projectRoot = Normalize(Path.GetDirectoryName(projectPath)!) + "/";
        if (!relative.StartsWith(projectRoot, StringComparison.Ordinal)) return null;
        string local = relative[projectRoot.Length..];

        var source = Regex.Match(sourceText, @"^//\s*source:\s*(?<path>[A-Za-z0-9_./-]+\.proto)\s*$", RegexOptions.Multiline);
        if (source.Success && local.StartsWith("Generated/Proto/", StringComparison.Ordinal))
        {
            string suffix = source.Groups["path"].Value;
            var owned = package.Protos.Where(path => Normalize(path).EndsWith("/" + suffix, StringComparison.Ordinal)).ToArray();
            return owned.Length == 1 ? Normalize(owned[0]) : null;
        }

        if (local == "Generated/Shapes/ProtoValidation.g.cs")
        {
            // Shape checks for the package's protobuf messages are generated from the authored constraint sidecar.
            string sidecar = package.Access + "/proto/constraints.json";
            return package.Protos.Length > 0 && File.Exists(Path.Combine(_root, sidecar)) ? sidecar : null;
        }

        if (local.StartsWith("Generated/Shapes/", StringComparison.Ordinal) && local.EndsWith(".g.cs", StringComparison.Ordinal)
            && local.IndexOf('/', "Generated/Shapes/".Length) < 0)
        {
            string name = local["Generated/Shapes/".Length..^".g.cs".Length];
            foreach (string suffix in new[] { "Validator", "Routes", "" })
            {
                if (suffix.Length > 0 && !name.EndsWith(suffix, StringComparison.Ordinal)) continue;
                string title = suffix.Length == 0 ? name : name[..^suffix.Length];
                if (_schemasByTitle.TryGetValue(title, out var owners) && owners.Count == 1) return owners[0];
            }

            return null;
        }

        if (local == "Generated/Services/ContractServices.g.cs")
        {
            // The catalogue lists every authored service of the package; its identity bound to the proto of the first one.
            // Equality of the whole catalogue with the authored services is asserted separately by the architecture tests.
            foreach (string proto in package.Protos)
            {
                string text = File.ReadAllText(Path.Combine(_root, proto));
                if (Regex.IsMatch(text, @"^service\s+[A-Za-z][A-Za-z0-9]*\s*\{", RegexOptions.Multiline)) return Normalize(proto);
            }

            return null;
        }

        if (local == "Generated/Values/Identifiers.g.cs" && File.Exists(Path.Combine(_root, ValueBoundaries)))
        {
            return ValueBoundaries;
        }

        return null;
    }

    /// <summary>The titles that eng/generate_shapes.py gives to the files it emits for one authored root schema.</summary>
    internal static IReadOnlyList<string> GeneratedRootTitles(string schemaPath)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(schemaPath));
        var root = document.RootElement;
        var result = new List<string>();
        if (!root.TryGetProperty("oneOf", out var alternatives))
        {
            if (root.TryGetProperty("title", out var single) && single.GetString() is { Length: > 0 } name) result.Add(name);
            return result;
        }

        root.TryGetProperty("$defs", out var definitions);
        foreach (var alternative in alternatives.EnumerateArray())
        {
            string? reference = alternative.TryGetProperty("$ref", out var value) ? value.GetString() : null;
            if (reference is null || !reference.StartsWith("#/$defs/", StringComparison.Ordinal)) continue;
            if (definitions.ValueKind == JsonValueKind.Object
                && definitions.TryGetProperty(reference["#/$defs/".Length..], out var definition)
                && definition.TryGetProperty("title", out var title) && title.GetString() is { Length: > 0 } rootTitle)
            {
                result.Add(rootTitle);
            }
        }

        // A bundle that declares closed routes also emits one route catalogue named after the bundle itself.
        if (root.TryGetProperty("x-arcforges-routes", out _) && root.TryGetProperty("title", out var bundle)
            && bundle.GetString() is { Length: > 0 } bundleTitle)
        {
            result.Add(bundleTitle);
        }

        return result;
    }

    private static string[] Strings(JsonElement array) => array.EnumerateArray().Select(item => item.GetString()!).ToArray();

    private static string Normalize(string path) => path.Replace('\\', '/');
}
