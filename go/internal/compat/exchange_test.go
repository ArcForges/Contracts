// SPDX-License-Identifier: Apache-2.0

package compat

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
)

// exchangeEnv names the exchange directory of python eng/contracts.py go exchange, which runs the C# leg first.
const exchangeEnv = "ARCFORGES_GO_EXCHANGE"

// TestCSharpExchange is the Go leg of the C#/Go exchange: it reads what the generated C# codecs wrote for every
// reference-codec sample of every message of the module (current/) and writes the Go encoding back (go/) for the
// reference reader and the C# re-read, and it decodes the C# encoding of every positive foundation fixture case to
// the value Go reads from the same authored protobuf JSON, writing its own encoding beside it (go-<n>.bin).
//
// The bytes need not be identical: protobuf-go writes the members of a (non-synthetic) oneof after the other fields
// ("to preserve compatibility with historic wire output", internal/impl/codec_message.go), while C# writes every
// field in number order. Both orders are valid protobuf and both runtimes read either; the exchange therefore proves
// equal meaning in both directions and reports the byte-identical share.
func TestCSharpExchange(t *testing.T) {
	directory := os.Getenv(exchangeEnv)
	if directory == "" {
		t.Skip("python eng/contracts.py go exchange runs the C# leg and sets " + exchangeEnv)
	}
	listed, err := os.ReadFile(filepath.Join(directory, "messages.txt"))
	if err != nil {
		t.Fatal(err)
	}
	samples := strings.Fields(string(listed))
	output := filepath.Join(directory, "go")
	if err := os.MkdirAll(output, 0o755); err != nil {
		t.Fatal(err)
	}
	exchanged := map[protoreflect.FullName]bool{}
	for _, sample := range samples {
		name, _, _ := strings.Cut(sample, "@")
		kind := messageType(t, name)
		exchanged[kind.Descriptor().FullName()] = true
		csharp, err := os.ReadFile(filepath.Join(directory, "current", sample+".bin"))
		if err != nil {
			t.Fatal(err)
		}
		message := kind.New().Interface()
		if err := proto.Unmarshal(csharp, message); err != nil {
			t.Errorf("%s: Go cannot read the C# encoding: %v", sample, err)
			continue
		}
		if err := os.WriteFile(filepath.Join(output, sample+".bin"), marshal(t, message), 0o644); err != nil {
			t.Fatal(err)
		}
		reference, err := os.ReadFile(filepath.Join(directory, "previous", sample+".bin"))
		if err != nil {
			t.Fatal(err)
		}
		direct := kind.New().Interface()
		if err := proto.Unmarshal(reference, direct); err != nil || !proto.Equal(direct, message) {
			t.Errorf("%s: the reference bytes and the C# rewrite decode differently in Go (%v)", sample, err)
		}
	}
	var missing []string
	var walk func(protoreflect.MessageDescriptors)
	walk = func(messages protoreflect.MessageDescriptors) {
		for index := range messages.Len() {
			message := messages.Get(index)
			if message.IsMapEntry() {
				continue
			}
			if !exchanged[message.FullName()] {
				missing = append(missing, string(message.FullName()))
			}
			walk(message.Messages())
		}
	}
	for _, file := range moduleFiles {
		walk(file.Messages())
	}
	if len(missing) != 0 || len(samples) == 0 {
		t.Fatalf("messages of the Go module without an exchanged sample: %v", missing)
	}

	var index []struct {
		ID   string `json:"id"`
		Type string `json:"type"`
		JSON string `json:"json"`
		File string `json:"file"`
	}
	readJSON(t, filepath.Join(directory, "fixtures", "index.json"), &index)
	checked, identical := make([]string, 0, len(index)), 0
	for _, item := range index {
		kind := messageType(t, item.Type)
		authored := kind.New().Interface()
		if err := protojson.Unmarshal([]byte(item.JSON), authored); err != nil {
			t.Errorf("%s: %v", item.ID, err)
			continue
		}
		csharp, err := os.ReadFile(filepath.Join(directory, "fixtures", item.File))
		if err != nil {
			t.Fatal(err)
		}
		decoded := kind.New().Interface()
		if err := proto.Unmarshal(csharp, decoded); err != nil || !proto.Equal(decoded, authored) {
			t.Errorf("%s: the C# encoding decodes to another value in Go (%v)", item.ID, err)
			continue
		}
		goBytes := marshal(t, authored)
		if !bytes.Equal(marshal(t, decoded), goBytes) {
			t.Errorf("%s: Go encodes the decoded C# value and the authored value differently", item.ID)
			continue
		}
		if err := os.WriteFile(filepath.Join(directory, "fixtures", "go-"+item.File), goBytes, 0o644); err != nil {
			t.Fatal(err)
		}
		if bytes.Equal(goBytes, csharp) {
			identical++
		}
		checked = append(checked, item.ID)
	}
	data, err := json.Marshal(checked)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "fixtures", "go-checked.json"), data, 0o644); err != nil {
		t.Fatal(err)
	}
	t.Logf("Go read %d C# samples of %d messages and %d C#-encoded fixture cases (%d byte-identical with C#)",
		len(samples), len(exchanged), len(checked), identical)
}
