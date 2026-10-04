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
        CompilationFailureCodesAreSpecificAndFailClosed();
        WireSchemaOwnershipIsExactAndFailsClosed();
        HostAgplClosureMustBeExactlyBuildPolicy();
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
