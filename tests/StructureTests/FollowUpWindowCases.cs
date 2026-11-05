// SPDX-License-Identifier: Apache-2.0
using System.Text;
using Google.Protobuf;
using ArcForges.Contracts.Fleet.V1;
using ArcForges.Contracts.PublicApi.Http.V1.WebBrowserError;
using ArcForges.Contracts.Validation;
using FleetShapes = ArcForges.Contracts.Fleet.Shapes.ContractShapeValidation;

// AF-CTR-05 part C1 (the Contracts follow-up window): the validate: rule of the approve decision (errors.md, "Built refusals
// the annotations do not name yet") through the generated validators, and the WebBrowserSession error body (Plan decision Q14)
// through its generated codec. The expected values are the C1 decisions, not values read from the generated code.
internal static class FollowUpWindowCases
{
    private static readonly ArcForges.Contracts.Foundation.V1.Id FlowId =
        new() { Value = ByteString.CopyFrom(Convert.FromHexString("0192f7a0c3e47b1a8d2e5f6a7b8c9d0e")) };

    public static void Run()
    {
        // approve: required. Approval (true) and denial (false) are both decisions; an absent approve is refused, as the center
        // refuses it (VALIDATION/invalid_argument).
        var signIn = new NodeEnrollmentServiceApproveNodeSignInRequest { FlowId = FlowId, Approve = true };
        Require(FleetShapes.IsValid(signIn), "ApproveNodeSignIn with approve = true is valid");
        Require(FleetShapes.IsValid(Change(signIn, r => r.Approve = false)), "ApproveNodeSignIn with approve = false (a denial) is valid");
        Require(!FleetShapes.IsValid(Change(signIn, r => r.ClearApprove())), "ApproveNodeSignIn without approve is refused");
        var deviceCode = new NodeEnrollmentServiceApproveDeviceCodeRequest { UserCode = "BCDFGHJK", Approve = true };
        Require(FleetShapes.IsValid(deviceCode), "ApproveDeviceCode with approve = true is valid");
        Require(FleetShapes.IsValid(Change(deviceCode, r => r.Approve = false)), "ApproveDeviceCode with approve = false (a denial) is valid");
        Require(!FleetShapes.IsValid(Change(deviceCode, r => r.ClearApprove())), "ApproveDeviceCode without approve is refused");

        // The error body: a capture of the center's errorOf for a rate limit reads into the typed records and is written back
        // byte for byte; an UNKNOWN effect with afterTime, the pair the foundation rule arcError rejects, is refused.
        const string limited = "{\"error\":{\"category\":\"resource\",\"code\":\"rate_limited\",\"messageKey\":\"error.resource.rate_limited\","
            + "\"retry\":{\"mode\":\"afterTime\",\"retryAt\":\"2026-10-29T12:01:30Z\"},\"effect\":\"didNotHappen\","
            + "\"correlationId\":\"4bf92f35-77b3-4da6-a3ce-929d0e0e4736\",\"details\":{\"limit\":{\"limitName\":\"sign_in_prefix\","
            + "\"maximum\":\"30\",\"recoveryAt\":\"2026-10-29T12:01:30Z\"}}}}";
        Require(WebBrowserErrorReplyJson.TryParse(Encoding.UTF8.GetBytes(limited), out var reply, out _), "the center's rate-limit reply parses");
        Require(reply!.Error.Retry.Mode == "afterTime" && reply.Error.Retry.RetryAt == "2026-10-29T12:01:30Z"
            && reply.Error.Details is WebBrowserErrorDetailsWebBrowserErrorLimitDetails { Value.Limit.LimitName: "sign_in_prefix" },
            "the typed reply carries the advice and the limit");
        Require(Encoding.UTF8.GetString(WebBrowserErrorReplyJson.Serialize(reply)) == limited, "the reply is written back byte for byte");
        var unknown = limited.Replace("\"didNotHappen\"", "\"unknown\"", StringComparison.Ordinal);
        Require(!WebBrowserErrorReplyJson.TryParse(Encoding.UTF8.GetBytes(unknown), out _, out _), "unknown with afterTime is refused");
        Require(WebBrowserErrorReplyJson.MaxBytes == 16384, "the error body bound");
        Console.WriteLine("Validated the AF-CTR-05 C1 approve vectors and the WebBrowserSession error body.");
    }

    private static T Change<T>(T value, Action<T> change) where T : IMessage<T>
    {
        var copy = value.Clone();
        change(copy);
        return copy;
    }

    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("AF-CTR-05 C1 case failed: " + name);
    }
}
