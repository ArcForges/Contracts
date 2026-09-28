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
