package io.github.arcforges.contracts.hello.v1;

import static io.grpc.MethodDescriptor.generateFullMethodName;

/**
 * <pre>
 * Packaging and transport demonstration, not a product API.
 * </pre>
 */
@io.grpc.stub.annotations.GrpcGenerated
public final class HelloServiceGrpc {

  private HelloServiceGrpc() {}

  public static final java.lang.String SERVICE_NAME = "arcforges.hello.v1.HelloService";

  // Static method descriptors that strictly reflect the proto.
  private static volatile io.grpc.MethodDescriptor<io.github.arcforges.contracts.hello.v1.SayHelloRequest,
      io.github.arcforges.contracts.hello.v1.SayHelloResponse> getSayHelloMethod;

  @io.grpc.stub.annotations.RpcMethod(
      fullMethodName = SERVICE_NAME + '/' + "SayHello",
      requestType = io.github.arcforges.contracts.hello.v1.SayHelloRequest.class,
      responseType = io.github.arcforges.contracts.hello.v1.SayHelloResponse.class,
      methodType = io.grpc.MethodDescriptor.MethodType.UNARY)
  public static io.grpc.MethodDescriptor<io.github.arcforges.contracts.hello.v1.SayHelloRequest,
      io.github.arcforges.contracts.hello.v1.SayHelloResponse> getSayHelloMethod() {
    io.grpc.MethodDescriptor<io.github.arcforges.contracts.hello.v1.SayHelloRequest, io.github.arcforges.contracts.hello.v1.SayHelloResponse> getSayHelloMethod;
    if ((getSayHelloMethod = HelloServiceGrpc.getSayHelloMethod) == null) {
      synchronized (HelloServiceGrpc.class) {
        if ((getSayHelloMethod = HelloServiceGrpc.getSayHelloMethod) == null) {
          HelloServiceGrpc.getSayHelloMethod = getSayHelloMethod =
              io.grpc.MethodDescriptor.<io.github.arcforges.contracts.hello.v1.SayHelloRequest, io.github.arcforges.contracts.hello.v1.SayHelloResponse>newBuilder()
              .setType(io.grpc.MethodDescriptor.MethodType.UNARY)
              .setFullMethodName(generateFullMethodName(SERVICE_NAME, "SayHello"))
              .setSampledToLocalTracing(true)
              .setRequestMarshaller(io.grpc.protobuf.lite.ProtoLiteUtils.marshaller(
                  io.github.arcforges.contracts.hello.v1.SayHelloRequest.getDefaultInstance()))
              .setResponseMarshaller(io.grpc.protobuf.lite.ProtoLiteUtils.marshaller(
                  io.github.arcforges.contracts.hello.v1.SayHelloResponse.getDefaultInstance()))
              .build();
        }
      }
    }
    return getSayHelloMethod;
  }

  /**
   * Creates a new async stub that supports all call types for the service
   */
  public static HelloServiceStub newStub(io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<HelloServiceStub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<HelloServiceStub>() {
        @java.lang.Override
        public HelloServiceStub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new HelloServiceStub(channel, callOptions);
        }
      };
    return HelloServiceStub.newStub(factory, channel);
  }

  /**
   * Creates a new blocking-style stub that supports all types of calls on the service
   */
  public static HelloServiceBlockingV2Stub newBlockingV2Stub(
      io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<HelloServiceBlockingV2Stub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<HelloServiceBlockingV2Stub>() {
        @java.lang.Override
        public HelloServiceBlockingV2Stub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new HelloServiceBlockingV2Stub(channel, callOptions);
        }
      };
    return HelloServiceBlockingV2Stub.newStub(factory, channel);
  }

  /**
   * Creates a new blocking-style stub that supports unary and streaming output calls on the service
   */
  public static HelloServiceBlockingStub newBlockingStub(
      io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<HelloServiceBlockingStub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<HelloServiceBlockingStub>() {
        @java.lang.Override
        public HelloServiceBlockingStub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new HelloServiceBlockingStub(channel, callOptions);
        }
      };
    return HelloServiceBlockingStub.newStub(factory, channel);
  }

  /**
   * Creates a new ListenableFuture-style stub that supports unary calls on the service
   */
  public static HelloServiceFutureStub newFutureStub(
      io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<HelloServiceFutureStub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<HelloServiceFutureStub>() {
        @java.lang.Override
        public HelloServiceFutureStub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new HelloServiceFutureStub(channel, callOptions);
        }
      };
    return HelloServiceFutureStub.newStub(factory, channel);
  }

  /**
   * <pre>
   * Packaging and transport demonstration, not a product API.
   * </pre>
   */
  public interface AsyncService {

    /**
     * <pre>
     * Returns "Hello, &lt;name&gt;!". An empty name returns INVALID_ARGUMENT.
     * </pre>
     */
    default void sayHello(io.github.arcforges.contracts.hello.v1.SayHelloRequest request,
        io.grpc.stub.StreamObserver<io.github.arcforges.contracts.hello.v1.SayHelloResponse> responseObserver) {
      io.grpc.stub.ServerCalls.asyncUnimplementedUnaryCall(getSayHelloMethod(), responseObserver);
    }
  }

  /**
   * Base class for the server implementation of the service HelloService.
   * <pre>
   * Packaging and transport demonstration, not a product API.
   * </pre>
   */
  public static abstract class HelloServiceImplBase
      implements io.grpc.BindableService, AsyncService {

    @java.lang.Override public final io.grpc.ServerServiceDefinition bindService() {
      return HelloServiceGrpc.bindService(this);
    }
  }

  /**
   * A stub to allow clients to do asynchronous rpc calls to service HelloService.
   * <pre>
   * Packaging and transport demonstration, not a product API.
   * </pre>
   */
  public static final class HelloServiceStub
      extends io.grpc.stub.AbstractAsyncStub<HelloServiceStub> {
    private HelloServiceStub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected HelloServiceStub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new HelloServiceStub(channel, callOptions);
    }

    /**
     * <pre>
     * Returns "Hello, &lt;name&gt;!". An empty name returns INVALID_ARGUMENT.
     * </pre>
     */
    public void sayHello(io.github.arcforges.contracts.hello.v1.SayHelloRequest request,
        io.grpc.stub.StreamObserver<io.github.arcforges.contracts.hello.v1.SayHelloResponse> responseObserver) {
      io.grpc.stub.ClientCalls.asyncUnaryCall(
          getChannel().newCall(getSayHelloMethod(), getCallOptions()), request, responseObserver);
    }
  }

  /**
   * A stub to allow clients to do synchronous rpc calls to service HelloService.
   * <pre>
   * Packaging and transport demonstration, not a product API.
   * </pre>
   */
  public static final class HelloServiceBlockingV2Stub
      extends io.grpc.stub.AbstractBlockingStub<HelloServiceBlockingV2Stub> {
    private HelloServiceBlockingV2Stub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected HelloServiceBlockingV2Stub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new HelloServiceBlockingV2Stub(channel, callOptions);
    }

    /**
     * <pre>
     * Returns "Hello, &lt;name&gt;!". An empty name returns INVALID_ARGUMENT.
     * </pre>
     */
    public io.github.arcforges.contracts.hello.v1.SayHelloResponse sayHello(io.github.arcforges.contracts.hello.v1.SayHelloRequest request) throws io.grpc.StatusException {
      return io.grpc.stub.ClientCalls.blockingV2UnaryCall(
          getChannel(), getSayHelloMethod(), getCallOptions(), request);
    }
  }

  /**
   * A stub to allow clients to do limited synchronous rpc calls to service HelloService.
   * <pre>
   * Packaging and transport demonstration, not a product API.
   * </pre>
   */
  public static final class HelloServiceBlockingStub
      extends io.grpc.stub.AbstractBlockingStub<HelloServiceBlockingStub> {
    private HelloServiceBlockingStub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected HelloServiceBlockingStub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new HelloServiceBlockingStub(channel, callOptions);
    }

    /**
     * <pre>
     * Returns "Hello, &lt;name&gt;!". An empty name returns INVALID_ARGUMENT.
     * </pre>
     */
    public io.github.arcforges.contracts.hello.v1.SayHelloResponse sayHello(io.github.arcforges.contracts.hello.v1.SayHelloRequest request) {
      return io.grpc.stub.ClientCalls.blockingUnaryCall(
          getChannel(), getSayHelloMethod(), getCallOptions(), request);
    }
  }

  /**
   * A stub to allow clients to do ListenableFuture-style rpc calls to service HelloService.
   * <pre>
   * Packaging and transport demonstration, not a product API.
   * </pre>
   */
  public static final class HelloServiceFutureStub
      extends io.grpc.stub.AbstractFutureStub<HelloServiceFutureStub> {
    private HelloServiceFutureStub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected HelloServiceFutureStub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new HelloServiceFutureStub(channel, callOptions);
    }

    /**
     * <pre>
     * Returns "Hello, &lt;name&gt;!". An empty name returns INVALID_ARGUMENT.
     * </pre>
     */
    public com.google.common.util.concurrent.ListenableFuture<io.github.arcforges.contracts.hello.v1.SayHelloResponse> sayHello(
        io.github.arcforges.contracts.hello.v1.SayHelloRequest request) {
      return io.grpc.stub.ClientCalls.futureUnaryCall(
          getChannel().newCall(getSayHelloMethod(), getCallOptions()), request);
    }
  }

  private static final int METHODID_SAY_HELLO = 0;

  private static final class MethodHandlers<Req, Resp> implements
      io.grpc.stub.ServerCalls.UnaryMethod<Req, Resp>,
      io.grpc.stub.ServerCalls.ServerStreamingMethod<Req, Resp>,
      io.grpc.stub.ServerCalls.ClientStreamingMethod<Req, Resp>,
      io.grpc.stub.ServerCalls.BidiStreamingMethod<Req, Resp> {
    private final AsyncService serviceImpl;
    private final int methodId;

    MethodHandlers(AsyncService serviceImpl, int methodId) {
      this.serviceImpl = serviceImpl;
      this.methodId = methodId;
    }

    @java.lang.Override
    @java.lang.SuppressWarnings("unchecked")
    public void invoke(Req request, io.grpc.stub.StreamObserver<Resp> responseObserver) {
      switch (methodId) {
        case METHODID_SAY_HELLO:
          serviceImpl.sayHello((io.github.arcforges.contracts.hello.v1.SayHelloRequest) request,
              (io.grpc.stub.StreamObserver<io.github.arcforges.contracts.hello.v1.SayHelloResponse>) responseObserver);
          break;
        default:
          throw new AssertionError();
      }
    }

    @java.lang.Override
    @java.lang.SuppressWarnings("unchecked")
    public io.grpc.stub.StreamObserver<Req> invoke(
        io.grpc.stub.StreamObserver<Resp> responseObserver) {
      switch (methodId) {
        default:
          throw new AssertionError();
      }
    }
  }

  public static final io.grpc.ServerServiceDefinition bindService(AsyncService service) {
    return io.grpc.ServerServiceDefinition.builder(getServiceDescriptor())
        .addMethod(
          getSayHelloMethod(),
          io.grpc.stub.ServerCalls.asyncUnaryCall(
            new MethodHandlers<
              io.github.arcforges.contracts.hello.v1.SayHelloRequest,
              io.github.arcforges.contracts.hello.v1.SayHelloResponse>(
                service, METHODID_SAY_HELLO)))
        .build();
  }

  private static volatile io.grpc.ServiceDescriptor serviceDescriptor;

  public static io.grpc.ServiceDescriptor getServiceDescriptor() {
    io.grpc.ServiceDescriptor result = serviceDescriptor;
    if (result == null) {
      synchronized (HelloServiceGrpc.class) {
        result = serviceDescriptor;
        if (result == null) {
          serviceDescriptor = result = io.grpc.ServiceDescriptor.newBuilder(SERVICE_NAME)
              .addMethod(getSayHelloMethod())
              .build();
        }
      }
    }
    return result;
  }
}
