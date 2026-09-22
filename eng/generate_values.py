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
    ts=HEADER+'''import { create } from "@bufbuild/protobuf";
import { IdSchema } from "../../gen/arcforges/foundation/v1/foundation_pb.js";
import type { Id } from "../../gen/arcforges/foundation/v1/foundation_pb.js";
declare const identifierBrand: unique symbol;
export type IdentifierDomain = '''+' | '.join(json.dumps(n) for names in profile['identifiers'].values() for n in names)+''';
export type DomainId<T extends IdentifierDomain> = string & { readonly [identifierBrand]: T };
export function parseId<T extends IdentifierDomain>(domain: T, value: string): DomainId<T> {
  if (typeof domain !== 'string' || !identifierDomains.has(domain) || typeof value !== 'string' || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.exec(value)?.[0] !== value || value === '00000000-0000-0000-0000-000000000000') throw new TypeError('Invalid canonical domain identity');
  return value as DomainId<T>;
}
export function idFromWire<T extends IdentifierDomain>(domain: T, value: Id): DomainId<T> {
  if (!(value?.value instanceof Uint8Array) || value.value.length !== 16 || !value.value.some(v => v !== 0)) throw new TypeError('Invalid wire UUID');
  const h = Array.from(value.value, v => v.toString(16).padStart(2, '0')).join('');
  return parseId(domain, `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`);
}
export function idToWire<T extends IdentifierDomain>(domain: T, value: DomainId<NoInfer<T>>): Id {
  const digits = parseId(domain, value).replaceAll('-', '');
  const bytes = Uint8Array.from({length:16}, (_, i) => Number.parseInt(digits.slice(i*2,i*2+2),16));
  return create(IdSchema, {value: bytes});
}
'''
    ts+='const identifierDomains: ReadonlySet<string> = new Set('+json.dumps([n for names in profile['identifiers'].values() for n in names])+');\n'
    for names in profile['identifiers'].values():
        for name in names:
            ts+=f'export type {name} = DomainId<"{name}">;\n'
    emit(ROOT/'src/public/ts/proto/src/values/gen/identifiers.ts',ts,check)
