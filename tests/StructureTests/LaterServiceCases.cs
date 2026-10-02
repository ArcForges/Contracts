// SPDX-License-Identifier: Apache-2.0
using Google.Protobuf;
using Google.Protobuf.Reflection;

/// <summary>
/// Generated-codec leg of the CON.17 later-service matrix. eng/check_compatibility.py writes what a
/// previous client (the pinned published descriptor) sends for every published message. The current
/// generated parsers read those bytes and write them back; the same script then checks that the pinned
/// minimum reader sees the meaning that was sent. No transport, service or published package is used.
/// </summary>
internal static class LaterServiceCases
{
    // Explicit list of every file in the pinned descriptor; nothing is discovered at runtime.
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
    ];

    internal static void Run(string directory)
    {
        var current = new Dictionary<string, MessageDescriptor>(StringComparer.Ordinal);
        foreach (var file in Files) Collect(file.MessageTypes, current);
        var listed = File.ReadAllLines(Path.Combine(directory, "messages.txt")).Where(line => line.Length != 0).ToArray();
        var output = Directory.CreateDirectory(Path.Combine(directory, "current")).FullName;
        foreach (var name in listed)
        {
            if (!current.TryGetValue(name, out var descriptor))
                throw new InvalidOperationException("The current generated codecs lack published message " + name);
            var sent = File.ReadAllBytes(Path.Combine(directory, "previous", name + ".bin"));
            var message = descriptor.Parser.ParseFrom(sent);
            File.WriteAllBytes(Path.Combine(output, name + ".bin"), message.ToByteArray());
        }
        Console.WriteLine($"Current generated codecs read and rewrote {listed.Length} previous-client messages; the pinned minimum reader verifies them next.");
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
