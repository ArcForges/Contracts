# SPDX-License-Identifier: Apache-2.0
"""Static generated in-process interfaces and owned, nonreflective shape rules.

These declarations neither register listeners nor implement product handlers.
The owner remains responsible for authorization, consent, state and resources.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTS = {
    "Platform": {
        "ICapabilityProvider": ("CapabilityProviderService", ("Describe", "EvaluateAvailability", "Invoke")),
        "IContextProvider": ("ContextProviderService", ("DescribeContextKinds", "ProvideContext")),
        "IArtifactHandler": ("ArtifactHandlerService", ("DescribeArtifactKinds", "Resolve", "RenderPreview", "Open")),
        "IResourceAccess": ("ResourceAccessService", ("GetMetadata", "OpenRead", "Release", "ReadChunk")),
        "IProductLifecycle": ("ProductLifecycleService", ("GetState", "PrepareForShutdown", "GetJob")),
        "IDeepLinkTarget": ("DeepLinkTargetService", ("HandleDeepLink",)),
        "ILocalEvents": ("LocalEventsService", ("Poll",)),
    },
    "Chat": {
        "IChatOperations": ("ChatOperationsService", ("ListConversations", "GetConversation", "CreateConversation", "AppendUserMessage", "StartAgentTurn", "SubmitApproval", "OpenArtifact")),
    },
    "Scope": {
        "IScopeOperations": ("ScopeOperationsService", ("ListSessions", "GetSession", "ListCaptures", "GetConfigurationSnapshot", "RunMeasurement", "RunAnalysis", "CompareSessions", "CreateAnnotation", "CreateFinding", "GenerateReport", "StartCapture", "StopCapture", "GetStructuredContext")),
    },
}

CS_RULES = {
    "turnOptions": "if (value.Mode == global::ArcForges.Contracts.PublicApi.V1.ChatMode.Agent ? value.TaskId is null || value.TurnId is not null : value.TurnId is null || value.TaskId is not null) return false;",
    "sourceConsentSpec": 'if (value.Override is not null && (value.Override.HasSearchable || value.Override.HasCloudIndexAllowed) || value.Purpose == "webSearch" && !value.HasQueryHash) return false;',
    "con06LocalHint": 'if (value.Kind == "resourceChanged" ? value.ResourceId is null || value.JobId is not null : value.Kind == "jobChanged" ? value.JobId is null || value.ResourceId is not null : value.ResourceId is not null || value.JobId is not null) return false;',
    "con06ReadChunk": "if (value.Offset > ulong.MaxValue - value.Length) return false;",
    "con06StartAgentTurn": "if (value.Options is null || value.Options.Mode != global::ArcForges.Contracts.PublicApi.V1.ChatMode.Agent || value.TaskId is null || !value.TaskId.Equals(value.Options.TaskId)) return false;",
    "con06ScopeAnalysis": 'if ((value.AnalysisKind switch { "spectrum" => 3, "correlation" => 4, "threshold" => 5, "pattern" => 6, "decode" => 7, _ => 0 }) != (int)value.OptionsCase) return false;',
    "con06Spectrum": "if ((value.Size & (value.Size - 1)) != 0 || value.ResampleRate is { Numerator: <= 0 }) return false;",
    "con06Threshold": "if (value.MinimumDuration.Ticks < 0) return false;",
    "con06EventPattern": "if (value.Channels.Count != value.Edges.Count || value.MaximumInterval.Ticks < 0) return false;",
    "con06CaptureRequest": 'if (value.Source.Kind is "serial" or "usb" && (!value.Source.HasDeviceId || value.DeviceId != value.Source.DeviceId)) return false;',
    "con06ScopeWriteMeta": "if (value.Meta.ExpectedNative is null || value.Meta.ExpectedRev is not null) return false;",
    "con06AcquisitionSource": 'if ((value.Serial is null ? 0 : 1) + (value.Endpoint is null ? 0 : 1) + (value.File is null ? 0 : 1) + (value.Usb is null ? 0 : 1) != 1) return false; if (value.Kind switch { "serial" => value.Serial is null || !value.HasDeviceId, "tcp" or "udp" => value.Endpoint is null, "file" => value.File is null, "usb" => value.Usb is null || !value.HasDeviceId, _ => true }) return false;',
    "con06Decoder": 'if (value.Timeout.Ticks <= 0) return false; if (value.Kind switch { "uart" => value.Channels.Count != 1 || !value.HasBaud || value.Bits is < 5 or > 9 || value.Mode != 0 || !value.MsbFirst || !value.ActiveLow || value.AddressBits != 7, "i2c" => value.Channels.Count != 2 || value.HasBaud || value.Bits != 8 || value.Parity != "none" || value.StopBits != 1 || value.Mode != 0 || !value.MsbFirst || !value.ActiveLow || !value.IdleHigh, "spi" => value.Channels.Count is < 3 or > 4 || value.HasBaud || value.Parity != "none" || value.StopBits != 1 || value.AddressBits != 7 || !value.IdleHigh, _ => true }) return false;',
}

TS_RULES = {
    "turnOptions": "if (value.mode === 2 ? value.taskId === undefined || value.turnId !== undefined : value.turnId === undefined || value.taskId !== undefined) return false;",
    "sourceConsentSpec": 'if (value.override !== undefined && ((value.override as Record<string, unknown>).searchable !== undefined || (value.override as Record<string, unknown>).cloudIndexAllowed !== undefined) || value.purpose === "webSearch" && value.queryHash === undefined) return false;',
}


def generate(check: bool = False) -> None:
    """Emit the complete closed interface set with explicit generated types."""
    for owner, interfaces in PORTS.items():
        namespace = f"ArcForges.Contracts.LocalRpc.{owner}"
        lines = ["// SPDX-License-Identifier: Apache-2.0", "// Generated by eng/con06_inprocess.py. Do not edit.", "#nullable enable", f"namespace {namespace}.Ports;", ""]
        for interface, (service, methods) in interfaces.items():
            lines += ["/// <summary>Typed application-owned in-process port; no listener, channel or service registration.</summary>", f"public interface {interface}", "{"]
            for method in methods:
                message = f"global::{namespace}.V1.{service}{method}"
                lines += ["    /// <summary>Calls the statically supplied owner handler; cancellation preserves dispatched-effect reconciliation.</summary>", f"    global::System.Threading.Tasks.ValueTask<{message}Response> {method}Async({message}Request request, global::System.Threading.CancellationToken cancellationToken = default);"]
            lines += ["}", ""]
        target = ROOT / f"src/internal/dotnet/{namespace}/Generated/InprocessPorts.g.cs"
        content = "\n".join(lines)
        if check:
            if not target.is_file() or target.read_text(encoding="utf-8") != content:
                raise ValueError(f"Stale in-process port interfaces: {target}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
