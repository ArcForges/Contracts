// SPDX-License-Identifier: Apache-2.0

using ArcForges.Build.Policy.Architecture;

namespace ArcForges.Contracts.ArchitectureTests;

/// <summary>Reviewed non-wire metadata identities; source changes require a new reviewed binding.</summary>
internal static class OperationMetadataBindings
{
    internal static IReadOnlyList<NonWireMetadataBinding> All { get; } = Array.AsReadOnly<NonWireMetadataBinding>(
    [
        new("ArcForges.Contracts.PublicApi.Operations.PublicOperationPolicy",
            "src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj",
            "src/public/dotnet/ArcForges.Contracts.PublicApi/Operations/PublicOperationPolicy.cs",
            "b30ea93999a46a9e326a93369a90b5fe004ba9ec806fd19c8befb4654c1b42d4",
            NonWireMetadataKind.OperationAuthorizationPolicy),
        new("ArcForges.Contracts.PublicApi.Operations.PublicOperationCatalog",
            "src/public/dotnet/ArcForges.Contracts.PublicApi/ArcForges.Contracts.PublicApi.csproj",
            "src/public/dotnet/ArcForges.Contracts.PublicApi/Generated/Operations/PublicOperationCatalog.g.cs",
            "83736b2d4378c370709e12d58fceaa4345813847fa7d6b68a5ec09c1782268c3",
            NonWireMetadataKind.OperationAuthorizationCatalog),
        new("ArcForges.Contracts.Events.Operations.EventOperationCatalog",
            "src/public/dotnet/ArcForges.Contracts.Events/ArcForges.Contracts.Events.csproj",
            "src/public/dotnet/ArcForges.Contracts.Events/Generated/Operations/EventOperationCatalog.g.cs",
            "8c3bfad1c61abdb4462fb2dc19bb33e72334344dece7dfb463ea4786e1c3e3cc",
            NonWireMetadataKind.OperationAuthorizationCatalog),
    ]);
}
