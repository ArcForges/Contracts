# SPDX-License-Identifier: Apache-2.0
"""CON.07 generator guards: the closed route catalogue, the form-urlencoded wire root and the protoc reserved-member rule refuse hostile input."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))

import generate_shapes as shapes  # noqa: E402

WIRES = {"JsonRequest": "json", "JsonResponse": "json", "OtherJson": "json", "FormRequest": "form-urlencoded"}


def route(**changes):
    row = {
        "id": "demo.post",
        "method": "POST",
        "path": "/session/v1/demo",
        "credential": "session-cookie",
        "origin": "exact-configured",
        "csrf": "required",
        "setCookie": "none",
        "cache": "no-store",
        "request": ["JsonRequest"],
        "response": ["JsonResponse"],
    }
    row.update(changes)
    return row


def catalogue(*routes, wires=WIRES):
    return shapes.route_catalogue("Demo", "Demo.Http.V1", list(routes), wires)


class RouteCatalogueGuards(unittest.TestCase):
    def test_a_closed_valid_catalogue_is_emitted(self):
        cs, ts = catalogue(
            route(),
            route(id="demo.get", method="GET", path="/session/v1/demo/{id}", request=["FormRequest"], response=[], csrf="none", origin="none"),
        )
        self.assertIn("DemoRoutes", cs)
        self.assertIn("demo.get", ts)

    def test_every_vocabulary_field_refuses_an_unknown_value(self):
        hostile = {
            "method": "DELETE",
            "credential": "bearer-token",
            "origin": "wildcard",
            "csrf": "optional",
            "setCookie": "persistent",
            "cache": "public",
        }
        for field, value in hostile.items():
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, f"unsupported {field}"):
                catalogue(route(**{field: value}))

    def test_the_field_set_is_exact(self):
        extra = route()
        extra["handler"] = "x"
        missing = route()
        del missing["cache"]
        for name, hostile in (("extra", extra), ("missing", missing)):
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, "route fields must be exactly"):
                catalogue(hostile)

    def test_empty_or_non_list_catalogues_are_refused(self):
        for hostile in ([], None, {}):
            with self.subTest(value=hostile), self.assertRaisesRegex(ValueError, "nonempty list"):
                shapes.route_catalogue("Demo", "Demo.Http.V1", hostile, WIRES)

    def test_route_identity_and_path_are_closed(self):
        for bad_id in ("Demo.post", "demo", "demo..post", "demo.1post", 7):
            with self.subTest(route_id=bad_id), self.assertRaises(ValueError):
                catalogue(route(id=bad_id))
        for bad_path in ("/other/v1/demo", "/session/v1/", "/session/v1/de mo", "/session/v1/demo?x=1", "session/v1/demo"):
            with self.subTest(path=bad_path), self.assertRaisesRegex(ValueError, "invalid or duplicate method/path"):
                catalogue(route(path=bad_path))
        with self.assertRaisesRegex(ValueError, "unique dotted"):
            catalogue(route(), route(path="/session/v1/other"))
        with self.assertRaisesRegex(ValueError, "invalid or duplicate method/path"):
            catalogue(route(), route(id="demo.again"))

    def test_roots_must_belong_to_the_bundle_and_share_one_wire(self):
        with self.assertRaisesRegex(ValueError, "distinct roots of this bundle"):
            catalogue(route(request=["ForeignRoot"]))
        with self.assertRaisesRegex(ValueError, "distinct roots of this bundle"):
            catalogue(route(request=["JsonRequest", "JsonRequest"]))
        with self.assertRaisesRegex(ValueError, "share one wire encoding"):
            catalogue(route(response=["JsonResponse", "FormRequest"]))

    def test_body_shape_follows_the_method(self):
        with self.assertRaisesRegex(ValueError, "GET request cannot carry a JSON body"):
            catalogue(route(method="GET", path="/session/v1/demo/get", csrf="none"))
        with self.assertRaisesRegex(ValueError, "exactly one root"):
            catalogue(route(request=["JsonRequest", "OtherJson"]))

    def test_the_pinned_bundles_keep_their_origin_vocabulary(self):
        self.assertEqual(shapes.ROUTE_VOCABULARY["origin"], {"exact-configured", "none"})
        self.assertEqual(shapes.ROUTE_VOCABULARY["cache"], {"no-store"})
        self.assertEqual(shapes.ROUTE_VOCABULARY["method"], {"GET", "POST"})


def form_root(**changes):
    root = {
        "title": "FormRoot",
        "type": "object",
        "properties": {"a": {"type": "string", "minLength": 1, "maxLength": 8}},
        "required": ["a"],
        "additionalProperties": False,
        "x-arcforges-wire": "form-urlencoded",
    }
    root.update(changes)
    return root


def compile_bundle(root):
    bundle = {"title": "Demo", "$defs": {"FormRoot": root, "Other": {"title": "Other", "type": "object", "properties": {}, "additionalProperties": False}},
              "oneOf": [{"$ref": "#/$defs/FormRoot"}, {"$ref": "#/$defs/Other"}]}
    return shapes.compile_bundle_roots(bundle, "Demo.Http.V1")


class WireRootGuards(unittest.TestCase):
    def test_a_string_only_form_root_compiles(self):
        roots, compilers, _ = compile_bundle(form_root())
        self.assertTrue(compilers[0].form)
        self.assertFalse(compilers[1].form)
        self.assertEqual(roots[0]["x-arcforges-wire"], "form-urlencoded")

    def test_only_the_form_wire_is_supported(self):
        with self.assertRaisesRegex(ValueError, "supported only as form-urlencoded on a root object"):
            compile_bundle(form_root(**{"x-arcforges-wire": "multipart"}))

    def test_the_wire_applies_only_to_an_object_root(self):
        with self.assertRaisesRegex(ValueError, "must be a titled object"):
            compile_bundle(form_root(type="array"))

    def test_the_wire_is_refused_on_a_nested_node(self):
        root = form_root()
        nested = copy.deepcopy(root)
        nested["properties"]["a"] = {"type": "string", "x-arcforges-wire": "form-urlencoded"}
        with self.assertRaisesRegex(ValueError, "supported only as form-urlencoded on a root object"):
            compile_bundle(nested)

    def test_a_form_root_cannot_declare_a_non_string_property(self):
        for hostile in ({"type": "integer"}, {"type": "boolean"}, {"type": "array", "items": {"type": "string"}}):
            root = form_root()
            root["properties"]["b"] = hostile
            with self.subTest(property=hostile), self.assertRaises(ValueError):
                compile_bundle(root)

    def test_a_form_root_cannot_be_a_string_map(self):
        with self.assertRaisesRegex(ValueError, "supported only as form-urlencoded on a root object"):
            compile_bundle(form_root(additionalProperties={"type": "string"}))


class ReservedMemberRule(unittest.TestCase):
    def test_the_protoc_reserved_member_set_is_suffixed(self):
        for member in sorted(shapes.CS_RESERVED_MEMBERS):
            with self.subTest(member=member):
                self.assertEqual(shapes.cs_member(member), member + "_")

    def test_ordinary_members_and_case_variants_are_untouched(self):
        for member in ("Product", "descriptor", "DescriptorX", "Parsers", "types", "Name"):
            with self.subTest(member=member):
                self.assertEqual(shapes.cs_member(member), member)

    def test_the_set_is_exactly_the_protoc_reserved_members(self):
        self.assertEqual(shapes.CS_RESERVED_MEMBERS, {
            "Types", "Descriptor", "Equals", "ToString", "GetHashCode", "GetType", "MemberwiseClone", "Parser",
            "Clone", "CalculateSize", "MergeFrom", "WriteTo",
        })


if __name__ == "__main__":
    unittest.main()
