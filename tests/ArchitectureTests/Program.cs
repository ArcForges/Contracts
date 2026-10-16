// SPDX-License-Identifier: Apache-2.0

namespace Xunit
{
    // The shared policy engine identifies real contract tests by this stable attribute
    // identity. The task-owned host is deliberately package-free and runs its own suite.
    [AttributeUsage(AttributeTargets.Method, Inherited = true)]
    public sealed class FactAttribute : Attribute { }
}

namespace ArcForges.Contracts.ArchitectureTests
{
    internal enum PolicyGateStage
    {
        ValidateArguments,
        RunArchitectureFixtures,
        RunLocalArchitecture,
        LocateRepository,
        ValidateHostedIdentity,
        ValidateRp01Evidence,
        ValidateRp08Evidence,
        ValidateSecurityWorkflow,
        ReadProjectGraph,
        ReadProjectCompilations,
        MissingSourceOrReferenceInputs,
        UnsupportedOutputType,
        ReconstructedCompilationDiagnostics,
        ValidateProtoDtoSymbols,
        ValidateSerializationClosure,
        ReadDependencyPolicy,
        ReadPolicyExceptions,
        ValidateHostLicenceClosure,
        BindContractTests,
        BindWireTypes,
        EvaluateSharedPolicy,
        ValidatePolicyResults,
        ValidateDispatchSymbols,
    }

    internal static class Program
    {
        public static int Main(string[] args)
        {
            PolicyGateStage stage = PolicyGateStage.ValidateArguments;
            // The SDK rules ran in their module initializer and already reported a failure; stop before any other stage.
            if (Sdk.SdkArchitectureTests.FailedRule is not null) return 1;
            try
            {
                if (args.Length > 1 || (args.Length == 1 && args[0] is not ("--hosted" or "--local-gate")))
                {
                    throw new InvalidOperationException("Expected no arguments, --hosted or --local-gate.");
                }

                stage = PolicyGateStage.RunArchitectureFixtures;
                ArchitectureFixtureTests.Run();
                stage = PolicyGateStage.RunLocalArchitecture;
                ContractsArchitectureTests.RunLocal();
                if (args.Length == 1)
                {
                    bool hosted = args[0] == "--hosted";
                    HostedPolicyGate.Run(next => stage = next, hosted);
                    Console.WriteLine(hosted
                        ? "Contracts architecture policy passed for the exact hosted source revision."
                        : "Contracts architecture policy passed for the checked-out source revision (local verification, no hosted identity).");
                }
                else
                {
                    Console.WriteLine("Local architecture fixtures passed; hosted naming and secret-scan evidence remains unverified.");
                }

                return 0;
            }
            catch (Exception exception)
            {
                // Never echo environment variables or build-job secrets.
                WriteFailure(Console.Error, stage, exception);
                return 1;
            }
        }

        internal static void WriteFailure(TextWriter writer, PolicyGateStage stage, Exception exception)
        {
            _ = exception;
            writer.WriteLine($"Contracts architecture policy failed closed at stage {stage}.");
        }
    }
}
