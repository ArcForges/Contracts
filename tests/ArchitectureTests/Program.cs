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
    internal static class Program
    {
        public static int Main(string[] args)
        {
            try
            {
                if (args.Length > 1 || (args.Length == 1 && args[0] != "--hosted"))
                {
                    throw new InvalidOperationException("Expected no arguments or --hosted.");
                }

                ArchitectureFixtureTests.Run();
                ContractsArchitectureTests.RunLocal();
                if (args.Length == 1)
                {
                    HostedPolicyGate.Run();
                    Console.WriteLine("Contracts architecture policy passed for the exact hosted source revision.");
                }
                else
                {
                    Console.WriteLine("Local architecture fixtures passed; hosted naming and secret-scan evidence remains unverified.");
                }

                return 0;
            }
            catch (Exception)
            {
                // Never echo environment variables or build-job secrets.
                Console.Error.WriteLine("Contracts architecture policy failed closed.");
                return 1;
            }
        }
    }
}
