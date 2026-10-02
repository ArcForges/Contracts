# SPDX-License-Identifier: Apache-2.0
"""Offline compatibility checks over compiled FileDescriptorSet bytes.

This reader covers descriptor metadata only; it is not a business wire codec.
It uses no source-regex approximation, package restore or live service.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import struct


def fields(data: bytes) -> dict[int, list[int | bytes]]:
    """Read a bounded protobuf metadata message, refusing malformed input."""
    result: dict[int, list[int | bytes]] = {}
    at = 0

    def varint() -> int:
        nonlocal at
        value = 0
        for shift in range(0, 70, 7):
            if at >= len(data):
                raise ValueError("Truncated descriptor varint")
            byte = data[at]
            at += 1
            if shift == 63 and byte > 1:
                raise ValueError("Descriptor varint overflow")
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError("Descriptor varint overflow")

    while at < len(data):
        key = varint()
        tag, wire = key >> 3, key & 7
        if not 1 <= tag <= 536870911:
            raise ValueError("Invalid descriptor field tag")
        if wire == 0:
            value = varint()
        elif wire in (1, 2, 5):
            length = varint() if wire == 2 else (8 if wire == 1 else 4)
            if length > len(data) - at:
                raise ValueError("Truncated descriptor field")
            value = data[at:at + length]
            at += length
        else:
            raise ValueError("Unsupported descriptor wire type")
        result.setdefault(tag, []).append(value)
    return result


def one(message: dict, tag: int, default=None):
    values = message.get(tag, [])
    if len(values) > 1:
        raise ValueError(f"Duplicate singular descriptor field {tag}")
    return values[0] if values else default


def text(message: dict, tag: int, default="") -> str:
    value = one(message, tag)
    if value is None:
        return default
    if not isinstance(value, bytes):
        raise ValueError("Descriptor string has wrong wire type")
    return value.decode("utf-8", errors="strict")


def descriptor(data: bytes) -> dict:
    if not data or len(data) > 64 * 1024 * 1024:
        raise ValueError("Descriptor set is empty or exceeds 64 MiB")
    model = {"messages": {}, "enums": {}, "services": {}, "files": {}}

    def put(kind: str, name: str, value):
        if name in model[kind]:
            raise ValueError(f"Duplicate descriptor definition {name}")
        model[kind][name] = value

    def enumeration(raw: bytes, prefix: str):
        item = fields(raw)
        name = prefix + "." + text(item, 1)
        entries = {}
        for raw_value in item.get(2, []):
            value = fields(raw_value)
            key = text(value, 1)
            if key in entries:
                raise ValueError("Duplicate enum name")
            entries[key] = one(value, 2, 0)
        put("enums", name, entries)

    def message(raw: bytes, prefix: str, depth: int = 0):
        if depth > 100:
            raise ValueError("Descriptor nesting exceeds 100")
        item = fields(raw)
        name = prefix + "." + text(item, 1)
        groups = [text(fields(group), 1) for group in item.get(8, [])]
        entries = {}
        names = set()
        for raw_field in item.get(2, []):
            value = fields(raw_field)
            tag = one(value, 3)
            field_name = text(value, 1)
            if not isinstance(tag, int) or tag <= 0 or tag in entries or field_name in names:
                raise ValueError("Invalid or duplicate descriptor field")
            names.add(field_name)
            group = one(value, 9)
            if group is not None and (not isinstance(group, int) or group >= len(groups)):
                raise ValueError("Invalid descriptor oneof index")
            entries[tag] = {"name": field_name, "type": one(value, 5),
                            "typeName": text(value, 6), "label": one(value, 4),
                            "oneof": None if group is None else groups[group],
                            "optional": one(value, 17, 0), "jsonName": text(value, 10)}
        put("messages", name, entries)
        for child in item.get(3, []):
            message(child, name, depth + 1)
        for child in item.get(4, []):
            enumeration(child, name)

    seen_files = set()
    for raw_file in fields(data).get(1, []):
        file = fields(raw_file)
        filename = text(file, 1)
        if not filename or filename in seen_files:
            raise ValueError("Missing or duplicate descriptor file")
        seen_files.add(filename)
        prefix = "." + text(file, 2)
        previous = {kind: set(model[kind]) for kind in ("messages", "enums", "services")}
        for raw in file.get(4, []):
            message(raw, prefix)
        for raw in file.get(5, []):
            enumeration(raw, prefix)
        for raw in file.get(6, []):
            service = fields(raw)
            methods = {}
            for raw_method in service.get(2, []):
                method = fields(raw_method)
                name = text(method, 1)
                if name in methods:
                    raise ValueError("Duplicate service method")
                methods[name] = {"input": text(method, 2), "output": text(method, 3),
                                 "clientStreaming": one(method, 5, 0),
                                 "serverStreaming": one(method, 6, 0)}
            put("services", prefix + "." + text(service, 1), methods)
        model["files"][filename] = {
            "package": text(file, 2),
            **{kind: {name: model[kind][name] for name in sorted(set(model[kind]) - previous[kind])}
               for kind in ("messages", "enums", "services")},
        }
    if not seen_files:
        raise ValueError("No files in descriptor set")
    return model


def frozen_file_projection(file_model: dict) -> dict:
    """Normalize one file's compiled declarations for an independently authored lock."""
    return {
        "package": file_model["package"],
        "messages": {
            name: [{"tag": tag, **field} for tag, field in sorted(fields.items())]
            for name, fields in sorted(file_model["messages"].items())
        },
        "enums": {
            name: [{"name": member, "number": number} for member, number in sorted(values.items())]
            for name, values in sorted(file_model["enums"].items())
        },
        "services": {
            name: {method: value for method, value in sorted(methods.items())}
            for name, methods in sorted(file_model["services"].items())
        },
    }


def con08_frozen_errors(root: Path, current: dict) -> list[str]:
    fixture_path = root / "fixtures/public/con-08-entitlement-commerce.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture.get("schemaVersion") != "con-08-entitlement-commerce.v1":
        raise ValueError("Unsupported CON.08 compatibility fixture")
    lock = fixture.get("frozenDescriptor")
    if not isinstance(lock, dict) or set(lock) != {"file", "projection"}:
        raise ValueError("Invalid CON.08 frozen descriptor envelope")
    filename = "arcforges/publicapi/v1/commerce.proto"
    if lock["file"] != filename or not isinstance(lock["projection"], dict):
        raise ValueError("Invalid CON.08 frozen descriptor identity")
    file_model = current.get("files", {}).get(filename)
    if file_model is None:
        return ["publicapi: CON.08 commerce.proto descriptor is missing"]
    if frozen_file_projection(file_model) != lock["projection"]:
        return ["publicapi: CON.08 frozen commerce.proto descriptor projection changed"]
    return []


def compare(previous: dict, current: dict) -> list[str]:
    """Existing tags, presence, exact types, enum numbers and RPC shapes are fixed.

    Additive declarations are allowed. Removal requires an explicit versioned
    surface retirement before selecting this comparison; it is never silently
    accepted just because a tag is reserved or has the same binary wire type.
    """
    errors = []
    for kind in ("messages", "enums", "services"):
        for name, old_entries in previous[kind].items():
            if name not in current[kind]:
                errors.append(f"{kind}:{name}: deleted definition")
                continue
            new_entries = current[kind][name]
            for key, old in old_entries.items():
                if key not in new_entries:
                    errors.append(f"{kind}:{name}:{key}: deleted member")
                elif old != new_entries[key]:
                    errors.append(f"{kind}:{name}:{key}: changed member or reused tag")
    return errors


def retained(model: dict, retirement: dict) -> dict:
    """Apply only the exact retirement inventory already validated by Foundation.

    The historical descriptor bytes remain immutable. This projection is limited
    to the two namespaces whose retirement is owned by CON.23; it never waives
    retained field changes or a later service's compatibility requirements.
    """
    result = deepcopy(model)
    prefixes = (".arcforges.foundation.v1.", ".arcforges.publicapi.v1.")
    for name in list(result["messages"]):
        if not name.startswith(prefixes):
            continue
        short = name.rsplit(".", 1)[1]
        if short in retirement.get("messages", []):
            del result["messages"][name]
            continue
        for row in retirement.get("fields", {}).get(short, []):
            tag = row["tag"]
            field = result["messages"][name].get(tag)
            if field is not None and field["name"] == row["name"]:
                del result["messages"][name][tag]
    return result


LATER_WINDOW = "eng/compatibility/later-services-window.json"
# The CON.17 completion prerequisites with published protobuf services and those whose published
# contracts are closed JSON schemas only (CON.07 has both).
LATER_SERVICE_TASKS = ["CON.07", "CON.08", "CON.09", "CON.10", "CON.11", "CON.13", "CON.14"]
LATER_SCHEMA_TASKS = ["CON.07", "CON.10", "CON.12", "CON.15", "CON.16"]
LATER_REQUIRED_TASKS = sorted(set(LATER_SERVICE_TASKS) | set(LATER_SCHEMA_TASKS))
PREVIOUS_TO_CURRENT = "previous-client/current-server"
CURRENT_TO_MINIMUM = "current-client/minimum-server"
UNKNOWN = "?"
MAX_DEPTH = 2
ERROR_REPORT_LIMIT = 100
# FieldDescriptorProto.Type numbers and the wire type of each. Groups are not part of the contract.
WIRE = {1: 1, 2: 5, 3: 0, 4: 0, 5: 0, 6: 1, 7: 5, 8: 0, 9: 2, 11: 2, 12: 2, 13: 0, 14: 0, 15: 5, 16: 1, 17: 0, 18: 0}
PACKABLE = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 13, 14, 15, 16, 17, 18})
FIXED = {1: "<d", 2: "<f", 6: "<Q", 7: "<I", 15: "<i", 16: "<q"}
SAMPLES = {
    1: (0.1, -0.5), 2: (1.5, -0.25),
    3: (9007199254740993, -9007199254740993), 4: (18446744073709551615, 9007199254740993),
    5: (-2147483648, 2147483647), 6: (18446744073709551615, 4294967297), 7: (4294967295, 65537),
    8: (True, False), 13: (4294967295, 1), 15: (-2147483648, 2147483647),
    16: (-9223372036854775808, 9223372036854775807), 17: (-2147483648, 2147483647),
    18: (-9223372036854775808, 9223372036854775807),
}


def encode_varint(value: int) -> bytes:
    value &= (1 << 64) - 1
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


# Field 99999, length-delimited "fut": an additive member that no published descriptor declares.
INJECTED_UNKNOWN = encode_varint((99999 << 3) | 2) + b"\x03fut"


def read_varint(data: bytes, at: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if at >= len(data):
            raise ValueError("truncated varint")
        byte = data[at]
        at += 1
        if shift == 63 and byte > 1:
            raise ValueError("varint overflow")
        value |= (byte & 127) << shift
        if byte < 128:
            return value, at
    raise ValueError("varint overflow")


def encode_scalar(kind: int, value) -> bytes:
    if kind == 8:
        return encode_varint(1 if value else 0)
    if kind in (3, 4, 5, 13, 14):
        return encode_varint(value)
    if kind == 17:
        return encode_varint((value << 1) ^ (value >> 31))
    if kind == 18:
        return encode_varint((value << 1) ^ (value >> 63))
    return struct.pack(FIXED[kind], value)


def decode_scalar(kind: int, wire: int, payload):
    """Interpret one raw wire value exactly as the declared type defines its meaning."""
    if wire != WIRE[kind]:
        raise ValueError("wire type does not match the declared type")
    if kind == 8:
        return payload != 0
    if kind == 3:
        return payload - (1 << 64) if payload >= 1 << 63 else payload
    if kind == 4:
        return payload
    if kind in (5, 14):
        value = payload & 0xFFFFFFFF
        return value - (1 << 32) if value >= 1 << 31 else value
    if kind == 13:
        return payload & 0xFFFFFFFF
    if kind == 17:
        value = payload & 0xFFFFFFFF
        return (value >> 1) ^ -(value & 1)
    if kind == 18:
        return (payload >> 1) ^ -(payload & 1)
    return struct.unpack(FIXED[kind], payload)[0]


def declared(model: dict, name: str) -> dict:
    if name not in model["messages"]:
        raise ValueError("unresolved message type " + name)
    return model["messages"][name]


def oneof_arms(message: dict) -> dict[str, list[int]]:
    """Member tags of every oneof group (including proto3 optional's synthetic groups), in tag order."""
    arms: dict[str, list[int]] = {}
    for tag in sorted(message):
        if message[tag]["oneof"] is not None:
            arms.setdefault(message[tag]["oneof"], []).append(tag)
    return arms


def sample_ids(model: dict, name: str) -> list[str]:
    """One default sample per message plus one extra sample per non-first arm of every oneof, so that
    every declared member is written at least once: `name`, then `name@1`, `name@2`, ..."""
    extra = sum(len(tags) - 1 for tags in oneof_arms(declared(model, name)).values())
    return [name] + [f"{name}@{index}" for index in range(1, extra + 1)]


def arm_choice(message: dict, index: int) -> dict[str, int]:
    """Which arm each oneof writes in extra sample `index` (the index-th non-first arm, in group and tag order)."""
    chosen = {}
    for group, tags in oneof_arms(message).items():
        for position in range(1, len(tags)):
            index -= 1
            if index == 0:
                chosen[group] = tags[position]
                return chosen
    return chosen


def synthesize(model: dict, name: str, depth: int = 0, stack: tuple = (), chosen: dict | None = None) -> dict:
    """Deterministically populate one message from its own descriptor: boundary integers, exact
    strings and bytes, one arm of every oneof (the first unless `chosen` names another), two repeated
    elements, nested messages to a bounded depth and an additive unknown member at every level."""
    message = declared(model, name)
    if 99999 in message:
        raise ValueError("the injected unknown field number is declared by " + name)
    tree: dict = {}
    taken = set()
    for tag in sorted(message):
        field = message[tag]
        kind, group, repeated = field["type"], field["oneof"], field["label"] == 3
        if kind not in WIRE:
            raise ValueError(f"unsupported field type {kind} in {name}")
        if group is not None and (group in taken or (chosen and group in chosen and chosen[group] != tag)):
            continue
        if kind == 11 and (depth >= MAX_DEPTH or field["typeName"] in stack + (name,)):
            continue
        values = []
        for index in range(2 if repeated else 1):
            if kind == 11:
                values.append(synthesize(model, field["typeName"], depth + 1, stack + (name,)))
            elif kind == 9:
                values.append(("A中\U0001F600" if index == 0 else "B") + str(tag))
            elif kind == 12:
                values.append(bytes([0, 255, tag & 255]) if index == 0 else bytes([tag & 255, 1]))
            elif kind == 14:
                enum = model["enums"].get(field["typeName"])
                if not enum:
                    raise ValueError("unresolved enum type " + field["typeName"])
                numbers = sorted(set(enum.values()))
                values.append(numbers[-1] if index == 0 else numbers[0])
            else:
                values.append(SAMPLES[kind][index])
        if group is not None:
            taken.add(group)
        tree[tag] = values if repeated else values[0]
    tree[UNKNOWN] = [INJECTED_UNKNOWN]
    return tree


def synthesize_sample(model: dict, sample: str) -> dict:
    name, _, index = sample.partition("@")
    return synthesize(model, name, chosen=arm_choice(declared(model, name), int(index)) if index else None)


def encode_field(model: dict, field: dict, tag: int, value) -> bytes:
    kind = field["type"]
    if field["label"] == 3 and kind in PACKABLE:
        body = b"".join(encode_scalar(kind, item) for item in value)
        return encode_varint((tag << 3) | 2) + encode_varint(len(body)) + body
    result = b""
    for item in value if field["label"] == 3 else [value]:
        if kind in (9, 11, 12):
            body = (encode_message(model, field["typeName"], item) if kind == 11
                    else item.encode("utf-8") if kind == 9 else item)
            result += encode_varint((tag << 3) | 2) + encode_varint(len(body)) + body
        else:
            result += encode_varint((tag << 3) | WIRE[kind]) + encode_scalar(kind, item)
    return result


def encode_message(model: dict, name: str, tree: dict) -> bytes:
    message = declared(model, name)
    return (b"".join(encode_field(model, message[tag], tag, tree[tag])
                     for tag in sorted(key for key in tree if key != UNKNOWN))
            + b"".join(tree.get(UNKNOWN, [])))


def decode_message(model: dict, name: str, data: bytes, depth: int = 0) -> dict:
    """Reference reader driven only by a descriptor. It refuses a wire type that differs from the
    declared type instead of reproducing a runtime's lenient unknown-field treatment, and it keeps
    every undeclared member as raw bytes."""
    if depth > 32:
        raise ValueError("nesting exceeds 32")
    message = declared(model, name)
    tree: dict = {}
    at = 0
    while at < len(data):
        start = at
        key, at = read_varint(data, at)
        tag, wire = key >> 3, key & 7
        if not 1 <= tag <= 536870911:
            raise ValueError("invalid field number")
        if wire == 0:
            payload, at = read_varint(data, at)
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if size > len(data) - at:
                raise ValueError("truncated fixed-width field")
            payload, at = data[at:at + size], at + size
        elif wire == 2:
            size, at = read_varint(data, at)
            if size > len(data) - at:
                raise ValueError("truncated length-delimited field")
            payload, at = data[at:at + size], at + size
        else:
            raise ValueError("unsupported wire type")
        field = message.get(tag)
        if field is None:
            tree.setdefault(UNKNOWN, []).append(data[start:at])
            continue
        kind, repeated = field["type"], field["label"] == 3
        if kind not in WIRE:
            raise ValueError(f"unsupported field type {kind}")
        values = []
        if repeated and kind in PACKABLE and wire == 2:
            inner = 0
            while inner < len(payload):
                if WIRE[kind] == 0:
                    raw, inner = read_varint(payload, inner)
                else:
                    size = 8 if WIRE[kind] == 1 else 4
                    if size > len(payload) - inner:
                        raise ValueError("truncated packed field")
                    raw, inner = payload[inner:inner + size], inner + size
                values.append(decode_scalar(kind, WIRE[kind], raw))
        elif kind in (9, 11, 12):
            if wire != 2:
                raise ValueError("wire type does not match the declared type")
            values.append(decode_message(model, field["typeName"], payload, depth + 1) if kind == 11
                          else payload.decode("utf-8", errors="strict") if kind == 9 else bytes(payload))
        else:
            values.append(decode_scalar(kind, wire, payload))
        if repeated:
            tree.setdefault(tag, []).extend(values)
        else:
            tree[tag] = values[-1]
    return tree


def project(writer: dict, reader: dict, name: str, tree: dict, strict: bool) -> dict:
    """What a reader holding `reader` must see of a message written under `writer`: declared members
    unchanged and every member it does not declare retained as raw unknown bytes. A strict reader
    (the current server reading a previous client) may not leave any written member undeclared."""
    source, known = writer["messages"][name], reader["messages"][name]
    result: dict = {}
    dropped = []
    for tag in sorted(key for key in tree if key != UNKNOWN):
        field = source[tag]
        if tag not in known:
            if strict:
                raise ValueError(f"member {tag} ({field['name']}) is not declared by the reader")
            dropped.append(encode_field(writer, field, tag, tree[tag]))
        elif field["type"] == 11:
            if known[tag]["typeName"] != field["typeName"] or known[tag]["type"] != 11:
                raise ValueError(f"member {tag} ({field['name']}) changed its message type")
            items = tree[tag] if field["label"] == 3 else [tree[tag]]
            projected = [project(writer, reader, field["typeName"], item, strict) for item in items]
            result[tag] = projected if field["label"] == 3 else projected[0]
        else:
            result[tag] = tree[tag]
    unknown = dropped + tree.get(UNKNOWN, [])
    if unknown:
        result[UNKNOWN] = unknown
    return result


def exchange(writer: dict, reader: dict, direction: str, required=None, strict: bool = False) -> tuple[dict, list[str]]:
    """One direction of the offline reference-codec matrix. Every message the writer declares is
    populated, written, read by the other side and compared with what it was meant to say. A message
    the reader lacks is an error only for the previously published `required` names; a current-only
    addition is skipped."""
    errors, count, size, samples = [], 0, 0, 0
    for name in sorted(required if required is not None else writer["messages"]):
        if name not in reader["messages"] or name not in writer["messages"]:
            if required is not None:
                errors.append(f"{direction}: {name}: message is not declared on both sides")
            continue
        count += 1
        try:
            for sample in sample_ids(writer, name):
                tree = synthesize_sample(writer, sample)
                data = encode_message(writer, name, tree)
                size += len(data)
                samples += 1
                if decode_message(reader, name, data) != project(writer, reader, name, tree, strict):
                    errors.append(f"{direction}: {sample}: decoded meaning differs from the written value")
        except (ValueError, UnicodeDecodeError, KeyError) as problem:
            errors.append(f"{direction}: {name}: {problem}")
    return {"direction": direction, "messages": count, "samples": samples, "bytes": size, "errors": len(errors)}, errors


def canonical_json(value) -> str:
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(key, ensure_ascii=False) + ":" + canonical_json(value[key])
                              for key in sorted(value)) + "}"
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, Decimal):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def schema_identity(raw: bytes) -> tuple[str, object]:
    """Canonical SHA-256 and declared schema version of one closed JSON schema document."""
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate JSON property: " + key)
            result[key] = item
        return result
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_float=Decimal)
    version = value.get("x-arcforges-schema-version") if isinstance(value, dict) else None
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest(), version


def exact(value, keys: str, label: str) -> None:
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError(f"Invalid {label}: expected exactly {keys}")


def digest_of(value, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("Invalid SHA-256 for " + label)
    return value


def task_ids(value) -> None:
    if (not isinstance(value, list) or not value or len(set(value)) != len(value)
            or any(not isinstance(item, str) or not re.fullmatch(r"CON\.[0-9]+", item) for item in value)):
        raise ValueError("Invalid task identifier list")


def build_number(version: str) -> tuple[int, int]:
    found = re.fullmatch(r"1\.0\.0-ci\.([1-9][0-9]*)\.([1-9][0-9]*)", version)
    if found is None:
        raise ValueError("Malformed candidate version: " + str(version))
    return int(found.group(1)), int(found.group(2))


def later_window(root: Path) -> dict:
    from check_foundation import safe_path
    window = json.loads((root / LATER_WINDOW).read_text(encoding="utf-8"))
    exact(window, "schemaVersion license contractMajor openedOn earliestRetirement minimumReadSupportDays "
                  "previousVersion minimumVersion candidates pins owners schemas profile coverage",
          "later-service window")
    if (window["schemaVersion"] != "contract-compatibility-later-services.v1" or window["license"] != "Apache-2.0"
            or window["contractMajor"] != 1):
        raise ValueError("Unsupported later-service compatibility window")
    if window["minimumReadSupportDays"] < 90 or (date.fromisoformat(window["earliestRetirement"])
                                                  - date.fromisoformat(window["openedOn"])).days < window["minimumReadSupportDays"]:
        raise ValueError("Later-service read window is shorter than its minimum")
    candidates = window["candidates"]
    if not isinstance(candidates, dict) or not candidates:
        raise ValueError("Missing published candidate identities")
    for version, candidate in candidates.items():
        build_number(version)
        exact(candidate, "publishedOn sourceCommit publication retainedArchive", "candidate " + version)
        date.fromisoformat(candidate["publishedOn"])
        if not (re.fullmatch("[0-9a-f]{40}", candidate["sourceCommit"]) and re.fullmatch(
                r"https://github\.com/ArcForges/Contracts/actions/runs/[1-9][0-9]*", candidate["publication"])):
            raise ValueError("Malformed candidate identity: " + version)
        exact(candidate["retainedArchive"], "artifactId name sha256", "retained archive of " + version)
        digest_of(candidate["retainedArchive"]["sha256"], "retained archive of " + version)
    ordered = sorted(candidates, key=build_number)
    if window["previousVersion"] != ordered[-1] or window["minimumVersion"] != ordered[0]:
        raise ValueError("The window must span from its oldest to its newest published candidate")
    if window["openedOn"] != candidates[ordered[-1]]["publishedOn"]:
        raise ValueError("The read window must open when its newest candidate was published")
    if not window["pins"]:
        raise ValueError("The window has no pinned descriptor")
    introduced, previous_build, serviced_before = [], None, set()
    owner_files, schema_tasks = set(), set()
    for owner in window["owners"]:
        exact(owner, "tasks name files", "file owner row")
        task_ids(owner["tasks"])
        if not isinstance(owner["name"], str) or not owner["name"].strip() or not owner["files"]:
            raise ValueError("Blank file owner row")
        for filename in owner["files"]:
            if filename in owner_files:
                raise ValueError("Descriptor file owned twice: " + filename)
            owner_files.add(filename)
    for pin in window["pins"]:
        exact(pin, "candidate package previousAndMinimum sha256 current introduces files", "descriptor pin")
        if pin["candidate"] not in candidates:
            raise ValueError("Pin names an unrecorded candidate: " + str(pin["candidate"]))
        if previous_build is not None and build_number(pin["candidate"]) < previous_build:
            raise ValueError("Pins must be ordered by increasing candidate")
        previous_build = build_number(pin["candidate"])
        digest_of(pin["sha256"], pin["candidate"])
        safe_path(root, pin["previousAndMinimum"])
        safe_path(root, pin["current"])
        if pin["introduces"]:
            task_ids(pin["introduces"])
        introduced.extend(pin["introduces"])
        for entry in pin["files"]:
            exact(entry, "file services messages enums", "pinned file")
            if entry["file"] not in owner_files:
                raise ValueError("Pinned file has no owner row: " + entry["file"])
        if len({entry["file"] for entry in pin["files"]}) != len(pin["files"]):
            raise ValueError("Descriptor file accounted twice in " + pin["candidate"])
        serviced_now = {task for owner in window["owners"] for task in owner["tasks"]
                        if any(entry["file"] in owner["files"] and entry["services"] for entry in pin["files"])}
        for task in pin["introduces"]:
            if task not in serviced_now or task in serviced_before:
                raise ValueError(f"{task} is not first published with services in {pin['candidate']}")
        serviced_before |= serviced_now
    if len(set(introduced)) != len(introduced) or set(introduced) != set(LATER_SERVICE_TASKS):
        raise ValueError("Each protobuf completion prerequisite must be introduced by exactly one pin: "
                         + ", ".join(sorted(set(LATER_SERVICE_TASKS) ^ set(introduced))))
    if window["pins"][-1]["candidate"] != window["previousVersion"]:
        raise ValueError("The newest pin must be the previous candidate")
    schema_paths = set()
    for schema in window["schemas"]:
        exact(schema, "task path schemaVersion identicalSince sha256", "closed schema row")
        digest_of(schema["sha256"], schema["path"])
        safe_path(root, schema["path"])
        if schema["path"] in schema_paths:
            raise ValueError("Closed schema pinned twice: " + schema["path"])
        if schema["identicalSince"] not in candidates:
            raise ValueError("Schema names an unrecorded candidate: " + schema["path"])
        schema_paths.add(schema["path"])
        task_ids([schema["task"]])
        schema_tasks.add(schema["task"])
    missing = sorted(set(LATER_SCHEMA_TASKS) - schema_tasks)
    if missing:
        raise ValueError("Later-service window omits closed schemas of completion prerequisites: " + ", ".join(missing))
    return window


def domain_index(window: dict, model: dict) -> dict[str, str]:
    """Map every definition of one pinned descriptor to the tasks that own its file."""
    owners = {filename: "/".join(owner["tasks"]) for owner in window["owners"] for filename in owner["files"]}
    index = {}
    for filename, content in model["files"].items():
        for kind in ("messages", "enums", "services"):
            for name in content[kind]:
                index[kind + ":" + name] = owners.get(filename, "unaccounted")
    return index


def later_accounting_errors(pin: dict, model: dict) -> list[str]:
    errors = []
    declared_files = {entry["file"]: entry for entry in pin["files"]}
    if set(declared_files) != set(model["files"]):
        errors.append(f"later-services: {pin['candidate']}: pinned descriptor files differ from the accounted files: "
                      + ", ".join(sorted(set(declared_files) ^ set(model["files"]))))
    for filename, entry in sorted(declared_files.items()):
        content = model["files"].get(filename)
        if content is None:
            continue
        actual = {"services": {name.lstrip("."): len(methods) for name, methods in content["services"].items()},
                  "messages": len(content["messages"]), "enums": len(content["enums"])}
        if {key: entry[key] for key in actual} != actual:
            errors.append(f"later-services: {pin['candidate']}: {filename}: pinned service, message and enum "
                          "accounting differs from the pinned descriptor")
    return errors


def later_schema_errors(root: Path, window: dict) -> list[str]:
    from check_foundation import safe_path
    errors = []
    for schema in window["schemas"]:
        try:
            current, version = schema_identity(safe_path(root, schema["path"]).read_bytes())
        except (OSError, ValueError, UnicodeDecodeError) as problem:
            errors.append(f"later-services: {schema['task']}: {schema['path']}: {problem}")
            continue
        if version != schema["schemaVersion"]:
            errors.append(f"later-services: {schema['task']}: {schema['path']}: published schema version "
                          f"{schema['schemaVersion']} became {version}")
        elif current != schema["sha256"]:
            errors.append(f"later-services: {schema['task']}: {schema['path']}: closed schema identical since "
                          f"{schema['identicalSince']} changed in place")
    return errors


def later_compare_errors(window: dict, pin: dict, pinned: dict, current: dict) -> list[str]:
    """Definitions published in this pin must survive in the current descriptor (additive growth only).
    One additive-only comparison covers the previous client reading the current server and the current
    client writing to the pinned server; the two directions differ only in the reference-codec exchange.
    Each error names the pin and the CON task that owns the file."""
    owners = domain_index(window, pinned)
    errors = []
    for problem in compare(pinned, current):
        parts = problem.split(":")
        errors.append(f"later-services: {pin['candidate']}: {owners.get(parts[0] + ':' + parts[1], 'unaccounted')}: {problem}")
    return errors


def later_exchange_errors(pin: dict, pinned: dict, current: dict, only=None) -> tuple[list[dict], list[str]]:
    """Both directions of the reference-codec exchange for one pin: every member the previous client
    writes must be understood by the current server with the meaning it was written with, and every
    additive member the current client writes must be retained by the pinned server, never reinterpreted."""
    runs, errors = [], []
    for direction, writer, reader, required, strict in (
            (PREVIOUS_TO_CURRENT, pinned, current, set(pinned["messages"]) if only is None else set(only), True),
            (CURRENT_TO_MINIMUM, current, pinned, None if only is None else set(only), False)):
        summary, problems = exchange(writer, reader, f"{direction} {pin['candidate']}", required, strict)
        runs.append({**summary, "direction": direction, "candidate": pin["candidate"], "pin": pin_key(pin)})
        errors.extend("later-services: " + problem for problem in problems)
    return runs, errors


def pinned_model(root: Path, pin: dict) -> dict:
    from check_foundation import safe_path
    raw = safe_path(root, pin["previousAndMinimum"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("Historical later-service descriptor fixture changed: " + pin["candidate"])
    return descriptor(raw)


def check_later_services(root: Path, current_descriptors: dict | None = None) -> dict:
    """Run the later-service window: every pinned published candidate against the current descriptor of
    its package in both directions, the reference-codec exchange, file/service/message accounting and
    the closed-schema pins. `current_descriptors` maps a pin's `current` path to another file (tests)."""
    from check_foundation import safe_path
    window = later_window(root)
    errors, runs, results = [], [], []
    currents = {}
    for pin in window["pins"]:
        pinned = pinned_model(root, pin)
        path = (current_descriptors or {}).get(pin["current"]) or safe_path(root, pin["current"])
        if pin["current"] not in currents:
            currents[pin["current"]] = descriptor(Path(path).read_bytes())
        current = currents[pin["current"]]
        pin_errors = later_accounting_errors(pin, pinned)
        pin_errors.extend(later_compare_errors(window, pin, pinned, current))
        pin_runs, problems = later_exchange_errors(pin, pinned, current)
        pin_errors.extend(problems)
        runs.extend(pin_runs)
        errors.extend(pin_errors)
        results.append({"pin": pin_key(pin), "candidate": pin["candidate"], "package": pin["package"], "introduces": pin["introduces"],
                        "pinnedDefinitions": {key: len(value) for key, value in pinned.items()},
                        "currentDefinitions": {key: len(value) for key, value in current.items()},
                        "errors": len(pin_errors)})
    errors.extend(later_schema_errors(root, window))
    return {"previousVersion": window["previousVersion"], "minimumVersion": window["minimumVersion"],
            "pins": results, "exchange": runs, "closedSchemas": len(window["schemas"]),
            "coverage": window["coverage"], "errorCount": len(errors), "errors": errors[:ERROR_REPORT_LIMIT]}


def pin_key(pin: dict) -> str:
    """Directory name of one pin in the generated-codec exchange (a candidate can carry several packages)."""
    return Path(pin["previousAndMinimum"]).stem


def pin_samples(pinned: dict) -> list[str]:
    """Every sample of every published message of one pin, without the leading dot of the type name."""
    return [sample.lstrip(".") for name in sorted(pinned["messages"]) for sample in sample_ids(pinned, name)]


def emit_later_exchange(root: Path, directory: Path) -> int:
    """Write what the previous client of every pin would send for each sample of each message that pin
    published, for the generated current codecs to read. Nothing here calls a service."""
    window = later_window(root)
    total = 0
    for pin in window["pins"]:
        pinned = pinned_model(root, pin)
        samples = pin_samples(pinned)
        target = directory / pin_key(pin)
        (target / "previous").mkdir(parents=True, exist_ok=True)
        for sample in samples:
            message = "." + sample.partition("@")[0]
            data = encode_message(pinned, message, synthesize_sample(pinned, "." + sample))
            (target / "previous" / (sample + ".bin")).write_bytes(data)
        (target / "messages.txt").write_text("\n".join(samples) + "\n", encoding="utf-8", newline="\n")
        total += len(samples)
    return total


def verify_later_exchange(root: Path, directory: Path) -> dict:
    """Check what the generated current codecs wrote back for every pin: each published sample must be
    present, and the pinned reader must see exactly the meaning the previous client sent."""
    window = later_window(root)
    errors, identical, total, per_pin = [], 0, 0, []
    for pin in window["pins"]:
        pinned = pinned_model(root, pin)
        key, target = pin_key(pin), directory / pin_key(pin)
        try:
            listed = (target / "messages.txt").read_text(encoding="utf-8").split()
        except OSError as problem:
            errors.append(f"generated-codec exchange: {key}: {problem}")
            continue
        if listed != pin_samples(pinned):
            errors.append(f"generated-codec exchange: {key}: the sample list differs from the pinned descriptor")
        pin_identical = 0
        for sample in listed:
            try:
                data = (target / "current" / (sample + ".bin")).read_bytes()
                pin_identical += data == (target / "previous" / (sample + ".bin")).read_bytes()
                if decode_message(pinned, "." + sample.partition("@")[0], data) != synthesize_sample(pinned, "." + sample):
                    errors.append(f"generated-codec exchange: {key}: {sample}: the pinned reader sees a different meaning")
            except (OSError, ValueError, UnicodeDecodeError, KeyError) as problem:
                errors.append(f"generated-codec exchange: {key}: {sample}: {problem}")
        identical += pin_identical
        total += len(listed)
        per_pin.append({"pin": key, "samples": len(listed), "byteIdentical": pin_identical})
    return {"schemaVersion": "contract-later-service-codec-exchange.v1", "pins": per_pin, "samples": total,
            "byteIdentical": identical, "errorCount": len(errors), "errors": errors[:ERROR_REPORT_LIMIT]}


def check_window(root: Path) -> dict:
    from check_foundation import check, safe_path
    # This verifies the exact CON.23 retirement exceptions before using them.
    check(root)
    window = json.loads((root / "eng/compatibility/window.json").read_text(encoding="utf-8"))
    if window["schemaVersion"] != "contract-compatibility-window.v1" or window["minimumReadSupportDays"] < 90:
        raise ValueError("Invalid minimum compatibility window")
    if (date.fromisoformat(window["earliestRetirement"]) - date.fromisoformat(window["openedOn"])).days < window["minimumReadSupportDays"]:
        raise ValueError("Read compatibility window is shorter than its minimum")
    if window["previousVersion"] != window["minimumVersion"]:
        raise ValueError("Distinct minimum versions require their own pinned descriptors and offline harness")
    inventory = json.loads((root / "eng/foundation-inventory.json").read_text(encoding="utf-8"))
    results, errors = [], []
    for row in window["descriptors"]:
        raw = safe_path(root, row["previousAndMinimum"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("Historical descriptor fixture changed: " + row["package"])
        previous = retained(descriptor(raw), inventory.get("retirement", {}))
        current = descriptor(safe_path(root, row["current"]).read_bytes())
        problems = compare(previous, current)
        if row["package"] == "ArcForges.Contracts.PublicApi":
            problems.extend(con08_frozen_errors(root, current))
        errors.extend(row["package"] + ": " + problem for problem in problems)
        results.append({"package": row["package"], "retainedDefinitions": {key: len(value) for key, value in previous.items()},
                        "check": "preserve published supported members used by both offline codec directions",
                        "errors": problems})
    later = check_later_services(root)
    errors.extend(later["errors"])
    return {"schemaVersion": "contract-compatibility-report.v1", "previousVersion": window["previousVersion"],
            "minimumVersion": window["minimumVersion"], "coverage": window["coverage"], "descriptors": results,
            "laterServices": later, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--window", action="store_true")
    parser.add_argument("--emit-later-exchange", type=Path, metavar="DIRECTORY")
    parser.add_argument("--verify-later-exchange", type=Path, metavar="DIRECTORY")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.emit_later_exchange:
        print(f"Wrote {emit_later_exchange(args.root, args.emit_later_exchange)} previous-client messages")
        return 0
    if args.window:
        report = check_window(args.root)
    elif args.verify_later_exchange:
        report = verify_later_exchange(args.root, args.verify_later_exchange)
    else:
        if args.previous is None or args.current is None:
            parser.error("Use --window, --emit-later-exchange, --verify-later-exchange or both --previous and --current")
        previous = descriptor(args.previous.read_bytes())
        current = descriptor(args.current.read_bytes())
        errors = compare(previous, current)
        report = {"schemaVersion": "contract-descriptor-compatibility.v1", "errors": errors,
                  "previousDefinitions": {key: len(value) for key, value in previous.items()},
                  "currentDefinitions": {key: len(value) for key, value in current.items()}}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
