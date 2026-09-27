// SPDX-License-Identifier: Apache-2.0
using P = ArcForges.Contracts.PublicApi.V1;

internal static class FoundationLinkCases
{
    public static void Run()
    {
        var retired = new[] { "LinkSpec", "RichText", "NotesFilter", "NotesDocument", "SlateMetadata" };
        foreach (var name in retired)
            if (P.ContentReflection.Descriptor.MessageTypes.Any(message => message.Name == name))
                throw new InvalidOperationException("Retired product message reappeared: " + name);
        if (!P.ContentReflection.Descriptor.MessageTypes.Any(message => message.Name == "StructuredValue"))
            throw new InvalidOperationException("The admitted recursive boundary value disappeared.");
        Console.WriteLine("Validated retired product descriptors remain absent.");
    }
}
