// SPDX-License-Identifier: Apache-2.0
using System.Security.Cryptography;
using Google.Protobuf;
using ArcForges.Contracts.Foundation.Serialization;
using ArcForges.Contracts.Foundation.V1;

namespace ArcForges.Contracts.Validation;

/// <summary>Reads an already authorized immutable projection using a fixed generated parser.</summary>
public static class EncodedBodyReader
{
    /// <summary>
    /// Verifies the complete reference and caller-bound type, descriptor and snapshot before parsing.
    /// The caller owns resource authorization, revocation and frozen revision admission; this method
    /// neither fetches content nor grants permission. Inputs are copied before hashing and decoding.
    /// </summary>
    public static T Read<T>(EncodedBodyRef reference, ReadOnlyMemory<byte> bytes,
        string expectedMessageType, string expectedDescriptorHash, string expectedSnapshotToken,
        Instant now, MessageParser<T> parser) where T : IMessage<T>, new()
    {
        ArgumentNullException.ThrowIfNull(reference);
        ArgumentNullException.ThrowIfNull(now);
        ArgumentNullException.ThrowIfNull(parser);
        var bound = reference.Clone();
        var instant = now.Clone();
        if (!ContractShapeValidation.IsValid(bound) || !ContractShapeValidation.IsValid(instant))
            throw new ContractSerializationException(ContractSerializationFailure.Invalid);
        if (bytes.Length > WireLimits.LargeProjectionBytes)
            throw new ContractSerializationException(ContractSerializationFailure.TooLarge);
        if (bound.MessageType != expectedMessageType || new T().Descriptor.FullName != expectedMessageType
            || bound.DescriptorHash != expectedDescriptorHash
            || bound.SnapshotToken != expectedSnapshotToken || bound.ByteLength != (ulong)bytes.Length
            || bound.ExpiresAt.UnixSeconds < instant.UnixSeconds
            || (bound.ExpiresAt.UnixSeconds == instant.UnixSeconds && bound.ExpiresAt.Nanos <= instant.Nanos))
            throw new ContractSerializationException(ContractSerializationFailure.Invalid);
        var snapshot = bytes.ToArray();
        if (Convert.ToHexStringLower(SHA256.HashData(snapshot)) != bound.Resource.ContentHash)
            throw new ContractSerializationException(ContractSerializationFailure.Invalid);
        return ContractWire.Decode(parser, snapshot, WireLimit.LargeProjection);
    }
}
