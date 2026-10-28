// SPDX-License-Identifier: Apache-2.0

package compat

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"connectrpc.com/connect/v2"
	"connectrpc.com/connect/v2/connecthttp"
	"connectrpc.com/connect/v2/connectproto"
	"google.golang.org/protobuf/proto"

	foundationv1 "github.com/ArcForges/Contracts/go/arcforges/foundation/v1"
	hellov1 "github.com/ArcForges/Contracts/go/arcforges/hello/v1"
	"github.com/ArcForges/Contracts/go/arcforges/hello/v1/hellov1connect"
)

// arcErrorType is the Connect error-detail type of foundation.v1 ArcError: its fully-qualified message name.
const arcErrorType = "arcforges.foundation.v1.ArcError"

// helloHandler is a test implementation of the generated HelloService handler with the C# HelloHost behaviour
// (fixtures/public/hello.json), plus failures selected by name for the error-detail transport test.
type helloHandler struct {
	invalidName *connect.Error
	failures    map[string]*connect.Error
}

func (h helloHandler) SayHello(_ context.Context, request *hellov1.SayHelloRequest) (*hellov1.SayHelloResponse, error) {
	if failure, ok := h.failures[request.GetName()]; ok {
		return nil, failure
	}
	if request.GetName() == "" {
		return nil, h.invalidName
	}
	return &hellov1.SayHelloResponse{Message: "Hello, " + request.GetName() + "!"}, nil
}

type protocol struct {
	name    string
	options []connecthttp.Option
}

// protocols are the three Connect-go protocols; every client and the handler use the binary protobuf codec only
// (WP03.02: no protobuf JSON mapping on the wire).
var protocols = []protocol{
	{"connect", nil},
	{"grpc", []connecthttp.Option{connecthttp.WithGRPC()}},
	{"grpc-web", []connecthttp.Option{connecthttp.WithGRPCWeb()}},
}

func binaryOnly() connecthttp.Option {
	return connecthttp.WithCodecs(connectproto.NewBinaryCodec())
}

// startHello serves the generated handler over HTTP/2 with TLS (gRPC needs HTTP/2) on a loopback test server.
func startHello(t *testing.T, handler hellov1connect.HelloServiceHandler) *httptest.Server {
	t.Helper()
	server := connect.NewServer()
	hellov1connect.RegisterHelloServiceHandler(server, handler)
	mux := http.NewServeMux()
	connecthttp.Mount(mux, server, binaryOnly())
	httpServer := httptest.NewUnstartedServer(mux)
	httpServer.EnableHTTP2 = true
	httpServer.StartTLS()
	t.Cleanup(httpServer.Close)
	return httpServer
}

func helloClient(server *httptest.Server, options ...connecthttp.Option) hellov1connect.HelloServiceClient {
	transport := connecthttp.NewTransport(server.Client(), server.URL, options...)
	return hellov1connect.NewHelloServiceClient(connect.NewClient(transport))
}

func arcErrorDetail(t *testing.T, arc *foundationv1.ArcError) *connect.ErrorDetail {
	t.Helper()
	detail, err := connectproto.NewErrorDetail(arc)
	if err != nil {
		t.Fatal(err)
	}
	if detail.Type != arcErrorType {
		t.Fatalf("ArcError detail type %q", detail.Type)
	}
	return detail
}

// receivedArcError decodes the single ArcError detail of a Connect error from its type name and bytes, without a
// type registry lookup.
func receivedArcError(t *testing.T, err error) (*connect.Error, *foundationv1.ArcError) {
	t.Helper()
	var connectError *connect.Error
	if !errors.As(err, &connectError) {
		t.Fatalf("expected a Connect error, got %v", err)
	}
	details := connectError.Details()
	if len(details) != 1 || details[0].Type != arcErrorType {
		t.Fatalf("expected one %s detail, got %d", arcErrorType, len(details))
	}
	var arc foundationv1.ArcError
	if err := proto.Unmarshal(details[0].Value, &arc); err != nil {
		t.Fatal(err)
	}
	return connectError, &arc
}

// TestHelloOverConnect runs the fixtures/public/hello.json cases through the generated Connect client and handler
// over the Connect, gRPC and gRPC-Web protocols, including the INVALID_ARGUMENT empty name with its ArcError detail.
func TestHelloOverConnect(t *testing.T) {
	root := repositoryRoot(t)
	var fixture struct {
		Cases []struct {
			Name    string `json:"name"`
			Message string `json:"message"`
		} `json:"cases"`
		EmptyNameStatus string `json:"emptyNameStatus"`
	}
	readJSON(t, filepath.Join(root, "fixtures", "public", "hello.json"), &fixture)
	if fixture.EmptyNameStatus != "INVALID_ARGUMENT" || len(fixture.Cases) == 0 {
		t.Fatalf("unexpected hello fixture %+v", fixture)
	}
	invalid := &foundationv1.ArcError{
		Code: proto.String("invalid_argument"), Category: foundationv1.ErrorCategory_ERROR_CATEGORY_VALIDATION.Enum(),
		MessageKey: proto.String("error.validation.invalid_argument"),
		Retry:      &foundationv1.RetryAdvice{Mode: foundationv1.RetryMode_RETRY_MODE_NEVER.Enum()},
		Effect:     foundationv1.EffectCertainty_EFFECT_CERTAINTY_DID_NOT_HAPPEN.Enum(),
		Details: &foundationv1.ErrorDetails{Detail: &foundationv1.ErrorDetails_State{
			State: &foundationv1.StateFailure{Reason: proto.String("name")}}},
	}
	server := startHello(t, helloHandler{
		invalidName: connect.NewError(connect.CodeInvalidArgument, "name must not be empty").
			WithDetail(arcErrorDetail(t, invalid)),
	})
	for _, protocol := range protocols {
		client := helloClient(server, append([]connecthttp.Option{binaryOnly()}, protocol.options...)...)
		for _, item := range fixture.Cases {
			response, err := client.SayHello(t.Context(), &hellov1.SayHelloRequest{Name: item.Name})
			if err != nil || response.GetMessage() != item.Message {
				t.Errorf("%s: SayHello(%q) = %q, %v; want %q", protocol.name, item.Name, response.GetMessage(), err,
					item.Message)
			}
		}
		_, err := client.SayHello(t.Context(), &hellov1.SayHelloRequest{})
		if connect.CodeOf(err) != connect.CodeInvalidArgument {
			t.Fatalf("%s: empty name returned %v", protocol.name, err)
		}
		if _, arc := receivedArcError(t, err); !proto.Equal(arc, invalid) {
			t.Errorf("%s: the ArcError detail changed in transit", protocol.name)
		}
	}
	// A client that sends protobuf JSON is refused by the binary-only handler.
	jsonClient := helloClient(server, connecthttp.WithProtoJSON())
	if _, err := jsonClient.SayHello(t.Context(), &hellov1.SayHelloRequest{Name: "World"}); err == nil {
		t.Fatal("the binary-only handler accepted protobuf JSON")
	}
}

type catalogueEntry struct {
	Category   string   `json:"category"`
	Code       string   `json:"code"`
	MessageKey string   `json:"messageKey"`
	RetryModes []string `json:"retryModes"`
	Effects    []string `json:"effects"`
	Details    string   `json:"details"`
}

func enumValue(t *testing.T, values map[string]int32, prefix, name string) int32 {
	t.Helper()
	value, ok := values[prefix+name]
	if !ok || value == 0 {
		t.Fatalf("no generated enum value %s%s", prefix, name)
	}
	return value
}

// TestErrorCatalogueAsConnectDetails maps every code of the AF-CON-01 error catalogue, with each of its retry modes
// and effects, to a foundation.v1 ArcError, attaches it to a Connect error and checks that the client receives the
// same Connect code and the same ArcError over the Connect, gRPC and gRPC-Web protocols. The design returns ArcError
// in the response outcome and defines no category-to-Connect-code table, so the test sends every Connect error code
// in turn: the code and the detail travel independently.
func TestErrorCatalogueAsConnectDetails(t *testing.T) {
	root := repositoryRoot(t)
	var catalogue struct {
		MessageKey string           `json:"messageKey"`
		Codes      []catalogueEntry `json:"codes"`
	}
	readJSON(t, filepath.Join(root, "fixtures", "public", "af-con-01-error-catalogue.json"), &catalogue)
	if catalogue.MessageKey != "error.<category>.<code>" || len(catalogue.Codes) < 60 {
		t.Fatalf("unexpected error catalogue (%d codes)", len(catalogue.Codes))
	}
	codes := []connect.Code{connect.CodeCanceled, connect.CodeUnknown, connect.CodeInvalidArgument,
		connect.CodeDeadlineExceeded, connect.CodeNotFound, connect.CodeAlreadyExists, connect.CodePermissionDenied,
		connect.CodeResourceExhausted, connect.CodeFailedPrecondition, connect.CodeAborted, connect.CodeOutOfRange,
		connect.CodeUnimplemented, connect.CodeInternal, connect.CodeUnavailable, connect.CodeDataLoss,
		connect.CodeUnauthenticated}
	type failure struct {
		code connect.Code
		arc  *foundationv1.ArcError
	}
	failures := map[string]failure{}
	errorsByName := map[string]*connect.Error{}
	for _, entry := range catalogue.Codes {
		category := foundationv1.ErrorCategory(enumValue(t, foundationv1.ErrorCategory_value, "ERROR_CATEGORY_",
			entry.Category))
		if key := "error." + strings.ToLower(entry.Category) + "." + entry.Code; key != entry.MessageKey {
			t.Fatalf("%s/%s: message key %s differs from %s", entry.Category, entry.Code, entry.MessageKey, key)
		}
		for _, modeName := range entry.RetryModes {
			for _, effectName := range entry.Effects {
				index := len(failures)
				arc := &foundationv1.ArcError{
					Code: proto.String(entry.Code), Category: category.Enum(), MessageKey: proto.String(entry.MessageKey),
					Retry: &foundationv1.RetryAdvice{Mode: foundationv1.RetryMode(enumValue(t,
						foundationv1.RetryMode_value, "RETRY_MODE_", modeName)).Enum()},
					Effect: foundationv1.EffectCertainty(enumValue(t, foundationv1.EffectCertainty_value,
						"EFFECT_CERTAINTY_", effectName)).Enum(),
					CorrelationId: &foundationv1.Id{Value: []byte(fmt.Sprintf("%016x", index))},
					Details: &foundationv1.ErrorDetails{Detail: &foundationv1.ErrorDetails_State{
						State: &foundationv1.StateFailure{State: proto.String(entry.Category),
							Reason: proto.String(entry.Details)}}},
				}
				name := fmt.Sprintf("%s/%s/%s/%s", entry.Category, entry.Code, modeName, effectName)
				code := codes[index%len(codes)]
				failures[name] = failure{code, arc}
				errorsByName[name] = connect.NewError(code, entry.MessageKey).WithDetail(arcErrorDetail(t, arc))
			}
		}
	}
	server := startHello(t, helloHandler{failures: errorsByName})
	for _, protocol := range protocols {
		client := helloClient(server, append([]connecthttp.Option{binaryOnly()}, protocol.options...)...)
		for name, want := range failures {
			_, err := client.SayHello(t.Context(), &hellov1.SayHelloRequest{Name: name})
			if connect.CodeOf(err) != want.code {
				t.Errorf("%s %s: code %v, want %v", protocol.name, name, connect.CodeOf(err), want.code)
				continue
			}
			received, arc := receivedArcError(t, err)
			if !proto.Equal(arc, want.arc) || received.Message() != want.arc.GetMessageKey() {
				t.Errorf("%s %s: the ArcError detail or message changed in transit", protocol.name, name)
			}
		}
	}
	t.Logf("%d catalogue ArcErrors crossed Connect, gRPC and gRPC-Web as error details", len(failures))
}
