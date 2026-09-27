# SPDX-License-Identifier: Apache-2.0
"""Offline compatibility checks over compiled FileDescriptorSet bytes.

This reader covers descriptor metadata only; it is not a business wire codec.
It uses no source-regex approximation, package restore or live service.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path


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
    model = {"messages": {}, "enums": {}, "services": {}}

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
    if not seen_files:
        raise ValueError("No files in descriptor set")
    return model


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
        errors.extend(row["package"] + ": " + problem for problem in problems)
        results.append({"package": row["package"], "retainedDefinitions": {key: len(value) for key, value in previous.items()},
                        "check": "preserve published supported members used by both offline codec directions",
                        "errors": problems})
    return {"schemaVersion": "contract-compatibility-report.v1", "previousVersion": window["previousVersion"],
            "minimumVersion": window["minimumVersion"], "coverage": window["coverage"], "descriptors": results, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--window", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.window:
        report = check_window(args.root)
    else:
        if args.previous is None or args.current is None:
            parser.error("Use --window or both --previous and --current")
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
