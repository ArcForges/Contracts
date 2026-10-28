// SPDX-License-Identifier: Apache-2.0

package compat

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"testing"

	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/reflect/protoregistry"

	catalogv1 "github.com/ArcForges/Contracts/go/arcforges/catalog/v1"
	fleetv1 "github.com/ArcForges/Contracts/go/arcforges/fleet/v1"
	foundationv1 "github.com/ArcForges/Contracts/go/arcforges/foundation/v1"
	hellov1 "github.com/ArcForges/Contracts/go/arcforges/hello/v1"
	nodev1 "github.com/ArcForges/Contracts/go/arcforges/node/v1"
	operatorv1 "github.com/ArcForges/Contracts/go/arcforges/operator/v1"
	publicapiv1 "github.com/ArcForges/Contracts/go/arcforges/publicapi/v1"
	relayv1 "github.com/ArcForges/Contracts/go/arcforges/relay/v1"
)

// rootEnv names the Contracts checkout whose fixtures the tests read. python eng/contracts.py go test sets it, and
// then a missing fixture fails; without it the tests look for the checkout above the module, and a copy of the
// module without its repository (for example in a module cache) skips them.
const rootEnv = "ARCFORGES_CONTRACTS_ROOT"

// moduleFiles is the explicit file set of the Go module (eng/contract-packages.json, the Go row). The tests look up
// generated message types by name in the global registry only to reach the generated Go types; a name outside these
// files fails.
var moduleFiles = []protoreflect.FileDescriptor{
	foundationv1.File_arcforges_foundation_v1_foundation_proto,
	hellov1.File_arcforges_hello_v1_hello_proto,
	publicapiv1.File_arcforges_publicapi_v1_application_proto,
	publicapiv1.File_arcforges_publicapi_v1_chat_proto,
	publicapiv1.File_arcforges_publicapi_v1_commerce_proto,
	publicapiv1.File_arcforges_publicapi_v1_connector_proto,
	publicapiv1.File_arcforges_publicapi_v1_content_proto,
	publicapiv1.File_arcforges_publicapi_v1_descriptors_proto,
	publicapiv1.File_arcforges_publicapi_v1_export_proto,
	publicapiv1.File_arcforges_publicapi_v1_identity_proto,
	publicapiv1.File_arcforges_publicapi_v1_inprocess_values_proto,
	publicapiv1.File_arcforges_publicapi_v1_scope_proto,
	publicapiv1.File_arcforges_publicapi_v1_support_proto,
	publicapiv1.File_arcforges_publicapi_v1_support_access_proto,
	publicapiv1.File_arcforges_publicapi_v1_sync_proto,
	publicapiv1.File_arcforges_publicapi_v1_transfer_proto,
	catalogv1.File_arcforges_catalog_v1_catalog_proto,
	nodev1.File_arcforges_node_v1_account_proto,
	nodev1.File_arcforges_node_v1_approvals_proto,
	nodev1.File_arcforges_node_v1_caches_proto,
	nodev1.File_arcforges_node_v1_common_proto,
	nodev1.File_arcforges_node_v1_diagnosis_proto,
	nodev1.File_arcforges_node_v1_events_proto,
	nodev1.File_arcforges_node_v1_integrations_proto,
	nodev1.File_arcforges_node_v1_memory_proto,
	nodev1.File_arcforges_node_v1_node_proto,
	nodev1.File_arcforges_node_v1_peers_proto,
	nodev1.File_arcforges_node_v1_policy_proto,
	nodev1.File_arcforges_node_v1_queue_proto,
	nodev1.File_arcforges_node_v1_resources_proto,
	nodev1.File_arcforges_node_v1_sessions_proto,
	nodev1.File_arcforges_node_v1_storage_proto,
	nodev1.File_arcforges_node_v1_support_proto,
	nodev1.File_arcforges_node_v1_tasks_proto,
	nodev1.File_arcforges_node_v1_toolchains_proto,
	nodev1.File_arcforges_node_v1_updates_proto,
	nodev1.File_arcforges_node_v1_workspaces_proto,
	fleetv1.File_arcforges_fleet_v1_fleet_proto,
	relayv1.File_arcforges_relay_v1_relay_proto,
	operatorv1.File_arcforges_operator_v1_operator_proto,
	operatorv1.File_arcforges_operator_v1_operator_read_proto,
}

func repositoryRoot(t *testing.T) string {
	t.Helper()
	if root := os.Getenv(rootEnv); root != "" {
		return root
	}
	directory, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if isFile(filepath.Join(directory, "fixtures", "public", "wp03-01.json")) &&
			isFile(filepath.Join(directory, "eng", "contract-packages.json")) {
			return directory
		}
		parent := filepath.Dir(directory)
		if parent == directory {
			t.Skip("the Contracts fixtures are outside the published Go module; run python eng/contracts.py go test")
		}
		directory = parent
	}
}

func isFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

// readJSON decodes a fixture with numbers kept as their literal text.
func readJSON(t *testing.T, path string, value any) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	if err := decoder.Decode(value); err != nil {
		t.Fatalf("%s: %v", path, err)
	}
}

func mustHex(t *testing.T, text string) []byte {
	t.Helper()
	data, err := hex.DecodeString(text)
	if err != nil {
		t.Fatalf("invalid hexadecimal fixture %q: %v", text, err)
	}
	return data
}

// messageType returns the generated Go type of a message of the module's files.
func messageType(t *testing.T, name string) protoreflect.MessageType {
	t.Helper()
	found, err := protoregistry.GlobalTypes.FindMessageByName(protoreflect.FullName(name))
	if err != nil {
		t.Fatalf("no generated Go message %s: %v", name, err)
	}
	if !slices.ContainsFunc(moduleFiles, func(file protoreflect.FileDescriptor) bool {
		return file.Path() == found.Descriptor().ParentFile().Path()
	}) {
		t.Fatalf("%s is not a message of the Go module's files", name)
	}
	return found
}

// marshal is the deterministic encoding (map entries in key order), as the exchange compares bytes.
func marshal(t *testing.T, message proto.Message) []byte {
	t.Helper()
	data, err := proto.MarshalOptions{Deterministic: true}.Marshal(message)
	if err != nil {
		t.Fatalf("marshal %s: %v", message.ProtoReflect().Descriptor().FullName(), err)
	}
	return data
}

// fromJSON reads a fixture's protobuf-JSON value, as the C# StructureTests do with JsonParser. Tests only: the
// bindings carry no JSON mapping (WP03.02).
func fromJSON(t *testing.T, kind protoreflect.MessageType, value any) proto.Message {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	message := kind.New().Interface()
	if err := protojson.Unmarshal(data, message); err != nil {
		t.Fatalf("%s: %v: %s", kind.Descriptor().FullName(), err, data)
	}
	return message
}

// orderedObject keeps the member order of a JSON object, which the fixture "set" edits rely on.
type orderedObject struct {
	keys   []string
	values map[string]any
}

func (o *orderedObject) UnmarshalJSON(data []byte) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	if _, err := decoder.Token(); err != nil {
		return err
	}
	o.values = map[string]any{}
	for decoder.More() {
		token, err := decoder.Token()
		if err != nil {
			return err
		}
		key := token.(string)
		var value any
		if err := decoder.Decode(&value); err != nil {
			return err
		}
		o.keys = append(o.keys, key)
		o.values[key] = value
	}
	_, err := decoder.Token()
	return err
}

// foundationFixture is wp03-01.json with the CON.02 and CON.09 additions, as the C# LoadFoundation builds it.
type foundationFixture struct {
	samples         map[string]any
	foundationTypes map[string]bool
	cases           []fixtureCase
	wireVectors     []wireVector
}

type fixtureCase struct {
	ID     string         `json:"id"`
	Target string         `json:"target"`
	Valid  bool           `json:"valid"`
	Value  any            `json:"value"`
	Sample string         `json:"sample"`
	Set    *orderedObject `json:"set"`
	Remove []string       `json:"remove"`
}

type wireVector struct {
	ID     string `json:"id"`
	Target string `json:"target"`
	Value  any    `json:"value"`
	Hex    string `json:"hex"`
}

func loadFoundation(t *testing.T, root string) foundationFixture {
	t.Helper()
	var base struct {
		Samples         map[string]any `json:"samples"`
		FoundationTypes []string       `json:"foundationTypes"`
		Cases           []fixtureCase  `json:"cases"`
		WireVectors     []wireVector   `json:"wireVectors"`
	}
	readJSON(t, filepath.Join(root, "fixtures", "public", "wp03-01.json"), &base)
	var descriptors struct {
		Exchange struct {
			Samples         map[string]any `json:"samples"`
			FoundationTypes []string       `json:"foundationTypes"`
			Cases           []fixtureCase  `json:"cases"`
		} `json:"exchange"`
	}
	readJSON(t, filepath.Join(root, "fixtures", "public", "con-02-descriptors.json"), &descriptors)
	var transfer struct {
		TransferTicket struct {
			Sample any           `json:"sample"`
			Cases  []fixtureCase `json:"cases"`
		} `json:"transferTicket"`
	}
	readJSON(t, filepath.Join(root, "fixtures", "public", "con-09-sync-transfer.json"), &transfer)
	fixture := foundationFixture{samples: base.Samples, foundationTypes: map[string]bool{}, cases: base.Cases,
		wireVectors: base.WireVectors}
	for _, name := range base.FoundationTypes {
		fixture.foundationTypes[name] = true
	}
	for name, sample := range descriptors.Exchange.Samples {
		if _, duplicate := fixture.samples[name]; duplicate {
			t.Fatalf("duplicate independent fixture %s", name)
		}
		fixture.samples[name] = sample
	}
	for _, name := range descriptors.Exchange.FoundationTypes {
		fixture.foundationTypes[name] = true
	}
	fixture.cases = append(fixture.cases, descriptors.Exchange.Cases...)
	if _, duplicate := fixture.samples["TransferTicket"]; duplicate {
		t.Fatal("duplicate independent fixture TransferTicket")
	}
	fixture.samples["TransferTicket"] = transfer.TransferTicket.Sample
	fixture.foundationTypes["TransferTicket"] = true
	fixture.cases = append(fixture.cases, transfer.TransferTicket.Cases...)
	return fixture
}

// target resolves a fixture target as the C# FoundationDescriptor does: foundation types, else content or
// descriptors.
func (f foundationFixture) target(t *testing.T, name string) protoreflect.MessageType {
	t.Helper()
	if _, ok := f.samples[name]; !ok || strings.HasPrefix(name, "$") {
		t.Fatalf("unregistered fixture target %s", name)
	}
	if f.foundationTypes[name] {
		return messageType(t, "arcforges.foundation.v1."+name)
	}
	kind := messageType(t, "arcforges.publicapi.v1."+name)
	path := kind.Descriptor().ParentFile().Path()
	if path != "arcforges/publicapi/v1/content.proto" && path != "arcforges/publicapi/v1/descriptors.proto" {
		t.Fatalf("fixture target %s is outside content.proto and descriptors.proto", name)
	}
	return kind
}

func (f foundationFixture) expand(t *testing.T, node any, stack map[string]bool) any {
	t.Helper()
	switch value := node.(type) {
	case map[string]any:
		if reference, ok := value["$ref"]; ok {
			name, isString := reference.(string)
			sample, known := f.samples[name]
			if len(value) != 1 || !isString || !known || stack[name] {
				t.Fatalf("invalid or recursive fixture reference %v", reference)
			}
			stack[name] = true
			result := f.expand(t, sample, stack)
			delete(stack, name)
			return result
		}
		result := make(map[string]any, len(value))
		for key, child := range value {
			result[key] = f.expand(t, child, stack)
		}
		return result
	case []any:
		result := make([]any, len(value))
		for index, child := range value {
			result[index] = f.expand(t, child, stack)
		}
		return result
	default:
		return value
	}
}

// materialize applies a case's sample, "set" edits (in authored order) and removals, as the C# Materialize does.
func (f foundationFixture) materialize(t *testing.T, item fixtureCase) any {
	t.Helper()
	source := item.Value
	if source == nil {
		source = f.samples[item.Sample]
	}
	value := f.expand(t, source, map[string]bool{})
	if item.Set != nil {
		for _, path := range item.Set.keys {
			parent, key := f.parent(t, value, path)
			var replacement any
			if item.Set.values[path] != nil {
				replacement = f.expand(t, item.Set.values[path], map[string]bool{})
			}
			switch container := parent.(type) {
			case []any:
				index, err := strconv.Atoi(key)
				if err != nil || index < 0 || index >= len(container) {
					t.Fatalf("%s: invalid fixture index %s", item.ID, path)
				}
				container[index] = replacement
			case map[string]any:
				container[key] = replacement
			default:
				t.Fatalf("%s: invalid fixture path %s", item.ID, path)
			}
		}
	}
	for _, path := range item.Remove {
		parent, key := f.parent(t, value, path)
		container, ok := parent.(map[string]any)
		if _, present := container[key]; !ok || !present {
			t.Fatalf("%s: unknown fixture removal path %s", item.ID, path)
		}
		delete(container, key)
	}
	return value
}

func (f foundationFixture) parent(t *testing.T, node any, path string) (any, string) {
	t.Helper()
	parts := strings.Split(path, ".")
	for _, part := range parts[:len(parts)-1] {
		switch container := node.(type) {
		case []any:
			index, err := strconv.Atoi(part)
			if err != nil || index < 0 || index >= len(container) {
				t.Fatalf("invalid fixture path %s", path)
			}
			node = container[index]
		case map[string]any:
			node = container[part]
		default:
			t.Fatalf("invalid fixture path %s", path)
		}
	}
	return node, parts[len(parts)-1]
}
