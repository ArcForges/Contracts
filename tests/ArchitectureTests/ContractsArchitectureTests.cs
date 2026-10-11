// SPDX-License-Identifier: Apache-2.0

using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using ArcForges.Build.Policy.Architecture;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace ArcForges.Contracts.ArchitectureTests;

internal static class RepositoryRoot
{
    public static string Find()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !File.Exists(Path.Combine(directory.FullName, "ArcForges.Contracts.slnx")))
        {
            directory = directory.Parent;
        }

        return directory?.FullName ?? throw new InvalidOperationException("Owning Contracts repository was not found.");
    }
}

internal static class ContractsArchitectureTests
{
    private static readonly (string Schema, string Model, string Context, string Validator)[] HttpRecords =
    [
        ("public/http/v1/schema.json", "PartReceipt", "src/public/dotnet/ArcForges.Contracts.PublicApi/Generated/Shapes/PartReceipt.g.cs", "src/public/dotnet/ArcForges.Contracts.Validation/Generated/Shapes/PartReceiptValidator.g.cs"),
        ("internal/ai-http/v1/schema.json", "CommitReceipt", "src/internal/dotnet/ArcForges.Contracts.CloudInternal/Generated/Shapes/CommitReceipt.g.cs", "src/internal/dotnet/ArcForges.Contracts.CloudInternal/Generated/Shapes/CommitReceiptValidator.g.cs"),
        ("public/http/v1/inventory.schema.json", "PackageInventory", "src/public/dotnet/ArcForges.Sdk.Contracts/Generated/Shapes/PackageInventory.g.cs", "src/public/dotnet/ArcForges.Contracts.Validation/Generated/Shapes/PackageInventoryValidator.g.cs"),
    ];

    public static void RunLocal() => VerifyEveryPublicApiHasGeneratedContractTestBinding();

    [Xunit.Fact]
    public static void VerifyEveryPublicApiHasGeneratedContractTestBinding()
    {
        string root = RepositoryRoot.Find();
        VerifyContractReferenceDirection(root);
        VerifyGeneratedProtoOwnership(root);
        VerifyHttpExceptionMetadata(root);
        VerifyGeneratedRpcDescriptors(root);
        VerifyInProcessPortIdentity(root);
        VerifySerializerMetadataBindings(root);
        VerifyBaselineGate(root);
        VerifyPolicyLayeringAndLicenceFixtures(root);
        VerifyLocalDispatchBoundary(root);
    }

    private static JsonElement HttpRecordSchema(JsonElement document, string model) =>
        document.TryGetProperty("$defs", out var definitions) && definitions.TryGetProperty(model, out var definition)
            && !document.TryGetProperty("properties", out _) ? definition : document;

    public static bool HasExplicitHttpMetadata(string schemaText, string generatedText, string model)
    {
        using var schema = JsonDocument.Parse(schemaText);
        var root = HttpRecordSchema(schema.RootElement, model);
        if (!root.TryGetProperty("title", out var titleElement) || titleElement.GetString() is not { Length: > 0 } title
            || title != model
            || !root.TryGetProperty("properties", out var properties)
            || !root.TryGetProperty("x-arcforges-max-bytes", out var maximumBytes)
            || maximumBytes.ValueKind != JsonValueKind.Number || !maximumBytes.TryGetInt32(out int bytes) || bytes <= 0)
        {
            return false;
        }

        if (!generatedText.Contains("JsonSourceGenerationOptions(", StringComparison.Ordinal)
            || !generatedText.Contains("AllowDuplicateProperties = false", StringComparison.Ordinal)
            || !generatedText.Contains("AllowTrailingCommas = false", StringComparison.Ordinal)
            || !generatedText.Contains("MaxDepth = 32", StringComparison.Ordinal)
            || !generatedText.Contains("NumberHandling = global::System.Text.Json.Serialization.JsonNumberHandling.Strict", StringComparison.Ordinal)
            || !generatedText.Contains("ReadCommentHandling = global::System.Text.Json.JsonCommentHandling.Disallow", StringComparison.Ordinal)
            || !generatedText.Contains("RespectNullableAnnotations = true", StringComparison.Ordinal)
            || !generatedText.Contains("RespectRequiredConstructorParameters = true", StringComparison.Ordinal)
            || !generatedText.Contains("UnmappedMemberHandling = global::System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow", StringComparison.Ordinal)
            || !generatedText.Contains($"JsonSerializable(typeof({title}))", StringComparison.Ordinal)
            || !generatedText.Contains($"class {title}JsonContext : global::System.Text.Json.Serialization.JsonSerializerContext", StringComparison.Ordinal))
        {
            return false;
        }

        foreach (var property in properties.EnumerateObject())
        {
            string escaped = JsonStringLiteral(property.Name);
            if (!generatedText.Contains($"JsonPropertyName({escaped})", StringComparison.Ordinal)) return false;
        }

        return true;
    }

    private static void VerifyContractReferenceDirection(string root)
    {
        using var catalog = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/contract-packages.json")));
        var packages = catalog.RootElement.GetProperty("packages").EnumerateArray()
            .Where(row => row.GetProperty("kind").GetString() == "nuget")
            .ToDictionary(row => row.GetProperty("id").GetString()!, StringComparer.Ordinal);
        foreach (var package in packages.Values)
        {
            string projectPath = Path.Combine(root, package.GetProperty("sourceRoot").GetString()!,
                package.GetProperty("id").GetString() + ".csproj");
            var document = XDocument.Load(projectPath);
            string[] actual = document.Descendants("ProjectReference")
                .Select(reference => Path.GetFileNameWithoutExtension(Path.GetFullPath(Path.Combine(Path.GetDirectoryName(projectPath)!,
                    reference.Attribute("Include")!.Value))))
                .Order(StringComparer.Ordinal).ToArray();
            string[] expected = package.GetProperty("dependencies").EnumerateArray().Select(dependency => dependency.GetString()!)
                .Order(StringComparer.Ordinal).ToArray();
            Checks.SequenceEqual(expected, actual, $"Contract project reference direction drifted for {package.GetProperty("id").GetString()}.");
            Checks.True(actual.All(packages.ContainsKey), "A contract project reference escaped the owned contract package set.");
        }

        Checks.True(IsAllowedContractReference(packages.Keys, "ArcForges.Contracts.Foundation"), "Foundation should be an allowed contract dependency.");
        Checks.True(!IsAllowedContractReference(packages.Keys, "Microsoft.AspNetCore.Mvc"), "A platform dependency must not enter the contract project graph.");
    }

    private static bool IsAllowedContractReference(IEnumerable<string> packageIds, string target) => packageIds.Contains(target, StringComparer.Ordinal);

    private static void VerifyGeneratedProtoOwnership(string root)
    {
        using var catalog = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/contract-packages.json")));
        foreach (var package in catalog.RootElement.GetProperty("packages").EnumerateArray()
            .Where(row => row.GetProperty("kind").GetString() == "nuget"))
        {
            string sourceRoot = package.GetProperty("sourceRoot").GetString()!;
            string[] protoFiles = package.GetProperty("proto").EnumerateArray().Select(item => item.GetString()!).ToArray();
            string generatedRoot = Path.Combine(root, sourceRoot, "Generated", "Proto");
            if (protoFiles.Length == 0)
            {
                Checks.True(!Directory.Exists(generatedRoot) || !Directory.GetFiles(generatedRoot, "*.cs").Any(),
                    "A package with no owned proto schemas contains generated public wire source.");
                continue;
            }

            Checks.True(Directory.Exists(generatedRoot), "A proto-owning contract project is missing its generated C# output.");
            var generated = Directory.GetFiles(generatedRoot, "*.cs", SearchOption.AllDirectories);
            var ownedSources = new HashSet<string>(StringComparer.Ordinal);
            bool negativeFixturesChecked = false;
            foreach (string file in generated)
            {
                string text = File.ReadAllText(file);
                var source = Regex.Match(text, @"^//\s*source:\s*(?<path>[A-Za-z0-9_./-]+\.proto)\s*$", RegexOptions.Multiline);
                Checks.True(source.Success, "Generated protobuf source is missing its authored schema identity.");
                string identity = source.Groups["path"].Value.Replace('\\', '/');
                Checks.True(HasGeneratedProtoOwnership(text, protoFiles),
                    "Generated protobuf source points outside its exact package schema ownership.");
                ownedSources.Add(identity);
                if (!negativeFixturesChecked)
                {
                    string unowned = text.Replace(identity, "arcforges/unowned/v1/unowned.proto", StringComparison.Ordinal);
                    Checks.True(!HasGeneratedProtoOwnership(unowned, protoFiles),
                        "A DTO generated from an unowned schema passed the negative fixture.");
                    string unattributed = text.Replace("GeneratedCode(\"protoc\"", "GeneratedCode(\"untrusted\"", StringComparison.Ordinal)
                        .Replace("GeneratedCode(\"grpc_csharp_plugin\"", "GeneratedCode(\"untrusted\"", StringComparison.Ordinal);
                    Checks.True(!HasGeneratedProtoOwnership(unattributed, protoFiles),
                        "A DTO without a recognized generator identity passed the negative fixture.");
                    negativeFixturesChecked = true;
                }
            }

            foreach (string proto in protoFiles)
            {
                string suffix = proto[(proto.IndexOf("arcforges/", StringComparison.Ordinal))..];
                Checks.True(ownedSources.Contains(suffix), "An authored proto schema has no generated C# artifact.");
            }
        }
    }

    private static bool HasGeneratedProtoOwnership(string generatedSource, IReadOnlyList<string> ownedProtoFiles)
    {
        var source = Regex.Match(generatedSource, @"^//\s*source:\s*(?<path>[A-Za-z0-9_./-]+\.proto)\s*$", RegexOptions.Multiline);
        return source.Success
            && ownedProtoFiles.Any(path => path.EndsWith(source.Groups["path"].Value.Replace('\\', '/'), StringComparison.Ordinal))
            && (generatedSource.Contains("GeneratedCode(\"protoc\"", StringComparison.Ordinal)
                || generatedSource.Contains("GeneratedCode(\"grpc_csharp_plugin\"", StringComparison.Ordinal));
    }

    private static void VerifyHttpExceptionMetadata(string root)
    {
        foreach (var record in HttpRecords)
        {
            string schemaText = File.ReadAllText(Path.Combine(root, record.Schema));
            string generated = File.ReadAllText(Path.Combine(root, record.Context));
            string validator = File.ReadAllText(Path.Combine(root, record.Validator));
            Checks.True(HasExplicitHttpMetadata(schemaText, generated, record.Model), $"HTTP record lacks explicit strict JSON metadata: {record.Model}.");
            Checks.True(validator.Contains("JsonSerializer.Deserialize", StringComparison.Ordinal)
                && validator.Contains($"{record.Model}JsonContext.Default.{record.Model}", StringComparison.Ordinal),
                $"HTTP record codec is not bound to generated JSON metadata: {record.Model}.");

            using var recordDocument = JsonDocument.Parse(schemaText);
            string property = HttpRecordSchema(recordDocument.RootElement, record.Model).GetProperty("properties").EnumerateObject().First().Name;
            string missingProperty = generated.Replace($"JsonPropertyName({JsonStringLiteral(property)})", "", StringComparison.Ordinal);
            Checks.True(!HasExplicitHttpMetadata(schemaText, missingProperty, record.Model), "A missing explicit JSON field name passed the negative fixture.");
            string unregistered = generated.Replace($"JsonSerializable(typeof({record.Model}))", "", StringComparison.Ordinal);
            Checks.True(!HasExplicitHttpMetadata(schemaText, unregistered, record.Model), "An unregistered JSON type passed the negative fixture.");
            string permissive = generated.Replace("UnmappedMemberHandling = global::System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow", "", StringComparison.Ordinal);
            Checks.True(!HasExplicitHttpMetadata(schemaText, permissive, record.Model), "Permissive unknown-field handling passed the negative fixture.");
            using var schema = JsonDocument.Parse(schemaText);
            var invalidSchema = schema.RootElement.GetRawText().Replace("\"x-arcforges-max-bytes\"", "\"missing-byte-limit\"", StringComparison.Ordinal);
            Checks.True(!HasExplicitHttpMetadata(invalidSchema, generated, record.Model), "An unbounded HTTP JSON record passed the negative fixture.");
        }
    }

    private static void VerifyGeneratedRpcDescriptors(string root)
    {
        using var catalog = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/contract-packages.json")));
        foreach (var package in catalog.RootElement.GetProperty("packages").EnumerateArray()
            .Where(row => row.GetProperty("kind").GetString() == "nuget"))
        {
            var expected = new List<string>();
            foreach (string protoPath in package.GetProperty("proto").EnumerateArray().Select(item => item.GetString()!))
            {
                string proto = File.ReadAllText(Path.Combine(root, protoPath));
                var ns = Regex.Match(proto, "^option csharp_namespace = \"(?<value>[A-Za-z0-9_.]+)\";", RegexOptions.Multiline);
                if (!ns.Success) continue;
                foreach (Match service in Regex.Matches(proto, @"^service\s+(?<name>[A-Za-z][A-Za-z0-9]*)\s*\{", RegexOptions.Multiline))
                {
                    expected.Add($"global::{ns.Groups["value"].Value}.{service.Groups["name"].Value}.Descriptor");
                }
            }

            string servicesPath = Path.Combine(root, package.GetProperty("sourceRoot").GetString()!, "Generated", "Services", "ContractServices.g.cs");
            if (expected.Count == 0)
            {
                Checks.True(!File.Exists(servicesPath), "A package without authored services contains a generated service catalogue.");
                continue;
            }

            Checks.True(File.Exists(servicesPath), "Generated service descriptor catalogue is missing.");
            string[] actual = Regex.Matches(File.ReadAllText(servicesPath), @"global::[A-Za-z0-9_.]+\.Descriptor")
                .Select(match => match.Value).ToArray();
            Checks.SequenceEqual(expected, actual, $"Generated service descriptor catalogue differs from authored proto for {package.GetProperty("id").GetString()}.");
            Checks.True(!DescriptorCatalogueMatches(expected, expected.Skip(1)), "A missing service descriptor passed the negative fixture.");
        }
    }

    private static bool DescriptorCatalogueMatches(IEnumerable<string> expected, IEnumerable<string> actual) => expected.SequenceEqual(actual);

    private static void VerifyInProcessPortIdentity(string root)
    {
        string generator = File.ReadAllText(Path.Combine(root, "eng/con06_inprocess.py"));
        var ports = Regex.Matches(generator, "\"(?<interface>I[A-Za-z0-9]+)\"\\s*:\\s*\\(\"(?<service>[A-Za-z0-9]+Service)\"\\s*,\\s*\\((?<methods>[^)]*)\\)\\)");
        Checks.True(ports.Count > 0, "No generated local RPC interface identities were found.");
        foreach (Match port in ports)
        {
            string interfaceName = port.Groups["interface"].Value;
            string serviceName = port.Groups["service"].Value;
            string[] methods = Regex.Matches(port.Groups["methods"].Value, "\"(?<name>[A-Za-z][A-Za-z0-9]*)\"")
                .Select(match => match.Groups["name"].Value).ToArray();
            string owner = new[] { "Platform", "Chat", "Scope" }.Single(value =>
            {
                string protoPath = value switch
                {
                    "Platform" => "internal/proto/arcforges/local/platform/v1/inprocess.proto",
                    "Chat" => "internal/proto/arcforges/local/chat/v1/chat.proto",
                    "Scope" => "internal/proto/arcforges/local/scope/v1/scope.proto",
                    _ => throw new InvalidOperationException("Unrecognized in-process owner."),
                };
                string proto = File.ReadAllText(Path.Combine(root, protoPath));
                return Regex.IsMatch(proto, $@"^message\s+{Regex.Escape(serviceName + methods[0])}Request\s*\{{", RegexOptions.Multiline);
            });
            string file = Path.Combine(root, $"src/internal/dotnet/ArcForges.Contracts.LocalRpc.{owner}/Generated/InprocessPorts.g.cs");
            string source = File.ReadAllText(file);
            string protoPath = owner switch
            {
                "Platform" => "internal/proto/arcforges/local/platform/v1/inprocess.proto",
                "Chat" => "internal/proto/arcforges/local/chat/v1/chat.proto",
                "Scope" => "internal/proto/arcforges/local/scope/v1/scope.proto",
                _ => throw new InvalidOperationException("Unrecognized in-process owner."),
            };
            string proto = File.ReadAllText(Path.Combine(root, protoPath));
            Checks.True(HasLocalRpcIdentity(source, proto, owner, interfaceName, serviceName, methods),
                "A local RPC interface lost its generated service, descriptor namespace or typed-message identity.");
            string changedIdentity = source.Replace(serviceName, "UnboundContractService", StringComparison.Ordinal);
            Checks.True(!HasLocalRpcIdentity(changedIdentity, proto, owner, interfaceName, serviceName, methods),
                "An interface with a substituted service identity passed the negative fixture.");
        }
    }

    private static bool HasLocalRpcIdentity(string generatedPorts, string proto, string owner, string interfaceName,
        string serviceName, IReadOnlyList<string> methods)
    {
        string package = $"arcforges.local.{owner.ToLowerInvariant()}.v1";
        string csharpNamespace = $"ArcForges.Contracts.LocalRpc.{owner}.V1";
        if (!Regex.IsMatch(proto, $@"^package\s+{Regex.Escape(package)};", RegexOptions.Multiline)
            || !Regex.IsMatch(proto, $"^option csharp_namespace\\s*=\\s*\"{Regex.Escape(csharpNamespace)}\";", RegexOptions.Multiline))
        {
            return false;
        }

        var body = Regex.Match(generatedPorts, $@"interface\s+{Regex.Escape(interfaceName)}\s*\{{(?<body>.*?)\}}", RegexOptions.Singleline);
        if (!body.Success) return false;
        var signatures = Regex.Matches(body.Groups["body"].Value,
            @"ValueTask<global::[A-Za-z0-9_.]+\.(?<response>[A-Za-z0-9]+Response)>\s+(?<method>[A-Za-z0-9]+)Async\(global::[A-Za-z0-9_.]+\.(?<request>[A-Za-z0-9]+Request)\s+request");
        if (signatures.Count != methods.Count) return false;
        foreach (string method in methods)
        {
            var signature = signatures.Cast<Match>().SingleOrDefault(match => match.Groups["method"].Value == method);
            if (signature is null || signature.Groups["request"].Value != serviceName + method + "Request"
                || signature.Groups["response"].Value != serviceName + method + "Response"
                || !Regex.IsMatch(proto, $@"^message\s+{Regex.Escape(serviceName + method)}Request\s*\{{", RegexOptions.Multiline)
                || !Regex.IsMatch(proto, $@"^message\s+{Regex.Escape(serviceName + method)}Response\s*\{{", RegexOptions.Multiline))
            {
                return false;
            }
        }

        return true;
    }

    private static void VerifySerializerMetadataBindings(string root)
    {
        const string badSource = "using System.Text.Json; record Wire { } class C { static object? Read(string json) => JsonSerializer.Deserialize<Wire>(json); }";
        const string goodSource = "using System.Text.Json; using System.Text.Json.Serialization.Metadata; record Wire { } class C { static JsonTypeInfo<Wire> Metadata => throw null!; static object? Read(string json) => JsonSerializer.Deserialize<Wire>(json, Metadata); }";
        var badFixture = FixtureCompiler.Compile("ReflectionJson", new Dictionary<string, string> { ["fixture.cs"] = badSource });
        var goodFixture = FixtureCompiler.Compile("RegisteredJson", new Dictionary<string, string> { ["fixture.cs"] = goodSource });
        Checks.True(FindUnregisteredJsonSerializer(badFixture).Count != 0, "An unregistered reflection-serializer fixture was accepted.");
        Checks.Empty(FindUnregisteredJsonSerializer(goodFixture), "Registered compile-time JSON metadata was rejected.");
    }

    internal static IReadOnlyList<string> FindUnregisteredJsonSerializer(Compilation compilation)
    {
        var findings = new List<string>();
        foreach (var tree in compilation.SyntaxTrees)
        {
            var model = compilation.GetSemanticModel(tree);
            foreach (var invocation in tree.GetRoot().DescendantNodes().OfType<InvocationExpressionSyntax>())
            {
                if (model.GetSymbolInfo(invocation).Symbol is not IMethodSymbol method
                    || method.ContainingType.ToDisplayString() != "System.Text.Json.JsonSerializer") continue;
                bool hasTypeInfo = method.Parameters.Any(parameter =>
                    parameter.Type.OriginalDefinition.ToDisplayString().StartsWith("System.Text.Json.Serialization.Metadata.JsonTypeInfo", StringComparison.Ordinal));
                if (!hasTypeInfo) findings.Add(invocation.GetLocation().ToString());
            }
        }

        return findings;
    }

    private static string JsonStringLiteral(string value)
    {
        var result = new StringBuilder(value.Length + 2).Append('"');
        foreach (char character in value)
        {
            switch (character)
            {
                case '"': result.Append("\\\""); break;
                case '\\': result.Append("\\\\"); break;
                case '\b': result.Append("\\b"); break;
                case '\f': result.Append("\\f"); break;
                case '\n': result.Append("\\n"); break;
                case '\r': result.Append("\\r"); break;
                case '\t': result.Append("\\t"); break;
                default:
                    if (character < ' ')
                    {
                        result.Append("\\u").Append(((int)character).ToString("x4", System.Globalization.CultureInfo.InvariantCulture));
                    }
                    else
                    {
                        result.Append(character);
                    }
                    break;
            }
        }

        return result.Append('"').ToString();
    }

    private static void VerifyBaselineGate(string root)
    {
        string ci = File.ReadAllText(Path.Combine(root, ".github/workflows/ci.yml"));
        string packer = File.ReadAllText(Path.Combine(root, "eng/packaging_tools.py"));
        Checks.True(HasCandidateBaselineGate(ci, packer), "The PR candidate no longer checks generated artifacts against their committed baseline.");
        Checks.True(!HasCandidateBaselineGate(ci.Replace("python eng/contracts.py pack --version \"$PACKAGE_VERSION\"", "", StringComparison.Ordinal), packer),
            "Removing the candidate regeneration check did not fail its negative fixture.");
    }

    private static bool HasCandidateBaselineGate(string ci, string packer) =>
        ci.Contains("python eng/contracts.py pack --version \"$PACKAGE_VERSION\"", StringComparison.Ordinal)
        && packer.Contains("generate(check=True)", StringComparison.Ordinal);

    private static void VerifyPolicyLayeringAndLicenceFixtures(string root)
    {
        using var fixtures = new PolicyFixtureRoot();
        Checks.Empty(fixtures.Check(violation: "none"), "The allowed contract-to-foundation graph was rejected.");
        Checks.True(fixtures.Check(violation: "layering").Any(finding => finding.Rule == "AT-04"),
            "A non-contract project reference escaped the negative layering fixture.");
        Checks.True(fixtures.Check(violation: "boundary").Any(finding => finding.Rule == "RP-03"),
            "An Apache-to-AGPL project edge escaped the negative licence fixture.");
        Checks.True(fixtures.Check(violation: "license").Any(finding => finding.Rule == "RP-02"),
            "A missing SPDX/boundary pair escaped the negative licence fixture.");
        Checks.True(fixtures.Check(violation: "wire").Any(finding => finding.Rule == "AT-12"),
            "A public contract type with no generated schema binding escaped the negative AT-12 fixture.");
    }

    private sealed class PolicyFixtureRoot : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "arcforges-gov05-" + Guid.NewGuid().ToString("N"));
        public PolicyFixtureRoot()
        {
            Directory.CreateDirectory(_root);
            File.WriteAllText(Path.Combine(_root, "global.json"), "{}\n");
        }

        public IReadOnlyList<PolicyFinding> Check(string violation)
        {
            var projects = new List<ProjectFacts>();
            var compilations = new Dictionary<string, Microsoft.CodeAnalysis.CSharp.CSharpCompilation>(StringComparer.Ordinal);
            Add("foundation/foundation.csproj", ProjectRole.Foundation, "Apache-2.0", "Apache", []);
            Add("contract/contract.csproj", ProjectRole.Contracts,
                violation == "license" ? "MIT" : "Apache-2.0", "Apache",
                violation == "layering" ? ["other/other.csproj"] : ["foundation/foundation.csproj"],
                violation == "wire" ? "public sealed class Authored { }" : "internal sealed class Empty { }");
            if (violation == "layering") Add("other/other.csproj", ProjectRole.Infrastructure, "Apache-2.0", "Apache", []);
            if (violation == "boundary")
            {
                projects[0] = projects[0] with
                {
                    Classification = projects[0].Classification with { Role = ProjectRole.Foundation },
                    License = "AGPL-3.0-only",
                    Boundary = "AGPL",
                };
            }

            string commit = new string('a', 40);
            var evidence = new[]
            {
                new ExternalPolicyEvidence("RP-01", commit, true, []),
                new ExternalPolicyEvidence("RP-08", commit, true, []),
                new ExternalPolicyEvidence("RP-09", commit, true, []),
            };
            var configuration = new RepositoryPolicyConfiguration(commit,
                new Dictionary<string, string> { ["global.json"] = HashNormalized(Path.Combine(_root, "global.json")) },
                new Dictionary<string, string>(), new HashSet<string>(), [], [], evidence);
            var repository = new RepositoryFacts(_root, "Contracts", projects, [], []);
            return PolicyEngine.Check(repository, configuration, compilations, new DateOnly(2026, 9, 28));

            void Add(string path, ProjectRole role, string license, string boundary, string[] references,
                string source = "internal sealed class Empty { }")
            {
                string full = Path.Combine(_root, path);
                Directory.CreateDirectory(Path.GetDirectoryName(full)!);
                File.WriteAllText(full, "<Project />\n");
                File.WriteAllText(Path.Combine(Path.GetDirectoryName(full)!, "packages.lock.json"), "{\"version\":1,\"dependencies\":{\"net10.0\":{}}}\n");
                string sourcePath = Path.Combine(Path.GetDirectoryName(full)!, "Empty.cs");
                File.WriteAllText(sourcePath, source + Environment.NewLine);
                var classification = new ProjectClassification(path, role, "Contracts");
                var properties = new Dictionary<string, string>(StringComparer.Ordinal)
                {
                    ["ManagePackageVersionsCentrally"] = "true",
                    ["RestorePackagesWithLockFile"] = "true",
                    ["SuppressTrimAnalysisWarnings"] = "false",
                    ["EnableTrimAnalyzer"] = "true",
                    ["EnableAotAnalyzer"] = "true",
                };
                projects.Add(new ProjectFacts(classification, "net10.0", "Library", license, boundary,
                    references, [sourcePath], [], properties, new Dictionary<string, string>()));
                compilations.Add(path, FixtureCompiler.Compile("Fixture" + projects.Count,
                    new Dictionary<string, string> { ["Empty.cs"] = source }));
            }
        }

        public void Dispose()
        {
            string temp = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            string target = Path.GetFullPath(_root);
            if (!target.StartsWith(temp, StringComparison.OrdinalIgnoreCase)
                || !Path.GetFileName(target).StartsWith("arcforges-gov05-", StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Refusing to remove an unexpected architecture-fixture directory.");
            }

            Directory.Delete(target, recursive: true);
        }
    }

    private static string HashNormalized(string path) => Convert.ToHexStringLower(
        SHA256.HashData(Encoding.UTF8.GetBytes(File.ReadAllText(path).Replace("\r\n", "\n", StringComparison.Ordinal))));

    // CON.43 (DP-01, DP-02, DP-06): the boundary dispatch assembly is the only place where the structured value meets
    // the Scope and Chat typed requests, it uses no reflection, and no production assembly depends on it.
    internal const string DispatchPackage = "ArcForges.Contracts.LocalRpc.Dispatch";
    internal const string DispatchProject = "src/internal/dotnet/ArcForges.Contracts.LocalRpc.Dispatch/ArcForges.Contracts.LocalRpc.Dispatch.csproj";
    internal static readonly string[] DispatchMeetingPackages =
        ["ArcForges.Contracts.PublicApi", "ArcForges.Contracts.LocalRpc.Scope", "ArcForges.Contracts.LocalRpc.Chat"];

    private static readonly Regex StructuredValueName = new(@"\b(CapabilityArguments|CapabilityResult|StructuredValue)\b", RegexOptions.CultureInvariant);
    private static readonly Regex ScopeTypedRequestName = new(@"\bScopeOperationsService[A-Za-z0-9]+Request\b", RegexOptions.CultureInvariant);
    private static readonly Regex ChatTypedRequestName = new(@"\bChatOperationsService[A-Za-z0-9]+Request\b", RegexOptions.CultureInvariant);

    // Source-level tokens of reflection, runtime code generation and assembly scanning. RegularExpressions and nameof are
    // not reflective; the patterns are word-bounded so that System.Text.RegularExpressions never matches Expression.
    internal static readonly (string Name, Regex Pattern)[] ReflectiveSourceTokens =
    [
        ("System.Reflection", new Regex(@"\bSystem\s*\.\s*Reflection\b", RegexOptions.CultureInvariant)),
        ("Google.Protobuf.Reflection", new Regex(@"\bGoogle\s*\.\s*Protobuf\s*\.\s*Reflection\b", RegexOptions.CultureInvariant)),
        ("MakeGenericType", new Regex(@"\bMakeGeneric(Type|Method)\b", RegexOptions.CultureInvariant)),
        ("Activator", new Regex(@"\bActivator\b", RegexOptions.CultureInvariant)),
        ("GetType", new Regex(@"\bGetType\s*\(", RegexOptions.CultureInvariant)),
        ("typeof", new Regex(@"\btypeof\s*\(", RegexOptions.CultureInvariant)),
        ("Assembly", new Regex(@"\b(Assembly|AssemblyLoadContext|AssemblyName)\b", RegexOptions.CultureInvariant)),
        ("System.Runtime.Loader", new Regex(@"\bSystem\s*\.\s*Runtime\s*\.\s*Loader\b", RegexOptions.CultureInvariant)),
        ("System.Linq.Expressions", new Regex(@"\bSystem\s*\.\s*Linq\s*\.\s*Expressions\b", RegexOptions.CultureInvariant)),
        ("Expression", new Regex(@"\bExpression\s*[<.]", RegexOptions.CultureInvariant)),
        ("Emit", new Regex(@"\b(DynamicMethod|ILGenerator|TypeBuilder|AssemblyBuilder|ModuleBuilder)\b", RegexOptions.CultureInvariant)),
    ];

    private static void VerifyLocalDispatchBoundary(string root)
    {
        // (a) No reflective token in any Dispatch source, scanned in ordinal order (never filesystem order).
        string dispatchDirectory = Path.Combine(root, Path.GetDirectoryName(DispatchProject)!);
        string[] dispatchSources = ProjectSources(dispatchDirectory);
        Checks.True(dispatchSources.Length > 0 && dispatchSources.Contains("Generated/Operations/LocalToolAllowlist.g.cs", StringComparer.Ordinal),
            "The boundary dispatch assembly lost its generated sources.");
        Checks.SequenceEqual(dispatchSources, OrdinalSourceOrder(Enumerable.Reverse(dispatchSources)),
            "Dispatch source enumeration is not independent of filesystem order.");
        Checks.Empty(FindReflectiveSourceTokens(dispatchSources.Select(path => (path, File.ReadAllText(Path.Combine(dispatchDirectory, path))))),
            "The boundary dispatch assembly uses reflection, runtime code generation or assembly scanning.");

        // (b) Dispatch is the only cataloged package whose closure holds PublicApi, Scope and Chat, and the only src owner
        // that names the structured value together with both Scope and Chat typed requests.
        var graph = ReadCatalogGraph(root);
        Checks.True(graph.ContainsKey(DispatchPackage), "The boundary dispatch package is missing from the contract catalog.");
        Checks.SequenceEqual(new[] { DispatchPackage }, PackagesJoiningScopeAndChat(graph),
            "A cataloged package other than the boundary dispatch assembly joins PublicApi, Scope and Chat.");
        string[] sourceProjects = RepositoryProjects(root, "src");
        Checks.True(sourceProjects.Contains(DispatchProject, StringComparer.Ordinal), "The boundary dispatch project is missing from src.");
        var owners = sourceProjects.Select(project =>
        {
            string directory = Path.Combine(root, Path.GetDirectoryName(project)!);
            return (project, ProjectSources(directory).Select(path => File.ReadAllText(Path.Combine(directory, path))));
        });
        Checks.SequenceEqual(new[] { DispatchProject }, OwnersJoiningStructuredValueAndTypedRequests(owners),
            "A src owner other than the boundary dispatch assembly names the structured value with Scope and Chat typed requests.");

        // (c) No cataloged package and no production or build-tool csproj references Dispatch; only test projects may.
        Checks.Empty(CatalogPackagesReferencingDispatch(graph), "A cataloged package depends on the boundary dispatch assembly.");
        foreach (string project in sourceProjects.Concat(RepositoryProjects(root, "eng")))
        {
            Checks.True(!ReferencesDispatch(File.ReadAllText(Path.Combine(root, project))),
                "A production or build-tool project references the boundary dispatch assembly.");
        }
    }

    internal static bool IsBuildOutput(string relativePath)
    {
        string normalized = relativePath.Replace('\\', '/');
        return normalized.StartsWith("bin/", StringComparison.Ordinal) || normalized.StartsWith("obj/", StringComparison.Ordinal)
            || normalized.Contains("/bin/", StringComparison.Ordinal) || normalized.Contains("/obj/", StringComparison.Ordinal)
            || normalized.Contains("node_modules/", StringComparison.Ordinal);
    }

    // Directory enumeration order is defined by the filesystem (ext4 order is not alphabetical), so every list is put in
    // ordinal order before it is scanned or compared.
    internal static string[] OrdinalSourceOrder(IEnumerable<string> relativePaths) =>
        relativePaths.Select(path => path.Replace('\\', '/')).Order(StringComparer.Ordinal).ToArray();

    internal static string[] ProjectSources(string projectDirectory) =>
        OrdinalSourceOrder(Directory.EnumerateFiles(projectDirectory, "*.cs", SearchOption.AllDirectories)
            .Select(path => Path.GetRelativePath(projectDirectory, path).Replace('\\', '/'))
            .Where(path => !IsBuildOutput(path)));

    private static string[] RepositoryProjects(string root, string top) =>
        OrdinalSourceOrder(Directory.EnumerateFiles(Path.Combine(root, top), "*.csproj", SearchOption.AllDirectories)
            .Select(path => Path.GetRelativePath(root, path).Replace('\\', '/'))
            .Where(path => !IsBuildOutput(path)));

    internal static IReadOnlyList<string> FindReflectiveSourceTokens(IEnumerable<(string Path, string Text)> sources)
    {
        var findings = new List<string>();
        foreach (var (path, text) in sources.OrderBy(source => source.Path, StringComparer.Ordinal))
        {
            foreach (var token in ReflectiveSourceTokens)
            {
                if (token.Pattern.IsMatch(text)) findings.Add(path + ": " + token.Name);
            }
        }

        return findings;
    }

    private static Dictionary<string, string[]> ReadCatalogGraph(string root)
    {
        using var catalog = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/contract-packages.json")));
        return catalog.RootElement.GetProperty("packages").EnumerateArray().ToDictionary(
            row => row.GetProperty("id").GetString()!,
            row => row.GetProperty("dependencies").EnumerateArray().Select(dependency => dependency.GetString()!).ToArray(),
            StringComparer.Ordinal);
    }

    /// <summary>The self-inclusive transitive dependency closure; an uncataloged dependency fails closed.</summary>
    internal static HashSet<string> CatalogClosure(IReadOnlyDictionary<string, string[]> graph, string package)
    {
        var closure = new HashSet<string>(StringComparer.Ordinal);
        var pending = new Stack<string>();
        pending.Push(package);
        while (pending.Count != 0)
        {
            string current = pending.Pop();
            if (!closure.Add(current)) continue;
            if (!graph.TryGetValue(current, out var dependencies))
            {
                throw new InvalidOperationException("A catalog dependency is not itself a cataloged package.");
            }

            foreach (string dependency in dependencies) pending.Push(dependency);
        }

        return closure;
    }

    internal static string[] PackagesJoiningScopeAndChat(IReadOnlyDictionary<string, string[]> graph) =>
        graph.Keys.Where(package => CatalogClosure(graph, package).IsSupersetOf(DispatchMeetingPackages))
            .Order(StringComparer.Ordinal).ToArray();

    internal static string[] CatalogPackagesReferencingDispatch(IReadOnlyDictionary<string, string[]> graph) =>
        graph.Where(row => row.Value.Contains(DispatchPackage, StringComparer.OrdinalIgnoreCase))
            .Select(row => row.Key).Order(StringComparer.Ordinal).ToArray();

    internal static string[] OwnersJoiningStructuredValueAndTypedRequests(IEnumerable<(string Owner, IEnumerable<string> Texts)> owners)
    {
        var result = new List<string>();
        foreach (var (owner, texts) in owners)
        {
            bool structured = false, scope = false, chat = false;
            foreach (string text in texts)
            {
                structured |= StructuredValueName.IsMatch(text);
                scope |= ScopeTypedRequestName.IsMatch(text);
                chat |= ChatTypedRequestName.IsMatch(text);
            }

            if (structured && scope && chat) result.Add(owner);
        }

        return result.Order(StringComparer.Ordinal).ToArray();
    }

    /// <summary>Whether a project file references the dispatch assembly as a project or as a package.</summary>
    internal static bool ReferencesDispatch(string projectXml)
    {
        var document = XDocument.Parse(projectXml);
        foreach (var reference in document.Descendants().Where(element => element.Name.LocalName == "ProjectReference"))
        {
            string include = (reference.Attribute("Include")?.Value ?? "").Replace('\\', '/').Trim();
            string target = include[(include.LastIndexOf('/') + 1)..];
            if (string.Equals(target, DispatchPackage + ".csproj", StringComparison.OrdinalIgnoreCase)) return true;
        }

        return document.Descendants().Where(element => element.Name.LocalName is "PackageReference" or "PackageVersion")
            .Any(element => string.Equals((element.Attribute("Include") ?? element.Attribute("Update"))?.Value?.Trim(), DispatchPackage,
                StringComparison.OrdinalIgnoreCase));
    }
}
