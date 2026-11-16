// SPDX-License-Identifier: Apache-2.0
package compat

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	foundationv1 "github.com/ArcForges/Contracts/go/arcforges/foundation/v1"
	managementv2 "github.com/ArcForges/Contracts/go/arcforges/management/v2"
	sandboxv2 "github.com/ArcForges/Contracts/go/arcforges/sandbox/v2"
	"google.golang.org/protobuf/encoding/protowire"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
)

func TestV2ContractVectors(t *testing.T) {
	data, err := os.ReadFile(filepath.Join(repositoryRoot(t), "fixtures/public/afv2-api-01.json"))
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Vectors []struct {
			Name, Type, WireHex string
			Valid               bool
		}
	}
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	for _, row := range fixture.Vectors {
		t.Run(row.Name, func(t *testing.T) {
			wire, err := hex.DecodeString(row.WireHex)
			if err != nil {
				t.Fatal(err)
			}
			var message proto.Message
			var check func() bool
			switch row.Type {
			case "NodeServiceHandshakeResponse":
				value := new(sandboxv2.NodeServiceHandshakeResponse)
				message = value
				check = func() bool { return sandboxv2.ValidateNodeServiceHandshakeResponse(value) }
			case "EnvironmentEntry":
				value := new(sandboxv2.EnvironmentEntry)
				message = value
				check = func() bool { return sandboxv2.ValidateEnvironmentEntry(value) }
			case "Capability":
				value := new(sandboxv2.Capability)
				message = value
				check = func() bool { return sandboxv2.ValidateCapability(value) }
			case "TerminalSize":
				value := new(sandboxv2.TerminalSize)
				message = value
				check = func() bool { return sandboxv2.ValidateTerminalSize(value) }
			case "RunServiceStartRequest":
				value := new(sandboxv2.RunServiceStartRequest)
				message = value
				check = func() bool { return sandboxv2.ValidateRunServiceStartRequest(value) }
			case "OutputChunk":
				value := new(sandboxv2.OutputChunk)
				message = value
				check = func() bool { return sandboxv2.ValidateOutputChunk(value) }
			case "RunServiceWriteTerminalRequest":
				value := new(sandboxv2.RunServiceWriteTerminalRequest)
				message = value
				check = func() bool { return sandboxv2.ValidateRunServiceWriteTerminalRequest(value) }
			case "RunServiceResizeTerminalRequest":
				value := new(sandboxv2.RunServiceResizeTerminalRequest)
				message = value
				check = func() bool { return sandboxv2.ValidateRunServiceResizeTerminalRequest(value) }
			case "SandboxServiceDeleteRequest":
				value := new(sandboxv2.SandboxServiceDeleteRequest)
				message = value
				check = func() bool { return sandboxv2.ValidateSandboxServiceDeleteRequest(value) }
			case "CenterControlServiceBeginConnectRequest":
				value := new(sandboxv2.CenterControlServiceBeginConnectRequest)
				message = value
				check = func() bool { return sandboxv2.ValidateCenterControlServiceBeginConnectRequest(value) }
			case "DataServiceInspectTransferRequest":
				value := new(sandboxv2.DataServiceInspectTransferRequest)
				message = value
				check = func() bool { return sandboxv2.ValidateDataServiceInspectTransferRequest(value) }
			case "Transfer":
				value := new(sandboxv2.Transfer)
				message = value
				check = func() bool { return sandboxv2.ValidateTransfer(value) }
			case "Operation":
				value := new(sandboxv2.Operation)
				message = value
				check = func() bool { return sandboxv2.ValidateOperation(value) }
			case "DeviceServiceRevokeRequest":
				value := new(managementv2.DeviceServiceRevokeRequest)
				message = value
				check = func() bool { return managementv2.ValidateDeviceServiceRevokeRequest(value) }
			default:
				t.Fatal("unregistered V2 vector type " + row.Type)
			}
			if err := proto.Unmarshal(wire, message); err != nil {
				t.Fatal(err)
			}
			if actual := check(); actual != row.Valid {
				t.Fatalf("shape=%v want=%v", actual, row.Valid)
			}
		})
	}
	for _, file := range moduleFiles {
		if file.Package() != "arcforges.sandbox.v2" && file.Package() != "arcforges.management.v2" {
			continue
		}
		for index := 0; index < file.Messages().Len(); index++ {
			descriptor := file.Messages().Get(index)
			factory := messageType(t, string(descriptor.FullName()))
			for fieldIndex := 0; fieldIndex < descriptor.Fields().Len(); fieldIndex++ {
				field := descriptor.Fields().Get(fieldIndex)
				if field.Kind() != protoreflect.EnumKind {
					continue
				}
				numbers := []int32{999}
				for enumIndex := 0; enumIndex < field.Enum().Values().Len(); enumIndex++ {
					numbers = append(numbers, int32(field.Enum().Values().Get(enumIndex).Number()))
				}
				for _, number := range numbers {
					wire := protowire.AppendTag(nil, protowire.Number(field.Number()), protowire.VarintType)
					wire = protowire.AppendVarint(wire, uint64(number))
					message := factory.New().Interface()
					if err := proto.Unmarshal(wire, message); err != nil {
						t.Fatal(err)
					}
					encoded, err := proto.Marshal(message)
					if err != nil || string(encoded) != string(wire) {
						t.Fatal("enum roundtrip " + string(field.FullName()))
					}
				}
			}
		}
	}
	var write sandboxv2.RunServiceWriteTerminalRequest
	for _, row := range fixture.Vectors {
		if row.Name == "terminal-write" {
			wire, _ := hex.DecodeString(row.WireHex)
			if err := proto.Unmarshal(wire, &write); err != nil {
				t.Fatal(err)
			}
		}
	}
	now := &foundationv1.Instant{UnixSeconds: proto.Int64(-1), Nanos: proto.Uint32(0)}
	if !sandboxv2.CanAdmitWrite(&write, proto.Clone(write.Lease).(*sandboxv2.TerminalLease), "run-epoch", 0, now) {
		t.Fatal("current writer next sequence")
	}
	if sandboxv2.CanAdmitWrite(&write, write.Lease, "run-epoch", 1, now) {
		t.Fatal("consumed input cannot become new after ack eviction")
	}
	stale := proto.Clone(write.Lease).(*sandboxv2.TerminalLease)
	stale.Generation = proto.Uint64(stale.GetGeneration() + 1)
	if sandboxv2.CanAdmitWrite(&write, stale, "run-epoch", 0, now) || sandboxv2.CanAdmitWrite(&write, write.Lease, "new-epoch", 0, now) {
		t.Fatal("stale lease authority")
	}
	now.UnixSeconds = proto.Int64(1)
	if sandboxv2.CanAdmitWrite(&write, write.Lease, "run-epoch", 0, now) {
		t.Fatal("expired lease")
	}
	countPolicies := 0
	checkPolicy := func(binding, kind string, localOnly, ownerEpoch bool) {
		countPolicies++
		if kind == "transient_terminal" && (!localOnly || ownerEpoch) {
			t.Fatal("transient terminal authority")
		}
		if kind == "durable_node" && !ownerEpoch {
			t.Fatal("durable epoch missing")
		}
		if strings.Contains(binding, "CenterControlService/") && !localOnly {
			t.Fatal("Center control locality")
		}
		if strings.HasSuffix(binding, "/InspectTransfer") && kind != "read" {
			t.Fatal("progress cannot replay creation")
		}
	}
	for _, method := range sandboxv2.MethodPolicies() {
		checkPolicy(method.Binding, method.Kind, method.LocalOnly, method.OwnerEpoch)
	}
	for _, method := range managementv2.MethodPolicies() {
		checkPolicy(method.Binding, method.Kind, method.LocalOnly, method.OwnerEpoch)
	}
	if countPolicies != 42 {
		t.Fatal("V2 method inventory")
	}
	if _, err := sandboxv2.DecodeRunServiceStartRequest(make([]byte, 1048577)); !errors.Is(err, sandboxv2.ErrWireTooLarge) {
		t.Fatal("unary ceiling")
	}
	if _, err := sandboxv2.DecodeDataServiceWriteImportRequest(make([]byte, 2097153)); !errors.Is(err, sandboxv2.ErrWireTooLarge) {
		t.Fatal("transfer ceiling")
	}
	unknown := []byte{0xc0, 0xde, 0x1f, 0x37}
	value, err := sandboxv2.DecodeTerminalSize(unknown)
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := sandboxv2.EncodeTerminalSize(value)
	if err != nil || string(encoded) != string(unknown) {
		t.Fatal("V2 unknown read preservation")
	}
}
