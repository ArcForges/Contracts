// SPDX-License-Identifier: Apache-2.0
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Google.Protobuf.Reflection;

/// <summary>
/// CON.41 consumer: reads operations/operation-metadata.v1.json exactly as eng/packaging_tools.py staged it for the
/// ArcForges.Contracts.PublicApi package and checks it against the generated C# service descriptors and the gated
/// eng/operations exports. JsonDocument only (duplicate properties refused); no reflection serialization.
/// </summary>
internal static class Con41OperationMetadataCases
{
    private const string SchemaVersion = "operation-metadata.v1";

    // The CON.18 gate's one retained migration example (EXAMPLES in eng/check_operation_scope.py). It is a generated
    // PublicApi method that has no operation row by CON.18's rule, so it is excluded by its exact name only.
    private const string MigrationExample = "arcforges.hello.v1.HelloService/SayHello";

    private static readonly JsonDocumentOptions Strict = new() { AllowDuplicateProperties = false };

    public static int Run(string root, string stagedPath)
    {
        var staged = File.ReadAllBytes(stagedPath);
        var sources = LoadSources(SourcePaths(root));
        var generated = GeneratedMethods(ArcForges.Contracts.PublicApi.ContractServices.All);

        using var document = Parse(staged);
        var rows = Validate(document.RootElement, sources, generated);

        NegativeFixtures(document.RootElement, sources, generated);
        FilesystemOrderFixture(root);

        var byService = new SortedDictionary<string, int>(StringComparer.Ordinal);
        foreach (var row in rows)
        {
            var service = row.GetProperty("binding").GetString()!.Split('/')[0];
            byService[service] = byService.GetValueOrDefault(service) + 1;
        }
        var counts = string.Join(", ", byService.Select(item => item.Key + "=" + item.Value.ToString(System.Globalization.CultureInfo.InvariantCulture)));
        Console.WriteLine($"CON.41 staged operation metadata: {rows.Count} rows, one per generated PublicApi method across {byService.Count} services " +
            $"(migration example {MigrationExample} has no row), each deep-equal to its eng/operations source row; " +
            $"sha256 {Convert.ToHexStringLower(SHA256.HashData(staged))}; by service: {counts}");
        return 0;
    }

    /// <summary>The generated method set, service.FullName/method.Name, minus exactly the retained migration example.</summary>
    private static SortedSet<string> GeneratedMethods(IReadOnlyList<ServiceDescriptor> services)
    {
        var methods = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var service in services)
        {
            foreach (var method in service.Methods)
            {
                Require(methods.Add(service.FullName + "/" + method.Name), "generated: duplicate method " + service.FullName + "/" + method.Name);
            }
        }
        // The exclusion must name a method that exists, so a renamed example cannot silently widen it.
        Require(methods.Remove(MigrationExample), "generated: the retained migration example is not a generated PublicApi method");
        Require(methods.Count > 0, "generated: PublicApi has no generated methods");
        return methods;
    }

    private static string[] SourcePaths(string root)
    {
        var paths = Directory.EnumerateFiles(Path.Combine(root, "eng", "operations"), "*.json", SearchOption.TopDirectoryOnly).ToArray();
        Require(paths.Length > 0, "sources: eng/operations has no exports");
        return paths;
    }

    /// <summary>operationId -> source row for every export row. Files are read in ordinal name order, never filesystem order.</summary>
    private static Dictionary<string, JsonElement> LoadSources(IEnumerable<string> paths)
    {
        var rows = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        foreach (var path in paths.Order(StringComparer.Ordinal))
        {
            var name = Path.GetFileName(path);
            // Clone detaches each row from its document, so the documents can be released here.
            using var export = Parse(File.ReadAllBytes(path));
            var top = export.RootElement;
            Require(top.ValueKind == JsonValueKind.Object && top.TryGetProperty("schemaVersion", out var version) && version.ValueKind == JsonValueKind.String
                && version.GetString() == SchemaVersion && top.TryGetProperty("operations", out var operations) && operations.ValueKind == JsonValueKind.Array,
                "sources: unsupported operation export " + name);
            foreach (var row in top.GetProperty("operations").EnumerateArray())
            {
                if (row.ValueKind != JsonValueKind.Object || !row.TryGetProperty("operationId", out var id) || id.ValueKind != JsonValueKind.String)
                    throw new InvalidOperationException("sources: operation row without operationId in " + name);
                Require(rows.TryAdd(id.GetString()!, row.Clone()), "sources: duplicate operationId " + id.GetString() + " in " + name);
            }
        }
        return rows;
    }

    private static JsonDocument Parse(byte[] utf8)
    {
        Require(!utf8.AsSpan().StartsWith(Encoding.UTF8.Preamble), "staged: UTF-8 byte order mark");
        try
        {
            return JsonDocument.Parse(utf8, Strict);
        }
        catch (JsonException error)
        {
            throw new InvalidOperationException("staged: invalid JSON: " + error.Message, error);
        }
    }

    /// <summary>
    /// The staged document is the closed operation-metadata.v1 export shape; its rows are in strict ordinal operationId
    /// order, are public proto rows, bind generated PublicApi methods one-to-one and are deep-equal (values and property
    /// order) to their eng/operations source rows.
    /// </summary>
    private static List<JsonElement> Validate(JsonElement top, IReadOnlyDictionary<string, JsonElement> sources, IReadOnlySet<string> generated)
    {
        Require(top.ValueKind == JsonValueKind.Object, "staged: document is not an object");
        var names = top.EnumerateObject().Select(property => property.Name).ToArray();
        Require(names.SequenceEqual(["schemaVersion", "operations"], StringComparer.Ordinal), "staged: document properties must be exactly schemaVersion, operations");
        var version = top.GetProperty("schemaVersion");
        Require(version.ValueKind == JsonValueKind.String && version.GetString() == SchemaVersion, "staged: schemaVersion is not " + SchemaVersion);
        var operations = top.GetProperty("operations");
        Require(operations.ValueKind == JsonValueKind.Array, "staged: operations is not an array");

        var rows = new List<JsonElement>();
        var operationIds = new HashSet<string>(StringComparer.Ordinal);
        var bindings = new HashSet<string>(StringComparer.Ordinal);
        string? previous = null;
        foreach (var row in operations.EnumerateArray())
        {
            Require(row.ValueKind == JsonValueKind.Object, "staged: operation row is not an object");
            var operationId = Text(row, "operationId");
            var binding = Text(row, "binding");
            Require(operationIds.Add(operationId), "staged: duplicate operationId " + operationId);
            Require(bindings.Add(binding), "staged: duplicate binding " + binding);
            Require(previous is null || string.CompareOrdinal(previous, operationId) < 0, "staged: rows are not in ordinal operationId order at " + operationId);
            previous = operationId;
            Require(Text(row, "surface") == "public", "staged: " + operationId + " is not a public row");
            Require(Text(row, "kind") == "proto", "staged: " + operationId + " is not a proto row");
            Require(binding != MigrationExample, "staged: the retained migration example has a row: " + operationId);
            Require(generated.Contains(binding), "staged: " + operationId + " binds " + binding + ", which is not a generated PublicApi method");
            if (!sources.TryGetValue(operationId, out var source))
                throw new InvalidOperationException("staged: " + operationId + " has no eng/operations source row");
            Require(DeepEqual(row, source), "staged: " + operationId + " differs from its eng/operations source row");
            rows.Add(row);
        }
        foreach (var method in generated)
        {
            Require(bindings.Contains(method), "staged: generated PublicApi method " + method + " has no row");
        }
        Require(rows.Count == generated.Count, "staged: row count differs from the generated method count");
        return rows;
    }

    private static string Text(JsonElement row, string name)
    {
        if (!row.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String || value.GetString()!.Length == 0)
            throw new InvalidOperationException("staged: operation row has no string " + name);
        return value.GetString()!;
    }

    /// <summary>Structural equality that also requires the same property order; numbers compare by their exact JSON text.</summary>
    private static bool DeepEqual(JsonElement left, JsonElement right)
    {
        if (left.ValueKind != right.ValueKind) return false;
        switch (left.ValueKind)
        {
            case JsonValueKind.Object:
                var a = left.EnumerateObject().ToArray();
                var b = right.EnumerateObject().ToArray();
                if (a.Length != b.Length) return false;
                for (var i = 0; i < a.Length; i++)
                {
                    if (!string.Equals(a[i].Name, b[i].Name, StringComparison.Ordinal) || !DeepEqual(a[i].Value, b[i].Value)) return false;
                }
                return true;
            case JsonValueKind.Array:
                var x = left.EnumerateArray().ToArray();
                var y = right.EnumerateArray().ToArray();
                if (x.Length != y.Length) return false;
                for (var i = 0; i < x.Length; i++)
                {
                    if (!DeepEqual(x[i], y[i])) return false;
                }
                return true;
            case JsonValueKind.String:
                return string.Equals(left.GetString(), right.GetString(), StringComparison.Ordinal);
            case JsonValueKind.Number:
                return string.Equals(left.GetRawText(), right.GetRawText(), StringComparison.Ordinal);
            default:
                return true;
        }
    }

    /// <summary>In-memory tampering of the staged rows; each must be refused for its own reason.</summary>
    private static void NegativeFixtures(JsonElement top, IReadOnlyDictionary<string, JsonElement> sources, IReadOnlySet<string> generated)
    {
        var rows = top.GetProperty("operations").EnumerateArray().ToArray();
        Require(rows.Length >= 2, "fixtures: at least two staged rows are needed");
        var first = rows[0];
        var firstBinding = first.GetProperty("binding").GetString()!;

        // Positive control: the same rows re-serialized by the fixture writer are accepted, so every refusal
        // below is caused by its tampering and not by the writer.
        using (var control = Parse(Document(rows, null)))
        {
            Require(Validate(control.RootElement, sources, generated).Count == rows.Length, "fixtures: positive control was not accepted");
        }

        Refused("drop", Document(rows.Skip(1), null), sources, generated, "generated PublicApi method " + firstBinding + " has no row");

        var service = firstBinding.Split('/')[0];
        var unknown = Document(rows, writer => WriteRow(writer, first, new()
        {
            ["operationId"] = "~con41.fixture.unknownBinding",
            ["binding"] = service + "/Con41FixtureNoSuchMethod",
        }));
        Refused("unknown binding", unknown, sources, generated, "which is not a generated PublicApi method");

        var duplicate = Document(rows.Take(1).Concat(rows), null);
        Refused("duplicate", duplicate, sources, generated, "duplicate operationId " + first.GetProperty("operationId").GetString());

        var risk = first.GetProperty("authorization").GetProperty("risk").GetString();
        var altered = Document(rows.Skip(1), writer => WriteRow(writer, first, new() { ["authorization.risk"] = risk == "R1" ? "R2" : "R1" }), prepend: true);
        Refused("altered value", altered, sources, generated, "differs from its eng/operations source row");

        var example = Document(rows, writer => WriteRow(writer, first, new()
        {
            ["operationId"] = "~con41.fixture.migrationExample",
            ["binding"] = MigrationExample,
        }));
        Refused("migration example row", example, sources, generated, "the retained migration example has a row");

        var reordered = Document(Enumerable.Reverse(rows), null);
        Refused("reordered", reordered, sources, generated, "rows are not in ordinal operationId order");

        // The same bytes with a distinct second name parse, so the refusal below is the duplicate property itself.
        using (Parse(Encoding.UTF8.GetBytes("{\"schemaVersion\":\"operation-metadata.v1\",\"schemaVersionX\":\"operation-metadata.v1\",\"operations\":[]}"))) { }
        Refused("duplicate property", Encoding.UTF8.GetBytes("{\"schemaVersion\":\"operation-metadata.v1\",\"schemaVersion\":\"operation-metadata.v1\",\"operations\":[]}"),
            sources, generated, "staged: invalid JSON");
    }

    private static void Refused(string name, byte[] utf8, IReadOnlyDictionary<string, JsonElement> sources, IReadOnlySet<string> generated, string reason)
    {
        try
        {
            using var document = Parse(utf8);
            Validate(document.RootElement, sources, generated);
        }
        catch (InvalidOperationException error) when (error.Message.Contains(reason, StringComparison.Ordinal))
        {
            return;
        }
        catch (InvalidOperationException error)
        {
            throw new InvalidOperationException("fixtures: " + name + " was refused for the wrong reason: " + error.Message, error);
        }
        throw new InvalidOperationException("fixtures: " + name + " was accepted");
    }

    /// <summary>The closed document around the given rows; an optional extra row is appended (or prepended).</summary>
    private static byte[] Document(IEnumerable<JsonElement> rows, Action<Utf8JsonWriter>? extra, bool prepend = false)
    {
        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer, new JsonWriterOptions { Indented = true }))
        {
            writer.WriteStartObject();
            writer.WriteString("schemaVersion", SchemaVersion);
            writer.WriteStartArray("operations");
            if (prepend) extra?.Invoke(writer);
            foreach (var row in rows) row.WriteTo(writer);
            if (!prepend) extra?.Invoke(writer);
            writer.WriteEndArray();
            writer.WriteEndObject();
        }
        return buffer.ToArray();
    }

    /// <summary>Copies a row in property order, replacing string values at dotted paths.</summary>
    private static void WriteRow(Utf8JsonWriter writer, JsonElement row, Dictionary<string, string> replacements, string prefix = "")
    {
        writer.WriteStartObject();
        foreach (var property in row.EnumerateObject())
        {
            var path = prefix + property.Name;
            if (replacements.TryGetValue(path, out var replacement))
            {
                writer.WriteString(property.Name, replacement);
            }
            else if (property.Value.ValueKind == JsonValueKind.Object)
            {
                writer.WritePropertyName(property.Name);
                WriteRow(writer, property.Value, replacements, path + ".");
            }
            else
            {
                property.WriteTo(writer);
            }
        }
        writer.WriteEndObject();
    }

    /// <summary>Ordinal source enumeration: reversed filesystem order yields the same rows, in the same order.</summary>
    private static void FilesystemOrderFixture(string root)
    {
        var paths = SourcePaths(root);
        var forward = LoadSources(paths.Order(StringComparer.Ordinal));
        var reversed = LoadSources(Enumerable.Reverse(paths.Order(StringComparer.Ordinal).ToArray()));
        Require(forward.Keys.SequenceEqual(reversed.Keys, StringComparer.Ordinal), "fixtures: source enumeration depends on filesystem order");
        foreach (var (operationId, row) in forward)
        {
            Require(DeepEqual(row, reversed[operationId]), "fixtures: source row " + operationId + " depends on filesystem order");
        }
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
