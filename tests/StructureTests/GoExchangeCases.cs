// SPDX-License-Identifier: Apache-2.0
using System.Text.Json.Nodes;
using Google.Protobuf;
using Google.Protobuf.Reflection;

/// <summary>
/// AF-CTR-01: the C# leg of the Go binding exchange that <c>python eng/contracts.py go exchange</c> drives. The generated
/// C# codecs read and rewrite the reference-codec sample of every message (and every oneof arm) of the Go module, and
/// encode every positive foundation fixture case; the generated Go codecs read both next, and the reference reader
/// checks what Go writes back. Offline files only; the message set is the explicit file list below, never discovered.
/// </summary>
internal static class GoExchangeCases
{
    // The proto files of the Go module row of eng/contract-packages.json; the Python verifier compares this list.
    private static readonly FileDescriptor[] Files =
    [
        ArcForges.Contracts.Foundation.V1.FoundationReflection.Descriptor,
        ArcForges.Contracts.Hello.V1.HelloReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ApplicationReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ChatReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.CommerceReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ConnectorReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ContentReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.DescriptorsReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ExportReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.IdentityReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.InprocessValuesReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ScopeReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.SupportReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.SupportAccessReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.SyncReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.TransferReflection.Descriptor,
        ArcForges.Contracts.Catalog.V1.CatalogReflection.Descriptor,
        ArcForges.Contracts.Node.V1.AccountReflection.Descriptor,
        ArcForges.Contracts.Node.V1.ApprovalsReflection.Descriptor,
        ArcForges.Contracts.Node.V1.CachesReflection.Descriptor,
        ArcForges.Contracts.Node.V1.CommonReflection.Descriptor,
        ArcForges.Contracts.Node.V1.DiagnosisReflection.Descriptor,
        ArcForges.Contracts.Node.V1.EventsReflection.Descriptor,
        ArcForges.Contracts.Node.V1.IntegrationsReflection.Descriptor,
        ArcForges.Contracts.Node.V1.MemoryReflection.Descriptor,
        ArcForges.Contracts.Node.V1.NodeReflection.Descriptor,
        ArcForges.Contracts.Node.V1.PeersReflection.Descriptor,
        ArcForges.Contracts.Node.V1.PolicyReflection.Descriptor,
        ArcForges.Contracts.Node.V1.QueueReflection.Descriptor,
        ArcForges.Contracts.Node.V1.ResourcesReflection.Descriptor,
        ArcForges.Contracts.Node.V1.SessionsReflection.Descriptor,
        ArcForges.Contracts.Node.V1.StorageReflection.Descriptor,
        ArcForges.Contracts.Node.V1.SupportReflection.Descriptor,
        ArcForges.Contracts.Node.V1.TasksReflection.Descriptor,
        ArcForges.Contracts.Node.V1.ToolchainsReflection.Descriptor,
        ArcForges.Contracts.Node.V1.UpdatesReflection.Descriptor,
        ArcForges.Contracts.Node.V1.WorkspacesReflection.Descriptor,
        ArcForges.Contracts.Fleet.V1.FleetReflection.Descriptor,
        ArcForges.Contracts.Relay.V1.RelayReflection.Descriptor,
        ArcForges.Contracts.CloudInternal.Operator.V1.OperatorReflection.Descriptor,
        ArcForges.Contracts.CloudInternal.Operator.V1.OperatorReadReflection.Descriptor,
    ];

    internal static void Run(string root, string directory)
    {
        var messages = new Dictionary<string, MessageDescriptor>(StringComparer.Ordinal);
        foreach (var file in Files) Collect(file.MessageTypes, messages);
        File.WriteAllText(Path.Combine(directory, "csharp-files.txt"), string.Join('\n', Files.Select(file => file.Name)) + "\n");

        // Reference-codec samples: parse with the generated C# codec and write back what C# encodes.
        var listed = File.ReadAllLines(Path.Combine(directory, "messages.txt")).Where(line => line.Length != 0).ToArray();
        if (listed.Length == 0) throw new InvalidOperationException("The Go exchange emitted no sample");
        var current = Directory.CreateDirectory(Path.Combine(directory, "current")).FullName;
        foreach (var sample in listed)
        {
            // A sample is a message name, or the name and "@" and the index of an extra oneof-arm sample.
            var name = sample.Split('@')[0];
            if (!messages.TryGetValue(name, out var descriptor))
                throw new InvalidOperationException("The C# generated codecs lack Go module message " + name);
            var message = descriptor.Parser.ParseFrom(File.ReadAllBytes(Path.Combine(directory, "previous", sample + ".bin")));
            File.WriteAllBytes(Path.Combine(current, sample + ".bin"), message.ToByteArray());
        }

        // Positive foundation fixture cases: the C# encoding of each authored protobuf-JSON value.
        var fixtures = Directory.CreateDirectory(Path.Combine(directory, "fixtures")).FullName;
        var index = new JsonArray();
        var number = 0;
        foreach (var (id, descriptor, json) in Con40SdkCases.PositiveFoundationCases(root))
        {
            if (!messages.ContainsKey(descriptor.FullName))
                throw new InvalidOperationException("A foundation fixture targets a message outside the Go module: " + id);
            var message = JsonParser.Default.Parse(json, descriptor);
            var file = number.ToString(System.Globalization.CultureInfo.InvariantCulture) + ".bin";
            File.WriteAllBytes(Path.Combine(fixtures, file), message.ToByteArray());
            JsonNode entry = new JsonObject { ["id"] = id, ["type"] = descriptor.FullName, ["json"] = json, ["file"] = file };
            index.Add(entry);
            number++;
        }
        if (number < 200) throw new InvalidOperationException("The foundation fixture set is incomplete");
        File.WriteAllText(Path.Combine(fixtures, "index.json"), index.ToJsonString() + "\n");
        Console.WriteLine($"C# generated codecs rewrote {listed.Length} Go module samples of {messages.Count} messages and encoded {number} foundation fixture cases; the Go codecs read them next.");
    }

    /// <summary>The second C# pass: the generated C# codecs read what Go wrote and must encode exactly what they
    /// encoded before, so Go's field order (oneof members last) carries the same meaning to C#.</summary>
    internal static void Verify(string directory)
    {
        var messages = new Dictionary<string, MessageDescriptor>(StringComparer.Ordinal);
        foreach (var file in Files) Collect(file.MessageTypes, messages);
        var listed = File.ReadAllLines(Path.Combine(directory, "messages.txt")).Where(line => line.Length != 0).ToArray();
        int samples = 0, fixtures = 0;
        foreach (var sample in listed)
        {
            var descriptor = messages[sample.Split('@')[0]];
            var written = File.ReadAllBytes(Path.Combine(directory, "current", sample + ".bin"));
            var fromGo = descriptor.Parser.ParseFrom(File.ReadAllBytes(Path.Combine(directory, "go", sample + ".bin")));
            if (!fromGo.ToByteArray().AsSpan().SequenceEqual(written))
                throw new InvalidOperationException("C# reads another value from the Go encoding of " + sample);
            samples++;
        }
        var index = JsonNode.Parse(File.ReadAllText(Path.Combine(directory, "fixtures", "index.json")))!.AsArray();
        foreach (var node in index)
        {
            var descriptor = messages[node!["type"]!.GetValue<string>()];
            var file = node["file"]!.GetValue<string>();
            var written = File.ReadAllBytes(Path.Combine(directory, "fixtures", file));
            var fromGo = descriptor.Parser.ParseFrom(File.ReadAllBytes(Path.Combine(directory, "fixtures", "go-" + file)));
            if (!fromGo.ToByteArray().AsSpan().SequenceEqual(written))
                throw new InvalidOperationException("C# reads another value from the Go encoding of fixture " + node["id"]!.GetValue<string>());
            fixtures++;
        }
        Console.WriteLine($"C# generated codecs read the Go encoding of {samples} samples and {fixtures} fixture cases back to their own bytes.");
    }

    private static void Collect(IEnumerable<MessageDescriptor> messages, Dictionary<string, MessageDescriptor> into)
    {
        foreach (var message in messages)
        {
            if (message.GetOptions()?.MapEntry == true) continue;
            into.Add(message.FullName, message);
            Collect(message.NestedTypes, into);
        }
    }
}
