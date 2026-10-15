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
        LocalDispatchBoundaryRulesFailClosed();
        SdkRuleFailureIsRecordedWithoutExiting();
    }

    // AF-CON-01: a failing SDK rule is reported with its fixed rule code and recorded for Main to return 1; the module
    // initializer never exits the process itself (Environment.Exit there can block process shutdown instead).
    private static void SdkRuleFailureIsRecordedWithoutExiting()
    {
        string root = Path.Combine(Path.GetTempPath(), "arcforges-sdk-fixture-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(Path.Combine(root, "src/public/dotnet/Fixture"));
            File.WriteAllText(Path.Combine(root, "src/public/dotnet/Fixture/Bad.cs"), "var json = JsonFormatter.Default.Format(message);");
            var output = new StringWriter();
            var error = new StringWriter();
            Checks.Equal("SDK-01", Sdk.SdkArchitectureTests.Evaluate(root, output, error), "A failing SDK rule was not recorded.");
            Checks.Equal("", output.ToString(), "A failing SDK rule reported success.");
            Checks.Equal("Contracts SDK architecture policy failed closed at rule SDK-01." + Environment.NewLine, error.ToString(),
                "SDK failure diagnostics must contain only the fixed rule code.");
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }

        Checks.True(Sdk.SdkArchitectureTests.FailedRule is null, "The SDK rules of this repository failed at module load.");
    }

    // CON.43: each boundary-dispatch architecture row is proven to fail on a fixture that violates it.
    private static void LocalDispatchBoundaryRulesFailClosed()
    {
        // Filesystem order: enumeration order is not alphabetical on ext4, and ordinal order is not culture order.
        string[] ordinal = ["A.g.cs", "B/x.g.cs", "Generated/Operations/LocalOperation.g.cs", "a.g.cs", "b.g.cs"];
        foreach (string[] permutation in new[]
        {
            new[] { "b.g.cs", "Generated\\Operations\\LocalOperation.g.cs", "a.g.cs", "B/x.g.cs", "A.g.cs" },
            Enumerable.Reverse(ordinal).ToArray(),
            new[] { "a.g.cs", "A.g.cs", "b.g.cs", "B/x.g.cs", "Generated/Operations/LocalOperation.g.cs" },
        })
        {
            Checks.SequenceEqual(ordinal, ContractsArchitectureTests.OrdinalSourceOrder(permutation),
                "Dispatch source order depends on filesystem enumeration order.");
        }

        Checks.True(!ordinal.SequenceEqual(ordinal.Order(StringComparer.OrdinalIgnoreCase)),
            "The filesystem-order fixture no longer distinguishes ordinal from case-insensitive order.");
        Checks.True(ContractsArchitectureTests.IsBuildOutput("obj/Release/net10.0/Example.AssemblyInfo.cs")
            && ContractsArchitectureTests.IsBuildOutput("bin\\Release\\Example.cs")
            && !ContractsArchitectureTests.IsBuildOutput("Generated/Operations/LocalOperation.g.cs"),
            "SDK build output is not separated from Dispatch sources.");

        // (a) Source tokens: the generated idioms pass, and each reflective token fails.
        const string allowed = "static class C { static bool M(string v) => global::System.Text.RegularExpressions.Regex.IsMatch(v, \"^a$\", "
            + "global::System.Text.RegularExpressions.RegexOptions.NonBacktracking) && nameof(M).Length == 1; "
            + "static int K(string? key) => key switch { \"IScopeOperations.CreateAnnotation\" => 1, _ => 0 }; }";
        Checks.Empty(ContractsArchitectureTests.FindReflectiveSourceTokens([("allowed.g.cs", allowed)]),
            "An allowed dispatch source triggered the no-reflection row.");
        var banned = new (string Token, string Source)[]
        {
            ("System.Reflection", "using System.Reflection; class C { }"),
            ("Google.Protobuf.Reflection", "class C { object? D => global::Google.Protobuf.Reflection.FileDescriptor.FromGeneratedCode(null, null); }"),
            ("MakeGenericType", "class C { object M(System.Type t) => t.MakeGenericType(t); }"),
            ("Activator", "class C { object? M() => System.Activator.CreateInstance(\"a\", \"b\"); }"),
            ("GetType", "class C { object? M() => System.Type.GetType(\"Example\"); }"),
            ("GetType", "class C { object M(object v) => v.GetType(); }"),
            ("typeof", "class C { object M() => typeof(string); }"),
            ("Assembly", "class C { object M() => System.AppDomain.CurrentDomain.GetAssemblies()[0].GetName(); static object N() => Assembly.Load(\"x\"); }"),
            ("System.Runtime.Loader", "class C { object M() => System.Runtime.Loader.AssemblyLoadContext.Default; }"),
            ("System.Linq.Expressions", "using System.Linq.Expressions; class C { }"),
            ("Expression", "class C { object M() => Expression.Constant(1); }"),
            ("Emit", "class C { object M() => new DynamicMethod(\"m\", null, null); }"),
        };
        foreach (var (token, source) in banned)
        {
            Checks.True(ContractsArchitectureTests.FindReflectiveSourceTokens([("banned.g.cs", source)])
                .Contains("banned.g.cs: " + token, StringComparer.Ordinal), $"A dispatch source using {token} passed the no-reflection row.");
        }

        // (b) Closure: only the dispatch package may join PublicApi, Scope and Chat.
        const string dispatch = ContractsArchitectureTests.DispatchPackage;
        const string foundation = "ArcForges.Contracts.Foundation", publicApi = "ArcForges.Contracts.PublicApi",
            platform = "ArcForges.Contracts.LocalRpc.Platform", scope = "ArcForges.Contracts.LocalRpc.Scope",
            chat = "ArcForges.Contracts.LocalRpc.Chat";
        Dictionary<string, string[]> Graph(params (string Id, string[] Dependencies)[] extra)
        {
            var graph = new Dictionary<string, string[]>(StringComparer.Ordinal)
            {
                [foundation] = [],
                [publicApi] = [foundation],
                [platform] = [foundation, publicApi],
                [scope] = [foundation, publicApi, platform],
                [chat] = [foundation, publicApi, platform],
                [dispatch] = [publicApi, platform, scope, chat],
            };
            foreach (var (id, dependencies) in extra) graph[id] = dependencies;
            return graph;
        }

        Checks.SequenceEqual(new[] { dispatch }, ContractsArchitectureTests.PackagesJoiningScopeAndChat(Graph()),
            "The exact catalog shape did not name the dispatch package as the only join.");
        Checks.True(!ContractsArchitectureTests.PackagesJoiningScopeAndChat(Graph((scope, [foundation, publicApi, platform, chat])))
            .SequenceEqual([dispatch]), "A Scope package that references Chat passed the single-join row.");
        Checks.True(!ContractsArchitectureTests.PackagesJoiningScopeAndChat(Graph(("Example.Consumer", [dispatch])))
            .SequenceEqual([dispatch]), "A package whose closure includes the dispatch package passed the single-join row.");
        Checks.True(!ContractsArchitectureTests.PackagesJoiningScopeAndChat(Graph(("Example.Bridge", [scope, chat])))
            .SequenceEqual([dispatch]), "A second bridge package over Scope and Chat passed the single-join row.");
        Checks.SequenceEqual(new[] { dispatch, "Example.Cycle" }, ContractsArchitectureTests.PackagesJoiningScopeAndChat(
            Graph(("Example.Cycle", [dispatch, "Example.Cycle"]))), "A self-referencing catalog row was not evaluated.");
        bool missingFailed = false;
        try
        {
            _ = ContractsArchitectureTests.PackagesJoiningScopeAndChat(Graph(("Example.Dangling", ["Example.Unlisted"])));
        }
        catch (InvalidOperationException)
        {
            missingFailed = true;
        }

        Checks.True(missingFailed, "An uncataloged dependency did not fail the closure row closed.");

        // (b) Owners: only the dispatch owner names the structured value with Scope and Chat typed requests.
        const string scopeRequest = "global::ArcForges.Contracts.LocalRpc.Scope.V1.ScopeOperationsServiceCreateAnnotationRequest r;";
        const string chatRequest = "global::ArcForges.Contracts.LocalRpc.Chat.V1.ChatOperationsServiceAppendUserMessageRequest c;";
        const string structured = "global::ArcForges.Contracts.PublicApi.V1.CapabilityArguments a;";
        (string, IEnumerable<string>) Owner(string name, params string[] texts) => (name, texts);
        Checks.SequenceEqual(new[] { "dispatch" }, ContractsArchitectureTests.OwnersJoiningStructuredValueAndTypedRequests(
            [Owner("chat", chatRequest, "StructuredValue v;"), Owner("dispatch", scopeRequest, chatRequest, structured), Owner("scope", scopeRequest)]),
            "The exact owner set did not name the dispatch owner as the only join.");
        Checks.SequenceEqual(new[] { "chat", "dispatch" }, ContractsArchitectureTests.OwnersJoiningStructuredValueAndTypedRequests(
            [Owner("chat", chatRequest, "StructuredValue v;", scopeRequest), Owner("dispatch", scopeRequest, chatRequest, structured)]),
            "A product-operation owner naming the structured value with Scope and Chat requests passed the single-owner row.");
        Checks.Empty(ContractsArchitectureTests.OwnersJoiningStructuredValueAndTypedRequests([Owner("dispatch", scopeRequest, chatRequest)]),
            "An owner without the structured value was counted as a join.");
        Checks.SequenceEqual(new[] { "split" }, ContractsArchitectureTests.OwnersJoiningStructuredValueAndTypedRequests(
            [Owner("split", scopeRequest, chatRequest + " CapabilityResult r;")]), "A join split across one owner's files was not counted.");

        // (c) References: no cataloged package and no production csproj may reference the dispatch assembly.
        Checks.Empty(ContractsArchitectureTests.CatalogPackagesReferencingDispatch(Graph()), "The exact catalog reported a dispatch consumer.");
        Checks.SequenceEqual(new[] { scope }, ContractsArchitectureTests.CatalogPackagesReferencingDispatch(
            Graph((scope, [foundation, publicApi, platform, dispatch]))), "A cataloged package depending on Dispatch passed the reference row.");
        const string projectReference = "<Project><ItemGroup><ProjectReference Include=\"..\\ArcForges.Contracts.LocalRpc.Dispatch\\ArcForges.Contracts.LocalRpc.Dispatch.csproj\" /></ItemGroup></Project>";
        const string packageReference = "<Project><ItemGroup><PackageReference Include=\"arcforges.contracts.localrpc.dispatch\" /></ItemGroup></Project>";
        const string sibling = "<Project><ItemGroup><ProjectReference Include=\"../ArcForges.Contracts.LocalRpc.Scope/ArcForges.Contracts.LocalRpc.Scope.csproj\" />"
            + "<ProjectReference Include=\"../ArcForges.Contracts.LocalRpc.DispatchTools/ArcForges.Contracts.LocalRpc.DispatchTools.csproj\" /></ItemGroup></Project>";
        Checks.True(ContractsArchitectureTests.ReferencesDispatch(projectReference), "A Dispatch project reference passed the reference row.");
        Checks.True(ContractsArchitectureTests.ReferencesDispatch(packageReference), "A Dispatch package reference passed the reference row.");
        Checks.True(!ContractsArchitectureTests.ReferencesDispatch(sibling), "A non-Dispatch project reference was reported as Dispatch.");

        // Hosted semantic row: the compiled-symbol scan sees reflection that no source token names.
        Checks.Empty(HostedPolicyGate.FindReflectiveSymbols(FixtureCompiler.Compile("DispatchAllowed",
                new Dictionary<string, string> { ["allowed.cs"] = allowed })),
            "An allowed dispatch compilation triggered the semantic no-reflection row.");
        Checks.Empty(HostedPolicyGate.FindReflectiveSymbols(FixtureCompiler.Compile("DispatchAssemblyMetadata",
                new Dictionary<string, string> { ["AssemblyInfo.cs"] = "using System; using System.Reflection; [assembly: AssemblyCompany(\"ArcForges\")] [assembly: AssemblyMetadata(\"k\", \"v\")]" })),
            "SDK assembly metadata attributes triggered the semantic no-reflection row.");
        var semantic = new (string Name, string Source)[]
        {
            ("assembly scanning", "class C { int M() => System.AppDomain.CurrentDomain.GetAssemblies().Length; }"),
            ("alias", "using R = System.Reflection.BindingFlags; class C { int M() => (int)R.Public; }"),
            ("imported", "using System.Reflection; class C { int M() => (int)BindingFlags.Public; }"),
            ("inferred", "class C { int M(object o) { var t = o.GetType(); return t.Name.Length; } }"),
            ("typeof", "class C { string M() => typeof(C).Name; }"),
            ("generic", "class C { object M() => typeof(System.Collections.Generic.List<>).MakeGenericType(typeof(int)); }"),
            ("activator", "class C { object? M() => System.Activator.CreateInstance(typeof(C)); }"),
            ("expression", "class C { object M() => System.Linq.Expressions.Expression.Constant(1); }"),
            ("emit", "class C { object M() => new System.Reflection.Emit.DynamicMethod(\"m\", typeof(void), System.Type.EmptyTypes); }"),
            ("protobuf descriptor", "namespace Google.Protobuf.Reflection { public sealed class MessageDescriptor { public string Name => \"m\"; } } "
                + "class Message { public static Google.Protobuf.Reflection.MessageDescriptor Descriptor => new(); } class C { int M() => Message.Descriptor.Name.Length; }"),
            ("loader", "class C { object M() => System.Runtime.Loader.AssemblyLoadContext.Default; }"),
        };
        foreach (var (name, source) in semantic)
        {
            Checks.True(HostedPolicyGate.FindReflectiveSymbols(FixtureCompiler.Compile("DispatchBanned",
                    new Dictionary<string, string> { ["banned.cs"] = source })).Count != 0,
                $"A compiled dispatch fixture using {name} passed the semantic no-reflection row.");
        }
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
