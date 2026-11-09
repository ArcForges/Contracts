// SPDX-License-Identifier: Apache-2.0

package compat

import (
	"bytes"
	"crypto/sha256"
	"testing"

	"google.golang.org/protobuf/proto"

	fleetv1 "github.com/ArcForges/Contracts/go/arcforges/fleet/v1"
	foundationv1 "github.com/ArcForges/Contracts/go/arcforges/foundation/v1"
	nodev1 "github.com/ArcForges/Contracts/go/arcforges/node/v1"
)

// Fixed protobuf-wire oracles are constructed independently from field numbers and wire types in
// node/v1/files.proto and fleet/v1/fleet.proto. The response oracle uses the C# generated codec's
// field-number order (value before audit). Go may emit a non-synthetic oneof after other fields,
// so that response is checked by decoded meaning, not by requiring identical re-encoding.
// These vectors check codecs only. Go codecs do not enforce shape, permissions, signed assertions,
// filesystem safety, or effects. The fleet assertion is synthetic and is not an authentic signature.
const (
	fileIDHex           = "00112233445566778899aabbccddeeff"
	filePathWire        = "0a120a1000112233445566778899aabbccddeeff120a7372632fc3a92e747874"
	fileReadWire        = "52200a120a1000112233445566778899aabbccddeeff120a7372632fc3a92e74787458006011"
	fileWriteAbsentWire = "0a280a120a1000112233445566778899aabbccddeeff1a120a1000112233445566778899aabbccddeeff" +
		"52200a120a1000112233445566778899aabbccddeeff120a7372632fc3a92e7478745a006801"
	fileWriteHashWire = "0a280a120a1000112233445566778899aabbccddeeff1a120a1000112233445566778899aabbccddeeff" +
		"52200a120a1000112233445566778899aabbccddeeff120a7372632fc3a92e7478745a006220" +
		"cba06b5736faf67e54b07b561eae94395e774c517a7d910a54369e1263ccfbd4"
	fileAuditWire               = "0a2a080410091a2028ec2d1189959004112bf8b746d6c12ceceb4ac4d859c82ededd334b16f49aa5204b2802"
	fileReadValueWire           = "520348690a5800600368017220c01a4cfa25cb895cdd0bb25181ba9c1622e93895a6de6f533a7299f70d6b0cfb7803"
	fileResponseCSharpOrderWire = "122f" + fileReadValueWire + "522c" + fileAuditWire
	fileFleetWire               = "52120a1000112233445566778899aabbccddeeff5a18080212120a1000112233445566778899aabbccddeeff1801" +
		"6226" + fileReadWire + "6a015a"
)

func fileWireOracle(t *testing.T, expected proto.Message, wireHex string) {
	t.Helper()
	wire := mustHex(t, wireHex)
	decoded := expected.ProtoReflect().Type().New().Interface()
	if err := proto.Unmarshal(wire, decoded); err != nil {
		t.Fatalf("%T: cannot decode fixed wire: %v", expected, err)
	}
	if !proto.Equal(decoded, expected) {
		t.Fatalf("%T: fixed wire decodes to %v; want %v", expected, decoded, expected)
	}
	got, err := proto.MarshalOptions{Deterministic: true}.Marshal(expected)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, wire) {
		t.Fatalf("%T: generated Go encoded %x; fixed wire is %x", expected, got, wire)
	}
}

func TestCtr06FileWireOracles(t *testing.T) {
	id := &foundationv1.Id{Value: mustHex(t, fileIDHex)}
	path := &nodev1.FilePath{WorkspaceId: id, Path: proto.String("src/é.txt")}
	read := &nodev1.FileServiceReadFileRequest{Path: path, Offset: proto.Uint64(0), Length: proto.Uint64(17)}
	meta := &foundationv1.RequestMeta{CommandId: id, CorrelationId: id}

	t.Run("unicode-path-and-present-zero", func(t *testing.T) {
		fileWireOracle(t, path, filePathWire)
		fileWireOracle(t, read, fileReadWire)
		var decoded nodev1.FileServiceReadFileRequest
		if err := proto.Unmarshal(mustHex(t, fileReadWire), &decoded); err != nil {
			t.Fatal(err)
		}
		offsetField := decoded.ProtoReflect().Descriptor().Fields().ByNumber(11)
		if !decoded.ProtoReflect().Has(offsetField) || decoded.GetOffset() != 0 || decoded.GetPath().GetPath() != "src/é.txt" {
			t.Fatal("the present zero offset or UTF-8 path was not retained")
		}
	})

	t.Run("write-oneof-and-empty-data", func(t *testing.T) {
		absent := &nodev1.FileServiceWriteFileRequest{
			Meta: meta, Path: path, Data: []byte{},
			Precondition: &nodev1.FileServiceWriteFileRequest_ExpectedAbsent{ExpectedAbsent: true},
		}
		oldDigest := sha256.Sum256([]byte("old"))
		hash := &nodev1.FileServiceWriteFileRequest{
			Meta: meta, Path: path, Data: []byte{},
			Precondition: &nodev1.FileServiceWriteFileRequest_ExpectedSha256{ExpectedSha256: oldDigest[:]},
		}
		fileWireOracle(t, absent, fileWriteAbsentWire)
		fileWireOracle(t, hash, fileWriteHashWire)
		var decoded nodev1.FileServiceWriteFileRequest
		if err := proto.Unmarshal(mustHex(t, fileWriteAbsentWire), &decoded); err != nil {
			t.Fatal(err)
		}
		dataField := decoded.ProtoReflect().Descriptor().Fields().ByNumber(11)
		if !decoded.ProtoReflect().Has(dataField) || len(decoded.GetData()) != 0 {
			t.Fatal("present empty write data lost its presence")
		}

		// An encoded false arm is representable by protobuf but is invalid under the separate
		// contract shape rules. A codec test must not claim that it rejects the invalid value.
		falseWire := bytes.Clone(mustHex(t, fileWriteAbsentWire))
		falseWire[len(falseWire)-1] = 0
		if err := proto.Unmarshal(falseWire, &decoded); err != nil {
			t.Fatal(err)
		}
		arm, ok := decoded.GetPrecondition().(*nodev1.FileServiceWriteFileRequest_ExpectedAbsent)
		if !ok || arm.ExpectedAbsent {
			t.Fatal("present false oneof arm did not survive decoding")
		}
		encoded, err := proto.MarshalOptions{Deterministic: true}.Marshal(&decoded)
		if err != nil || !bytes.Equal(encoded, falseWire) {
			t.Fatalf("present false oneof arm did not re-encode: %v", err)
		}

		// If a wire carries both arms, protobuf's last arm wins; shape/policy checks are separate.
		combined := append(bytes.Clone(mustHex(t, fileWriteAbsentWire)), mustHex(t,
			"6220cba06b5736faf67e54b07b561eae94395e774c517a7d910a54369e1263ccfbd4")...)
		if err := proto.Unmarshal(combined, &decoded); err != nil {
			t.Fatal(err)
		}
		if _, ok := decoded.GetPrecondition().(*nodev1.FileServiceWriteFileRequest_ExpectedSha256); !ok {
			t.Fatal("last oneof hash arm did not replace expected_absent")
		}
	})

	t.Run("read-value-and-audit", func(t *testing.T) {
		readHash := sha256.Sum256([]byte("Hi\n"))
		value := &nodev1.FileServiceReadFileValue{
			Data: []byte("Hi\n"), Offset: proto.Uint64(0), NextOffset: proto.Uint64(3), Eof: proto.Bool(true),
			Sha256: readHash[:], FileSize: proto.Uint64(3),
		}
		audit := &nodev1.FileAuditMetadata{Observations: []*nodev1.FileAuditObservation{{
			Kind: nodev1.FileAuditKind_FILE_AUDIT_KIND_SEARCH_TRANSCRIPT.Enum(), SizeBytes: proto.Uint64(9),
			Sha256:           mustHex(t, "28ec2d1189959004112bf8b746d6c12ceceb4ac4d859c82ededd334b16f49aa5"),
			DigestInputBytes: proto.Uint64(75), ItemCount: proto.Uint32(2),
		}}}
		fileWireOracle(t, value, fileReadValueWire)
		fileWireOracle(t, audit, fileAuditWire)

		want := &nodev1.FileServiceReadFileResponse{
			Outcome: &nodev1.FileServiceReadFileResponse_Value{Value: value}, Audit: audit,
		}
		var decoded nodev1.FileServiceReadFileResponse
		if err := proto.Unmarshal(mustHex(t, fileResponseCSharpOrderWire), &decoded); err != nil {
			t.Fatal(err)
		}
		if !proto.Equal(&decoded, want) {
			t.Fatal("C# field-order-shaped response decoded to a different value")
		}
		goWire, err := proto.MarshalOptions{Deterministic: true}.Marshal(&decoded)
		if err != nil {
			t.Fatal(err)
		}
		var roundTrip nodev1.FileServiceReadFileResponse
		if err := proto.Unmarshal(goWire, &roundTrip); err != nil || !proto.Equal(&roundTrip, want) {
			t.Fatalf("Go response did not round-trip semantically: %v", err)
		}
	})

	t.Run("fleet-envelope", func(t *testing.T) {
		fleet := &fleetv1.FleetServiceReadNodeFileRequest{
			NodeId: id,
			Caller: &fleetv1.RoutedCaller{
				Kind: fleetv1.CallerKind_CALLER_KIND_NODE_RELAY.Enum(), RelayingNodeId: id,
				LocalOrigin: nodev1.Origin_ORIGIN_HUMAN.Enum(),
			},
			Request: mustHex(t, fileReadWire), RelayAssertion: []byte{0x5a},
		}
		fileWireOracle(t, fleet, fileFleetWire)
		var decoded fleetv1.FleetServiceReadNodeFileRequest
		if err := proto.Unmarshal(mustHex(t, fileFleetWire), &decoded); err != nil {
			t.Fatal(err)
		}
		var inner nodev1.FileServiceReadFileRequest
		if err := proto.Unmarshal(decoded.GetRequest(), &inner); err != nil || !proto.Equal(&inner, read) {
			t.Fatalf("fleet envelope did not carry the exact encoded read request: %v", err)
		}
	})
}
