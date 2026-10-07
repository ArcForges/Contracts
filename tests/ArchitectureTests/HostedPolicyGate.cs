// SPDX-License-Identifier: Apache-2.0

using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using ArcForges.Build.Policy.Architecture;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace ArcForges.Contracts.ArchitectureTests;

internal static class HostedPolicyGate
{
    // Cataloged projects whose public surface is partly authored rather than generated from an owned schema.
    internal static readonly IReadOnlyDictionary<string, ProjectRole> AuthoredRoles = new Dictionary<string, ProjectRole>(StringComparer.Ordinal)
    {
        ["src/public/dotnet/ArcForges.Contracts.Validation/ArcForges.Contracts.Validation.csproj"] = ProjectRole.Abstractions,
        ["src/internal/dotnet/ArcForges.Contracts.LocalRpc.Sandbox/ArcForges.Contracts.LocalRpc.Sandbox.csproj"] = ProjectRole.Abstractions,
        ["src/public/dotnet/ArcForges.Sdk.Client/ArcForges.Sdk.Client.csproj"] = ProjectRole.Abstractions,
        ["src/public/dotnet/ArcForges.Cli/ArcForges.Cli.csproj"] = ProjectRole.Shell,
    };

    public static void Run(Action<PolicyGateStage> setStage)
    {
        setStage(PolicyGateStage.LocateRepository);
        string root = RepositoryRoot.Find();

        setStage(PolicyGateStage.ValidateHostedIdentity);
        string sourceCommit = RequireHostedIdentity(root);

        setStage(PolicyGateStage.ValidateRp01Evidence);
        ExternalPolicyEvidence naming = ReadNamingEvidence(root, sourceCommit, "RP-01");

        setStage(PolicyGateStage.ValidateRp08Evidence);
        ExternalPolicyEvidence licence = ReadNamingEvidence(root, sourceCommit, "RP-08");

        setStage(PolicyGateStage.ValidateSecurityWorkflow);
        VerifySecurityWorkflow(root);

        setStage(PolicyGateStage.ReadProjectGraph);
        var projects = ReadProjectGraph(root);

        setStage(PolicyGateStage.ReadProjectCompilations);
        var compilations = new Dictionary<string, CSharpCompilation>(StringComparer.Ordinal);
        var owningCompilations = projects.Where(project => project.Classification.Role is not (ProjectRole.BuildTool or ProjectRole.NativeLibrary or ProjectRole.NativeWorker)).ToArray();
        foreach (var project in owningCompilations)
        {
            var elapsed = Stopwatch.StartNew();
            try
            {
                compilations.Add(project.Classification.Path, ProjectGraph.ReadCompilation(project));
                Program.WriteProgress(Console.Out, PolicyGateStage.ReadProjectCompilations, elapsed.ElapsedMilliseconds,
                    compilations.Count, owningCompilations.Length);
            }
            catch (Exception exception)
            {
                PolicyGateStage diagnosticStage = ClassifyCompilationFailure(exception);
                if (diagnosticStage != PolicyGateStage.ReadProjectCompilations) setStage(diagnosticStage);
                throw;
            }
        }

        setStage(PolicyGateStage.ValidateProtoDtoSymbols);
        VerifyProtoDtoSymbols(root, projects, compilations);

        setStage(PolicyGateStage.ValidateSerializationClosure);
        VerifySerializationClosure(root, projects, compilations);

        setStage(PolicyGateStage.ReadDependencyPolicy);
        var dependency = ReadDependencyPolicy(root);

        setStage(PolicyGateStage.ReadPolicyExceptions);
        var exceptions = ReadPolicyExceptions(root);

        setStage(PolicyGateStage.ValidateHostLicenceClosure);
        VerifyHostLicenceClosure(projects, dependency.Licenses);

        setStage(PolicyGateStage.BindContractTests);
        var contractTests = BindPublicApiToArchitectureFact(projects, compilations);

        setStage(PolicyGateStage.BindWireTypes);
        var wireTypes = BuildWireTypeBindings(root, projects, compilations);
        var evidence = new[] { naming, licence, new ExternalPolicyEvidence("RP-09", sourceCommit, true, []) };
        var repository = new RepositoryFacts(root, "Contracts", projects, exceptions, contractTests);
        var configuration = new RepositoryPolicyConfiguration(sourceCommit, dependency.Hashes,
            dependency.Licenses, new HashSet<string>(StringComparer.Ordinal), [], wireTypes, evidence,
            NonWireMetadataBindings: OperationMetadataBindings.All);

        setStage(PolicyGateStage.EvaluateSharedPolicy);
        var findings = PolicyEngine.Check(repository, configuration, compilations, DateOnly.FromDateTime(DateTime.UtcNow));
        if (findings.Count != 0)
        {
            setStage(PolicyGateStage.ValidatePolicyResults);
            WriteFindingCounts(Console.Error, findings);
            throw new InvalidOperationException("Shared architecture policy reported findings.");
        }
    }

    internal static void WriteFindingCounts(TextWriter writer, IReadOnlyList<PolicyFinding> findings)
    {
        // Emit closed IDs/counts and bounded hashes of safe compiler subjects,
        // never paths, source symbols, rule messages or arbitrary caller strings.
        const int limit = 1000000;
        if (findings.Count is < 0 or > limit) throw new InvalidOperationException("Finding count exceeds diagnostic bound.");
        var known = PolicyEngine.Rules.ToHashSet(StringComparer.Ordinal);
        foreach (string rule in PolicyEngine.Rules.Order(StringComparer.Ordinal))
        {
            int count = findings.Count(finding => finding.Rule == rule);
            if (count != 0) writer.WriteLine(FormattableString.Invariant($"Contracts architecture findings: rule={rule}; count={count}."));
        }
        int unknown = findings.Count(finding => !known.Contains(finding.Rule));
        if (unknown != 0) writer.WriteLine(FormattableString.Invariant($"Contracts architecture findings: rule=Unknown; count={unknown}."));
        WriteAt12Categories(writer, findings);
    }

    private static void WriteAt12Categories(TextWriter writer, IReadOnlyList<PolicyFinding> findings)
    {
        // These are the actual published producer's fixed message categories.
        // A future/unrecognized producer message is counted as Unknown, never printed.
        (string Category, string Prefix)[] categories =
        [
            ("SourceBinding", "Missing, duplicate, ambiguous or invalid reviewed metadata source binding: "),
            ("PolicyShape", "Metadata is not the closed immutable authorization policy: "),
            ("CatalogShape", "Metadata is not a canonical immutable authorization catalog: "),
            ("Payload", "Reviewed non-wire metadata reaches a wire/RPC/serializer payload: "),
            ("Sink", "Reviewed non-wire metadata escapes through a serialization/transport invocation: "),
            ("WireBinding", "Wire type is not bound to generated owned schema: "),
            ("Unknown", ""),
        ];
        int[] counts = new int[categories.Length];
        int[] sampled = new int[categories.Length];
        var subjects = categories.Select(_ => new HashSet<string>(StringComparer.Ordinal)).ToArray();
        foreach (var finding in findings.Where(finding => finding.Rule == "AT-12"))
        {
            int index = Array.FindIndex(categories, category => category.Prefix.Length != 0
                && finding.Message is not null && finding.Message.StartsWith(category.Prefix, StringComparison.Ordinal));
            if (index < 0) index = categories.Length - 1;
            counts[index]++;
            // At most eight observations per category are inspected for a hash.
            // Unsafe/long subjects are omitted, never truncated or reinterpreted.
            if (index == categories.Length - 1 || sampled[index]++ >= 8) continue;
            string subject = finding.Message[categories[index].Prefix.Length..];
            if (!SafeDiagnosticSubject(subject)) continue;
            subjects[index].Add(Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(
                System.Text.Encoding.UTF8.GetBytes(subject))));
        }
        for (int index = 0; index < categories.Length; index++)
        {
            if (counts[index] == 0) continue;
            string category = categories[index].Category;
            writer.WriteLine(FormattableString.Invariant($"Contracts architecture AT-12: category={category}; count={counts[index]}."));
            foreach (string hash in subjects[index].Order(StringComparer.Ordinal))
                writer.WriteLine($"Contracts architecture AT-12 subject: category={category}; sha256={hash}.");
        }
    }

    private static bool SafeDiagnosticSubject(string value) =>
        value.Length is > 0 and <= 1024 && char.IsAsciiLetter(value[0])
        && value.Contains('.', StringComparison.Ordinal) && value == value.Trim()
        && value.All(character => char.IsAsciiLetterOrDigit(character)
            || "_ .+[]<>(),?`".Contains(character, StringComparison.Ordinal));

    internal const string HostProject = "tests/ArchitectureTests/ArcForges.Contracts.ArchitectureTests.csproj";
    internal const string BuildPolicyPackage = "ArcForges.Build.Policy";

    /// <summary>
    /// The one reviewed RP-03 exception waives every RP-03 finding of the architecture host project while it
    /// lives, so the host's complete AGPL closure must be exactly the Build.Policy package and nothing else.
    /// </summary>
    internal static bool AgplClosureIsExactlyBuildPolicy(IEnumerable<string> agplPackages) =>
        agplPackages.Order(StringComparer.OrdinalIgnoreCase).SequenceEqual([BuildPolicyPackage], StringComparer.OrdinalIgnoreCase);

    private static void VerifyHostLicenceClosure(IReadOnlyList<ProjectFacts> projects, IReadOnlyDictionary<string, string> licenses)
    {
        var host = projects.Single(project => project.Classification.Path == HostProject);
        string[] agpl = host.Packages.Keys.Where(package => !licenses.TryGetValue(package, out string? licence)
            || licence.StartsWith("AGPL", StringComparison.Ordinal)).Order(StringComparer.OrdinalIgnoreCase).ToArray();
        Checks.True(AgplClosureIsExactlyBuildPolicy(agpl),
            "The architecture host's AGPL or unclassified closure is not exactly the Build.Policy package.");
        Checks.True(host.Boundary == "Apache" && host.ProjectReferences.Count == 0 && host.Classification.Role == ProjectRole.Test,
            "The architecture host must stay an Apache test project with no project references.");
    }

    // The repository forbids reflection-based System.Text.Json, so the inventory is read as a document.
    private static PolicyException[] ReadPolicyExceptions(string root)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/policy/exceptions.json")));
        if (document.RootElement.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidOperationException("Policy exception inventory is not an array.");
        }

        string Text(JsonElement row, string name) => row.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()! : throw new InvalidOperationException("Policy exception row is incomplete.");
        return document.RootElement.EnumerateArray().Select(row => new PolicyException(Text(row, "rule"), Text(row, "path"),
            Text(row, "owner"), Text(row, "reason"), DateOnly.ParseExact(Text(row, "expires"), "yyyy-MM-dd",
                System.Globalization.CultureInfo.InvariantCulture))).ToArray();
    }

    internal static PolicyGateStage ClassifyCompilationFailure(Exception exception)
    {
        if (exception is not InvalidOperationException invalidOperation) return PolicyGateStage.ReadProjectCompilations;

        // These prefixes are emitted by the exact pinned Build.Policy producer. They are
        // consumed only to select a fixed enum; the message itself is never displayed.
        if (invalidOperation.Message.StartsWith("Completed source/reference inputs are required:", StringComparison.Ordinal))
        {
            return PolicyGateStage.MissingSourceOrReferenceInputs;
        }

        if (invalidOperation.Message.StartsWith("Unsupported managed output kind:", StringComparison.Ordinal))
        {
            return PolicyGateStage.UnsupportedOutputType;
        }

        if (invalidOperation.Message.StartsWith("Invalid owning compilation:", StringComparison.Ordinal))
        {
            return PolicyGateStage.ReconstructedCompilationDiagnostics;
        }

        return PolicyGateStage.ReadProjectCompilations;
    }

    private static string RequireHostedIdentity(string root)
    {
        string? actions = Environment.GetEnvironmentVariable("GITHUB_ACTIONS");
        string? job = Environment.GetEnvironmentVariable("GITHUB_JOB");
        string? source = Environment.GetEnvironmentVariable("GITHUB_SHA");
        if (actions != "true" || job != "secrets" || source is null || !Regex.IsMatch(source, "^[0-9a-f]{40}$"))
        {
            throw new InvalidOperationException("The architecture gate requires the exact hosted Security/secrets job identity.");
        }

        string head = Git(root, "rev-parse", "HEAD");
        if (head != source) throw new InvalidOperationException("The architecture gate source differs from GITHUB_SHA.");
        return source;
    }

    private static ExternalPolicyEvidence ReadNamingEvidence(string root, string sourceCommit, string rule)
    {
        string path = Path.Combine(root, "artifacts/evidence/naming.json");
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        Checks.Equal("source-policy-scan", document.RootElement.GetProperty("evidenceClass").GetString(),
            "Canonical naming report has the wrong evidence class.");
        Checks.SequenceEqual(new[] { "WP00.00", "WP00.01" }, document.RootElement.GetProperty("substeps").EnumerateArray()
            .Select(value => value.GetString()!), "Canonical naming report omitted an authoritative WP00 scan.");
        var rows = document.RootElement.GetProperty("repositories").EnumerateArray()
            .Where(value => value.GetProperty("repository").GetString() == "Contracts").ToArray();
        Checks.Equal(1, rows.Length, "Canonical naming report must contain exactly one Contracts source row.");
        var row = rows[0];
        Checks.Equal(sourceCommit, row.GetProperty("commit").GetString(), "Canonical naming report is not bound to GITHUB_SHA.");
        Checks.Equal(false, row.GetProperty("dirty").GetBoolean(), "Canonical naming report is not from a clean checkout.");
        Checks.Equal("pass", row.GetProperty("status").GetString(), "Canonical naming policy did not pass.");
        Checks.Equal(0, row.GetProperty("findings").GetArrayLength(), "Canonical naming report contains findings.");
        return new ExternalPolicyEvidence(rule, sourceCommit, true, []);
    }

    private static void VerifySecurityWorkflow(string root)
    {
        string workflow = File.ReadAllText(Path.Combine(root, ".github/workflows/security.yml"));
        const string scanName = "- name: Scan full reviewed history with redacted output";
        const string dotnetPin = "actions/setup-dotnet@a98b56852c35b8e3190ac28c8c2271da59106c68";
        const string pythonPin = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97";
        string[] orderedSteps =
        [
            scanName,
            dotnetPin,
            pythonPin,
            "dotnet restore ArcForges.Contracts.slnx --locked-mode",
            "dotnet build ArcForges.Contracts.slnx --configuration Release --no-restore --verbosity minimal",
            "python eng/check_naming.py --report artifacts/evidence/naming.json",
            "dotnet tests/ArchitectureTests/bin/Release/net10.0/ArcForges.Contracts.ArchitectureTests.dll --hosted",
        ];
        int previous = -1;
        foreach (string step in orderedSteps)
        {
            int current = workflow.IndexOf(step, StringComparison.Ordinal);
            Checks.True(current > previous, "Security workflow must preserve the successful Gitleaks -> pinned full build -> naming -> architecture sequence.");
            previous = current;
        }

        Checks.True(workflow.Contains("fetch-depth: 0", StringComparison.Ordinal), "The hosted secret scan must inspect reviewed history.");
        Checks.True(workflow.Contains("ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f", StringComparison.Ordinal)
            && workflow.Contains("--redact --no-banner --verbose --config /repo/.gitleaks.toml", StringComparison.Ordinal),
            "The existing pinned, redacted Gitleaks command changed or was removed.");
        string afterScan = workflow[workflow.IndexOf(scanName, StringComparison.Ordinal)..];
        Checks.True(!afterScan.Contains("continue-on-error: true", StringComparison.Ordinal)
            && !afterScan.Contains("if: always()", StringComparison.Ordinal),
            "A later Security step can no longer treat failed Gitleaks as successful antecedent evidence.");
        Checks.True(workflow.Contains("python-version-file: .python-version", StringComparison.Ordinal)
            && workflow.Contains("global-json-file: global.json", StringComparison.Ordinal),
            "Hosted canonical report/build is not bound to existing pinned toolchains.");
    }

    private static List<ProjectFacts> ReadProjectGraph(string root)
    {
        using var manifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/contract-packages.json")));
        var packages = manifest.RootElement.GetProperty("packages").EnumerateArray()
            .Where(row => row.GetProperty("kind").GetString() == "nuget")
            .ToDictionary(row => row.GetProperty("sourceRoot").GetString()!.Replace('\\', '/'), StringComparer.Ordinal);
        var solution = XDocument.Load(Path.Combine(root, "ArcForges.Contracts.slnx"));
        string[] paths = solution.Descendants("Project").Select(project => project.Attribute("Path")?.Value)
            .Where(path => path is not null && path.EndsWith(".csproj", StringComparison.Ordinal))!
            .Select(path => path!).Order(StringComparer.Ordinal).ToArray();
        Checks.True(paths.Contains("tests/ArchitectureTests/ArcForges.Contracts.ArchitectureTests.csproj", StringComparer.Ordinal),
            "ArchitectureTests is absent from the full solution build graph.");

        var result = new List<ProjectFacts>(paths.Length);
        foreach (string path in paths)
        {
            var elapsed = Stopwatch.StartNew();
            ProjectRole role;
            bool production;
            if (path.StartsWith("tests/", StringComparison.Ordinal))
            {
                role = ProjectRole.Test;
                production = false;
            }
            else if (path == "eng/Codegen/Codegen.csproj")
            {
                role = ProjectRole.BuildTool;
                production = false;
            }
            else if (path == "src/public/dotnet/ArcForges.Contracts.Foundation/ArcForges.Contracts.Foundation.csproj")
            {
                role = ProjectRole.Foundation;
                production = true;
            }
            else
            {
                string projectRoot = Path.GetDirectoryName(path)!.Replace('\\', '/');
                if (!packages.ContainsKey(projectRoot)) throw new InvalidOperationException("Unclassified solution project in the Contracts policy graph.");
                // Contracts hosts no RPC adapter or port implementation, so none is classified as one. A cataloged
                // project is a Contracts project only when it holds generated wire and shape types. The projects below
                // also hold authored public types (validation, sandbox profile, SDK client, CLI); they are classified
                // by their real role so that the generated-wire-type rule does not apply to code that is not generated.
                // No policy exception is used: an exception matches a whole project path and would hide generated types.
                role = AuthoredRoles.TryGetValue(path, out var authored) ? authored : ProjectRole.Contracts;
                production = true;
            }

            var classification = new ProjectClassification(path, role, "Contracts", Production: production, Aot: false);
            result.Add(ProjectGraph.Evaluate(root, classification, configuration: "Release"));
            Program.WriteProgress(Console.Out, PolicyGateStage.ReadProjectGraph, elapsed.ElapsedMilliseconds, result.Count, paths.Length);
        }

        return result;
    }

    private static void VerifyProtoDtoSymbols(string root, IReadOnlyList<ProjectFacts> projects,
        IReadOnlyDictionary<string, CSharpCompilation> compilations)
    {
        using var manifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/contract-packages.json")));
        var protoPackages = manifest.RootElement.GetProperty("packages").EnumerateArray()
            .Where(row => row.GetProperty("kind").GetString() == "nuget" && row.GetProperty("proto").GetArrayLength() > 0)
            .ToDictionary(row => Path.GetDirectoryName(Path.Combine(row.GetProperty("sourceRoot").GetString()!, row.GetProperty("id").GetString() + ".csproj"))!
                .Replace('\\', '/') + "/" + row.GetProperty("id").GetString() + ".csproj", StringComparer.Ordinal);
        int publicWireDtos = 0;
        // Every cataloged project, whatever its role: authored helper projects may not define protobuf messages by hand.
        foreach (var project in projects.Where(project => project.Classification.Role is not (ProjectRole.Test or ProjectRole.BuildTool)))
        {
            if (!compilations.TryGetValue(project.Classification.Path, out var compilation)) continue;
            foreach (var tree in compilation.SyntaxTrees)
            {
                var model = compilation.GetSemanticModel(tree);
                foreach (var declaration in tree.GetRoot().DescendantNodes().OfType<BaseTypeDeclarationSyntax>())
                {
                    if (model.GetDeclaredSymbol(declaration) is not INamedTypeSymbol type
                        || type.DeclaredAccessibility != Accessibility.Public || type.TypeKind != TypeKind.Class
                        || !type.AllInterfaces.Any(contract => contract.OriginalDefinition.ToDisplayString().StartsWith("Google.Protobuf.IMessage<", StringComparison.Ordinal))) continue;
                    publicWireDtos++;
                    string relative = Path.GetRelativePath(root, tree.FilePath).Replace('\\', '/');
                    Checks.True(relative.Contains("/Generated/Proto/", StringComparison.Ordinal), "A public business DTO was authored outside protoc-generated source.");
                    var source = Regex.Match(File.ReadAllText(tree.FilePath), @"^//\s*source:\s*(?<path>[A-Za-z0-9_./-]+\.proto)\s*$", RegexOptions.Multiline);
                    Checks.True(source.Success, "A public business DTO source is missing its generated schema identity.");
                    string sourceIdentity = source.Groups["path"].Value;
                    Checks.True(protoPackages.TryGetValue(project.Classification.Path, out var package)
                        && package.GetProperty("proto").EnumerateArray().Any(proto => proto.GetString()!.EndsWith(sourceIdentity, StringComparison.Ordinal)),
                        "A public business DTO was generated from a schema not owned by its contract package.");
                    // protoc stamps its generator identity on the members of each message, not on the class itself.
                    Checks.True(type.GetMembers().Any(member => member.GetAttributes().Any(attribute =>
                        attribute.AttributeClass?.ToDisplayString() == "System.CodeDom.Compiler.GeneratedCodeAttribute"
                        && attribute.ConstructorArguments.FirstOrDefault().Value as string == "protoc")),
                        "A public business DTO is missing the protoc generator identity.");
                }
            }
        }

        Checks.True(publicWireDtos > 0, "No compiled public business DTOs were validated against their authored proto source.");
    }

    private static void VerifySerializationClosure(string root, IReadOnlyList<ProjectFacts> projects,
        IReadOnlyDictionary<string, CSharpCompilation> compilations)
    {
        string commonProps = File.ReadAllText(Path.Combine(root, "Directory.Build.props"));
        const string disabled = "<JsonSerializerIsReflectionEnabledByDefault>false</JsonSerializerIsReflectionEnabledByDefault>";
        Checks.True(commonProps.Contains(disabled, StringComparison.Ordinal),
            "The shared project configuration must disable reflection-based JSON metadata.");
        foreach (var project in projects)
        {
            string projectPath = Path.Combine(root, project.Classification.Path);
            var projectXml = XDocument.Load(projectPath);
            Checks.True(projectXml.Descendants().Where(element => element.Name.LocalName == "JsonSerializerIsReflectionEnabledByDefault")
                .All(element => element.Value == "false"), "A project enables reflection-based JSON metadata.");
        }

        foreach (var project in projects.Where(project => project.Classification.Production))
        {
            if (!compilations.TryGetValue(project.Classification.Path, out var compilation)) continue;
            Checks.Empty(ContractsArchitectureTests.FindUnregisteredJsonSerializer(compilation),
                "A serializer call bypasses registered compile-time JsonTypeInfo metadata.");
        }
    }

    private static (Dictionary<string, string> Hashes, Dictionary<string, string> Licenses) ReadDependencyPolicy(string root)
    {
        using var policy = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/policy/dependency-policy.json")));
        var hashes = policy.RootElement.GetProperty("inputHashes").EnumerateObject()
            .ToDictionary(item => item.Name, item => item.Value.GetString()!, StringComparer.Ordinal);
        var licenses = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
        foreach (var package in policy.RootElement.GetProperty("closure").EnumerateObject())
        {
            string key = package.Name;
            if (!key.StartsWith("nuget:", StringComparison.OrdinalIgnoreCase)) continue;
            int versionSeparator = key.LastIndexOf('@');
            if (versionSeparator <= 6) throw new InvalidOperationException("Malformed NuGet identity in the reviewed dependency closure.");
            string name = key[6..versionSeparator];
            if (!licenses.TryGetValue(name, out var values)) licenses.Add(name, values = []);
            values.Add(package.Value.GetProperty("licence").GetString()!);
        }

        return (hashes, licenses.ToDictionary(group => group.Key,
            group => group.Value.Distinct(StringComparer.Ordinal).Single(), StringComparer.OrdinalIgnoreCase));
    }

    private static IReadOnlyList<ContractTestBinding> BindPublicApiToArchitectureFact(
        IReadOnlyList<ProjectFacts> projects, IReadOnlyDictionary<string, CSharpCompilation> compilations)
    {
        const string testProject = "tests/ArchitectureTests/ArcForges.Contracts.ArchitectureTests.csproj";
        var host = compilations[testProject];
        var testMethod = host.GetTypeByMetadataName("ArcForges.Contracts.ArchitectureTests.ContractsArchitectureTests")?
            .GetMembers("VerifyEveryPublicApiHasGeneratedContractTestBinding").OfType<IMethodSymbol>().SingleOrDefault();
        if (testMethod is null || !testMethod.GetAttributes().Any(attribute =>
            attribute.AttributeClass?.ToDisplayString() == "Xunit.FactAttribute"))
        {
            throw new InvalidOperationException("The architecture contract fact is missing or not registered as a real test.");
        }

        string binding = PolicyEngine.MethodIdentity(testMethod);
        var result = new List<ContractTestBinding>();
        foreach (var project in projects.Where(project => project.Classification.Production))
        {
            var compilation = compilations[project.Classification.Path];
            foreach (var tree in compilation.SyntaxTrees)
            {
                var model = compilation.GetSemanticModel(tree);
                foreach (var declaration in tree.GetRoot().DescendantNodes().OfType<BaseTypeDeclarationSyntax>())
                {
                    if (model.GetDeclaredSymbol(declaration) is not INamedTypeSymbol type) continue;
                    foreach (var method in type.GetMembers().OfType<IMethodSymbol>().Where(method => method.DeclaredAccessibility == Accessibility.Public
                        && method.MethodKind == MethodKind.Ordinary && !method.IsImplicitlyDeclared))
                    {
                        result.Add(new ContractTestBinding(PolicyEngine.MethodIdentity(method), testProject, binding));
                    }
                }
            }
        }

        return result;
    }

    private static IReadOnlyList<WireTypeBinding> BuildWireTypeBindings(string root, IReadOnlyList<ProjectFacts> projects,
        IReadOnlyDictionary<string, CSharpCompilation> compilations)
    {
        var catalog = WireSchemaCatalog.Read(root);
        var hashes = new Dictionary<string, string>(StringComparer.Ordinal);
        var bindings = new Dictionary<string, WireTypeBinding>(StringComparer.Ordinal);
        foreach (var project in projects.Where(project => project.Classification.Role == ProjectRole.Contracts))
        {
            var compilation = compilations[project.Classification.Path];
            foreach (var tree in compilation.SyntaxTrees)
            {
                // Only the owned schema of the exact generated file binds its types; an authored or unrecognized
                // file resolves to nothing and its public types stay unbound for the shared rule to report.
                string? schema = catalog.SchemaFor(project.Classification.Path, tree.FilePath, File.ReadAllText(tree.FilePath));
                if (schema is null) continue;
                if (!hashes.TryGetValue(schema, out string? hash)) hashes.Add(schema, hash = HashNormalized(Path.Combine(root, schema)));
                var model = compilation.GetSemanticModel(tree);
                foreach (var declaration in tree.GetRoot().DescendantNodes().OfType<BaseTypeDeclarationSyntax>())
                {
                    if (model.GetDeclaredSymbol(declaration) is not INamedTypeSymbol type || type.DeclaredAccessibility != Accessibility.Public
                        || type.TypeKind is not (TypeKind.Class or TypeKind.Struct or TypeKind.Enum)) continue;
                    bindings.TryAdd(type.ToDisplayString(), new WireTypeBinding(type.ToDisplayString(), schema, hash));
                }
            }
        }

        return bindings.Values.ToArray();
    }

    private static string HashNormalized(string path) => Convert.ToHexStringLower(
        SHA256.HashData(Encoding.UTF8.GetBytes(File.ReadAllText(path).Replace("\r\n", "\n", StringComparison.Ordinal))));

    private static string Git(string root, params string[] args)
    {
        var start = new ProcessStartInfo("git") { WorkingDirectory = root, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true };
        foreach (string argument in args) start.ArgumentList.Add(argument);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Git could not be started.");
        string output = process.StandardOutput.ReadToEnd().Trim();
        process.WaitForExit();
        if (process.ExitCode != 0) throw new InvalidOperationException("Git source identity could not be read.");
        return output;
    }
}
