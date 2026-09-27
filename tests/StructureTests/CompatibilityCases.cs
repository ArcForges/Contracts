// SPDX-License-Identifier: Apache-2.0
using Google.Protobuf;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.Hello.V1;

internal static class CompatibilityCases
{
    internal static void Run(string mode, string directory)
    {
        if (mode == "current")
        {
            var request = SayHelloRequest.Parser.ParseFrom(File.ReadAllBytes(Path.Combine(directory, "previous-request.bin")));
            if (request.Name != "A中😀" || Revision.Parser.ParseFrom(File.ReadAllBytes(Path.Combine(directory, "previous-int64.bin"))).Value != 9007199254740993
                || ArcForges.Contracts.Foundation.V1.Decimal.Parser.ParseFrom(File.ReadAllBytes(Path.Combine(directory, "previous-decimal.bin"))).Value != "0.000000001")
                throw new InvalidOperationException("Current codec changed exact previous-client meaning");
            var response = new SayHelloResponse { Message = "Hello, " + request.Name + "!" }.ToByteArray();
            var future = Convert.FromHexString("9a0603667574"); // field 99, length 3, UTF-8 "fut"
            File.WriteAllBytes(Path.Combine(directory, "current-response.bin"), [.. response, .. future]);
            File.WriteAllBytes(Path.Combine(directory, "current-request.bin"), new SayHelloRequest { Name = "minimum" }.ToByteArray());
            return;
        }
        if (mode != "verify") throw new ArgumentException("Unknown current compatibility mode");
        var minimum = SayHelloResponse.Parser.ParseFrom(File.ReadAllBytes(Path.Combine(directory, "minimum-response.bin")));
        if (minimum.Message != "Hello, minimum!") throw new InvalidOperationException("Current client rejected minimum response");
        if (!File.ReadAllBytes(Path.Combine(directory, "current-response.bin")).AsSpan()
            .SequenceEqual(File.ReadAllBytes(Path.Combine(directory, "previous-retained-response.bin"))))
            throw new InvalidOperationException("Additive field retention failed across previous/current codecs");
        Console.WriteLine("Bidirectional previous published/current codec matrix passed; Hello is a packaging demonstration, not product service acceptance.");
    }
}
