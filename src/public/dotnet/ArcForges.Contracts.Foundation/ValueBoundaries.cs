// SPDX-License-Identifier: Apache-2.0
using System.Globalization;
using System.Numerics;
using Google.Protobuf;
using ArcForges.Contracts.Foundation.V1;
namespace ArcForges.Contracts.Foundation.Values;

/// <summary>Explicit UUID network-order conversions; never Guid native byte layout.</summary>
public static class UuidBoundary
{
    /// <summary>Reads a nonzero 16-byte identity without retaining mutable input state.</summary>
    public static Guid FromWire(Id value)
    {
        ArgumentNullException.ThrowIfNull(value);
        if (!value.HasValue || value.Value.Length != 16) throw new ArgumentException("Invalid UUID bytes.", nameof(value));
        var id = new Guid(value.Value.Span, bigEndian: true);
        if (id == Guid.Empty) throw new ArgumentException("An identity cannot be empty.", nameof(value));
        return id;
    }
    /// <summary>Writes an owned immutable byte sequence in canonical UUID order.</summary>
    public static Id ToWire(Guid value)
    {
        if (value == Guid.Empty) throw new ArgumentException("An identity cannot be empty.", nameof(value));
        return new Id { Value = ByteString.CopyFrom(value.ToByteArray(bigEndian: true)) };
    }
}

/// <summary>Strict canonical integer projections used at language and declared JSON boundaries.</summary>
public static class ExactInteger
{
    /// <summary>Parses a signed integer with no whitespace, exponent, plus, leading zero or negative zero.</summary>
    public static long ParseInt64(string value)
    {
        if (!Canonical(value, signed: true) || !long.TryParse(value, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var result)) throw new FormatException("Invalid canonical int64.");
        return result;
    }
    /// <summary>Parses an unsigned integer without passing through floating point.</summary>
    public static ulong ParseUInt64(string value)
    {
        if (!Canonical(value, signed: false) || !ulong.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out var result)) throw new FormatException("Invalid canonical uint64.");
        return result;
    }
    private static bool Canonical(string value, bool signed)
    {
        if (string.IsNullOrEmpty(value)) return false;
        var first = signed && value[0] == '-' ? 1 : 0;
        if (first == value.Length || (value[first] == '0' && (first != 0 || value.Length != 1))) return false;
        for (var i = first; i < value.Length; i++) if (value[i] is < '0' or > '9') return false;
        return true;
    }
}

/// <summary>Committed Cloud revision; an absent/new root uses the explicit zero wire precondition.</summary>
public readonly record struct CloudRevision
{
    /// <summary>Constructs a positive committed revision.</summary>
    public CloudRevision(long value) { if (value <= 0) throw new ArgumentOutOfRangeException(nameof(value)); Value = value; }
    /// <summary>Exact owner revision.</summary>
    public long Value { get; }
    /// <summary>Reads a present committed wire revision.</summary>
    public static CloudRevision FromWire(Revision value) => value is { HasValue: true } ? new(value.Value) : throw new ArgumentException("Missing revision.", nameof(value));
    /// <summary>Writes this committed revision; the default value is invalid.</summary>
    public Revision ToWire() => Value > 0 ? new Revision { Value = Value } : throw new InvalidOperationException("Uninitialized revision.");
    /// <summary>Explicit new-root precondition, distinct from a committed revision.</summary>
    public static Revision NewRootPrecondition() => new() { Value = 0 };
}

/// <summary>Native owner content revision, not a Cloud acknowledgement.</summary>
public readonly record struct NativeRevision(ulong Value)
{
    /// <summary>Reads a present native token.</summary>
    public static NativeRevision FromWire(NativeContentRev value) => value is { HasValue: true } ? new(value.Value) : throw new ArgumentException("Missing native revision.", nameof(value));
    /// <summary>Writes exact native revision bits.</summary>
    public NativeContentRev ToWire() => new() { Value = Value };
}

/// <summary>Exact per-channel delivery sequence, never an owner revision.</summary>
public readonly record struct DeliverySequence(ulong Value)
{
    /// <summary>Reads a canonical unsigned projection.</summary>
    public static DeliverySequence Parse(string value) => new(ExactInteger.ParseUInt64(value));
    /// <summary>Canonical unsigned projection.</summary>
    public override string ToString() => Value.ToString(CultureInfo.InvariantCulture);
}

/// <summary>Composite local Notes token preserves both acknowledgement and pending-local sequence.</summary>
public readonly record struct LocalNotesToken
{
    /// <summary>Constructs a composite token; zero acknowledgement explicitly means no acknowledged root.</summary>
    public LocalNotesToken(long acknowledgedRevision, ulong headLocalSequence)
    {
        if (acknowledgedRevision < 0) throw new ArgumentOutOfRangeException(nameof(acknowledgedRevision));
        AcknowledgedRevision = acknowledgedRevision; HeadLocalSequence = headLocalSequence;
    }
    /// <summary>Exact acknowledged revision, including explicit new-root zero.</summary>
    public long AcknowledgedRevision { get; }
    /// <summary>Exact local pending sequence.</summary>
    public ulong HeadLocalSequence { get; }
    /// <summary>Reads both present token components.</summary>
    public static LocalNotesToken FromWire(LocalNotesVersion value) => value is { AckedRev.HasValue: true, HasHeadLocalSeq: true } ? new(value.AckedRev.Value, value.HeadLocalSeq) : throw new ArgumentException("Missing local version component.", nameof(value));
    /// <summary>Writes the composite without discarding pending state.</summary>
    public LocalNotesVersion ToWire() => new() { AckedRev = new Revision { Value = AcknowledgedRevision }, HeadLocalSeq = HeadLocalSequence };
}

/// <summary>Opaque bounded cursor; possession confers no authority and does not establish validity.</summary>
public readonly record struct OpaqueCursor
{
    /// <summary>Checks Unicode and the 4096-byte wire bound without interpreting the token.</summary>
    public OpaqueCursor(string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        var strict = new System.Text.UTF8Encoding(false, true);
        if (strict.GetByteCount(value) > 4096) throw new ArgumentOutOfRangeException(nameof(value));
        Value = value;
    }
    /// <summary>Uninterpreted token, never logged or parsed as an identity.</summary>
    public string Value { get; }
    /// <summary>Returns the opaque token; default values refuse use.</summary>
    public string ToWire() => Value ?? throw new InvalidOperationException("Uninitialized cursor.");
}

/// <summary>Exact canonical coefficient/scale boundary with no binary floating-point conversion.</summary>
public readonly record struct ExactDecimal
{
    /// <summary>Parses the shared decimal bound; Notes requires the stricter FromNotes conversion.</summary>
    public ExactDecimal(string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        var negative = value.StartsWith('-');
        var unsigned = negative ? value[1..] : value;
        var parts = unsigned.Split('.');
        if (parts.Length is < 1 or > 2 || parts[0].Length == 0 || parts[0].Length > 1 && parts[0][0] == '0' || parts.Any(p => p.Length == 0 || p.Any(c => c is < '0' or > '9')) || parts.Length == 2 && parts[1].Length > 9) throw new FormatException("Invalid decimal shape.");
        var digits = string.Concat(parts);
        if (digits.TrimStart('0').Length > 28 || negative && digits.All(c => c == '0')) throw new FormatException("Invalid decimal precision or negative zero.");
        Value = value;
    }
    /// <summary>Canonical decimal wire text.</summary>
    public string Value { get; }
    /// <summary>Exact coefficient, with no machine-width intermediate.</summary>
    public BigInteger Coefficient => BigInteger.Parse(ToWire().Value.Replace(".", "", StringComparison.Ordinal), CultureInfo.InvariantCulture);
    /// <summary>Declared scale preserved from the wire.</summary>
    public int Scale => ToWire().Value.IndexOf('.') is var index && index >= 0 ? Value.Length - index - 1 : 0;
    /// <summary>Parses Notes canonical form, additionally refusing trailing fractional zeros.</summary>
    public static ExactDecimal FromNotes(string value)
    {
        var result = new ExactDecimal(value);
        if (value.Contains('.') && value.EndsWith('0')) throw new FormatException("Noncanonical Notes decimal.");
        return result;
    }
    /// <summary>Reads the present generated shared decimal.</summary>
    public static ExactDecimal FromWire(V1.Decimal value) => value is { HasValue: true } ? new(value.Value) : throw new ArgumentException("Missing decimal.", nameof(value));
    /// <summary>Writes exact text and refuses an uninitialized struct.</summary>
    public V1.Decimal ToWire() => Value is not null ? new V1.Decimal { Value = Value } : throw new InvalidOperationException("Uninitialized decimal.");
    /// <summary>Constructs exact coefficient/scale without rounding, preserving declared trailing scale.</summary>
    public static ExactDecimal FromCoefficient(BigInteger coefficient, int scale)
    {
        if (scale is < 0 or > 9) throw new ArgumentOutOfRangeException(nameof(scale));
        var digits = BigInteger.Abs(coefficient).ToString(CultureInfo.InvariantCulture).PadLeft(scale + 1, '0');
        var value = scale == 0 ? digits : digits.Insert(digits.Length - scale, ".");
        return new ExactDecimal(coefficient.Sign < 0 ? "-" + value : value);
    }
}

/// <summary>Reduced exact rational used at timebase conversion boundaries.</summary>
public readonly record struct RationalValue
{
    /// <summary>Constructs an already-reduced rational; external noncanonical values refuse rather than normalize.</summary>
    public RationalValue(long numerator, ulong denominator)
    {
        if (denominator == 0 || BigInteger.GreatestCommonDivisor(BigInteger.Abs(new BigInteger(numerator)), new BigInteger(denominator)) != BigInteger.One) throw new ArgumentException("Rational must be reduced with positive denominator.");
        Numerator = numerator; Denominator = denominator;
    }
    /// <summary>Exact signed numerator.</summary>
    public long Numerator { get; }
    /// <summary>Exact positive denominator.</summary>
    public ulong Denominator { get; }
    /// <summary>Reads both required scalar components.</summary>
    public static RationalValue FromWire(Rational value) => value is { HasNumerator: true, HasDenominator: true } ? new(value.Numerator, value.Denominator) : throw new ArgumentException("Missing rational component.", nameof(value));
    /// <summary>Writes the exact pair and rejects default structs.</summary>
    public Rational ToWire() => Denominator != 0 ? new Rational { Numerator = Numerator, Denominator = Denominator } : throw new InvalidOperationException("Uninitialized rational.");
    /// <summary>Converts exact ticks between positive rates using unbounded intermediates, refusing unrepresentable results.</summary>
    public static long ConvertTicksExact(long ticks, RationalValue sourceRate, RationalValue targetRate)
    {
        if (sourceRate.Numerator <= 0 || targetRate.Numerator <= 0 || sourceRate.Denominator == 0 || targetRate.Denominator == 0) throw new ArgumentException("Timebase rates must be positive.");
        var numerator = new BigInteger(ticks) * targetRate.Numerator * sourceRate.Denominator;
        var denominator = new BigInteger(sourceRate.Numerator) * targetRate.Denominator;
        var result = BigInteger.DivRem(numerator, denominator, out var remainder);
        if (remainder != 0 || result < long.MinValue || result > long.MaxValue) throw new OverflowException("Time is not representable in the target timebase.");
        return (long)result;
    }
}

/// <summary>Compatible response data with an explicit known-profile observation, never an authorization grant.</summary>
public sealed class ReadProjection<T> where T : class, IMessage<T>
{
    private ReadProjection(T message, bool knownProfile) { Message = message; KnownProfile = knownProfile; }
    /// <summary>The original generated message retains inert unknown protobuf fields.</summary>
    public T Message { get; }
    /// <summary>Whether strict current-profile validation passed when read.</summary>
    public bool KnownProfile { get; }
    /// <summary>Decodes with an explicit generated parser and keeps unsupported read values without making them mutation inputs.</summary>
    public static ReadProjection<T> Parse(MessageParser<T> parser, byte[] bytes, Func<T, bool> validate)
    {
        ArgumentNullException.ThrowIfNull(parser); ArgumentNullException.ThrowIfNull(bytes); ArgumentNullException.ThrowIfNull(validate);
        var message = parser.ParseFrom(bytes);
        return new ReadProjection<T>(message, validate(message));
    }
    /// <summary>Preserves the generated message and its unknown fields during re-emission.</summary>
    public byte[] Preserve() => Message.ToByteArray();
}
