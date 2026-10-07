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
    }

    internal static class Program
    {
        public static int Main(string[] args)
        {
            PolicyGateStage stage = PolicyGateStage.ValidateArguments;
            var elapsed = System.Diagnostics.Stopwatch.StartNew();
            void SetStage(PolicyGateStage next)
            {
                stage = next;
                WriteProgress(Console.Out, next, elapsed.ElapsedMilliseconds);
            }
            try
            {
                if (args.Length > 1 || (args.Length == 1 && args[0] != "--hosted"))
                {
                    throw new InvalidOperationException("Expected no arguments or --hosted.");
                }

                SetStage(PolicyGateStage.RunArchitectureFixtures);
                ArchitectureFixtureTests.Run();
                SetStage(PolicyGateStage.RunLocalArchitecture);
                ContractsArchitectureTests.RunLocal();
                if (args.Length == 1)
                {
                    HostedPolicyGate.Run(SetStage);
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

        internal static void WriteProgress(TextWriter writer, PolicyGateStage stage, long elapsedMilliseconds,
            int projectIndex = 0, int projectCount = 0)
        {
            if (!Enum.IsDefined(stage) || elapsedMilliseconds < 0 || projectCount is < 0 or > 10000
                || projectIndex < 0 || projectIndex > projectCount)
                throw new InvalidOperationException("Invalid bounded architecture progress.");
            // Only fixed stages and bounded numeric facts. Never a project path, source text or exception message.
            writer.WriteLine(FormattableString.Invariant($"Contracts architecture progress: stage={stage}; elapsedMs={elapsedMilliseconds}; project={projectIndex}/{projectCount}."));
        }

        internal static void WriteFailure(TextWriter writer, PolicyGateStage stage, Exception exception)
        {
            _ = exception;
            writer.WriteLine($"Contracts architecture policy failed closed at stage {stage}.");
        }
    }
}
