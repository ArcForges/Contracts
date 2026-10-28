// SPDX-License-Identifier: Apache-2.0

package compat

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"google.golang.org/protobuf/encoding/protowire"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protodesc"
	"google.golang.org/protobuf/types/descriptorpb"

	publicapiv1 "github.com/ArcForges/Contracts/go/arcforges/publicapi/v1"
)

// TestModuleFilesAreTheCompiledSchema compares the descriptor embedded in every generated Go file with the descriptor
// set that the repository's pinned protoc compiles from the same .proto files (artifacts/go-module.binpb, written by
// python eng/contracts.py generate and go test), so the Go bindings carry exactly the schema the C# packages carry.
func TestModuleFilesAreTheCompiledSchema(t *testing.T) {
	root := repositoryRoot(t)
	data, err := os.ReadFile(filepath.Join(root, "artifacts", "go-module.binpb"))
	if err != nil {
		t.Fatalf("compile the descriptor set first (python eng/contracts.py go test does): %v", err)
	}
	var set descriptorpb.FileDescriptorSet
	if err := proto.Unmarshal(data, &set); err != nil {
		t.Fatal(err)
	}
	compiled := map[string]*descriptorpb.FileDescriptorProto{}
	for _, file := range set.GetFile() {
		file.SourceCodeInfo = nil
		compiled[file.GetName()] = file
	}
	var catalog struct {
		Packages []struct {
			Kind  string   `json:"kind"`
			Proto []string `json:"proto"`
		} `json:"packages"`
	}
	readJSON(t, filepath.Join(root, "eng", "contract-packages.json"), &catalog)
	var registered []string
	for _, row := range catalog.Packages {
		if row.Kind == "go" {
			for _, source := range row.Proto {
				registered = append(registered, source[strings.Index(source, "/proto/")+len("/proto/"):])
			}
		}
	}
	var embedded []string
	for _, file := range moduleFiles {
		embedded = append(embedded, file.Path())
		want, ok := compiled[file.Path()]
		if !ok {
			t.Errorf("%s is not in the compiled descriptor set", file.Path())
			continue
		}
		if got := protodesc.ToFileDescriptorProto(file); !proto.Equal(got, want) {
			t.Errorf("%s: the generated Go descriptor differs from the compiled schema", file.Path())
		}
	}
	slices.Sort(embedded)
	slices.Sort(registered)
	if !slices.Equal(embedded, registered) || len(compiled) != len(embedded) {
		t.Fatalf("the Go module files %v differ from the registered %v or the compiled closure (%d files)",
			embedded, registered, len(compiled))
	}
}

// TestFoundationWireOracles: the ten published wire oracles of wp03-01.json decode and re-encode byte for byte.
func TestFoundationWireOracles(t *testing.T) {
	root := repositoryRoot(t)
	fixture := loadFoundation(t, root)
	if len(fixture.wireVectors) != 10 {
		t.Fatalf("expected the ten wire oracles, found %d", len(fixture.wireVectors))
	}
	for _, vector := range fixture.wireVectors {
		kind := fixture.target(t, vector.Target)
		authored := fromJSON(t, kind, fixture.expand(t, vector.Value, map[string]bool{}))
		if got := marshal(t, authored); !bytes.Equal(got, mustHex(t, vector.Hex)) {
			t.Errorf("%s: Go encodes %x, the oracle is %s", vector.ID, got, vector.Hex)
		}
		decoded := kind.New().Interface()
		if err := proto.Unmarshal(mustHex(t, vector.Hex), decoded); err != nil || !proto.Equal(decoded, authored) {
			t.Errorf("%s: the oracle bytes do not decode to the authored value (%v)", vector.ID, err)
		}
	}
}

// TestFoundationFixtureCases: every positive foundation case (wp03-01, CON.02 descriptors, CON.09 transfer ticket)
// read from its authored protobuf-JSON value encodes, decodes to the same value and re-encodes to the same bytes.
func TestFoundationFixtureCases(t *testing.T) {
	root := repositoryRoot(t)
	fixture := loadFoundation(t, root)
	positives, targets := 0, map[string]bool{}
	for _, item := range fixture.cases {
		if !item.Valid {
			continue
		}
		kind := fixture.target(t, item.Target)
		authored := fromJSON(t, kind, fixture.materialize(t, item))
		data := marshal(t, authored)
		decoded := kind.New().Interface()
		if err := proto.Unmarshal(data, decoded); err != nil {
			t.Errorf("%s: %v", item.ID, err)
			continue
		}
		if !proto.Equal(decoded, authored) || !bytes.Equal(marshal(t, decoded), data) {
			t.Errorf("%s: the Go round trip changed the value", item.ID)
		}
		targets[item.Target] = true
		positives++
	}
	for name := range fixture.samples {
		if !strings.HasPrefix(name, "$") && !targets[name] {
			t.Errorf("fixture record %s has no positive case", name)
		}
	}
	if positives <= 200 {
		t.Fatalf("expected the complete positive set, ran %d", positives)
	}
	t.Logf("%d positive foundation fixture cases round-trip through the Go bindings", positives)
}

// serializationFixture is the binary half of wp03-02.json. The registry limits belong to the C# ContractWire helper;
// the Go bindings have no such helper, so decodeWithin applies the same limits with the protobuf runtime's own
// options, which is how a Go consumer configures them (see docs/consuming.md).
type serializationFixture struct {
	Limits map[string]any `json:"limits"`
	Binary []struct {
		ID        string `json:"id"`
		Operation string `json:"operation"`
		Limit     string `json:"limit"`
		Construct struct {
			Kind       string `json:"kind"`
			Target     string `json:"target"`
			Hex        string `json:"hex"`
			TotalBytes int    `json:"totalBytes"`
			Fields     []int  `json:"fields"`
			Levels     int    `json:"levels"`
		} `json:"construct"`
		Expect      string  `json:"expect"`
		ReencodeHex *string `json:"reencodeHex"`
	} `json:"binary"`
}

var errTooLarge = errors.New("tooLarge")
var errTooDeep = errors.New("tooDeep")

// decodeWithin applies the WP03.02 decode policy: the byte limit before parsing, then the root plus at most
// nestedLevels nested message levels.
func decodeWithin(data []byte, limit, nestedLevels int, message proto.Message) error {
	if len(data) > limit {
		return errTooLarge
	}
	err := proto.UnmarshalOptions{RecursionLimit: nestedLevels + 1}.Unmarshal(data, message)
	if err != nil && strings.Contains(err.Error(), "exceeded maximum recursion depth") {
		return errTooDeep
	}
	return err
}

func filler(t *testing.T, total int) []byte {
	t.Helper()
	tag := protowire.AppendTag(nil, 15999, protowire.BytesType)
	for size := total - len(tag); size >= 0; size-- {
		if len(tag)+protowire.SizeVarint(uint64(size))+size == total {
			return protowire.AppendBytes(tag, make([]byte, size))
		}
	}
	t.Fatalf("no filler of %d bytes", total)
	return nil
}

func nested(fields []int, levels int) []byte {
	var inner []byte
	for level := levels - 1; level >= 0; level-- {
		wrapped := protowire.AppendTag(nil, protowire.Number(fields[level%len(fields)]), protowire.BytesType)
		inner = protowire.AppendBytes(wrapped, inner)
	}
	return inner
}

// TestSerializationVectors: the wp03-02.json binary vectors (exact re-encoding of unknown fields and unknown enum
// numbers, malformed input refused, the registry byte and depth limits applied with the runtime's options).
func TestSerializationVectors(t *testing.T) {
	root := repositoryRoot(t)
	var fixture serializationFixture
	readJSON(t, filepath.Join(root, "fixtures", "public", "wp03-02.json"), &fixture)
	limits := map[string]int{}
	for name, value := range fixture.Limits {
		if number, ok := value.(json.Number); ok {
			if parsed, err := number.Int64(); err == nil {
				limits[name] = int(parsed)
			}
		}
	}
	depth := limits["nestedMessageLevels"]
	if depth != 100 || len(fixture.Binary) < 30 {
		t.Fatalf("unexpected wp03-02 binary fixture (depth %d, %d vectors)", depth, len(fixture.Binary))
	}
	for _, vector := range fixture.Binary {
		limit, ok := limits[vector.Limit]
		if !ok {
			t.Fatalf("%s: unknown limit %s", vector.ID, vector.Limit)
		}
		var data []byte
		switch vector.Construct.Kind {
		case "hex":
			data = mustHex(t, vector.Construct.Hex)
		case "filler":
			data = filler(t, vector.Construct.TotalBytes)
		case "nested":
			data = nested(vector.Construct.Fields, vector.Construct.Levels)
		default:
			t.Fatalf("%s: unknown construction %s", vector.ID, vector.Construct.Kind)
		}
		kind := messageType(t, vector.Construct.Target)
		message := kind.New().Interface()
		var err error
		if vector.Operation == "encode" {
			// Encoding builds the message first (unbounded) and refuses an oversized result.
			if err = proto.Unmarshal(data, message); err == nil {
				var encoded []byte
				if encoded, err = proto.Marshal(message); err == nil && len(encoded) > limit {
					err = errTooLarge
				}
			}
		} else {
			err = decodeWithin(data, limit, depth, message)
		}
		switch vector.Expect {
		case "accept":
			if err != nil {
				t.Errorf("%s: refused: %v", vector.ID, err)
			} else if vector.ReencodeHex != nil {
				if got, _ := proto.Marshal(message); !bytes.Equal(got, mustHex(t, *vector.ReencodeHex)) {
					t.Errorf("%s: re-encoded %x, expected %s", vector.ID, got, *vector.ReencodeHex)
				}
			}
		case "tooLarge":
			if !errors.Is(err, errTooLarge) {
				t.Errorf("%s: expected the byte limit, got %v", vector.ID, err)
			}
		case "tooDeep":
			if !errors.Is(err, errTooDeep) {
				t.Errorf("%s: expected the depth limit, got %v", vector.ID, err)
			}
		case "malformed":
			if err == nil || errors.Is(err, errTooLarge) || errors.Is(err, errTooDeep) {
				t.Errorf("%s: malformed bytes were not refused as malformed (%v)", vector.ID, err)
			}
		default:
			t.Errorf("%s: unknown outcome %s", vector.ID, vector.Expect)
		}
	}
}

// TestDescriptorWireVectors: the CON.02 descriptor wire vectors decode and re-encode byte for byte.
func TestDescriptorWireVectors(t *testing.T) {
	root := repositoryRoot(t)
	var fixture struct {
		Wire map[string]string `json:"wire"`
	}
	readJSON(t, filepath.Join(root, "fixtures", "public", "con-02-descriptors.json"), &fixture)
	targets := map[string]string{
		"operationBinding": "arcforges.foundation.v1.OperationBinding",
		"actionDescriptor": "arcforges.foundation.v1.ActionDescriptor",
		"contextProvider":  "arcforges.publicapi.v1.ContextProvider",
		"featureSet":       "arcforges.foundation.v1.FeatureSet",
	}
	if len(fixture.Wire) != len(targets) {
		t.Fatalf("unexpected CON.02 wire vectors %v", fixture.Wire)
	}
	for key, text := range fixture.Wire {
		message := messageType(t, targets[key]).New().Interface()
		data := mustHex(t, text)
		if err := proto.Unmarshal(data, message); err != nil {
			t.Fatalf("%s: %v", key, err)
		}
		if got := marshal(t, message); !bytes.Equal(got, data) {
			t.Errorf("%s: re-encoded %x, expected %s", key, got, text)
		}
	}
}

// TestSyncUnknownResponse: the CON.03 forward-compatible AggregateBody keeps its unknown member byte for byte.
func TestSyncUnknownResponse(t *testing.T) {
	root := repositoryRoot(t)
	var fixture struct {
		Compatible struct {
			Schema  string `json:"schema"`
			WireHex string `json:"wireHex"`
		} `json:"compatibleUnknownResponse"`
		Cases []struct {
			ID   string `json:"id"`
			Body struct {
				Kind    string `json:"kind"`
				WireHex string `json:"wireHex"`
			} `json:"body"`
		} `json:"cases"`
	}
	readJSON(t, filepath.Join(root, "fixtures", "public", "con-03-sync-allowlist.json"), &fixture)
	if fixture.Compatible.Schema != "AggregateBody" {
		t.Fatalf("unexpected schema %s", fixture.Compatible.Schema)
	}
	data := mustHex(t, fixture.Compatible.WireHex)
	var body publicapiv1.AggregateBody
	if err := proto.Unmarshal(data, &body); err != nil {
		t.Fatal(err)
	}
	if body.GetScopeProjectMetadata() == nil || len(body.ProtoReflect().GetUnknown()) == 0 {
		t.Fatal("the compatible response lost its known body or its unknown member")
	}
	if got := marshal(t, &body); !bytes.Equal(got, data) {
		t.Fatalf("unknown response fields changed: %x", got)
	}
	opaque := 0
	for _, item := range fixture.Cases {
		if item.Body.Kind != "opaque" {
			continue
		}
		data := mustHex(t, item.Body.WireHex)
		var value publicapiv1.AggregateBody
		if err := proto.Unmarshal(data, &value); err != nil || !bytes.Equal(marshal(t, &value), data) {
			t.Errorf("%s: the opaque body does not round-trip (%v)", item.ID, err)
		}
		opaque++
	}
	if opaque == 0 {
		t.Fatal("no opaque CON.03 body was exercised")
	}
}
