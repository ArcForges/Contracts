// SPDX-License-Identifier: Apache-2.0

using ArcForges.Build.Policy.Architecture;

namespace ArcForges.Contracts.ArchitectureTests;

internal static class ArchitectureFixtureTests
{
    private static readonly (string Rule, string Allowed, string Banned, ProjectRole Role)[] BannedCases =
    [
        ("BAN-REFLECTION", "class C { object? M() => typeof(string); }", "class C { object? M() => System.Type.GetType(\"Example\"); }", ProjectRole.Foundation),
        ("BAN-CODEGEN", "class C { object M() => System.Linq.Expressions.Expression.Constant(1); }", "class C { object M() => new System.Reflection.Emit.DynamicMethod(\"example\", typeof(void), System.Type.EmptyTypes); }", ProjectRole.Foundation),
        ("BAN-BLOCKING", "class C { async System.Threading.Tasks.Task M() { await System.Threading.Tasks.Task.Delay(1); } }", "class C { async System.Threading.Tasks.Task M() { await System.Threading.Tasks.Task.Yield(); System.Threading.Tasks.Task.Delay(1).Wait(); } }", ProjectRole.Foundation),
        ("BAN-PROVIDER", "class C { int M() => 1; }", "namespace OpenAI { public static class Client { public static int Call() => 1; } } class C { int M() => OpenAI.Client.Call(); }", ProjectRole.Foundation),
        ("BAN-LOGGING", "class C { void M(string content) { _ = content.Length; } }", "class C { void M(string contentBody) { System.Console.WriteLine(contentBody); } }", ProjectRole.Foundation),
        ("BAN-MONEY", "class Money { decimal Add(decimal value) => value + 1m; }", "class Money { double Add(double value) => value + 1d; }", ProjectRole.Foundation),
        ("BAN-POINTER", "class C { internal System.Runtime.InteropServices.SafeHandle? Handle; }", "class C { internal System.IntPtr Handle; }", ProjectRole.Foundation),
    ];

    public static void Run()
    {
        string[] expected = Enumerable.Range(1, 14).Select(value => $"AT-{value:00}")
            .Concat(Enumerable.Range(1, 10).Select(value => $"RP-{value:00}")).ToArray();
        Checks.SequenceEqual(expected, PolicyEngine.Rules, "Shared AT/RP rule manifest changed.");
        Checks.SequenceEqual(new[] { "BAN-REFLECTION", "BAN-CODEGEN", "BAN-BLOCKING", "BAN-PROVIDER",
            "BAN-LOGGING", "BAN-MONEY", "BAN-POINTER" }, BannedCases.Select(test => test.Rule).Distinct(),
            "A banned-API regression fixture is missing.");

        foreach (var test in BannedCases)
        {
            var classification = new ProjectClassification("fixture.csproj", test.Role, "Contracts", Aot: true);
            var allowed = FixtureCompiler.Compile("Allowed", new Dictionary<string, string> { ["allowed.cs"] = test.Allowed });
            var banned = FixtureCompiler.Compile("Banned", new Dictionary<string, string> { ["banned.cs"] = test.Banned });
            Checks.Empty(BannedSymbolScanner.Scan(allowed, classification), $"Allowed fixture triggered {test.Rule}.");
            Checks.True(BannedSymbolScanner.Scan(banned, classification).Any(finding => finding.Rule == test.Rule),
                $"Banned fixture did not trigger {test.Rule}.");
        }

        ExternalPolicyEvidenceMustBeExactAndFailClosed();
        FailureDiagnosticsDoNotRevealExceptionDetails();
        ProgressIsBoundedAndContainsOnlyFixedStagesAndNumbers();
        CompilationFailureCodesAreSpecificAndFailClosed();
        WireSchemaOwnershipIsExactAndFailsClosed();
        HostAgplClosureMustBeExactlyBuildPolicy();
        OperationMetadataApprovalIsExactAndFailsClosed();
    }

    private static void OperationMetadataApprovalIsExactAndFailsClosed()
    {
        string root = RepositoryRoot.Find();
        var bindings = OperationMetadataBindings.All;
        Checks.Equal(3, bindings.Count, "The non-wire metadata approval must contain exactly the reviewed three symbols.");
        Checks.Equal(1, bindings.Count(binding => binding.Kind == NonWireMetadataKind.OperationAuthorizationPolicy),
            "The metadata approval must contain exactly one immutable policy type.");
        Checks.Equal(2, bindings.Count(binding => binding.Kind == NonWireMetadataKind.OperationAuthorizationCatalog),
            "The metadata approval must contain exactly two public business catalogues.");
        Checks.Equal(3, bindings.Select(binding => binding.TypeSymbol).Distinct(StringComparer.Ordinal).Count(),
            "The metadata approval contains duplicate symbols.");
        Checks.True(bindings.All(binding => binding.ProjectPath.StartsWith("src/public/dotnet/", StringComparison.Ordinal)
            && !binding.TypeSymbol.Contains("CloudInternal", StringComparison.Ordinal)
            && !binding.TypeSymbol.Contains("LocalRpc", StringComparison.Ordinal)),
            "Private, operator or local metadata entered the public non-wire approval.");
        var projects = new List<ProjectFacts>();
        var compilations = new Dictionary<string, Microsoft.CodeAnalysis.CSharp.CSharpCompilation>(StringComparer.Ordinal);
        foreach (var group in bindings.GroupBy(binding => binding.ProjectPath, StringComparer.Ordinal))
        {
            var files = group.ToDictionary(binding => Path.Combine(root, binding.SourcePath),
                binding => File.ReadAllText(Path.Combine(root, binding.SourcePath)), StringComparer.Ordinal);
            foreach (var binding in group)
            {
                string text = files[Path.Combine(root, binding.SourcePath)].TrimStart('\uFEFF').Replace("\r\n", "\n", StringComparison.Ordinal);
                string hash = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(text)));
                Checks.Equal(binding.SourceSha256, hash, "Reviewed metadata source identity changed.");
            }
            // Real project sources use SDK implicit System/collections/LINQ usings; mirror those compiler inputs explicitly.
            var compilation = FixtureCompiler.Create("MetadataFixture" + projects.Count, files).AddSyntaxTrees(
                Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree.ParseText(
                    "global using System; global using System.Collections.Generic; global using System.Linq;",
                    new Microsoft.CodeAnalysis.CSharp.CSharpParseOptions(Microsoft.CodeAnalysis.CSharp.LanguageVersion.CSharp14),
                    "metadata-fixture-global-usings.cs"));
            if (compilations.Count != 0) compilation = compilation.AddReferences(compilations.Values.First().ToMetadataReference());
            Checks.True(!compilation.GetDiagnostics().Any(diagnostic => diagnostic.Severity == Microsoft.CodeAnalysis.DiagnosticSeverity.Error),
                "The real approved metadata sources did not compile against their exact producer references.");
            compilations.Add(group.Key, compilation);
            projects.Add(new ProjectFacts(new ProjectClassification(group.Key, ProjectRole.Contracts, "Contracts"),
                "net10.0", "Library", "Apache-2.0", "Apache", [], files.Keys.ToArray(), [],
                new Dictionary<string, string>(StringComparer.Ordinal)
                {
                    ["ManagePackageVersionsCentrally"] = "true",
                    ["RestorePackagesWithLockFile"] = "true",
                }, new Dictionary<string, string>(StringComparer.Ordinal)));
        }
        var repository = new RepositoryFacts(root, "Contracts", projects, [], []);
        PolicyFinding[] Findings(IReadOnlyList<NonWireMetadataBinding>? approved, IReadOnlyList<WireTypeBinding>? wire = null) =>
            PolicyEngine.Check(repository, new RepositoryPolicyConfiguration(new string('a', 40),
                new Dictionary<string, string>(StringComparer.Ordinal), new Dictionary<string, string>(StringComparer.Ordinal),
                new HashSet<string>(StringComparer.Ordinal), [], wire ?? [], [], NonWireMetadataBindings: approved),
                compilations, new DateOnly(2026, 10, 6)).Where(finding => finding.Rule == "AT-12").ToArray();
        Checks.Empty(Findings(bindings), "Exact reviewed production metadata was rejected by the published shared policy.");
        Checks.True(Findings(null).Length != 0, "Missing approval incorrectly waived ordinary generated-wire requirements.");
        var first = bindings[0];
        var invalid = new[]
        {
            first with { SourceSha256 = new string('0', 64) },
            first with { TypeSymbol = "ArcForges.Contracts.PublicApi.Operations.UnreviewedPolicy" },
            first with { ProjectPath = "src/internal/dotnet/ArcForges.Contracts.CloudInternal/ArcForges.Contracts.CloudInternal.csproj" },
            first with { SourcePath = bindings[1].SourcePath },
            first with { SourcePath = "../outside.cs" },
            first with { Kind = NonWireMetadataKind.Unknown },
        };
        foreach (var mutation in invalid)
        {
            var changed = bindings.ToArray();
            changed[0] = mutation;
            Checks.True(Findings(changed).Length != 0, "An invalid non-wire source approval created an exemption.");
        }
        Checks.True(Findings(bindings.Concat([first]).ToArray()).Length != 0,
            "An ambiguous duplicate source approval created an exemption.");
        Checks.True(Findings(bindings, [new(first.TypeSymbol, "public/proto/arcforges/publicapi/v1/identity.proto", new string('a', 64))]).Length != 0,
            "Metadata was incorrectly admitted as both a wire symbol and non-wire source approval.");
    }

    private static void HostAgplClosureMustBeExactlyBuildPolicy()
    {
        Checks.True(HostedPolicyGate.AgplClosureIsExactlyBuildPolicy(["ArcForges.Build.Policy"]),
            "The exact Build.Policy closure was rejected.");
        Checks.True(!HostedPolicyGate.AgplClosureIsExactlyBuildPolicy([]),
            "A closure without Build.Policy passed the exact-AGPL negative fixture.");
        Checks.True(!HostedPolicyGate.AgplClosureIsExactlyBuildPolicy(["ArcForges.Build.Policy", "Some.Other.Agpl"]),
            "A second AGPL or unclassified package passed the exact-AGPL negative fixture.");
        Checks.True(!HostedPolicyGate.AgplClosureIsExactlyBuildPolicy(["Some.Other.Agpl"]),
            "A different AGPL package passed the exact-AGPL negative fixture.");
    }

    private static void WireSchemaOwnershipIsExactAndFailsClosed()
    {
        string root = RepositoryRoot.Find();
        var catalog = WireSchemaCatalog.Read(root);
        const string publicApi = "src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj";
        const string cloud = "src/internal/dotnet/ArcForges.Contracts.CloudInternal/ArcForges.Contracts.CloudInternal.csproj";
        string Source(string project, string local) => Path.Combine(root, Path.GetDirectoryName(project)!, local);
        string? Resolve(string project, string local, string text = "") => catalog.SchemaFor(project, Source(project, local), text);
        const string protoText = "// source: arcforges/publicapi/v1/application.proto\n";

        Checks.Equal("public/proto/arcforges/publicapi/v1/application.proto", Resolve(publicApi, "Generated/Proto/Application.cs", protoText),
            "A protoc class did not resolve to the exact owned proto.");
        Checks.Equal(null, Resolve(publicApi, "Generated/Proto/Application.cs", "// source: arcforges/unowned/v1/unowned.proto\n"),
            "A protoc class from an unowned schema resolved to an owner.");
        Checks.Equal(null, Resolve(publicApi, "Generated/Proto/Application.cs"),
            "A generated proto file without its source identity resolved to an owner.");
        Checks.Equal("public/http/v1/signed-formats.schema.json", Resolve(publicApi, "Generated/Shapes/AndroidUpdate.g.cs"),
            "A schema-generated record did not resolve to its owned JSON schema.");
        Checks.Equal("internal/ai-http/v1/schema.json", Resolve(cloud, "Generated/Shapes/CommitReceiptValidator.g.cs"),
            "A schema-generated validator did not resolve to its owned JSON schema.");
        Checks.Equal("public/proto/value-boundaries.json", Resolve(publicApi, "Generated/Values/Identifiers.g.cs"),
            "Generated value types did not resolve to the authored value-boundary profile.");
        Checks.Equal("internal/proto/constraints.json", Resolve(cloud, "Generated/Shapes/ProtoValidation.g.cs"),
            "Generated protobuf shape checks did not resolve to the authored constraint sidecar.");
        Checks.True(Resolve(publicApi, "Generated/Services/ContractServices.g.cs") is { } services
            && services.EndsWith(".proto", StringComparison.Ordinal), "The service catalogue did not resolve to an owned proto.");
        Checks.Equal(null, Resolve(publicApi, "Generated/Shapes/NoSuchModel.g.cs"),
            "A shape file with no authored root schema resolved to an owner.");
        Checks.Equal(null, Resolve(publicApi, "Authored.cs"), "An authored file resolved to a generated-schema owner.");
        Checks.Equal(null, Resolve(publicApi, "Generated/Shapes/Nested/AndroidUpdate.g.cs"),
            "A nested path resolved like a generator output.");
        Checks.Equal(null, catalog.SchemaFor("src/public/dotnet/Unlisted/Unlisted.csproj", Source(publicApi, "Generated/Shapes/AndroidUpdate.g.cs"), ""),
            "A project outside the package inventory resolved to an owner.");
        Checks.Equal(null, catalog.SchemaFor(cloud, Source(publicApi, "Generated/Shapes/AndroidUpdate.g.cs"), ""),
            "A file outside its project root resolved to an owner.");
    }

    private static void FailureDiagnosticsDoNotRevealExceptionDetails()
    {
        const string privateDetail = "untrusted exception detail must never be printed";
        using var output = new StringWriter();
        Program.WriteFailure(output, PolicyGateStage.EvaluateSharedPolicy, new Exception(privateDetail));

        string message = output.ToString().Trim();
        Checks.Equal("Contracts architecture policy failed closed at stage EvaluateSharedPolicy.", message,
            "Failure diagnostics must contain only a fixed stage code.");
        Checks.True(!message.Contains(privateDetail, StringComparison.Ordinal),
            "An exception detail escaped the redacted fail-closed diagnostic.");
    }

    private static void ProgressIsBoundedAndContainsOnlyFixedStagesAndNumbers()
    {
        using var output = new StringWriter(System.Globalization.CultureInfo.GetCultureInfo("ar-SA"));
        Program.WriteProgress(output, PolicyGateStage.ReadProjectGraph, 125, 1, 31);
        Program.WriteProgress(output, PolicyGateStage.ReadProjectCompilations, 200, 2, 30);
        Program.WriteProgress(output, PolicyGateStage.EvaluateSharedPolicy, 325);
        Checks.SequenceEqual(new[]
        {
            "Contracts architecture progress: stage=ReadProjectGraph; elapsedMs=125; project=1/31.",
            "Contracts architecture progress: stage=ReadProjectCompilations; elapsedMs=200; project=2/30.",
            "Contracts architecture progress: stage=EvaluateSharedPolicy; elapsedMs=325; project=0/0.",
        }, output.ToString().Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries),
            "Architecture progress changed its static order or revealed non-numeric details.");
        foreach (var invalid in new (PolicyGateStage Stage, long Elapsed, int Index, int Count)[]
        {
            ((PolicyGateStage)999, 0, 0, 0), (PolicyGateStage.ReadProjectGraph, -1, 0, 0),
            (PolicyGateStage.ReadProjectGraph, 0, -1, 1), (PolicyGateStage.ReadProjectGraph, 0, 2, 1),
            (PolicyGateStage.ReadProjectGraph, 0, 0, 10001), (PolicyGateStage.ReadProjectGraph, 0, 0, -1),
        })
        {
            using var refused = new StringWriter();
            bool failed = false;
            try { Program.WriteProgress(refused, invalid.Stage, invalid.Elapsed, invalid.Index, invalid.Count); }
            catch (InvalidOperationException) { failed = true; }
            Checks.True(failed && refused.ToString().Length == 0, "Invalid progress escaped before refusal.");
        }
    }

    private static void CompilationFailureCodesAreSpecificAndFailClosed()
    {
        const string missingInputsDetail = "Completed source/reference inputs are required: private/path";
        const string outputTypeDetail = "Unsupported managed output kind: SecretOutputType";
        const string compilationDetail = "Invalid owning compilation: private/path\nprivate compiler diagnostic";
        const string unknownDetail = "unrecognized private producer detail";
        var cases = new (Exception Exception, PolicyGateStage Stage, string Secret)[]
        {
            (new InvalidOperationException(missingInputsDetail), PolicyGateStage.MissingSourceOrReferenceInputs, "private/path"),
            (new InvalidOperationException(outputTypeDetail), PolicyGateStage.UnsupportedOutputType, "SecretOutputType"),
            (new InvalidOperationException(compilationDetail), PolicyGateStage.ReconstructedCompilationDiagnostics, "private compiler diagnostic"),
            (new InvalidOperationException(unknownDetail), PolicyGateStage.ReadProjectCompilations, unknownDetail),
            (new IOException("private I/O detail"), PolicyGateStage.ReadProjectCompilations, "private I/O detail"),
        };

        foreach (var test in cases)
        {
            Checks.Equal(test.Stage, HostedPolicyGate.ClassifyCompilationFailure(test.Exception),
                "A compilation failure selected the wrong fixed diagnostic stage.");
            using var output = new StringWriter();
            Program.WriteFailure(output, test.Stage, test.Exception);
            string message = output.ToString().Trim();
            Checks.Equal($"Contracts architecture policy failed closed at stage {test.Stage}.", message,
                "A compilation failure diagnostic did not contain only its fixed stage code.");
            Checks.True(!message.Contains(test.Secret, StringComparison.Ordinal),
                "A compilation failure detail escaped the redacted diagnostic.");
        }
    }

    private static void ExternalPolicyEvidenceMustBeExactAndFailClosed()
    {
        string root = RepositoryRoot.Find();
        string sourceCommit = new string('a', 40);
        var projects = Array.Empty<ProjectFacts>();
        var repository = new RepositoryFacts(root, "Contracts", projects, [], []);
        var hashes = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["global.json"] = HashNormalized(Path.Combine(root, "global.json")),
        };
        var missing = Configuration([]);
        var absent = PolicyEngine.Check(repository, missing, new Dictionary<string, Microsoft.CodeAnalysis.CSharp.CSharpCompilation>(), new DateOnly(2026, 9, 28));
        foreach (string rule in new[] { "RP-01", "RP-08", "RP-09" })
        {
            Checks.True(absent.Any(finding => finding.Rule == rule), $"Missing evidence incorrectly passed {rule}.");
        }

        var evidence = new[]
        {
            new ExternalPolicyEvidence("RP-01", sourceCommit, true, []),
            new ExternalPolicyEvidence("RP-08", sourceCommit, true, []),
            new ExternalPolicyEvidence("RP-09", sourceCommit, true, []),
        };
        var valid = PolicyEngine.Check(repository, Configuration(evidence),
            new Dictionary<string, Microsoft.CodeAnalysis.CSharp.CSharpCompilation>(), new DateOnly(2026, 9, 28));
        Checks.True(valid.All(finding => finding.Rule is not ("RP-01" or "RP-08" or "RP-09")),
            "Exact, successful evidence was not accepted.");

        var stale = evidence.Select(row => row.Rule == "RP-08" ? row with { SourceCommit = new string('b', 40) } : row).ToArray();
        var rejected = PolicyEngine.Check(repository, Configuration(stale),
            new Dictionary<string, Microsoft.CodeAnalysis.CSharp.CSharpCompilation>(), new DateOnly(2026, 9, 28));
        Checks.True(rejected.Any(finding => finding.Rule == "RP-08"), "Stale source evidence incorrectly passed RP-08.");

        RepositoryPolicyConfiguration Configuration(IReadOnlyList<ExternalPolicyEvidence> supplied) =>
            new(sourceCommit, hashes, new Dictionary<string, string>(), new HashSet<string>(), [], [], supplied);
    }

    private static string HashNormalized(string path) => Convert.ToHexStringLower(
        System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(
            File.ReadAllText(path).Replace("\r\n", "\n", StringComparison.Ordinal))));
}

internal static class Checks
{
    public static void True(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    public static void Equal<T>(T expected, T actual, string message)
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual)) throw new InvalidOperationException(message);
    }

    public static void SequenceEqual<T>(IEnumerable<T> expected, IEnumerable<T> actual, string message)
    {
        if (!expected.SequenceEqual(actual)) throw new InvalidOperationException(message);
    }

    public static void Empty<T>(IEnumerable<T> values, string message)
    {
        if (values.Any()) throw new InvalidOperationException(message);
    }
}
