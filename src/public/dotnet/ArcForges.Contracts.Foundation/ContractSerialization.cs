// SPDX-License-Identifier: Apache-2.0
using Google.Protobuf;
namespace ArcForges.Contracts.Foundation.Serialization;

/// <summary>Why a bounded contract encode or decode was refused.</summary>
public enum ContractSerializationFailure
{
    /// <summary>The input or output exceeds the selected byte limit.</summary>
    TooLarge = 1,
    /// <summary>The message nests deeper than the permitted message levels.</summary>
    TooDeep = 2,
    /// <summary>Invalid protobuf bytes, invalid UTF-8/JSON syntax, a duplicate property or excess JSON depth.</summary>
    Malformed = 3,
    /// <summary>Well-formed JSON that the closed schema refuses.</summary>
    Invalid = 4,
}

/// <summary>A typed refusal from a bounded contract codec; the message never carries payload content.</summary>
public sealed class ContractSerializationException : Exception
{
    /// <summary>Creates a refusal of the given kind.</summary>
    public ContractSerializationException(ContractSerializationFailure failure, Exception? innerException = null)
        : base("Contract serialization refused: " + failure + ".", innerException) => Failure = failure;

    /// <summary>The refusal kind.</summary>
    public ContractSerializationFailure Failure { get; }
}

/// <summary>Selected transport size classes from the wire registry.</summary>
public enum WireLimit
{
    /// <summary>Unary public request/response message.</summary>
    UnaryMessage = 1,
    /// <summary>Private helper message.</summary>
    HelperMessage = 2,
    /// <summary>Inline list or event page.</summary>
    InlinePage = 3,
    /// <summary>One server-streaming frame.</summary>
    StreamFrame = 4,
    /// <summary>A verified large read projection body.</summary>
    LargeProjection = 5,
}

/// <summary>The registry's fixed decode and encode bounds.</summary>
public static class WireLimits
{
    /// <summary>Unary public request/response bytes (4 MiB).</summary>
    public const int UnaryMessageBytes = 4 * 1024 * 1024;
    /// <summary>Private helper message bytes (4 MiB).</summary>
    public const int HelperMessageBytes = 4 * 1024 * 1024;
    /// <summary>Inline list/event page bytes (256 KiB).</summary>
    public const int InlinePageBytes = 256 * 1024;
    /// <summary>Server-streaming frame bytes (32 KiB).</summary>
    public const int StreamFrameBytes = 32 * 1024;
    /// <summary>Encoded large read projection bytes (64 MiB).</summary>
    public const int LargeProjectionBytes = 64 * 1024 * 1024;
    /// <summary>Message levels permitted below the root message.</summary>
    public const int NestedMessageLevels = 100;

    /// <summary>Returns the byte bound of a size class.</summary>
    public static int Bytes(WireLimit limit) => limit switch
    {
        WireLimit.UnaryMessage => UnaryMessageBytes,
        WireLimit.HelperMessage => HelperMessageBytes,
        WireLimit.InlinePage => InlinePageBytes,
        WireLimit.StreamFrame => StreamFrameBytes,
        WireLimit.LargeProjection => LargeProjectionBytes,
        _ => throw new ArgumentOutOfRangeException(nameof(limit)),
    };
}

/// <summary>Bounded binary codec over generated Google.Protobuf parsers; unknown fields are retained.</summary>
public static class ContractWire
{
    // Google.Protobuf applies its fixed default nesting limit to span parsing; fail closed if a runtime differs.
    private static readonly bool RuntimeNestingMatches =
        new CodedInputStream(Array.Empty<byte>()).RecursionLimit == WireLimits.NestedMessageLevels;

    /// <summary>Decodes one complete message or throws a typed refusal.</summary>
    public static T Decode<T>(MessageParser<T> parser, ReadOnlyMemory<byte> bytes, WireLimit limit) where T : IMessage<T>
        => TryDecode(parser, bytes, limit, out var message, out var failure) ? message! : throw new ContractSerializationException(failure);

    /// <summary>Decodes one complete message, reporting oversized, too deep or malformed input.</summary>
    public static bool TryDecode<T>(MessageParser<T> parser, ReadOnlyMemory<byte> bytes, WireLimit limit,
        out T? message, out ContractSerializationFailure failure) where T : IMessage<T>
    {
        ArgumentNullException.ThrowIfNull(parser);
        message = default;
        var maximum = WireLimits.Bytes(limit);
        if (bytes.Length > maximum)
        {
            failure = ContractSerializationFailure.TooLarge;
            return false;
        }
        if (!RuntimeNestingMatches)
            throw new InvalidOperationException("The Google.Protobuf runtime nesting limit differs from the contract limit.");
        try
        {
            // The span parser checks the end-of-stream tag, so an unmatched end-group is refused.
            message = parser.ParseFrom(bytes.Span);
            failure = default;
            return true;
        }
        catch (InvalidProtocolBufferException error)
        {
            // Google.Protobuf reports recursion exhaustion through its fixed nesting message.
            failure = error.Message.Contains("levels of nesting", StringComparison.Ordinal)
                ? ContractSerializationFailure.TooDeep : ContractSerializationFailure.Malformed;
            return false;
        }
    }

    /// <summary>Encodes a message only when its serialized size fits the selected class.</summary>
    public static byte[] Encode(IMessage message, WireLimit limit)
    {
        ArgumentNullException.ThrowIfNull(message);
        if (message.CalculateSize() > WireLimits.Bytes(limit))
            throw new ContractSerializationException(ContractSerializationFailure.TooLarge);
        return message.ToByteArray();
    }
}
