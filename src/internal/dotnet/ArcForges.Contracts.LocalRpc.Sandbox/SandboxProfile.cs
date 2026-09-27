// SPDX-License-Identifier: Apache-2.0
using Google.Protobuf;
using Google.Protobuf.Reflection;
using ArcForges.Contracts.LocalRpc.Sandbox.V1;
using Shape = ArcForges.Contracts.LocalRpc.Sandbox.Shapes.ContractShapeValidation;

namespace ArcForges.Contracts.LocalRpc.Sandbox;

/// <summary>Closed descriptor-role metadata for this private child contract, not peer authentication.</summary>
public static class ContentSandboxPolicy
{
    /// <summary>The role of an endpoint in a preverified launch pair; never a wire authority claim.</summary>
    public enum EndpointRole { Parent, Sandbox, Product, Extension, Connector }

    /// <summary>Checks whether a generated method can be registered on this receiver direction.
    /// LocalRpc must separately verify OS launch identity, connection credentials, current grants,
    /// actor and invocation. This metadata check neither authenticates peers nor creates authority.</summary>
    public static bool IsAdmittedBinding(MethodDescriptor method, EndpointRole caller, EndpointRole receiver,
        bool parentAlive, bool sameApplication) =>
        parentAlive && sameApplication && caller == EndpointRole.Parent && receiver == EndpointRole.Sandbox &&
        ReferenceEquals(method.Service, ContentSandboxService.Descriptor) &&
        ReferenceEquals(ContentSandboxService.Descriptor.FindMethodByName(method.Name), method);
}

/// <summary>Self-contained sandbox shape and geometry checks. Stateful launch, lease, slot sequence,
/// inventory, digest-on-private-copy and cancellation enforcement remain with the owning runtime.</summary>
public static class SandboxProfile
{
    private const ulong SlotBytes = 64UL * 1024 * 1024;
    private const ulong MaxPixels = 268435456;

    /// <summary>Validates a bounded image description without allocating pixel storage.</summary>
    public static bool IsValid(SandboxImageInfo value) => Shape.IsValid(value) &&
        value.Width <= 65535 && value.Height <= 65535 && (ulong)value.Width * value.Height <= MaxPixels;

    /// <summary>Validates finite positive page geometry and the closed rotation profile.</summary>
    public static bool IsValid(SandboxPdfPage value) => Shape.IsValid(value) &&
        value.WidthPoints > 0 && value.HeightPoints > 0;

    /// <summary>Validates a nonempty image/PDF tile; obsolete audio sample coordinates must be zero.</summary>
    public static bool IsValid(SandboxRegion value) => Shape.IsValid(value) && value.Width > 0 && value.Height > 0 &&
        value.FirstSample == 0 && value.SampleCount == 0 && value.RowStride <= SlotBytes;

    /// <summary>Validates a complete bounded text page chunk, including UTF16 and box coverage.</summary>
    public static bool IsValid(SandboxPdfText value)
    {
        if (!Shape.IsValid(value) || !CompleteUtf16(value.Text) || value.CalculateSize() > 65536) return false;
        ulong end = (ulong)value.Start + (uint)value.Text.Length;
        if (end > uint.MaxValue || (value.HasNext && (value.Next != end || value.Next <= value.Start))) return false;
        foreach (var box in value.Boxes)
        {
            ulong boxEnd = (ulong)box.Start + box.Length;
            if (box.Start < value.Start || boxEnd > end || box.Width < 0 || box.Height < 0) return false;
            int start = checked((int)(box.Start - value.Start));
            int finish = checked((int)(boxEnd - value.Start));
            if (!Boundary(value.Text, start) || !Boundary(value.Text, finish)) return false;
        }
        return true;
    }

    private static bool CompleteUtf16(string value)
    {
        for (int i = 0; i < value.Length; i++)
        {
            if (char.IsLowSurrogate(value[i])) return false;
            if (char.IsHighSurrogate(value[i]) && (++i == value.Length || !char.IsLowSurrogate(value[i]))) return false;
        }
        return true;
    }

    private static bool Boundary(string value, int position) => position == 0 || position == value.Length ||
        !(char.IsLowSurrogate(value[position]) && char.IsHighSurrogate(value[position - 1]));

    /// <summary>Checks the image/PDF buffer seal against its exact slot grant and requested tile.
    /// The caller must bind invocation/lease/generation, then copy and verify the digest before use.</summary>
    public static bool IsValid(SandboxBufferDescriptor value, SandboxSlotGrant grant, SandboxRegion region)
    {
        if (!Shape.IsValid(value) || !Shape.IsValid(grant) || !IsValid(region) || value.Kind != 1 ||
            value.Format is not (1 or 2) || value.SampleStart != 0 || value.SampleCount != 0 ||
            value.SlotId != grant.SlotId || value.Sequence != grant.Sequence ||
            value.TileX != region.X || value.TileY != region.Y || value.TileWidth != region.Width ||
            value.TileHeight != region.Height || value.RowStride != region.RowStride ||
            value.FullWidth == 0 || value.FullHeight == 0 || value.FullWidth > 65535 || value.FullHeight > 65535 ||
            (ulong)value.FullWidth * value.FullHeight > MaxPixels ||
            (ulong)value.TileX + value.TileWidth > value.FullWidth ||
            (ulong)value.TileY + value.TileHeight > value.FullHeight ||
            value.Offset > grant.Capacity || value.Length > grant.Capacity - value.Offset) return false;
        ulong pixelBytes = value.Format == 1 ? 4UL : 16UL;
        ulong rowBytes = value.TileWidth * pixelBytes;
        if (value.RowStride < rowBytes || value.TileWidth > 2048 || value.TileHeight > 2048) return false;
        ulong required = (value.TileHeight - 1UL) * value.RowStride + rowBytes;
        return value.Length == required && required <= SlotBytes;
    }
}
