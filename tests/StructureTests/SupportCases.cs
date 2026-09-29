// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.PublicApi.V1;
using ArcForges.Contracts.Validation;

internal static class SupportCases
{
    public static void Run(string root)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-22-account-support.json")));
        foreach (var item in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            var target = item.GetProperty("target").GetString()!;
            var json = item.GetProperty("value").GetRawText();
            var actual = target switch
            {
                "SupportCase" => ContractShapeValidation.IsValid(JsonParser.Default.Parse<SupportCase>(json)),
                "SupportMessage" => ContractShapeValidation.IsValid(JsonParser.Default.Parse<SupportMessage>(json)),
                "NotificationView" => ContractShapeValidation.IsValid(JsonParser.Default.Parse<NotificationView>(json)),
                "PolicyBundle" => ContractShapeValidation.IsValid(JsonParser.Default.Parse<PolicyBundle>(json)),
                _ => throw new InvalidOperationException("Unknown CON.22 fixture target: " + target)
            };
            Require(actual == item.GetProperty("valid").GetBoolean(), item.GetProperty("id").GetString()!);
        }

        Require(SupportReflection.Descriptor.Services.Count == 4, "exact support file service count");
        Require(ExportReflection.Descriptor.Services.Count == 2, "exact export file service count");
        Require(SupportReflection.Descriptor.Services.Single(s => s.Name == "SupportService")
            .Methods.Select(m => m.Name).SequenceEqual(new[] { "CreateCase", "ListCases", "AppendMessage", "DecideAccess" }), "exact support methods");
        Require(SupportReflection.Descriptor.Services.Single(s => s.Name == "NotificationService")
            .Methods.Select(m => m.Name).SequenceEqual(new[] { "List", "Acknowledge", "RegisterPush", "UnregisterPush" }), "exact notification methods");
        Require(SupportReflection.Descriptor.Services.Single(s => s.Name == "PreferenceService")
            .Methods.Select(m => m.Name).SequenceEqual(new[] { "Put" }), "exact preference methods");
        Require(SupportReflection.Descriptor.Services.Single(s => s.Name == "PolicyService")
            .Methods.Select(m => m.Name).SequenceEqual(new[] { "GetBundle" }), "exact policy methods");
        Require(ExportReflection.Descriptor.Services.Single(s => s.Name == "DataService")
            .Methods.Select(m => m.Name).SequenceEqual(new[] { "RequestExport", "GetExportState" }), "exact data methods");
        Require(ExportReflection.Descriptor.Services.Single(s => s.Name == "ExportService")
            .Methods.Select(m => m.Name).SequenceEqual(new[] { "GetStatus", "Cancel", "GetDownload" }), "exact export methods");

        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "SupportService"), "CreateCase",
            "1:meta,10:case_id,11:subject,12:message,13:diagnostic,14:category,15:related_action_id", "10:case");
        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "SupportService"), "ListCases",
            "1:meta,10:page", "10:items,11:page");
        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "SupportService"), "AppendMessage",
            "1:meta,10:case_id,11:message_id,12:text", "10:case");
        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "SupportService"), "DecideAccess",
            "1:meta,10:access_id,11:proposal_hash,12:approve", "10:receipt");
        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "NotificationService"), "List",
            "1:meta,10:page", "10:items,11:page");
        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "NotificationService"), "Acknowledge",
            "1:meta,10:notification_id", "10:receipt");
        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "NotificationService"), "RegisterPush",
            "1:meta,10:installation_id,11:platform,12:token", "10:registration_id");
        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "NotificationService"), "UnregisterPush",
            "1:meta,10:registration_id", "10:receipt");
        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "PreferenceService"), "Put",
            "1:meta,10:value", "10:value");
        AssertOperation(SupportReflection.Descriptor.Services.Single(s => s.Name == "PolicyService"), "GetBundle",
            "1:meta,10:installation_id,11:last_version", "10:bundle");
        AssertOperation(ExportReflection.Descriptor.Services.Single(s => s.Name == "DataService"), "RequestExport",
            "1:meta,10:export_id", "10:job");
        AssertOperation(ExportReflection.Descriptor.Services.Single(s => s.Name == "DataService"), "GetExportState",
            "1:meta,10:export_id", "10:job");
        AssertOperation(ExportReflection.Descriptor.Services.Single(s => s.Name == "ExportService"), "GetStatus",
            "1:meta,10:export_id", "10:job");
        AssertOperation(ExportReflection.Descriptor.Services.Single(s => s.Name == "ExportService"), "Cancel",
            "1:meta,10:export_id", "10:job");
        AssertOperation(ExportReflection.Descriptor.Services.Single(s => s.Name == "ExportService"), "GetDownload",
            "1:meta,10:export_id", "10:ticket");

        foreach (var service in SupportReflection.Descriptor.Services.Concat(ExportReflection.Descriptor.Services))
        foreach (var method in service.Methods)
        {
            var supportsEncodedBody = (service.Name, method.Name) is
                ("SupportService", "ListCases") or
                ("NotificationService", "List") or
                ("PolicyService", "GetBundle") or
                ("DataService", "GetExportState") or
                ("ExportService", "GetStatus");
            Require(!method.IsClientStreaming && !method.IsServerStreaming, "unary " + service.Name + "." + method.Name);
            Require(method.InputType.FindFieldByNumber(1)?.MessageType == RequestMeta.Descriptor, "request metadata");
            Require(method.InputType.Fields.InDeclarationOrder().All(f => f.FieldNumber == 1 || f.FieldNumber >= 10), "request business tags");
            Require(method.OutputType.FindFieldByNumber(1)?.MessageType == ResponseMeta.Descriptor, "response metadata");
            Require(method.OutputType.FindFieldByNumber(2)?.ContainingOneof?.Name == "outcome", "success/error oneof");
            Require(method.OutputType.FindFieldByNumber(3)?.ContainingOneof?.Name == "outcome", "success/error oneof");
            Require(method.OutputType.FindFieldByNumber(3)?.MessageType == ArcForges.Contracts.Foundation.V1.ArcError.Descriptor, "typed error outcome");
            Require((method.OutputType.FindFieldByNumber(4) is not null) == supportsEncodedBody, "read projection encoded-body binding");
            if (supportsEncodedBody)
                Require(method.OutputType.FindFieldByNumber(4)?.MessageType == EncodedBodyRef.Descriptor, "typed encoded-body outcome");
            for (var tag = 2; tag <= 9; tag++) Require(method.InputType.FindFieldByNumber(tag) is null, "reserved request envelope tag");
            for (var tag = 5; tag <= 9; tag++) Require(method.OutputType.FindFieldByNumber(tag) is null, "reserved response envelope tag");
        }

        Require(FieldShape(SupportCase.Descriptor) == "1:case_id,2:subject,3:state,4:messages,5:revision,6:category,7:related_action_id,8:message_page", "SupportCase exact tags");
        Require(FieldShape(SupportMessage.Descriptor) == "1:message_id,2:actor_kind,3:text,4:created_at,5:diagnostic", "SupportMessage exact tags");
        Require(FieldShape(NotificationView.Descriptor) == "1:notification_id,2:kind,3:durability,4:message_key,5:target,6:state,7:created_at", "NotificationView exact tags");
        Require(FieldShape(PolicyBundle.Descriptor) == "1:version,2:issued_at,3:expires_at,4:body,5:signature,6:key_id", "PolicyBundle exact tags");
        Require(SupportServiceAppendMessageRequest.Descriptor.Fields.InDeclarationOrder().Select(f => f.Name)
            .SequenceEqual(new[] { "meta", "case_id", "message_id", "text" }), "appendMessage carries no diagnostic field");

        var id = Id();
        var validCase = Case("open", "support", 256, 100);
        Require(ContractShapeValidation.IsValid(validCase), "Name 256 scalars and one message page at max 100");
        var missingSubject = validCase.Clone();
        missingSubject.ClearSubject();
        Require(!ContractShapeValidation.IsValid(missingSubject), "SupportCase subject presence");
        var missingRevision = validCase.Clone();
        missingRevision.ClearRevision();
        Require(!ContractShapeValidation.IsValid(missingRevision), "SupportCase revision presence");
        var missingPage = validCase.Clone();
        missingPage.ClearMessagePage();
        Require(!ContractShapeValidation.IsValid(missingPage), "SupportCase messagePage presence");
        validCase.Subject += "x";
        Require(!ContractShapeValidation.IsValid(validCase), "Name rejects 257 scalars");
        Require(!ContractShapeValidation.IsValid(Case("futureState", "support", 1, 0)), "closed support case state meanings");
        Require(!ContractShapeValidation.IsValid(Case("open", "futureCategory", 1, 0)), "closed support case categories");
        Require(!ContractShapeValidation.IsValid(Case("open", "support", 1, 101)), "message page max 100");

        var message = Message(new string('é', 131072));
        Require(ContractShapeValidation.IsValid(message), "Text exact UTF-8 maximum");
        var missingText = message.Clone();
        missingText.ClearText();
        Require(!ContractShapeValidation.IsValid(missingText), "SupportMessage text presence");
        var missingCreatedAt = message.Clone();
        missingCreatedAt.ClearCreatedAt();
        Require(!ContractShapeValidation.IsValid(missingCreatedAt), "SupportMessage createdAt presence");
        message.Text += "é";
        Require(!ContractShapeValidation.IsValid(message), "Text exceeds UTF-8 maximum");
        message = Message("forward.compatible.actor");
        Require(ContractShapeValidation.IsValid(message), "actorKind is a forward-compatible Key");
        message.ActorKind = "not valid";
        Require(!ContractShapeValidation.IsValid(message), "actorKind enforces Key syntax");

        var bundle = new PolicyBundle
        {
            Version = "policy.1",
            IssuedAt = new Instant { UnixSeconds = 1 },
            ExpiresAt = new Instant { UnixSeconds = 2 },
            Body = ByteString.CopyFrom(new byte[1048576]),
            Signature = ByteString.CopyFrom(new byte[] { 1 }),
            KeyId = "key.1"
        };
        Require(ContractShapeValidation.IsValid(bundle), "PolicyBundle body exact 1 MiB limit");
        var missingBody = bundle.Clone();
        missingBody.ClearBody();
        Require(!ContractShapeValidation.IsValid(missingBody), "PolicyBundle body presence");
        var missingSignature = bundle.Clone();
        missingSignature.ClearSignature();
        Require(!ContractShapeValidation.IsValid(missingSignature), "PolicyBundle signature presence");
        bundle.Body = ByteString.CopyFrom(new byte[1048577]);
        Require(!ContractShapeValidation.IsValid(bundle), "PolicyBundle body exceeds 1 MiB");
        var missingIssuedAt = new PolicyBundle
        {
            Version = "policy.1", ExpiresAt = new Instant { UnixSeconds = 2 },
            Body = ByteString.CopyFrom(new byte[] { 1 }), Signature = ByteString.CopyFrom(new byte[] { 1 }), KeyId = "key.1"
        };
        Require(!ContractShapeValidation.IsValid(missingIssuedAt), "PolicyBundle issuedAt presence");

        var request = new SupportServiceAppendMessageRequest
        {
            Meta = new RequestMeta { CorrelationId = id },
            CaseId = id,
            MessageId = id,
            Text = "A public support reply."
        };
        Require(ContractShapeValidation.IsValid(request), "appendMessage exact wire request");
        request.Meta.CorrelationId = null;
        Require(!ContractShapeValidation.IsValid(request), "appendMessage requires correlated request metadata");
        Console.WriteLine("CON.22: exact six services, canonical records and independent shape/wire boundary vectors passed.");
    }

    private static void AssertOperation(ServiceDescriptor service, string methodName, string requestShape, string valueShape)
    {
        var method = service.Methods.Single(candidate => candidate.Name == methodName);
        Require(FieldShape(method.InputType) == requestShape, service.Name + "." + methodName + " request tags");
        Require(FieldShape(method.OutputType.FindFieldByNumber(2)!.MessageType) == valueShape,
            service.Name + "." + methodName + " success tags");
    }

    private static string FieldShape(MessageDescriptor descriptor) =>
        string.Join(",", descriptor.Fields.InDeclarationOrder().Select(field => $"{field.FieldNumber}:{field.Name}"));

    private static SupportCase Case(string state, string category, int subjectScalars, int messages)
    {
        var value = new SupportCase
        {
            CaseId = Id(),
            Subject = string.Concat(Enumerable.Repeat("😀", subjectScalars)),
            State = state,
            Revision = new Revision { Value = 1 },
            Category = category,
            MessagePage = new PageState { HasMore = false }
        };
        for (var i = 0; i < messages; i++) value.Messages.Add(Message("case message"));
        return value;
    }

    private static SupportMessage Message(string text) => new()
    {
        MessageId = Id(), ActorKind = "future.owner", Text = text, CreatedAt = new Instant { UnixSeconds = 1 }
    };

    private static Id Id() => new() { Value = ByteString.CopyFrom(Convert.FromHexString("112233445566478899AABBCCDDEEFF00")) };

    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("CON.22 fixture: " + name);
    }
}
