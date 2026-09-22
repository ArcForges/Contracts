// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using ArcForges.Contracts.Validation;

if (args.Length != 2 || args[0] != "validate-inventory")
{
    Console.Error.WriteLine("Usage: arcforges validate-inventory <inventory.json>");
    return 2;
}

try
{
    using var input = File.OpenRead(args[1]);
    using var document = JsonDocument.Parse(input, new JsonDocumentOptions
    {
        AllowTrailingCommas = false,
        CommentHandling = JsonCommentHandling.Disallow,
        MaxDepth = 16,
    });
    if (!PackageInventoryJson.IsValid(document.RootElement))
    {
        Console.Error.WriteLine("Invalid inventory.v1 document: check required fields, paths, ordering, declared sizes and SHA256 values.");
        return 1;
    }

    Console.WriteLine("Valid inventory.v1 document shape and declared bounds. Archive bytes, hashes, signatures and trust were not verified.");
    return 0;
}
catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException)
{
    Console.Error.WriteLine("Unable to validate inventory: " + error.Message);
    return 1;
}
