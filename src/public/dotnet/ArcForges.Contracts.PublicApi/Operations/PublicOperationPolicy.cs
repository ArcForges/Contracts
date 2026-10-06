// SPDX-License-Identifier: Apache-2.0
namespace ArcForges.Contracts.PublicApi.Operations;

/// <summary>Immutable authored authorization facts for one public business operation.
/// Generated catalogs are the producer authority; constructing a value does not admit an operation or grant access.</summary>
public sealed class PublicOperationPolicy
{
    /// <summary>Creates an immutable metadata projection, retaining proposal-derived requirements separately from literals.</summary>
    public PublicOperationPolicy(string operationId, string binding, string scope, string idempotency,
        string profile, string sourceRule, string? capability, string? risk, string? riskSource,
        string approval, bool? stepUp, string? stepUpSource, bool? localPresence,
        string? localPresenceSource, string egress, bool patEligible, IEnumerable<string> actorKinds)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(operationId);
        ArgumentException.ThrowIfNullOrWhiteSpace(binding);
        ArgumentException.ThrowIfNullOrWhiteSpace(scope);
        ArgumentException.ThrowIfNullOrWhiteSpace(idempotency);
        ArgumentException.ThrowIfNullOrWhiteSpace(profile);
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceRule);
        ArgumentException.ThrowIfNullOrWhiteSpace(approval);
        ArgumentException.ThrowIfNullOrWhiteSpace(egress);
        ArgumentNullException.ThrowIfNull(actorKinds);
        RequireValueOrSource(risk, riskSource, nameof(risk));
        RequireValueOrSource(stepUp, stepUpSource, nameof(stepUp));
        RequireValueOrSource(localPresence, localPresenceSource, nameof(localPresence));
        var actors = actorKinds.ToArray();
        if (actors.Length == 0 || actors.Any(string.IsNullOrWhiteSpace) ||
            actors.Distinct(StringComparer.Ordinal).Count() != actors.Length)
            throw new ArgumentException("Actor kinds must be nonempty and unique.", nameof(actorKinds));
        OperationId = operationId;
        Binding = binding;
        Scope = scope;
        Idempotency = idempotency;
        Profile = profile;
        SourceRule = sourceRule;
        Capability = capability;
        Risk = risk;
        RiskSource = riskSource;
        Approval = approval;
        StepUp = stepUp;
        StepUpSource = stepUpSource;
        LocalPresence = localPresence;
        LocalPresenceSource = localPresenceSource;
        Egress = egress;
        PatEligible = patEligible;
        ActorKinds = Array.AsReadOnly(actors);
        PatScopes = Array.AsReadOnly(patEligible ? new[] { operationId } : Array.Empty<string>());
    }

    /// <summary>The exact case-sensitive operation identifier.</summary>
    public string OperationId { get; }
    /// <summary>The exact generated protobuf service/method binding.</summary>
    public string Binding { get; }
    /// <summary>This catalog contains only the public business surface.</summary>
    public string Surface => "public";
    /// <summary>The ownership/tenancy profile; this is not a token scope.</summary>
    public string Scope { get; }
    /// <summary>The authored idempotency class.</summary>
    public string Idempotency { get; }
    /// <summary>The closed authorization profile.</summary>
    public string Profile { get; }
    /// <summary>The exact source rule governing this operation.</summary>
    public string SourceRule { get; }
    /// <summary>The authored capability, if present.</summary>
    public string? Capability { get; }
    /// <summary>The literal risk, or null when it must be obtained from <see cref="RiskSource"/>.</summary>
    public string? Risk { get; }
    /// <summary>The verified source expression for a derived risk, or null for a literal.</summary>
    public string? RiskSource { get; }
    /// <summary>The authored approval requirement.</summary>
    public string Approval { get; }
    /// <summary>The literal step-up requirement, or null for a verified proposal-derived requirement.</summary>
    public bool? StepUp { get; }
    /// <summary>The verified source expression for a derived step-up requirement.</summary>
    public string? StepUpSource { get; }
    /// <summary>The literal local-presence requirement, or null for a verified proposal-derived requirement.</summary>
    public bool? LocalPresence { get; }
    /// <summary>The verified source expression for a derived local-presence requirement.</summary>
    public string? LocalPresenceSource { get; }
    /// <summary>The authored egress profile.</summary>
    public string Egress { get; }
    /// <summary>Whether the closed producer policy permits PAT authentication for this operation.</summary>
    public bool PatEligible { get; }
    /// <summary>Eligible operations have exactly their operation ID as a PAT scope; denied operations have none.</summary>
    public IReadOnlyList<string> PatScopes { get; }
    /// <summary>The immutable authored actor kinds; no caller-owned array is retained.</summary>
    public IReadOnlyList<string> ActorKinds { get; }

    private static void RequireValueOrSource<T>(T? value, string? source, string name)
    {
        if ((value is null) == (source is null) || source is not null && string.IsNullOrWhiteSpace(source))
            throw new ArgumentException("Exactly one literal or verified source expression is required.", name);
    }
}
