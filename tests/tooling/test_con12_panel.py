# SPDX-License-Identifier: Apache-2.0
"""Independent panel document/tree vectors; no host UI or operation authority claim."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


def shape(value, node, schema):
    if "$ref" in node:
        return shape(value, schema["$defs"][node["$ref"].split("/")[-1]], schema)
    if "oneOf" in node:
        return sum(shape(value, branch, schema) for branch in node["oneOf"]) == 1
    kind = node["type"]
    if kind == "object":
        if not isinstance(value, dict): return False
        if isinstance(node.get("additionalProperties"), dict):
            if not node.get("minProperties", 0) <= len(value) <= node["maxProperties"]: return False
            return all(shape(key, node["propertyNames"], schema) and shape(item, node["additionalProperties"], schema) for key, item in value.items())
        return (set(node["required"]).issubset(value) and not set(value) - set(node["properties"])
                and all(shape(item, node["properties"][key], schema) for key, item in value.items()))
    if kind == "array":
        return isinstance(value, list) and node.get("minItems", 0) <= len(value) <= node["maxItems"] and all(shape(item, node["items"], schema) for item in value)
    if kind == "string":
        if not isinstance(value, str) or not node.get("minLength", 0) <= len(value) <= node.get("maxLength", 1000000): return False
        if "pattern" in node and re.fullmatch(node["pattern"], value) is None: return False
    elif kind == "integer":
        if type(value) is not int or not node["minimum"] <= value <= node["maximum"]: return False
    elif kind == "boolean":
        if type(value) is not bool: return False
    else: raise AssertionError(kind)
    return ("const" not in node or value == node["const"]) and ("enum" not in node or value in node["enum"])


def locale(tag):
    parts = tag.lower().split("-")
    grandfathered = {"en-gb-oed", "i-ami", "i-bnn", "i-default", "i-enochian", "i-hak", "i-klingon", "i-lux", "i-mingo", "i-navajo", "i-pwn", "i-tao", "i-tay", "i-tsu", "sgn-be-fr", "sgn-be-nl", "sgn-ch-de", "art-lojban", "cel-gaulish", "no-bok", "no-nyn", "zh-guoyu", "zh-hakka", "zh-min", "zh-min-nan", "zh-xiang"}
    if tag.lower() in grandfathered: return True
    if parts[0] == "x": return len(parts) > 1 and all(1 <= len(x) <= 8 and x.isalnum() for x in parts[1:])
    if not parts[0].isalpha() or not 2 <= len(parts[0]) <= 8: return False
    index = 1
    if len(parts[0]) <= 3:
        count = 0
        while index < len(parts) and len(parts[index]) == 3 and parts[index].isalpha() and count < 3:
            count += 1; index += 1
    if index < len(parts) and len(parts[index]) == 4 and parts[index].isalpha(): index += 1
    if index < len(parts) and ((len(parts[index]) == 2 and parts[index].isalpha()) or (len(parts[index]) == 3 and parts[index].isdigit())): index += 1
    variants, extensions = set(), set()
    while index < len(parts):
        token = parts[index]
        if token == "x": return index + 1 < len(parts) and all(1 <= len(x) <= 8 and x.isalnum() for x in parts[index+1:])
        if len(token) == 1 and token.isalnum():
            if token in extensions: return False
            extensions.add(token); index += 1; count = 0
            while index < len(parts) and 2 <= len(parts[index]) <= 8 and parts[index].isalnum(): index += 1; count += 1
            if not count: return False
            continue
        if extensions or token in variants or not (token.isalnum() and (5 <= len(token) <= 8 or len(token) == 4 and token[0].isdigit())): return False
        variants.add(token); index += 1
    return True


def profile(value):
    controls = {control["id"]: control for control in value["controls"]}
    if len(controls) != len(value["controls"]): return False
    parent = {}
    def predicate(node, depth=1):
        if depth > 8: raise ValueError("predicate depth")
        return 1 + sum(predicate(child, depth + 1) for child in node.get("predicates", []))
    for control in controls.values():
        if any(field in control for field in ["binding", "optionsBinding", "visible"]) or control.get("arguments"):
            if "inputSchemaId" not in value: return False
        args = control.get("arguments", [])
        if len({arg["name"] for arg in args}) != len(args): return False
        if "visible" in control:
            try:
                if predicate(control["visible"]) > 128: return False
            except ValueError: return False
        for field in ["label", "help", "text"]:
            if field in control:
                tags = list(control[field])
                if len({tag.lower() for tag in tags}) != len(tags) or not all(map(locale, tags)): return False
        for child in control.get("children", []):
            if child not in controls or child in parent: return False
            parent[child] = control["id"]
    for identity in controls:
        current, seen = identity, set()
        while current is not None:
            if current in seen: return False
            seen.add(current)
            if len(seen) > 16: return False
            current = parent.get(current)
    return True


class PanelVectors(unittest.TestCase):
    def test_independent_panel_shapes_and_tree_constraints(self):
        schema = json.loads((ROOT / "public/http/v1/panel.schema.json").read_text(encoding="utf-8"))
        fixture = json.loads((ROOT / "fixtures/public/con-12-extension-policy.json").read_text(encoding="utf-8"))["panel"]
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(shape(case["value"], schema, schema) and profile(case["value"]), case["valid"])


if __name__ == "__main__": unittest.main()
