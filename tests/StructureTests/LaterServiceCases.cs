// SPDX-License-Identifier: Apache-2.0
using Google.Protobuf;
using Google.Protobuf.Reflection;

/// <summary>
/// Generated-codec leg of the CON.17 later-service matrix. eng/check_compatibility.py writes what a
/// previous client of each pinned published candidate sends for every message that candidate published. The current
/// generated parsers read those bytes and write them back; the same script then checks that the pinned
/// reader sees the meaning that was sent. No transport, service or published package is used.
/// </summary>
internal static class LaterServiceCases
{
    // Explicit list of every file of every pinned descriptor; nothing is discovered at runtime.
    private static readonly FileDescriptor[] Files =
    [
        ArcForges.Contracts.Foundation.V1.FoundationReflection.Descriptor,
        ArcForges.Contracts.Hello.V1.HelloReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.DescriptorsReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ContentReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.InprocessValuesReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.IdentityReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.CommerceReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.SyncReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.TransferReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ChatReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ApplicationReflection.Descriptor,
        ArcForges.Contracts.Events.V1.EventsReflection.Descriptor,
        ArcForges.Contracts.CloudInternal.Cf.V1.StreamReflection.Descriptor,
        ArcForges.Contracts.Catalog.V1.CatalogReflection.Descriptor,
        ArcForges.Contracts.CloudInternal.Operator.V1.OperatorReflection.Descriptor,
        ArcForges.Contracts.Simulation.V1.SimulationReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ExportReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.SupportReflection.Descriptor,
        ArcForges.Contracts.PublicApi.V1.ScopeReflection.Descriptor,
        ArcForges.Sdk.Contracts.V1.ExtensionsReflection.Descriptor,
        ArcForges.Contracts.LocalRpc.Platform.V1.PlatformReflection.Descriptor,
        ArcForges.Contracts.LocalRpc.Platform.V1.InprocessReflection.Descriptor,
        ArcForges.Contracts.LocalRpc.Chat.V1.ChatReflection.Descriptor,
        ArcForges.Contracts.LocalRpc.Scope.V1.ScopeReflection.Descriptor,
        ArcForges.Contracts.LocalRpc.Sandbox.V1.SandboxReflection.Descriptor,
    ];

    internal static void Run(string directory)
    {
        var current = new Dictionary<string, MessageDescriptor>(StringComparer.Ordinal);
        foreach (var file in Files) Collect(file.MessageTypes, current);
        var pins = Directory.GetDirectories(directory).Where(pin => File.Exists(Path.Combine(pin, "messages.txt"))).Order(StringComparer.Ordinal).ToArray();
        if (pins.Length == 0) throw new InvalidOperationException("No previous-client exchange was emitted");
        var total = 0;
        foreach (var pin in pins)
        {
            var listed = File.ReadAllLines(Path.Combine(pin, "messages.txt")).Where(line => line.Length != 0).ToArray();
            var output = Directory.CreateDirectory(Path.Combine(pin, "current")).FullName;
            foreach (var sample in listed)
            {
                // A sample is a message name, or the name and "@" and the index of an extra oneof-arm sample.
                var name = sample.Split('@')[0];
                if (!current.TryGetValue(name, out var descriptor))
                    throw new InvalidOperationException("The current generated codecs lack message " + name + " published in " + Path.GetFileName(pin));
                var sent = File.ReadAllBytes(Path.Combine(pin, "previous", sample + ".bin"));
                var message = descriptor.Parser.ParseFrom(sent);
                File.WriteAllBytes(Path.Combine(output, sample + ".bin"), message.ToByteArray());
            }
            total += listed.Length;
        }
        Console.WriteLine($"Current generated codecs read and rewrote {total} previous-client messages of {pins.Length} published candidates; the pinned readers verify them next.");
    }

    private static void Collect(IEnumerable<MessageDescriptor> messages, Dictionary<string, MessageDescriptor> into)
    {
        foreach (var message in messages)
        {
            into.Add(message.FullName, message);
            Collect(message.NestedTypes, into);
        }
    }
}
