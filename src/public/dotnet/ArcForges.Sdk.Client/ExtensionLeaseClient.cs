// SPDX-License-Identifier: Apache-2.0
using ArcForges.Contracts.Validation;
using ArcForges.Sdk.Contracts.V1;
using Grpc.Core;

namespace ArcForges.Sdk.Client;

/// <summary>Typed extension lease calls over a transport and credentials owned by the caller.</summary>
public sealed class ExtensionLeaseClient
{
    private readonly ExtensionHostService.ExtensionHostServiceClient client;

    /// <summary>Creates typed lease calls using the supplied transport without taking ownership of it.</summary>
    public ExtensionLeaseClient(CallInvoker callInvoker)
    {
        ArgumentNullException.ThrowIfNull(callInvoker);
        client = new ExtensionHostService.ExtensionHostServiceClient(callInvoker);
    }

    /// <summary>Renews an existing lease without owning endpoint, session, retry or authentication policy.</summary>
    public AsyncUnaryCall<ExtensionHostServiceRenewLeaseResponse> RenewLeaseAsync(
        ExtensionHostServiceRenewLeaseRequest request, CallOptions options = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (!ContractShapeValidation.IsValid(request))
        {
            throw new ArgumentException("The request does not satisfy the declared extension lease shape.", nameof(request));
        }

        return client.RenewLeaseAsync(request, options);
    }
}
