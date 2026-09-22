# SPDX-License-Identifier: Apache-2.0
"""Offline negative tests for the WP03.02 serialization posture gate."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))
import check_serialization as gate
from generate_shapes import CS_CONTEXT_OPTIONS


class SerializationPolicy(unittest.TestCase):
    def tree(self, files: dict[str, str]) -> tuple[Path, list[str]]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, content in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(content, encoding="utf-8")
        return root, sorted(files)

    def rejects(self, check, files: dict[str, str], message: str) -> None:
        root, names = self.tree(files)
        with self.assertRaisesRegex(ValueError, message):
            check(root, names)

    def test_current_repository_passes(self):
        result = gate.audit(ROOT)
        self.assertEqual(result["result"], "passed")
        self.assertEqual(result["strictJsonContexts"], 3)
        self.assertGreaterEqual(result["packableAotProjects"], 14)

    def test_forbidden_dependencies_in_every_lock_kind(self):
        nuget = {"version": 2, "dependencies": {"net10.0": {"Newtonsoft.Json": {"type": "Transitive"}}}}
        self.rejects(gate.check_locks, {"a/packages.lock.json": json.dumps(nuget)}, "Newtonsoft.Json")
        for package in ["Refit", "protobuf-net", "Grpc.AspNetCore.Server.Reflection", "Castle.Core"]:
            graph = {"version": 2, "dependencies": {"net10.0": {package: {"type": "Direct"}}}}
            self.rejects(gate.check_locks, {"packages.lock.json": json.dumps(graph)}, "forbidden NuGet")
        for package in ["protobufjs", "google-protobuf", "@grpc/proto-loader"]:
            lock = {"packages": {"": {}, f"node_modules/{package}": {}}}
            self.rejects(gate.check_locks, {"package-lock.json": json.dumps(lock)}, "forbidden npm")
        self.rejects(gate.check_locks, {"m/gradle.lockfile": "com.google.protobuf:protobuf-java:4.36.1=runtimeClasspath\n"},
                     "protobuf-java")
        self.rejects(gate.check_locks, {"gradle.lockfile": "io.grpc:grpc-services:1.84.0=runtimeClasspath\n"}, "reflection")

    def test_lite_protobuf_runtime_is_admitted(self):
        root, names = self.tree({"gradle.lockfile": "com.google.protobuf:protobuf-javalite:4.36.1=runtimeClasspath\n"})
        self.assertEqual(gate.check_locks(root, names), 1)

    def test_runtime_selected_proto_types(self):
        self.rejects(gate.check_protos, {"a.proto": 'import "google/protobuf/any.proto";\n'}, "any.proto")
        self.rejects(gate.check_protos, {"a.proto": "message A { google.protobuf.Struct s = 1; }\n"}, "Struct")
        self.rejects(gate.check_protos, {"a.proto": "service ServerReflection {}\n"}, "reflection")

    def test_forbidden_production_apis(self):
        cs = lambda text: {"src/public/dotnet/P/A.cs": text}
        ts = lambda text: {"src/public/ts/p/src/a.ts": text}
        check_cs = lambda root, names: gate.scan(root, names, ".cs", gate.CSHARP_APIS, gate.HANDWRITTEN_CSHARP)
        check_ts = lambda root, names: gate.scan(root, names, ".ts", gate.TYPESCRIPT_APIS, gate.HANDWRITTEN_TYPESCRIPT)
        for text in ["JsonFormatter.Default.Format(m);", "new TypeRegistry();", "Activator.CreateInstance(t);",
                     "Type.GetType(name);", "Assembly.Load(bytes);", "t.MakeGenericType(u);", "parser.WithDiscardUnknownFields(true);"]:
            self.rejects(check_cs, cs(text), "forbidden")
        for text in ["toJson(Schema, m)", "createFileRegistry(set)", "anyUnpack(any, registry)",
                     "fromBinary(S, b, { readUnknownFields: false })", "createGrpcWebTransport({ useBinaryFormat: false })"]:
            self.rejects(check_ts, ts(text), "forbidden")

    def test_handwritten_wire_types_outside_generated_owners(self):
        check_cs = lambda root, names: gate.scan(root, names, ".cs", gate.CSHARP_APIS, gate.HANDWRITTEN_CSHARP)
        self.rejects(check_cs, {"src/public/dotnet/P/Dto.cs": "public sealed class Dto : pb::IMessage<Dto> { }"}, "handwritten protobuf message")
        self.rejects(check_cs, {"src/public/dotnet/P/Dto.cs": 'public record Dto { [JsonPropertyName("a")] public int A { get; init; } }'},
                     "handwritten JSON wire record")
        self.rejects(check_cs, {"src/public/dotnet/P/C.cs": "partial class C : JsonSerializerContext { }"}, "handwritten JSON metadata")
        check_ts = lambda root, names: gate.scan(root, names, ".ts", gate.TYPESCRIPT_APIS, gate.HANDWRITTEN_TYPESCRIPT)
        self.rejects(check_ts, {"src/public/ts/p/src/a.ts": 'export const S = messageDesc(file, 0);'}, "handwritten protobuf descriptor")
        root, names = self.tree({"src/public/dotnet/P/Values.cs": "static T Decode<T>(MessageParser<T> p) where T : IMessage<T> => default!;"})
        self.assertEqual(gate.scan(root, names, ".cs", gate.CSHARP_APIS, gate.HANDWRITTEN_CSHARP), 1)

    def test_project_posture(self):
        props = "<Project><PropertyGroup><JsonSerializerIsReflectionEnabledByDefault>false</JsonSerializerIsReflectionEnabledByDefault></PropertyGroup></Project>"
        library = "<Project><PropertyGroup><IsPackable>true</IsPackable>{}</PropertyGroup></Project>"
        self.rejects(gate.check_projects, {"Directory.Build.props": "<Project />"}, "disable reflection")
        self.rejects(gate.check_projects, {"Directory.Build.props": props, "src/public/dotnet/A/A.csproj": library.format("")}, "not AOT-compatible")
        self.rejects(gate.check_projects, {"Directory.Build.props": props, "tests/T/T.csproj":
                     "<Project><PropertyGroup><JsonSerializerIsReflectionEnabledByDefault>true</JsonSerializerIsReflectionEnabledByDefault></PropertyGroup></Project>"},
                     "overrides")
        root, names = self.tree({"Directory.Build.props": props,
                                 "src/public/dotnet/A/A.csproj": library.format("<IsAotCompatible>true</IsAotCompatible>")})
        self.assertEqual(gate.check_projects(root, names), 1)

    def test_json_contexts_require_strict_options(self):
        context = "public partial class AJsonContext : global::System.Text.Json.Serialization.JsonSerializerContext { }\n"
        self.rejects(gate.check_contexts, {"src/public/dotnet/A/Generated/Shapes/A.g.cs": context}, "strict generation options")
        self.rejects(gate.check_contexts, {"src/public/dotnet/A/A.cs": CS_CONTEXT_OPTIONS + context}, "outside generated shapes")
        root, names = self.tree({"src/public/dotnet/A/Generated/Shapes/A.g.cs": CS_CONTEXT_OPTIONS + context})
        self.assertEqual(gate.check_contexts(root, names), 1)

    def test_service_catalogue_must_match_authored_services(self):
        row = {"id": "Example.Package", "kind": "nuget", "sourceRoot": "src/public/dotnet/Example.Package", "proto": ["p.proto"]}
        service = {"name": "EchoService", "csharp": "Example.V1.EchoService"}
        root, _ = self.tree({})
        with patch("package_catalog.packages", return_value=[row]), patch("contracts.proto_services", return_value=[service]):
            with self.assertRaisesRegex(ValueError, "missing generated service catalogue"):
                gate.check_services(root)
            target = root / row["sourceRoot"] / "Generated/Services/ContractServices.g.cs"
            target.parent.mkdir(parents=True)
            target.write_text("public static class ContractServices { }", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "omits"):
                gate.check_services(root)
        with patch("package_catalog.packages", return_value=[row]), patch("contracts.proto_services", return_value=[]):
            with self.assertRaisesRegex(ValueError, "absent from its schemas"):
                gate.check_services(root)


if __name__ == "__main__":
    unittest.main()
