// SPDX-License-Identifier: Apache-2.0
using Google.Protobuf;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.Hello.V1;

if (args.Length != 2) throw new ArgumentException("PreviousClient <emit|verify-and-serve> <exchange-directory>");
var directory = Path.GetFullPath(args[1]);
Directory.CreateDirectory(directory);
// This executable references the exact previously published package, never a
// current source project. File exchange exercises codecs offline, not a live RPC.
if (args[0] == "emit")
{
    File.WriteAllBytes(Path.Combine(directory, "previous-request.bin"), new SayHelloRequest { Name = "A中😀" }.ToByteArray());
    File.WriteAllBytes(Path.Combine(directory, "previous-int64.bin"), new Revision { Value = 9007199254740993 }.ToByteArray());
    File.WriteAllBytes(Path.Combine(directory, "previous-decimal.bin"), new ArcForges.Contracts.Foundation.V1.Decimal { Value = "0.000000001" }.ToByteArray());
    return;
}
if (args[0] != "verify-and-serve") throw new ArgumentException("Unknown previous-client mode");
var responseBytes = File.ReadAllBytes(Path.Combine(directory, "current-response.bin"));
var response = SayHelloResponse.Parser.ParseFrom(responseBytes);
if (response.Message != "Hello, A中😀!") throw new InvalidOperationException("Previous client rejected current response");
// The current fixture appends tag 99, representing an additive future read field.
// The old generated assembly must retain it when storing/re-emitting the message.
if (!response.ToByteArray().AsSpan().SequenceEqual(responseBytes)) throw new InvalidOperationException("Previous client lost unknown response field");
File.WriteAllBytes(Path.Combine(directory, "previous-retained-response.bin"), response.ToByteArray());
var request = SayHelloRequest.Parser.ParseFrom(File.ReadAllBytes(Path.Combine(directory, "current-request.bin")));
if (request.Name != "minimum") throw new InvalidOperationException("Minimum server could not read current request");
File.WriteAllBytes(Path.Combine(directory, "minimum-response.bin"), new SayHelloResponse { Message = "Hello, " + request.Name + "!" }.ToByteArray());
Console.WriteLine("Previous published client/current handler and current client/minimum handler offline codecs passed.");
