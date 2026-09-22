# SPDX-License-Identifier: Apache-2.0
"""Offline checks for the selected foundation closure and its published baseline.

This deliberately parses only the explicit, top-level authored schema form used
by these two files. The existing protoc/access gate remains the protobuf compiler.
No package restore, compiler, network access or generated-code execution occurs.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "eng/foundation-inventory.json"
BASELINE = "eng/foundation-baseline.json"
CONSTRAINTS = "public/proto/constraints.json"
VALUES = "public/proto/value-boundaries.json"
FOUNDATION = "public/proto/arcforges/foundation/v1/foundation.proto"
CONTENT = "public/proto/arcforges/publicapi/v1/content.proto"
PUBLISHED_COMMIT = "30ddcad2bcb3634e089abb5e29d6c9ce05d38386"
PUBLISHED_RECORDS = set("Id Revision LocalNotesVersion NativeContentRev Instant Decimal AggregateRef VersionedRef Receipt ApplicationScope RequestMeta ResponseMeta ArcError RetryAdvice ErrorDetails RevisionConflict LimitFailure VersionFailure StateFailure".split())
PUBLISHED_ENUMS = {"EffectCertainty", "RetryMode", "ErrorCategory"}
EXTRA_SEEDS = set("PageRequest PageState Rational MediaTime MediaRange ByteRange TimeRangeUtc ContentOrigin NotesQuery MeasurementRequest MeasurementResult AggregateBody".split())
SCALARS = set("string bytes int32 int64 sint32 sint64 uint32 uint64 fixed32 fixed64 sfixed32 sfixed64 double float bool".split())
ALIASES = {name: "string" for name in "Name Text Email SecretText Key CountryCode Cursor ReasonCode Hash ModelId".split()}
ALIASES.update(Bytes="bytes", Int32="int32", Int64="int64", UInt64="uint64", Bool="bool")
TOKEN = re.compile(r'\s+|//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z_0-9]*|-?[0-9]+|[{}\[\];=,.]')
NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(root: Path, relative: str) -> dict:
    return json.loads(safe_path(root, relative).read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)


def safe_path(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and relative and "\\" not in relative and ":" not in relative,
            "Invalid repository-relative path")
    parsed = PurePosixPath(relative)
    require(not parsed.is_absolute() and all(part not in {"", ".", ".."} for part in relative.split("/")),
            f"Unsafe source path: {relative}")
    target = root.joinpath(*parsed.parts)
    require(target.resolve().is_relative_to(root.resolve()), f"Source path escapes repository: {relative}")
    return target


class SchemaParser:
    def __init__(self, source: str, path: str):
        self.path = path
        self.tokens: list[str] = []
        position = 0
        while position < len(source):
            match = TOKEN.match(source, position)
            require(match is not None, f"{path}: unsupported schema token at byte {position}")
            token = match[0]
            if not token.isspace() and not token.startswith(("//", "/*")):
                self.tokens.append(token)
            position = match.end()
        self.at = 0

    def take(self, expected: str | None = None) -> str:
        require(self.at < len(self.tokens), f"{self.path}: unexpected end of schema")
        value = self.tokens[self.at]
        self.at += 1
        require(expected is None or value == expected, f"{self.path}: expected {expected}, received {value}")
        return value

    def peek(self) -> str | None:
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def name(self) -> str:
        value = self.take()
        require(NAME.fullmatch(value), f"{self.path}: expected identifier")
        return value

    def qualified(self) -> str:
        name = ""
        if self.peek() == ".":
            name = self.take()
        name += self.name()
        while self.peek() == ".":
            name += self.take() + self.name()
        return name

    def string(self) -> str:
        value = self.take()
        require(value.startswith('"'), f"{self.path}: expected quoted string")
        return json.loads(value)

    def reservations(self, result: dict) -> None:
        self.take("reserved")
        while True:
            value = self.take()
            if value.startswith('"'):
                result["reservedNames"].append(json.loads(value))
            else:
                require(value.isdecimal(), f"{self.path}: unsupported reserved range")
                result["reservedTags"].append(int(value))
            if self.peek() != ",":
                break
            self.take(",")
        self.take(";")

    def field(self, oneof: str | None = None) -> dict:
        label = self.take() if self.peek() in {"optional", "repeated"} else ""
        require(not oneof or not label, f"{self.path}: labeled oneof member")
        kind, name = self.qualified(), self.name()
        self.take("=")
        tag = int(self.take())
        require(1 <= tag <= 536870911 and not 19000 <= tag <= 19999, f"{self.path}: invalid field tag")
        self.take("[")
        self.take("json_name")
        self.take("=")
        json_name = self.string()
        self.take("]")
        self.take(";")
        return {"name": name, "jsonName": json_name, "type": kind, "tag": tag, "label": label, "oneof": oneof}

    def message(self) -> tuple[str, dict]:
        self.take("message")
        name = self.name()
        self.take("{")
        result = {"fields": [], "reservedTags": [], "reservedNames": []}
        while self.peek() != "}":
            if self.peek() == "reserved":
                self.reservations(result)
            elif self.peek() == "oneof":
                self.take("oneof")
                group = self.name()
                self.take("{")
                while self.peek() != "}":
                    result["fields"].append(self.field(group))
                self.take("}")
            else:
                result["fields"].append(self.field())
        self.take("}")
        fields = result["fields"]
        for key in ["name", "jsonName", "tag"]:
            require(len({f[key] for f in fields}) == len(fields), f"{self.path}: duplicate {name} {key}")
        require(not {f["tag"] for f in fields}.intersection(result["reservedTags"]), f"{name}: reused reserved tag")
        require(not {f["name"] for f in fields}.intersection(result["reservedNames"]), f"{name}: reused reserved name")
        return name, result

    def enumeration(self) -> tuple[str, list[dict]]:
        self.take("enum")
        name = self.name()
        self.take("{")
        values = []
        while self.peek() != "}":
            value = self.name()
            self.take("=")
            number = int(self.take())
            self.take(";")
            values.append({"name": value, "number": number})
        self.take("}")
        require(len({v["name"] for v in values}) == len(values) and len({v["number"] for v in values}) == len(values), f"{name}: duplicate enum value")
        return name, values

    def parse(self) -> dict:
        result = {"package": None, "options": {}, "imports": [], "messages": {}, "enums": {}}
        self.take("syntax")
        self.take("=")
        require(self.string() == "proto3", f"{self.path}: expected proto3")
        self.take(";")
        self.take("package")
        result["package"] = self.qualified()
        self.take(";")
        while self.peek() is not None:
            token = self.peek()
            if token == "import":
                self.take("import")
                result["imports"].append(self.string())
                self.take(";")
            elif token == "option":
                self.take("option")
                key = self.name()
                self.take("=")
                value = self.string() if self.peek().startswith('"') else self.take()
                self.take(";")
                require(key not in result["options"], f"{self.path}: duplicate option")
                result["options"][key] = value
            elif token in {"message", "enum"}:
                name, definition = self.message() if token == "message" else self.enumeration()
                require(name not in result["messages"] and name not in result["enums"], f"{self.path}: duplicate type {name}")
                result["messages" if token == "message" else "enums"][name] = definition
            else:
                raise ValueError(f"{self.path}: unexpected declaration {token}; this projection defines no services")
        return result


def parse_schema(source: str, path: str) -> dict:
    return SchemaParser(source, path).parse()


def snake(name: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()


def check_model(inventory: dict, schemas: dict, constraints: dict, values: dict, baseline: dict) -> tuple[int, int]:
    require(inventory.get("schemaVersion") == "foundation-inventory.v1" and inventory.get("license") == "Apache-2.0", "Unknown foundation inventory")
    require(re.fullmatch(r"[0-9a-f]{40}", inventory.get("designCommit", "")), "Invalid Design identity")
    require(inventory.get("designProfile") == "docs/assurance/wp03-01-foundation-contract-profile.md", "Unexpected Design scope")
    require(baseline.get("schemaVersion") == "foundation-baseline.v1" and baseline.get("license") == "Apache-2.0", "Unknown compatibility baseline")
    require(baseline.get("sourceCommit") == PUBLISHED_COMMIT and baseline.get("sourcePath") == FOUNDATION, "Published compatibility source changed")
    records = {row["name"]: row for row in inventory["records"]}
    enums = {row["name"]: row for row in inventory["enums"]}
    require(len(records) == len(inventory["records"]) and len(enums) == len(inventory["enums"]), "Duplicate selected type")
    require(not records.keys() & enums.keys(), "Message/enum ownership collision")
    old = baseline["foundation"]
    require(set(old["messages"]) == PUBLISHED_RECORDS and set(old["enums"]) == PUBLISHED_ENUMS and not old["imports"], "Published baseline type set changed")
    require(schemas[FOUNDATION]["package"] == old["package"] == "arcforges.foundation.v1", "Published Foundation package changed")
    require(schemas[FOUNDATION]["options"] == old["options"], "Published Foundation generator namespace changed")
    require(not schemas[FOUNDATION]["imports"], "Foundation cannot import owner or internal projections")
    require(schemas[CONTENT]["package"] == "arcforges.publicapi.v1" and schemas[CONTENT]["imports"] == ["arcforges/foundation/v1/foundation.proto"], "PublicApi projection import/package mismatch")
    require(schemas[CONTENT]["options"] == {"csharp_namespace": "ArcForges.Contracts.PublicApi.V1", "java_package": "io.github.arcforges.contracts.publicapi.v1", "java_multiple_files": "true", "java_outer_classname": "ContentProto"}, "PublicApi generator namespace mismatch")
    all_messages, all_enums = {}, {}
    for path, schema in schemas.items():
        for name, definition in schema["messages"].items():
            require(name not in all_messages, f"Duplicate schema ownership: {name}")
            all_messages[name] = (path, definition)
        for name, definition in schema["enums"].items():
            require(name not in all_enums, f"Duplicate enum ownership: {name}")
            all_enums[name] = (path, definition)
    require(set(records) == set(all_messages), "Selected message inventory differs from authored schemas")
    require(set(enums) == set(all_enums), "Selected enum inventory differs from authored schemas")
    seeds = set(old["messages"]) | EXTRA_SEEDS
    require(set(inventory["seeds"]) == seeds and len(inventory["seeds"]) == len(seeds), "Selected seed closure changed")
    edges: dict[str, set[str]] = {}
    used_enums: set[str] = set()
    for name, row in records.items():
        path, definition = all_messages[name]
        schema = schemas[path]
        owner = "ArcForges.Contracts.Foundation" if path == FOUNDATION else "ArcForges.Contracts.PublicApi"
        require(row["source"] == path and row["owner"] == owner and row["protobufType"] == schema["package"] + "." + name, f"{name}: owner/namespace mismatch")
        expected_rule = "docs/architecture/contracts/10-application-scope-and-streams.md#2-new-records-and-field-assignments" if name == "ApplicationScope" else "docs/architecture/contracts/04-protobuf-wire-registry.md#4-shared-record-field-registry"
        require(row["sourceRule"] == expected_rule, f"{name}: missing exact source rule")
        fields = {field["jsonName"]: field for field in definition["fields"]}
        require(len(row["fields"]) == len(fields) and {f["name"] for f in row["fields"]} == set(fields), f"{name}: incomplete or duplicate fields")
        profile = constraints["messages"].get(row["protobufType"])
        require(profile and profile["csharpType"] == owner + ".V1." + name and set(profile["fields"]) == set(fields), f"{name}: constraint ownership/field mismatch")
        require(profile.get("rules", []) == row["rules"], f"{name}: semantic rule inventory mismatch")
        oneof_names, edges[name] = set(), set()
        for expected in row["fields"]:
            actual = fields[expected["name"]]
            kind = ALIASES.get(expected["type"], expected["type"])
            require(expected["wireType"] == kind, f"{name}: alias encoding changed")
            if kind not in SCALARS:
                require(kind in records or kind in enums, f"{name}: unresolved type {kind}")
                target = records[kind] if kind in records else enums[kind]
                target_domain = "foundation" if target["owner"].endswith(".Foundation") else "publicapi"
                target_package = f"arcforges.{target_domain}.v1"
                resolved = actual["type"].lstrip(".") if "." in actual["type"] else schema["package"] + "." + actual["type"]
                require(resolved == target_package + "." + kind, f"{name}: incorrect dependency owner for {kind}")
                (edges[name] if kind in records else used_enums).add(kind)
            else:
                require(actual["type"] == kind, f"{name}: scalar wire encoding changed")
            require(actual["name"] == expected["protoName"] == snake(expected["name"]) and actual["tag"] == expected["tag"] and actual["oneof"] == expected["oneof"], f"{name}.{expected['name']}: field name/tag/oneof mismatch")
            presence = "oneof" if expected["oneof"] else {"[]": "repeated", "?": "optional", "required": "required"}.get(expected["cardinality"])
            require(expected["presence"] == presence, f"{name}: inconsistent recorded presence")
            label = "repeated" if presence == "repeated" else "optional" if presence != "oneof" and (kind in SCALARS or kind in enums) else ""
            require(actual["label"] == label, f"{name}.{expected['name']}: lost scalar/repeated/oneof presence")
            field_rules = profile["fields"][expected["name"]]
            require(bool(field_rules.get("required")) == (presence == "required"), f"{name}.{expected['name']}: required constraint mismatch")
            if presence == "oneof":
                oneof_names.add(expected["oneof"])
            if kind in enums:
                permitted = [v["number"] for v in enums[kind]["values"] if v["number"] != 0]
                rule = field_rules.get("items", {}) if presence == "repeated" else field_rules
                require(rule.get("enumValues") == permitted, f"{name}.{expected['name']}: request enum validation mismatch")
        require(set(profile.get("oneofRequired", [])) == oneof_names, f"{name}: required oneof validation mismatch")
        require(sorted(definition["reservedTags"]) == sorted(row.get("reservedTags", [])) and sorted(definition["reservedNames"]) == sorted(row.get("reservedNames", [])), f"{name}: removed fields not reserved")
        domain, stem = ("foundation", "Foundation") if path == FOUNDATION else ("publicapi", "Content")
        expected_outputs = {
            "csharp": f"src/public/dotnet/{owner}/Generated/Proto/{stem}.cs",
            "typescript": f"src/public/ts/proto/src/gen/arcforges/{domain}/v1/{stem.lower()}_pb.ts",
            "java": f"src/public/kotlin/contracts-proto/generated/java/io/github/arcforges/contracts/{domain}/v1/{name}.java",
            "kotlin": f"src/public/kotlin/contracts-proto/generated/kotlin/io/github/arcforges/contracts/{domain}/v1/{name}Kt.kt",
        }
        require(row["outputs"] == expected_outputs, f"{name}: generated output ownership mismatch")
    for name, row in enums.items():
        path, actual = all_enums[name]
        require(row["owner"] == ("ArcForges.Contracts.Foundation" if path == FOUNDATION else "ArcForges.Contracts.PublicApi"), f"{name}: enum owner mismatch")
        expected = [{"name": snake(name).upper() + "_" + snake(v["name"]).upper(), "number": v["number"]} for v in row["values"]]
        require(actual == expected and actual[0]["number"] == 0 and row["values"][0]["name"] == "unspecified", f"{name}: enum name/number drift")
    visited, pending = set(), list(seeds)
    while pending:
        name = pending.pop()
        require(name in records, f"Missing selected seed/dependency: {name}")
        if name not in visited:
            visited.add(name)
            pending.extend(edges[name])
    require(visited == set(records) and used_enums == set(enums), "Unreachable extra or missing selected type")
    for name, previous in old["messages"].items():
        current = schemas[FOUNDATION]["messages"].get(name)
        require(current, f"Published Foundation record removed: {name}")
        current_fields = {field["tag"]: field for field in current["fields"]}
        require(all(current_fields.get(field["tag"]) == field for field in previous["fields"]), f"Published Foundation field changed or reused: {name}")
    for name, previous in old["enums"].items():
        current = schemas[FOUNDATION]["enums"].get(name, [])
        require(all(value in current for value in previous), f"Published Foundation enum removed or renumbered: {name}")
    require(values.get("schemaVersion") == "value-boundaries.v1" and values.get("license") == "Apache-2.0", "Unknown value boundary inventory")
    domains = values["identifiers"]
    require(set(domains) == {"Foundation", "PublicApi"}, "Unexpected identifier owner")
    flat = [name for names in domains.values() for name in names]
    require(len(set(flat)) == len(flat) and all(re.fullmatch(r"[A-Z][A-Za-z0-9]*Id", name) for name in flat), "Duplicate/invalid identity domain")
    require({k: sorted(v) for k, v in domains.items()} == {k: sorted(v) for k, v in baseline["identifierDomains"].items()}, "Selected identifier domain missing, unreviewed or moved")
    return len(records), len(flat)


def check(root: Path = ROOT, generated: bool = False, self_test: bool = False) -> None:
    inventory, baseline, constraints, values = [read_json(root, path) for path in [INVENTORY, BASELINE, CONSTRAINTS, VALUES]]
    schemas = {path: parse_schema(safe_path(root, path).read_text(encoding="utf-8"), path) for path in [FOUNDATION, CONTENT]}
    counts = check_model(inventory, schemas, constraints, values, baseline)
    if generated:
        for record in inventory["records"]:
            for path in record["outputs"].values():
                require(safe_path(root, path).is_file(), f"Missing selected generated output: {path}")
    if self_test:
        cases = []
        changed = deepcopy(schemas)
        changed[FOUNDATION]["messages"]["Id"]["fields"][0]["tag"] = 2
        changed_inventory = deepcopy(inventory)
        next(row for row in changed_inventory["records"] if row["name"] == "Id")["fields"][0]["tag"] = 2
        cases.append(("published tag reuse despite matching inventory", changed_inventory, changed, constraints, values))
        changed = deepcopy(schemas)
        changed[FOUNDATION]["messages"]["Revision"]["fields"][0]["type"] = "uint64"
        changed_inventory = deepcopy(inventory)
        changed_field = next(row for row in changed_inventory["records"] if row["name"] == "Revision")["fields"][0]
        changed_field.update(type="uint64", wireType="uint64")
        cases.append(("published signedness change despite matching inventory", changed_inventory, changed, constraints, values))
        changed = deepcopy(schemas)
        changed[CONTENT]["messages"]["MeasurementValue"]["fields"][2]["oneof"] = None
        cases.append(("oneof presence loss", inventory, changed, constraints, values))
        changed = deepcopy(inventory)
        changed["records"] = [r for r in changed["records"] if r["name"] != "TextRunSegment"]
        cases.append(("missing owner dependency", changed, schemas, constraints, values))
        changed = deepcopy(schemas)
        changed[CONTENT]["imports"].append("arcforges/local/notes/v1/notes.proto")
        cases.append(("public internal import", inventory, changed, constraints, values))
        changed = deepcopy(schemas)
        changed[CONTENT]["enums"]["TaskState"][1]["number"] = 99
        cases.append(("enum renumbering", inventory, changed, constraints, values))
        changed = deepcopy(constraints)
        changed["messages"]["arcforges.foundation.v1.Id"]["fields"]["value"].pop("required")
        cases.append(("required field validator removal", inventory, schemas, changed, values))
        changed = deepcopy(values)
        changed["identifiers"]["PublicApi"].remove("TextRunId")
        cases.append(("text/execution run identity collapse", inventory, schemas, constraints, changed))
        for label, selected, authored, rules, identities in cases:
            try:
                check_model(selected, authored, rules, identities, baseline)
            except ValueError:
                continue
            raise ValueError(f"Negative policy case passed: {label}")
    print(f"Foundation inventory: {counts[0]} selected messages, {counts[1]} ID domains, published baseline and closure passed" + ("; 8 negative cases passed" if self_test else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--generated", action="store_true", help="Also require all selected generated output files")
    parser.add_argument("--self-test", action="store_true", help="Exercise targeted invalid schema/inventory mutations in memory")
    options = parser.parse_args()
    try:
        check(options.root.resolve(), options.generated, options.self_test)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(f"Foundation inventory failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
