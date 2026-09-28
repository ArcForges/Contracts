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
        ValidateProtoDtoSymbols,
        ValidateSerializationClosure,
        ReadDependencyPolicy,
        ReadPolicyExceptions,
        BindContractTests,
        BindWireTypes,
        EvaluateSharedPolicy,
        ValidatePolicyResults,
    }

    internal static class Program
    {
        public static int Main(string[] args)
        {
            PolicyGateStage stage = PolicyGateStage.ValidateArguments;
            try
            {
                if (args.Length > 1 || (args.Length == 1 && args[0] != "--hosted"))
                {
                    throw new InvalidOperationException("Expected no arguments or --hosted.");
                }

                stage = PolicyGateStage.RunArchitectureFixtures;
                ArchitectureFixtureTests.Run();
                stage = PolicyGateStage.RunLocalArchitecture;
                ContractsArchitectureTests.RunLocal();
                if (args.Length == 1)
                {
                    HostedPolicyGate.Run(next => stage = next);
                    Console.WriteLine("Contracts architecture policy passed for the exact hosted source revision.");
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
