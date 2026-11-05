// SPDX-License-Identifier: Apache-2.0

package compat

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/binary"
	"encoding/hex"
	"math/big"
	"path/filepath"
	"testing"

	"google.golang.org/protobuf/encoding/protowire"
	"google.golang.org/protobuf/proto"

	fleetv1 "github.com/ArcForges/Contracts/go/arcforges/fleet/v1"
	foundationv1 "github.com/ArcForges/Contracts/go/arcforges/foundation/v1"
	nodev1 "github.com/ArcForges/Contracts/go/arcforges/node/v1"
	relayv1 "github.com/ArcForges/Contracts/go/arcforges/relay/v1"
)

// The signature domain strings of the node channel (Design 11 section 3; Plan decision PB-3), one per signature kind.
var (
	callDomain   = []byte("ArcForges relay-call v1\n")
	resultDomain = []byte("ArcForges relay-result v1\n")
	helloDomain  = []byte("ArcForges relay-hello v1\n")
	originDomain = []byte("ArcForges relay-origin v1\n")
)

type relayVectors struct {
	Audience       string            `json:"audience"`
	AudienceSHA256 string            `json:"audienceSha256"`
	Domains        map[string]string `json:"domains"`
	Keys           map[string]struct {
		Kid  string `json:"kid"`
		SPKI string `json:"spki"`
	} `json:"keys"`
	IDs        map[string]string `json:"ids"`
	RoutedCall struct {
		Frame        string  `json:"frame"`
		CallHeader   string  `json:"callHeader"`
		SigningInput string  `json:"signingInput"`
		Kid          string  `json:"kid"`
		HighS        string  `json:"highSSignature"`
		IssuedAt     []int64 `json:"issuedAt"`
		ExpiresAt    []int64 `json:"expiresAt"`
		Deadline     []int64 `json:"deadline"`
		RequestSize  uint32  `json:"requestSize"`
	} `json:"routedCall"`
	RoutedResult struct {
		Frame        string  `json:"frame"`
		SigningInput string  `json:"signingInput"`
		HighS        string  `json:"highSSignature"`
		ExecutedAt   []int64 `json:"executedAt"`
	} `json:"routedResult"`
	Hello struct {
		ChallengeFrame string   `json:"challengeFrame"`
		Nonce          string   `json:"nonce"`
		HelloFrame     string   `json:"helloFrame"`
		SigningInput   string   `json:"signingInput"`
		HighS          string   `json:"highSSignature"`
		Capabilities   []string `json:"capabilities"`
	} `json:"hello"`
	RelayClose struct {
		Frame            string `json:"frame"`
		Code             uint32 `json:"code"`
		Reason           string `json:"reason"`
		ReconnectAfterMs uint32 `json:"reconnectAfterMs"`
	} `json:"relayClose"`
	RelayAssertions []struct {
		ID                               string  `json:"id"`
		Assertion                        string  `json:"assertion"`
		SigningInput                     string  `json:"signingInput"`
		Signature                        string  `json:"signature"`
		HighS                            string  `json:"highSSignature"`
		ListNodesRequest                 string  `json:"listNodesRequest"`
		ListNodesRequestWithoutAssertion string  `json:"listNodesRequestWithoutAssertion"`
		GetNodeRequest                   string  `json:"getNodeRequest"`
		GetNodeRequestWithoutAssertion   string  `json:"getNodeRequestWithoutAssertion"`
		Method                           int32   `json:"method"`
		LocalOrigin                      int32   `json:"localOrigin"`
		TargetNodeID                     *string `json:"targetNodeId"`
		CommandID                        *string `json:"commandId"`
	} `json:"relayAssertions"`
}

func loadRelayVectors(t *testing.T) *relayVectors {
	t.Helper()
	var v relayVectors
	readJSON(t, filepath.Join(repositoryRoot(t), "fixtures", "internal", "af-ctr-05-relay-vectors.json"), &v)
	return &v
}

var p256Order, _ = new(big.Int).SetString("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)

// verifyES256 checks an IEEE P1363 ES256 signature (64 bytes, r and s in [1, n-1], low-S) over data.
func verifyES256(key *ecdsa.PublicKey, data, signature []byte) bool {
	if len(signature) != 64 {
		return false
	}
	r, s := new(big.Int).SetBytes(signature[:32]), new(big.Int).SetBytes(signature[32:])
	if r.Sign() == 0 || s.Sign() == 0 || r.Cmp(p256Order) >= 0 || s.Cmp(new(big.Int).Rsh(p256Order, 1)) > 0 {
		return false
	}
	digest := sha256.Sum256(data)
	return ecdsa.Verify(key, digest[:], r, s)
}

func publicKey(t *testing.T, v *relayVectors, name string) *ecdsa.PublicKey {
	t.Helper()
	parsed, err := x509.ParsePKIXPublicKey(mustHex(t, v.Keys[name].SPKI))
	if err != nil {
		t.Fatal(err)
	}
	return parsed.(*ecdsa.PublicKey)
}

func concat(parts ...[]byte) []byte { return bytes.Join(parts, nil) }

func canonicalInstant(value *foundationv1.Instant) []byte {
	out := binary.BigEndian.AppendUint64(nil, uint64(value.GetUnixSeconds()))
	return binary.BigEndian.AppendUint32(out, value.GetNanos())
}

func canonicalID(value *foundationv1.Id) []byte {
	if value == nil {
		return make([]byte, 16)
	}
	return value.GetValue()
}

func sameInstant(value *foundationv1.Instant, expected []int64) bool {
	return len(expected) == 2 && value.GetUnixSeconds() == expected[0] && int64(value.GetNanos()) == expected[1]
}

func idHex(value *foundationv1.Id) string { return hex.EncodeToString(value.GetValue()) }

// withoutField is a message's top-level fields in wire order, byte for byte, without every occurrence of one field.
func withoutField(t *testing.T, message []byte, drop protowire.Number) []byte {
	t.Helper()
	var out []byte
	for rest := message; len(rest) > 0; {
		number, kind, tagLength := protowire.ConsumeTag(rest)
		if tagLength < 0 {
			t.Fatal("malformed message tag")
		}
		valueLength := protowire.ConsumeFieldValue(number, kind, rest[tagLength:])
		if valueLength < 0 {
			t.Fatal("malformed message field")
		}
		if number != drop {
			out = append(out, rest[:tagLength+valueLength]...)
		}
		rest = rest[tagLength+valueLength:]
	}
	return out
}

func decode(t *testing.T, data []byte, message proto.Message) {
	t.Helper()
	if err := proto.Unmarshal(data, message); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(marshal(t, message), data) {
		t.Errorf("%T does not re-encode byte for byte", message)
	}
}

// TestRelayDomainStrings: four distinct domain strings, none a prefix of another, as the fixture and the C# cases state.
func TestRelayDomainStrings(t *testing.T) {
	v := loadRelayVectors(t)
	domains := map[string][]byte{"call": callDomain, "result": resultDomain, "hello": helloDomain, "origin": originDomain}
	lengths := map[string]int{"call": 24, "result": 26, "hello": 25, "origin": 26}
	for name, domain := range domains {
		if v.Domains[name] != string(domain) || len(domain) != lengths[name] {
			t.Errorf("%s: the domain string is %q (%d bytes)", name, v.Domains[name], len(domain))
		}
		for other, second := range domains {
			if name != other && bytes.HasPrefix(domain, second) {
				t.Errorf("%s starts with the %s domain string", name, other)
			}
		}
	}
}

// TestRelayGoldenVectors decodes the node channel's golden frames with the generated Go codecs, rebuilds every signing input
// from the decoded fields and verifies every signature; the bare bytes, another domain string, another key and a high-S
// signature are refused. tests/StructureTests/NodeChannelCases.cs checks the same bytes with the generated C# codecs.
func TestRelayGoldenVectors(t *testing.T) {
	v := loadRelayVectors(t)
	audience := mustHex(t, v.AudienceSHA256)
	if sum := sha256.Sum256([]byte(v.Audience)); !bytes.Equal(sum[:], audience) {
		t.Fatal("the audience digest")
	}
	center, node, other := publicKey(t, v, "center"), publicKey(t, v, "node"), publicKey(t, v, "otherInstallation")
	otherCenter := publicKey(t, v, "otherCenter")

	// Relay assertions.
	assertions := make([]*relayv1.RelayAssertion, 0, len(v.RelayAssertions))
	for _, vector := range v.RelayAssertions {
		assertion := &relayv1.RelayAssertion{}
		decode(t, mustHex(t, vector.Assertion), assertion)
		if idHex(assertion.GetRelayingNodeId()) != v.IDs["node"] || idHex(assertion.GetRelayingInstallationId()) != v.IDs["installation"] ||
			idHex(assertion.GetLocalSessionId()) != v.IDs["localSession"] || int32(assertion.GetMethod()) != vector.Method ||
			int32(assertion.GetLocalOrigin()) != vector.LocalOrigin {
			t.Errorf("%s: the decoded identity, method or origin", vector.ID)
		}
		if (vector.TargetNodeID == nil) != (assertion.GetTargetNodeId() == nil) || (vector.CommandID == nil) != (assertion.GetCommandId() == nil) {
			t.Errorf("%s: target or command presence", vector.ID)
		}
		signing := concat(originDomain, audience, assertion.GetRelayingNodeId().GetValue(), assertion.GetRelayingInstallationId().GetValue(),
			[]byte{byte(assertion.GetLocalOrigin())}, assertion.GetLocalSessionId().GetValue(), []byte{byte(assertion.GetMethod())},
			assertion.GetRequestSha256(), canonicalID(assertion.GetTargetNodeId()), canonicalID(assertion.GetCommandId()),
			assertion.GetRelayNonce(), canonicalInstant(assertion.GetIssuedAt()), canonicalInstant(assertion.GetExpiresAt()))
		if len(signing) != 228 || !bytes.Equal(signing, mustHex(t, vector.SigningInput)) {
			t.Errorf("%s: the canonical relay-origin bytes differ", vector.ID)
		}
		signature := assertion.GetSignature()
		if !bytes.Equal(signature, mustHex(t, vector.Signature)) || !verifyES256(node, signing, signature) {
			t.Errorf("%s: the relay assertion signature does not verify", vector.ID)
		}
		if verifyES256(node, signing[len(originDomain):], signature) || verifyES256(node, concat(callDomain, signing[len(originDomain):]), signature) ||
			verifyES256(node, signing, mustHex(t, vector.HighS)) || verifyES256(other, signing, signature) {
			t.Errorf("%s: a bare, cross-domain, high-S or other-key signature verified", vector.ID)
		}
		if vector.ListNodesRequest != "" {
			full := mustHex(t, vector.ListNodesRequest)
			request := &fleetv1.FleetServiceListNodesRequest{}
			decode(t, full, request)
			kept := withoutField(t, full, 11)
			digest := sha256.Sum256(kept)
			if !bytes.Equal(kept, mustHex(t, vector.ListNodesRequestWithoutAssertion)) || !bytes.Equal(digest[:], assertion.GetRequestSha256()) ||
				!bytes.Equal(request.GetRelayAssertion(), mustHex(t, vector.Assertion)) ||
				request.GetCaller().GetKind() != fleetv1.CallerKind_CALLER_KIND_NODE_RELAY || request.GetCaller().GetLocalOrigin() != assertion.GetLocalOrigin() {
				t.Errorf("%s: the ListNodes request digest or caller", vector.ID)
			}
		}
		if vector.GetNodeRequest != "" {
			full := mustHex(t, vector.GetNodeRequest)
			request := &fleetv1.FleetServiceGetNodeRequest{}
			decode(t, full, request)
			kept := withoutField(t, full, 12)
			digest := sha256.Sum256(kept)
			if !bytes.Equal(kept, mustHex(t, vector.GetNodeRequestWithoutAssertion)) || !bytes.Equal(digest[:], assertion.GetRequestSha256()) ||
				!bytes.Equal(request.GetRelayAssertion(), mustHex(t, vector.Assertion)) || !proto.Equal(request.GetNodeId(), assertion.GetTargetNodeId()) ||
				request.GetCaller().GetLocalOrigin() != assertion.GetLocalOrigin() {
				t.Errorf("%s: the GetNode request digest, node or caller", vector.ID)
			}
		}
		assertions = append(assertions, assertion)
	}
	if len(assertions) != 3 || assertions[1].GetTargetNodeId() != nil || assertions[2].GetMethod() != relayv1.RoutedMethod_ROUTED_METHOD_GET_NODE {
		t.Fatal("the submit, ListNodes and GetNode assertions")
	}

	// The routed call.
	frame := &relayv1.RelayFrame{}
	decode(t, mustHex(t, v.RoutedCall.Frame), frame)
	call := frame.GetCall()
	if call == nil || frame.GetFrameVersion() != 1 || frame.GetFrameSeq() != 7 {
		t.Fatal("the call frame is not RelayFrame member 23")
	}
	headerBytes := call.GetHeader().GetHeader()
	signing := concat(callDomain, headerBytes)
	if !bytes.Equal(headerBytes, mustHex(t, v.RoutedCall.CallHeader)) || !bytes.Equal(signing, mustHex(t, v.RoutedCall.SigningInput)) {
		t.Fatal("the routed-call signing input")
	}
	if !verifyES256(center, signing, call.GetHeader().GetSignature()) {
		t.Error("the routed-call signature does not verify")
	}
	for _, domain := range [][]byte{nil, resultDomain, helloDomain, originDomain} {
		if verifyES256(center, concat(domain, headerBytes), call.GetHeader().GetSignature()) {
			t.Errorf("a call signature verified under %q", domain)
		}
	}
	if verifyES256(center, signing, mustHex(t, v.RoutedCall.HighS)) || verifyES256(otherCenter, signing, call.GetHeader().GetSignature()) {
		t.Error("a high-S call signature, or another center's key, verified")
	}
	header := &relayv1.CallHeader{}
	decode(t, headerBytes, header)
	payload := call.GetPayload()
	payloadDigest := sha256.Sum256(payload)
	assertionDigest := sha256.Sum256(marshal(t, assertions[0]))
	caller := header.GetCaller()
	switch {
	case idHex(header.GetCallId()) != v.IDs["call"] || !proto.Equal(header.GetCallId(), call.GetCallId()):
		t.Error("call_id")
	case header.GetKid() != v.RoutedCall.Kid || header.GetKid() != call.GetHeader().GetKid() || call.GetHeader().GetAlgorithm() != "ES256":
		t.Error("kid and algorithm")
	case !bytes.Equal(header.GetCenterUrlSha256(), audience) || idHex(header.GetAccountId()) != v.IDs["account"] || idHex(header.GetTargetNodeId()) != v.IDs["node"]:
		t.Error("center, account and target")
	case caller.GetKind() != nodev1.CenterCallerKind_CENTER_CALLER_KIND_NODE_RELAY || caller.GetLocalOrigin() != nodev1.Origin_ORIGIN_HUMAN ||
		!proto.Equal(caller.GetRelayingNodeId(), assertions[0].GetRelayingNodeId()) || !proto.Equal(caller.GetLocalSessionId(), assertions[0].GetLocalSessionId()):
		t.Error("the center caller is not the verified assertion's")
	case header.GetMethod() != relayv1.RoutedMethod_ROUTED_METHOD_SUBMIT_NODE_TASK || !proto.Equal(header.GetCommandId(), assertions[0].GetCommandId()):
		t.Error("method and command")
	case !bytes.Equal(header.GetRequestSha256(), payloadDigest[:]) || !bytes.Equal(header.GetRequestSha256(), assertions[0].GetRequestSha256()) ||
		header.GetRequestSize() != uint32(len(payload)) || header.GetRequestSize() != v.RoutedCall.RequestSize:
		t.Error("the request digest and size")
	case !sameInstant(header.GetIssuedAt(), v.RoutedCall.IssuedAt) || !sameInstant(header.GetExpiresAt(), v.RoutedCall.ExpiresAt) ||
		!sameInstant(header.GetDeadline(), v.RoutedCall.Deadline):
		t.Error("issued, expires and deadline")
	case !bytes.Equal(header.GetRelayAssertionSha256(), assertionDigest[:]):
		t.Error("relay_assertion_sha256")
	}
	submit := &nodev1.TaskServiceSubmitTaskRequest{}
	decode(t, payload, submit)
	if !proto.Equal(submit.GetMeta().GetCommandId(), header.GetCommandId()) {
		t.Error("the payload's command ID")
	}

	// The routed result.
	frame = &relayv1.RelayFrame{}
	decode(t, mustHex(t, v.RoutedResult.Frame), frame)
	result := frame.GetCallResult()
	if result == nil {
		t.Fatal("the result frame is not RelayFrame member 24")
	}
	resultBytes := result.GetHeader().GetHeader()
	signing = concat(resultDomain, resultBytes)
	if !bytes.Equal(signing, mustHex(t, v.RoutedResult.SigningInput)) || !verifyES256(node, signing, result.GetHeader().GetSignature()) {
		t.Error("the routed-result signature")
	}
	if verifyES256(node, resultBytes, result.GetHeader().GetSignature()) || verifyES256(node, concat(callDomain, resultBytes), result.GetHeader().GetSignature()) ||
		verifyES256(other, signing, result.GetHeader().GetSignature()) || verifyES256(node, signing, mustHex(t, v.RoutedResult.HighS)) {
		t.Error("a bare, cross-domain, other-key or high-S result signature verified")
	}
	resultHeader := &relayv1.ResultHeader{}
	decode(t, resultBytes, resultHeader)
	responseDigest := sha256.Sum256(result.GetPayload())
	if resultHeader.GetOutcome() != relayv1.RoutedOutcome_ROUTED_OUTCOME_EXECUTED || idHex(resultHeader.GetNodeId()) != v.IDs["node"] ||
		!bytes.Equal(resultHeader.GetResponseSha256(), responseDigest[:]) || resultHeader.GetResponseSize() != uint32(len(result.GetPayload())) ||
		!bytes.Equal(resultHeader.GetRequestSha256(), payloadDigest[:]) || !proto.Equal(resultHeader.GetCallId(), header.GetCallId()) ||
		!sameInstant(resultHeader.GetExecutedAt(), v.RoutedResult.ExecutedAt) || result.GetHeader().Kid != nil {
		t.Error("the decoded result header")
	}
	response := &nodev1.TaskServiceSubmitTaskResponse{}
	decode(t, result.GetPayload(), response)
	if idHex(response.GetValue().GetTaskId()) != v.IDs["task"] {
		t.Error("the payload is the node.v1 response")
	}

	// The channel challenge and the proved hello.
	frame = &relayv1.RelayFrame{}
	decode(t, mustHex(t, v.Hello.ChallengeFrame), frame)
	challenge := frame.GetChallenge()
	frame = &relayv1.RelayFrame{}
	decode(t, mustHex(t, v.Hello.HelloFrame), frame)
	hello := frame.GetNodeHello()
	if challenge == nil || hello == nil || !bytes.Equal(challenge.GetNonce(), mustHex(t, v.Hello.Nonce)) || idHex(challenge.GetConnectionId()) != v.IDs["connection"] {
		t.Fatal("the challenge is not member 27 or the hello not member 10")
	}
	signing = concat(helloDomain, challenge.GetNonce(), challenge.GetConnectionId().GetValue(), audience, hello.GetNodeId().GetValue(),
		hello.GetInstallationId().GetValue())
	if len(signing) != 137 || !bytes.Equal(signing, mustHex(t, v.Hello.SigningInput)) || !verifyES256(node, signing, hello.GetHelloSignature()) {
		t.Error("the hello proof")
	}
	if verifyES256(other, signing, hello.GetHelloSignature()) || verifyES256(node, signing[len(helloDomain):], hello.GetHelloSignature()) ||
		verifyES256(node, concat(resultDomain, signing[len(helloDomain):]), hello.GetHelloSignature()) ||
		verifyES256(node, concat(originDomain, signing[len(helloDomain):]), hello.GetHelloSignature()) ||
		verifyES256(node, signing, mustHex(t, v.Hello.HighS)) {
		t.Error("another installation's key, another domain string, the bare bytes or a high-S proof verified")
	}
	if len(hello.GetCapabilities()) != len(v.Hello.Capabilities) || hello.GetCapabilities()[0] != v.Hello.Capabilities[0] {
		t.Error("the hello capabilities")
	}

	// A graceful shutdown: close code 4500 with the reconnect hint (RelayClose.reconnect_after_ms = 3).
	frame = &relayv1.RelayFrame{}
	decode(t, mustHex(t, v.RelayClose.Frame), frame)
	closing := frame.GetClose()
	if closing == nil || closing.GetCode() != v.RelayClose.Code || closing.GetReason() != v.RelayClose.Reason ||
		closing.ReconnectAfterMs == nil || closing.GetReconnectAfterMs() != v.RelayClose.ReconnectAfterMs {
		t.Error("the close frame")
	}
}
