// SPDX-License-Identifier: Apache-2.0
// CON.40: C# replacements for the architecture checks that the retired TypeScript and Kotlin consumer
// tests carried for the business SDKs. Each rule runs over the repository sources and over a negative
// fixture that must fail, so a rule that stops matching anything is itself a failure.
//   SDK-01 binary wire only: retired "public transport is binary gRPC-Web and refuses codec overrides".
//   SDK-02 caller-owned transport: the same TypeScript case; a C# SDK client never builds its own channel.
//   SDK-03 operator surface internal: retired "CON.14 keeps OperatorService and its records out of the public package".
//   SDK-04 public SDK imports no local or internal schema: retired "CON.25 the public connector package imports no local schema".
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;

namespace ArcForges.Contracts.ArchitectureTests.Sdk;

internal static class SdkArchitectureTests
{
    private static readonly string[] JsonCodecSymbols = ["JsonFormatter", "Google.Protobuf.JsonParser", "JsonParser.Default", "TypeRegistry"];
    private static readonly string[] OwnedTransportSymbols = ["GrpcChannel", "HttpClient", "GrpcWebHandler", "new Channel(", "ChannelCredentials", "SslCredentials", "GetEnvironmentVariable"];
    private static readonly string[] OperatorSymbols = ["arcforges.operator", "OperatorService", "OperatorCallContext", "OperatorProposalRef", "CloudInternal.Operator"];
    private static readonly string[] InternalNamespaces = ["ArcForges.Contracts.LocalRpc", "ArcForges.Contracts.CloudInternal", "arcforges/local/", "internal/proto/"];

    private static readonly Regex Marshaller = new(@"grpc::Marshaller<[^>]+>\s+\w+\s*=\s*(?<create>[^;]+);", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(5));
    private static readonly Regex BinaryMarshaller = new(
        @"^grpc::Marshallers\.Create\(__Helper_SerializeMessage, context => __Helper_DeserializeMessage\(context, global::[A-Za-z0-9_.]+\.Parser\)\)$",
        RegexOptions.CultureInvariant, TimeSpan.FromSeconds(5));
    private static readonly Regex PublicConstructor = new(@"public\s+(?<type>[A-Z]\w*)\s*\((?<parameters>[^)]*)\)", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(5));
    private static readonly Regex PublicClass = new(@"public\s+(?:sealed\s+|static\s+|abstract\s+|partial\s+)*class\s+(?<type>[A-Z]\w*)", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(5));

    /// <summary>
    /// Self-registration: the architecture host has a fixed entry point, so these rules run when the host module
    /// loads, before Main. A violation prints only the rule identifier and exits non-zero, like the host's own
    /// fail-closed stage report, and never echoes source text or environment values.
    /// </summary>
    [ModuleInitializer]
    internal static void Register()
    {
        var rule = "SDK-00";
        try
        {
            Run(RepositoryRoot.Find(), next => rule = next);
            Console.WriteLine("Contracts SDK architecture rules SDK-01 to SDK-04 passed with their negative fixtures.");
        }
        catch (Exception exception)
        {
            _ = exception;
            Console.Error.WriteLine($"Contracts SDK architecture policy failed closed at rule {rule}.");
            Environment.Exit(1);
        }
    }

    internal static void Run(string root, Action<string> setRule)
    {
        setRule("SDK-00");
        SelfTest();
        var publicSources = Sources(root, "src/public/dotnet", "*.cs");
        Require(publicSources.Count > 0, "public C# SDK sources");

        setRule("SDK-01");
        var grpcFiles = publicSources.Where(source => source.Path.EndsWith("Grpc.cs", StringComparison.Ordinal) && source.Path.Contains("/Generated/Proto/", StringComparison.Ordinal)).ToArray();
        Require(grpcFiles.Length > 0, "generated public gRPC bindings");
        foreach (var file in grpcFiles) Require(BinaryWireOnly(file.Text), "binary marshallers in " + file.Path);
        foreach (var file in publicSources) Require(!UsesJsonCodec(file.Text), "no protobuf JSON codec in " + file.Path);

        setRule("SDK-02");
        var clientSources = publicSources.Where(source => source.Path.StartsWith("src/public/dotnet/ArcForges.Sdk.Client/", StringComparison.Ordinal)).ToArray();
        Require(clientSources.Length > 0, "SDK client sources");
        foreach (var file in clientSources) Require(CallerOwnedTransport(file.Text), "caller-owned transport in " + file.Path);

        setRule("SDK-03");
        foreach (var file in publicSources.Concat(Sources(root, "public/proto", "*.proto")).Concat(Sources(root, "public/proto", "*.json")))
            Require(!MentionsOperator(file.Text), "no operator surface in " + file.Path);
        var operatorOwners = Sources(root, "src", "OperatorGrpc.cs").Select(source => source.Path).ToArray();
        Require(operatorOwners.SequenceEqual(["src/internal/dotnet/ArcForges.Contracts.CloudInternal/Generated/Proto/OperatorGrpc.cs"]), "OperatorService is generated only in CloudInternal");

        setRule("SDK-04");
        foreach (var file in publicSources) Require(!ImportsInternal(file.Text), "no internal or local schema in " + file.Path);
        foreach (var project in Sources(root, "src/public/dotnet", "*.csproj"))
            Require(!project.Text.Contains("src/internal/", StringComparison.Ordinal) && !project.Text.Contains("src\\internal\\", StringComparison.Ordinal)
                && !project.Text.Contains("../../../internal/", StringComparison.Ordinal) && !project.Text.Contains("..\\..\\..\\internal\\", StringComparison.Ordinal),
                "no internal project reference in " + project.Path);
        foreach (var proto in Sources(root, "public/proto", "*.proto"))
            Require(!proto.Text.Split('\n').Any(line => line.TrimStart().StartsWith("import ", StringComparison.Ordinal) && ImportsInternal(line)), "no internal import in " + proto.Path);
    }

    internal static bool BinaryWireOnly(string text)
    {
        var marshallers = Marshaller.Matches(text);
        return marshallers.Count > 0
            && marshallers.All(match => BinaryMarshaller.IsMatch(match.Groups["create"].Value.Trim()))
            && text.Contains("global::Google.Protobuf.MessageExtensions.WriteTo(message, context.GetBufferWriter())", StringComparison.Ordinal)
            && !UsesJsonCodec(text);
    }

    // protoc's generated ToString() is the only permitted JsonFormatter use: a diagnostic string, never a wire codec.
    internal static bool UsesJsonCodec(string text)
    {
        var codecText = text.Replace("pb::JsonFormatter.ToDiagnosticString(this)", "", StringComparison.Ordinal);
        return JsonCodecSymbols.Any(symbol => codecText.Contains(symbol, StringComparison.Ordinal));
    }

    internal static bool CallerOwnedTransport(string text)
    {
        if (OwnedTransportSymbols.Any(symbol => text.Contains(symbol, StringComparison.Ordinal))) return false;
        var classes = PublicClass.Matches(text).Select(match => match.Groups["type"].Value).ToHashSet(StringComparer.Ordinal);
        var constructors = PublicConstructor.Matches(text).Where(match => classes.Contains(match.Groups["type"].Value)).ToArray();
        return constructors.All(match => Regex.IsMatch(match.Groups["parameters"].Value, @"^\s*CallInvoker\s+\w+\s*$", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(5)));
    }

    internal static bool MentionsOperator(string text) => OperatorSymbols.Any(symbol => text.Contains(symbol, StringComparison.Ordinal));

    internal static bool ImportsInternal(string text) => InternalNamespaces.Any(symbol => text.Contains(symbol, StringComparison.Ordinal));

    private static void SelfTest()
    {
        const string binary = """
            static readonly grpc::Marshaller<global::A.B.Request> __Marshaller_a = grpc::Marshallers.Create(__Helper_SerializeMessage, context => __Helper_DeserializeMessage(context, global::A.B.Request.Parser));
            global::Google.Protobuf.MessageExtensions.WriteTo(message, context.GetBufferWriter());
            """;
        Require(BinaryWireOnly(binary), "binary fixture accepted");
        Require(!BinaryWireOnly(binary.Replace("__Helper_SerializeMessage, context", "message => global::System.Text.Encoding.UTF8.GetBytes(global::Google.Protobuf.JsonFormatter.Default.Format(message)), context", StringComparison.Ordinal)),
            "JSON marshaller fixture refused");
        Require(!BinaryWireOnly("public static class NoBinding { }"), "a binding without marshallers is refused");
        Require(UsesJsonCodec("var json = JsonFormatter.Default.Format(message);") && !UsesJsonCodec("var bytes = message.ToByteArray();"), "JSON codec detection both ways");
        Require(!UsesJsonCodec("public override string ToString() { return pb::JsonFormatter.ToDiagnosticString(this); }")
            && UsesJsonCodec("return pb::JsonFormatter.ToDiagnosticString(this) + pb::JsonParser.Default.ToString();"), "only the generated diagnostic ToString is exempt");

        const string client = """
            public sealed class LeaseClient
            {
                public LeaseClient(CallInvoker callInvoker) { }
            }
            """;
        Require(CallerOwnedTransport(client), "caller-owned client fixture accepted");
        Require(!CallerOwnedTransport(client.Replace("CallInvoker callInvoker", "string address", StringComparison.Ordinal)), "an endpoint-owning constructor is refused");
        Require(!CallerOwnedTransport(client + "\nvar channel = GrpcChannel.ForAddress(address);"), "an SDK-owned channel is refused");
        Require(!CallerOwnedTransport(client.Replace("{ }", "{ _ = new HttpClient(); }", StringComparison.Ordinal)), "an SDK-owned HTTP client is refused");

        Require(MentionsOperator("namespace ArcForges.Contracts.CloudInternal.Operator.V1;") && MentionsOperator("service OperatorService {")
            && !MentionsOperator("service ConnectorService {"), "operator detection both ways");
        Require(ImportsInternal("using ArcForges.Contracts.LocalRpc.Platform.V1;") && ImportsInternal("import \"arcforges/local/platform/v1/platform.proto\";")
            && !ImportsInternal("import \"arcforges/foundation/v1/foundation.proto\";"), "internal import detection both ways");
    }

    private sealed record Source(string Path, string Text);

    private static List<Source> Sources(string root, string directory, string pattern)
    {
        var start = System.IO.Path.Combine(root, directory);
        if (!Directory.Exists(start)) return [];
        return Directory.EnumerateFiles(start, pattern, SearchOption.AllDirectories)
            .Select(path => System.IO.Path.GetRelativePath(root, path).Replace('\\', '/'))
            .Where(path => !path.Split('/').Any(segment => segment is "bin" or "obj"))
            .Order(StringComparer.Ordinal)
            .Select(path => new Source(path, File.ReadAllText(System.IO.Path.Combine(root, path))))
            .ToList();
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
