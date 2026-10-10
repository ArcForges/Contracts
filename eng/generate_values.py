# SPDX-License-Identifier: Apache-2.0
"""Emit domain-safe identity adapters; protobuf remains the wire authority."""
from __future__ import annotations
import json
from pathlib import Path
from generate_shapes import emit, HEADER
ROOT=Path(__file__).resolve().parents[1]

def generate(check: bool=False) -> None:
    profile=json.loads((ROOT/'public/proto/value-boundaries.json').read_text())
    for owner, names in profile['identifiers'].items():
        namespace=f'ArcForges.Contracts.{owner}.Values'
        content=HEADER+'#nullable enable\n'+f'namespace {namespace};\n\n'
        for name in names:
            content+=f'''/// <summary>Domain identity {name}; never implicitly interchangeable with another identifier.</summary>
public readonly record struct {name}
{{
    /// <summary>Constructs a nonempty domain identity.</summary>
    public {name}(global::System.Guid value)
    {{
        if (value == global::System.Guid.Empty) throw new global::System.ArgumentException("An identity cannot be empty.", nameof(value));
        Value = value;
    }}
    /// <summary>The canonical UUID value, independent of storage and process identity.</summary>
    public global::System.Guid Value {{ get; }}
    /// <summary>Converts a validated generated wire identity in UUID network order.</summary>
    public static {name} FromWire(global::ArcForges.Contracts.Foundation.V1.Id value) => new(global::ArcForges.Contracts.Foundation.Values.UuidBoundary.FromWire(value));
    /// <summary>Creates an independently owned generated wire identity; default structs refuse conversion.</summary>
    public global::ArcForges.Contracts.Foundation.V1.Id ToWire() => global::ArcForges.Contracts.Foundation.Values.UuidBoundary.ToWire(Value);
}}

'''
        emit(ROOT/f'src/public/dotnet/ArcForges.Contracts.{owner}/Generated/Values/Identifiers.g.cs',content,check)
    # CON.40: the TypeScript identity adapters (src/public/ts/proto) retired with @arcforges/proto; the C#
    # value types above are the only generated identity adapters.
