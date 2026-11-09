// SPDX-License-Identifier: Apache-2.0
using System.Security.Cryptography;
using System.Text.Json;
using Google.Protobuf;
using ArcForges.Contracts.Fleet.V1;
using ArcForges.Contracts.Foundation.V1;
using ArcForges.Contracts.Node.V1;
using ArcForges.Contracts.Relay.V1;
using FleetShapes = ArcForges.Contracts.Fleet.Shapes.ContractShapeValidation;
using NodeShapes = ArcForges.Contracts.Node.Shapes.ContractShapeValidation;
using RelayShapes = ArcForges.Contracts.Relay.Shapes.ContractShapeValidation;

// AF-CTR-06 target contract: independent boundary examples from Design 06a and AD-0021.
// These are offline generated-codec and shape tests, not authorization, signatures or product I/O tests.
internal static class FileContractCases
{
    private const int NodePayloadLimit = 245_760;
    private const int FileWriteLimit = 196_608;
    private const int ChannelCallLimit = 253_952;
    private const int ChannelResultLimit = 1_040_384;
    private const int FrameLimit = 1_048_576;

    private static Id Id() => new() { Value = ByteString.CopyFrom(Convert.FromHexString("00112233445566778899aabbccddeeff")) };
    private static ByteString Bytes(int length) => ByteString.CopyFrom(new byte[length]);
    private static RequestMeta MutationMeta() => new() { CommandId = Id(), CorrelationId = Id() };
    private static FilePath Path(string value = "dir/file.txt") => new() { WorkspaceId = Id(), Path = value };

    public static void Run(string root)
    {
        ServiceSignatures();
        PathsAndRequests();
        ReadCommandPresence();
        WorkspaceContracts();
        GitSummaryQuality();
        ReadValues();
        Operations();
        Audit();
        RoutedRequests();
        RelayHeadersAndFrames(root);
        Console.WriteLine("AF-CTR-06: generated file codecs, presence, bounds, operation states, audits, 12 routed envelopes and relay shapes.");
    }

    private static void ServiceSignatures()
    {
        var service = FilesReflection.Descriptor.Services.Single(s => s.Name == "FileService");
        string[] expected = ["ReadFile", "WriteFile", "EditFile", "SearchFiles", "ListDirectory", "PlanRemoval",
            "ExecuteRemoval", "GetFileOperation", "AcknowledgeFileOperation"];
        Require(service.Methods.Select(m => m.Name).SequenceEqual(expected), "FileService has the exact nine methods in order");
        foreach (var method in service.Methods)
            Require(!method.IsClientStreaming && !method.IsServerStreaming
                && method.InputType.FullName == $"arcforges.node.v1.FileService{method.Name}Request"
                && method.OutputType.FullName == $"arcforges.node.v1.FileService{method.Name}Response",
                method.Name + ": exact FileService signature");
    }

    private static void PathsAndRequests()
    {
        Require(NodeShapes.IsValid(Path()), "relative file path");
        Require(NodeShapes.IsValid(Path("")), "explicit root is a valid FilePath for list/search");
        var absentPath = new FilePath { WorkspaceId = Id() };
        Require(!NodeShapes.IsValid(absentPath), "missing path differs from an explicit empty root");
        Require(!NodeShapes.IsValid(new FilePath { Path = "a" }), "workspace ID is required");
        foreach (var path in new[] { "/absolute", "C:/absolute", "../x", "x/../y", "./x", "x//y", "x/", @"x\y", "x\0y", "\ud800" })
            Require(!NodeShapes.IsValid(Path(path)), "reject invalid path " + path.Length);
        Require(NodeShapes.IsValid(Path(new string('é', 2048))), "4096 UTF-8 path bytes accepted");
        Require(!NodeShapes.IsValid(Path(new string('é', 2049))), "4098 UTF-8 path bytes rejected");
        var unicode = Path("目录/😀.txt");
        var unicodeWire = unicode.ToByteArray();
        Require(FilePath.Parser.ParseFrom(unicodeWire).Equals(unicode), "Unicode path protobuf round trip");

        var read = new FileServiceReadFileRequest { Path = Path(), Offset = 0, Length = 1 };
        Require(NodeShapes.IsValid(read), "read with present zero offset");
        Require(!NodeShapes.IsValid(new FileServiceReadFileRequest { Path = Path(), Length = 1 }), "read offset presence");
        Require(!NodeShapes.IsValid(new FileServiceReadFileRequest { Path = Path(), Offset = 0 }), "read length presence");
        Require(!NodeShapes.IsValid(new FileServiceReadFileRequest { Path = Path(), Offset = 0, Length = 0 }), "zero read length");
        Require(!NodeShapes.IsValid(new FileServiceReadFileRequest { Path = Path(""), Offset = 0, Length = 1 }), "read refuses root");

        var write = new FileServiceWriteFileRequest { Meta = MutationMeta(), Path = Path(), Data = ByteString.Empty, ExpectedAbsent = true };
        Require(NodeShapes.IsValid(write), "present empty bytes and expected absence");
        Require(FileServiceWriteFileRequest.Parser.ParseFrom(write.ToByteArray()).HasData, "empty write data presence survives codec");
        Require(!NodeShapes.IsValid(new FileServiceWriteFileRequest { Meta = MutationMeta(), Path = Path(), ExpectedAbsent = true }), "missing write data");
        Require(!NodeShapes.IsValid(new FileServiceWriteFileRequest { Meta = MutationMeta(), Path = Path(), Data = ByteString.Empty }), "missing precondition");
        Require(!NodeShapes.IsValid(new FileServiceWriteFileRequest { Meta = MutationMeta(), Path = Path(), Data = ByteString.Empty, ExpectedAbsent = false }), "expectedAbsent must be true");
        Require(!NodeShapes.IsValid(new FileServiceWriteFileRequest { Path = Path(), Data = ByteString.Empty, ExpectedAbsent = true }), "write requires command ID");
        Require(!NodeShapes.IsValid(new FileServiceWriteFileRequest { Meta = MutationMeta(), Path = Path(""), Data = ByteString.Empty, ExpectedAbsent = true }), "write refuses root");
        Require(NodeShapes.IsValid(new FileServiceWriteFileRequest { Meta = MutationMeta(), Path = Path(), Data = ByteString.Empty, ExpectedSha256 = Bytes(32) }), "32-byte expected hash");
        Require(!NodeShapes.IsValid(new FileServiceWriteFileRequest { Meta = MutationMeta(), Path = Path(), Data = ByteString.Empty, ExpectedSha256 = Bytes(31) }), "31-byte expected hash");
        Require(!NodeShapes.IsValid(new FileServiceWriteFileRequest { Meta = MutationMeta(), Path = Path(), Data = ByteString.Empty, ExpectedSha256 = Bytes(33) }), "33-byte expected hash");
        write.Data = Bytes(FileWriteLimit);
        Require(NodeShapes.IsValid(write), "192 KiB write accepted");
        var maxWriteWire = write.ToByteArray();
        Require(NodeShapes.IsValid(FileServiceWriteFileRequest.Parser.ParseFrom(maxWriteWire)), "192 KiB write codec round trip");
        write.Data = Bytes(FileWriteLimit + 1);
        Require(!NodeShapes.IsValid(write), "write above 192 KiB refused");

        // Unknown protobuf fields still count toward the complete serialized-node-request bound.
        var maxEncoded = WithUnknownPayload(maxWriteWire, NodePayloadLimit);
        var overEncoded = WithUnknownPayload(maxWriteWire, NodePayloadLimit + 1);
        var atLimit = FileServiceWriteFileRequest.Parser.ParseFrom(maxEncoded);
        var overLimit = FileServiceWriteFileRequest.Parser.ParseFrom(overEncoded);
        Require(atLimit.CalculateSize() == NodePayloadLimit && NodeShapes.IsValid(atLimit), "245760-byte encoded request accepted");
        Require(overLimit.CalculateSize() == NodePayloadLimit + 1 && !NodeShapes.IsValid(overLimit), "245761-byte encoded request refused");

        var edit = new FileServiceEditFileRequest
        {
            Meta = MutationMeta(), Path = Path(), OldText = "old", NewText = "", ExpectedOccurrences = 1, ExpectedSha256 = Bytes(32),
        };
        Require(NodeShapes.IsValid(edit), "edit permits present empty replacement");
        Require(!NodeShapes.IsValid(new FileServiceEditFileRequest { Meta = MutationMeta(), Path = Path(), OldText = "old", ExpectedOccurrences = 1, ExpectedSha256 = Bytes(32) }), "edit replacement presence");
        Require(!NodeShapes.IsValid(new FileServiceEditFileRequest { Meta = MutationMeta(), Path = Path(), OldText = "", NewText = "", ExpectedOccurrences = 1, ExpectedSha256 = Bytes(32) }), "edit old text nonempty");
        var invalidEdit = edit.Clone();
        invalidEdit.ExpectedOccurrences = 0;
        Require(!NodeShapes.IsValid(invalidEdit), "edit count minimum");
        invalidEdit.ExpectedOccurrences = 1001;
        Require(!NodeShapes.IsValid(invalidEdit), "edit count maximum");
        invalidEdit = edit.Clone();
        invalidEdit.ExpectedSha256 = Bytes(31);
        Require(!NodeShapes.IsValid(invalidEdit), "edit requires 32-byte expected hash");
        invalidEdit = edit.Clone();
        invalidEdit.OldText = new string('é', 32768);
        Require(NodeShapes.IsValid(invalidEdit), "edit old text 65536 UTF-8 bytes accepted");
        invalidEdit.OldText += "é";
        Require(!NodeShapes.IsValid(invalidEdit), "edit old text above 65536 UTF-8 bytes refused");

        var search = new FileServiceSearchFilesRequest { Path = Path(""), Pattern = "x", Mode = FileSearchMode.Literal, MaxMatches = 100, MaxScanBytes = 8_388_608 };
        Require(NodeShapes.IsValid(search), "bounded search accepts root and maxima");
        var badSearch = search.Clone();
        badSearch.MaxMatches = 101;
        Require(!NodeShapes.IsValid(badSearch), "search match maximum");
        badSearch = search.Clone();
        badSearch.MaxScanBytes = 8_388_609;
        Require(!NodeShapes.IsValid(badSearch), "search scan maximum");
        badSearch = search.Clone();
        badSearch.Pattern = new string('é', 513);
        Require(!NodeShapes.IsValid(badSearch), "search pattern UTF-8 maximum");
        var list = new FileServiceListDirectoryRequest { Path = Path(""), PageSize = 128 };
        Require(NodeShapes.IsValid(list), "bounded root listing");
        list.PageSize = 129;
        Require(!NodeShapes.IsValid(list), "listing page maximum");

        var plan = new FileServicePlanRemovalRequest { Meta = MutationMeta(), WorkspacePath = Path() };
        Require(NodeShapes.IsValid(plan), "workspace removal target");
        plan.AttemptId = Id();
        Require(plan.TargetCase == FileServicePlanRemovalRequest.TargetOneofCase.AttemptId && NodeShapes.IsValid(plan), "attempt replaces workspace oneof target");
        plan.ClearTarget();
        Require(!NodeShapes.IsValid(plan), "removal plan requires a target");
        plan.WorkspacePath = Path("");
        Require(!NodeShapes.IsValid(plan), "removal cannot plan the workspace root");
        var execute = new FileServiceExecuteRemovalRequest { Meta = MutationMeta(), PlanId = Id(), PlanDigest = Bytes(32) };
        Require(NodeShapes.IsValid(execute), "execute exact plan");
        execute.PlanDigest = Bytes(31);
        Require(!NodeShapes.IsValid(execute), "execute plan digest length");
        var get = new FileServiceGetFileOperationRequest { OperationCommandId = Id() };
        Require(NodeShapes.IsValid(get), "operation lookup requires command ID");
        get.OperationCommandId = null;
        Require(!NodeShapes.IsValid(get), "lookup without target command");
        var ack = new FileServiceAcknowledgeFileOperationRequest { Meta = MutationMeta(), OperationCommandId = Id(), OperationDigest = Bytes(32) };
        Require(NodeShapes.IsValid(ack), "acknowledgment binds operation ID and digest");
        ack.OperationDigest = Bytes(31);
        Require(!NodeShapes.IsValid(ack), "acknowledgment digest length");
    }

    private static void ReadCommandPresence()
    {
        NodeRead(new FileServiceReadFileRequest { Path = Path(), Offset = 0, Length = 1 }, NodeShapes.IsValid);
        NodeRead(new FileServiceSearchFilesRequest { Path = Path(""), Pattern = "a", Mode = FileSearchMode.Literal }, NodeShapes.IsValid);
        NodeRead(new FileServiceListDirectoryRequest { Path = Path("") }, NodeShapes.IsValid);
        NodeRead(new FileServiceGetFileOperationRequest { OperationCommandId = Id() }, NodeShapes.IsValid);
        NodeRead(new WorkspaceServiceListWorkspacesRequest(), NodeShapes.IsValid);
        NodeRead(new WorkspaceServiceGetWorkspaceRequest { WorkspaceId = Id() }, NodeShapes.IsValid);
    }

    private static void NodeRead<T>(T request, Func<T, bool> valid) where T : class, IMessage<T>
    {
        var descriptor = ((IMessage)request).Descriptor;
        var meta = descriptor.FindFieldByNumber(1).Accessor;
        var label = descriptor.Name;
        Require(valid(request), label + ": read without metadata");
        meta.SetValue(request, new RequestMeta { CorrelationId = Id() });
        Require(valid(request), label + ": read with correlation and no command");
        meta.SetValue(request, MutationMeta());
        Require(!valid(request), label + ": read cannot carry command ID");
    }

    private static void WorkspaceContracts()
    {
        var register = new WorkspaceServiceRegisterWorkspaceRequest { Meta = MutationMeta(), Path = "/synthetic/workspace" };
        Require(NodeShapes.IsValid(register), "workspace register with command and path");
        Require(NodeShapes.IsValid(WorkspaceServiceRegisterWorkspaceRequest.Parser.ParseFrom(register.ToByteArray())), "workspace register codec round trip");
        var badRegister = register.Clone();
        badRegister.Meta = null;
        Require(!NodeShapes.IsValid(badRegister), "workspace register requires mutation command");
        badRegister = register.Clone();
        badRegister.Meta.CommandId = null;
        Require(!NodeShapes.IsValid(badRegister), "workspace register cannot omit command ID");
        badRegister = register.Clone();
        badRegister.ClearPath();
        Require(!NodeShapes.IsValid(badRegister), "workspace register requires path presence");
        badRegister.Path = "";
        Require(!NodeShapes.IsValid(badRegister), "workspace register requires nonempty path");
        badRegister.Path = "/" + new string('a', 4095);
        Require(NodeShapes.IsValid(badRegister), "workspace path 4096 UTF-8 bytes");
        badRegister.Path += "a";
        Require(!NodeShapes.IsValid(badRegister), "workspace path above 4096 UTF-8 bytes");
        badRegister.Path = "/" + new string('é', 2048);
        Require(!NodeShapes.IsValid(badRegister), "workspace path bound counts UTF-8 bytes");
        badRegister = register.Clone();
        badRegister.Name = new string('x', 100);
        Require(NodeShapes.IsValid(badRegister), "workspace name 100 characters");
        badRegister.Name += "x";
        Require(!NodeShapes.IsValid(badRegister), "workspace name above 100 characters");

        var unregister = new WorkspaceServiceUnregisterWorkspaceRequest { Meta = MutationMeta(), WorkspaceId = Id() };
        Require(NodeShapes.IsValid(unregister), "workspace unregister with command and ID");
        var badUnregister = unregister.Clone();
        badUnregister.Meta = null;
        Require(!NodeShapes.IsValid(badUnregister), "workspace unregister requires mutation command");
        badUnregister = unregister.Clone();
        badUnregister.WorkspaceId = null;
        Require(!NodeShapes.IsValid(badUnregister), "workspace unregister requires ID");

        var list = new WorkspaceServiceListWorkspacesRequest();
        list.Kinds.Add(WorkspaceKind.Registered);
        list.Kinds.Add(WorkspaceKind.ManagedWorktree);
        list.Kinds.Add(WorkspaceKind.Remote);
        Require(NodeShapes.IsValid(list), "workspace list accepts three distinct supported kinds");
        var badList = list.Clone();
        badList.Kinds.Add(WorkspaceKind.Registered);
        Require(!NodeShapes.IsValid(badList), "workspace list rejects fourth or duplicate kind");
        badList = list.Clone();
        badList.Kinds[1] = WorkspaceKind.Registered;
        Require(!NodeShapes.IsValid(badList), "workspace list rejects duplicate kinds");
        badList = list.Clone();
        badList.Kinds[0] = WorkspaceKind.Unspecified;
        Require(!NodeShapes.IsValid(badList), "workspace list rejects unspecified kind");
        badList.Kinds[0] = (WorkspaceKind)99;
        Require(!NodeShapes.IsValid(badList), "workspace list rejects unknown kind");
        Require(!NodeShapes.IsValid(new WorkspaceServiceGetWorkspaceRequest()), "workspace get requires ID");
        Require(NodeShapes.IsValid(new WorkspaceServiceGetWorkspaceRequest { WorkspaceId = Id() }), "workspace get with ID");

        var workspace = new Workspace
        {
            WorkspaceId = Id(), Kind = WorkspaceKind.Registered, State = WorkspaceState.Active,
            Name = "sample", RootPath = "/synthetic/workspace", CreatedAt = new Instant { UnixSeconds = 100, Nanos = 0 },
        };
        var receipt = new Receipt { CommandId = Id(), Effect = EffectCertainty.Happened };
        Require(!NodeShapes.IsValid(new WorkspaceServiceRegisterWorkspaceResponse()), "register response requires outcome");
        Require(!NodeShapes.IsValid(new WorkspaceServiceRegisterWorkspaceResponse { Value = new WorkspaceServiceRegisterWorkspaceValue() }), "register value requires workspace");
        Require(NodeShapes.IsValid(new WorkspaceServiceRegisterWorkspaceResponse { Value = new WorkspaceServiceRegisterWorkspaceValue { Workspace = workspace } }), "register value with workspace");
        Require(!NodeShapes.IsValid(new WorkspaceServiceUnregisterWorkspaceResponse()), "unregister response requires outcome");
        Require(!NodeShapes.IsValid(new WorkspaceServiceUnregisterWorkspaceResponse { Value = new WorkspaceServiceUnregisterWorkspaceValue() }), "unregister value requires receipt");
        Require(NodeShapes.IsValid(new WorkspaceServiceUnregisterWorkspaceResponse { Value = new WorkspaceServiceUnregisterWorkspaceValue { Receipt = receipt } }), "unregister value with receipt");
        Require(!NodeShapes.IsValid(new WorkspaceServiceGetWorkspaceResponse()), "workspace get response requires outcome");
        Require(!NodeShapes.IsValid(new WorkspaceServiceGetWorkspaceResponse { Value = new WorkspaceServiceGetWorkspaceValue() }), "get value requires workspace");
        Require(NodeShapes.IsValid(new WorkspaceServiceGetWorkspaceResponse { Value = new WorkspaceServiceGetWorkspaceValue { Workspace = workspace } }), "get value with workspace");
        Require(!NodeShapes.IsValid(new WorkspaceServiceListWorkspacesResponse()), "workspace list response requires outcome");
        var listValue = new WorkspaceServiceListWorkspacesValue();
        for (var i = 0; i < 500; i++) listValue.Workspaces.Add(workspace.Clone());
        var listResponse = new WorkspaceServiceListWorkspacesResponse { Value = listValue };
        Require(NodeShapes.IsValid(listResponse), "workspace list accepts 500 records");
        listValue.Workspaces.Add(workspace.Clone());
        Require(!NodeShapes.IsValid(listResponse), "workspace list refuses more than 500 records");

        // Unknown wire fields count toward the complete response limit, not merely the list items.
        var minimal = new WorkspaceServiceListWorkspacesResponse { Value = new WorkspaceServiceListWorkspacesValue() }.ToByteArray();
        var atSize = WorkspaceServiceListWorkspacesResponse.Parser.ParseFrom(WithUnknownPayload(minimal, 131_072));
        var aboveSize = WorkspaceServiceListWorkspacesResponse.Parser.ParseFrom(WithUnknownPayload(minimal, 131_073));
        Require(atSize.CalculateSize() == 131_072 && NodeShapes.IsValid(atSize), "workspace list accepts encoded 131072-byte response");
        Require(aboveSize.CalculateSize() == 131_073 && !NodeShapes.IsValid(aboveSize), "workspace list rejects encoded 131073-byte response");
        var error = new ArcError
        {
            Code = "operation_failed", Category = ErrorCategory.Execution, MessageKey = "error.execution.operation_failed",
            Retry = new RetryAdvice { Mode = RetryMode.Never }, Effect = EffectCertainty.DidNotHappen, CorrelationId = Id(),
        };
        Require(NodeShapes.IsValid(new WorkspaceServiceRegisterWorkspaceResponse { Error = error }), "register error outcome");
        Require(NodeShapes.IsValid(new WorkspaceServiceUnregisterWorkspaceResponse { Error = error }), "unregister error outcome");
        Require(NodeShapes.IsValid(new WorkspaceServiceListWorkspacesResponse { Error = error }), "list error outcome");
        Require(NodeShapes.IsValid(new WorkspaceServiceGetWorkspaceResponse { Error = error }), "get error outcome");
    }

    private static void GitSummaryQuality()
    {
        var legacy = new GitStatusSummary { Branch = "main", Dirty = false, ModifiedFiles = 0 };
        Require(!legacy.HasQuality && NodeShapes.IsValid(legacy), "legacy Git summary remains valid without quality");
        Require(NodeShapes.IsValid(new Workspace { WorkspaceId = Id(), Git = legacy }), "legacy generic Workspace remains valid");
        Require(!GitStatusSummary.Parser.ParseFrom(legacy.ToByteArray()).HasQuality, "legacy missing quality survives wire");

        var complete = new GitStatusSummary
        {
            Quality = GitStatusQuality.Complete, Dirty = false, ModifiedFiles = 0, UntrackedFiles = 0, Locked = false,
        };
        var unknown = new GitStatusSummary { Quality = GitStatusQuality.Unknown, Branch = "main", Head = "abc" };
        var truncated = new GitStatusSummary { Quality = GitStatusQuality.Truncated, Branch = "main", Head = "abc" };
        Require(NodeShapes.IsValid(complete) && NodeShapes.IsValid(unknown) && NodeShapes.IsValid(truncated), "three explicit Git qualities");
        Require(GitStatusSummary.Parser.ParseFrom(complete.ToByteArray()).Quality == GitStatusQuality.Complete, "complete Git quality wire");
        Require(GitStatusSummary.Parser.ParseFrom(unknown.ToByteArray()).Quality == GitStatusQuality.Unknown, "unknown Git quality wire");
        Require(GitStatusSummary.Parser.ParseFrom(truncated.ToByteArray()).Quality == GitStatusQuality.Truncated, "truncated Git quality wire");

        Action<GitStatusSummary>[] dropRequired =
        [
            git => git.ClearDirty(), git => git.ClearModifiedFiles(), git => git.ClearUntrackedFiles(), git => git.ClearLocked(),
        ];
        foreach (var drop in dropRequired)
        {
            var invalid = complete.Clone();
            drop(invalid);
            Require(!NodeShapes.IsValid(invalid), "complete Git summary requires all four declared fields");
        }
        Action<GitStatusSummary>[] addPartial =
        [
            git => git.Dirty = false, git => git.ModifiedFiles = 0, git => git.UntrackedFiles = 0,
            git => git.Ahead = 0, git => git.Behind = 0, git => git.MergedIntoBase = false,
            git => git.UpstreamDeleted = false, git => git.Locked = false,
        ];
        foreach (var status in new[] { unknown, truncated })
            foreach (var add in addPartial)
            {
                var invalid = status.Clone();
                add(invalid);
                Require(!NodeShapes.IsValid(invalid), "incomplete Git summary cannot present a boolean or count");
            }
        var optional = complete.Clone();
        optional.Branch = "main";
        optional.Head = "abc";
        optional.Ahead = 0;
        optional.Behind = 0;
        optional.MergedIntoBase = false;
        optional.UpstreamDeleted = false;
        Require(NodeShapes.IsValid(optional), "complete Git summary may include optional independently applicable fields");

        var workspace = new Workspace { WorkspaceId = Id() };
        void Projections(bool valid, string label)
        {
            var register = new WorkspaceServiceRegisterWorkspaceValue { Workspace = workspace };
            var get = new WorkspaceServiceGetWorkspaceValue { Workspace = workspace };
            var list = new WorkspaceServiceListWorkspacesValue { Workspaces = { workspace } };
            Require(NodeShapes.IsValid(register) == valid, label + ": register projection");
            Require(NodeShapes.IsValid(get) == valid, label + ": get projection");
            Require(NodeShapes.IsValid(list) == valid, label + ": list projection");
            var response = new WorkspaceServiceListWorkspacesResponse { Value = list };
            if (valid)
                Require(NodeShapes.IsValid(WorkspaceServiceListWorkspacesResponse.Parser.ParseFrom(response.ToByteArray())), label + ": list wire round trip");
        }
        workspace.Git = null;
        Projections(true, "no summary wire shape; non-git still requires runtime proof");
        workspace.Git = complete;
        Projections(true, "complete quality");
        workspace.Git = unknown;
        Projections(true, "unknown quality");
        workspace.Git = truncated;
        Projections(true, "truncated quality");
        workspace.Git = legacy;
        Projections(false, "legacy absent quality cannot count as complete in activated projection");
        workspace.Git = new GitStatusSummary { Quality = GitStatusQuality.Unspecified };
        Projections(false, "unspecified quality refused in activated projection");
        workspace.Git = new GitStatusSummary { Quality = (GitStatusQuality)99 };
        Projections(false, "unknown quality number refused in activated projection");
    }

    private static void ReadValues()
    {
        var data = ByteString.CopyFromUtf8("abc");
        var result = new FileServiceReadFileValue
        {
            Data = data, Offset = 42, NextOffset = 45, Eof = false, FileSize = 100,
            Sha256 = ByteString.CopyFrom(SHA256.HashData(data.Span)),
        };
        Require(NodeShapes.IsValid(result), "read result matches actual bytes and next offset");
        Require(NodeShapes.IsValid(FileServiceReadFileValue.Parser.ParseFrom(result.ToByteArray())), "read value codec round trip");
        var bad = result.Clone();
        bad.NextOffset = 44;
        Require(!NodeShapes.IsValid(bad), "read next offset mismatch");
        bad = result.Clone();
        bad.Sha256 = Bytes(32);
        Require(!NodeShapes.IsValid(bad), "read digest does not match actual bytes");
        bad = result.Clone();
        bad.Sha256 = Bytes(31);
        Require(!NodeShapes.IsValid(bad), "read digest length");
        bad = result.Clone();
        bad.Offset = ulong.MaxValue - 2;
        bad.NextOffset = 0;
        bad.FileSize = ulong.MaxValue;
        Require(!NodeShapes.IsValid(bad), "read offset addition overflow refused");
        bad = result.Clone();
        bad.Offset = ulong.MaxValue - 3;
        bad.NextOffset = ulong.MaxValue;
        bad.FileSize = ulong.MaxValue;
        bad.Eof = true;
        Require(NodeShapes.IsValid(bad), "read offset addition exactly at uint64 maximum");
        bad = result.Clone();
        bad.FileSize = 44;
        Require(!NodeShapes.IsValid(bad), "read data cannot extend beyond file size");
        bad = result.Clone();
        bad.Eof = true;
        Require(!NodeShapes.IsValid(bad), "read cannot report EOF before its file size");
        bad = result.Clone();
        bad.Offset = 100;
        bad.NextOffset = 103;
        bad.Eof = true;
        Require(!NodeShapes.IsValid(bad), "read at EOF must return no data");
        var empty = new FileServiceReadFileValue
        {
            Data = ByteString.Empty, Offset = 0, NextOffset = 0, Eof = true, FileSize = 0,
            Sha256 = ByteString.CopyFrom(SHA256.HashData(Array.Empty<byte>())),
        };
        Require(NodeShapes.IsValid(empty), "zero-byte EOF and SHA-256 of empty content");
        var beyond = empty.Clone();
        beyond.Offset = 7;
        beyond.NextOffset = 7;
        Require(NodeShapes.IsValid(beyond), "offset beyond EOF remains unchanged with empty data");
        var noProgress = empty.Clone();
        noProgress.FileSize = 1;
        noProgress.Eof = false;
        Require(!NodeShapes.IsValid(noProgress), "non-EOF read cannot claim zero progress");
        var falseEof = result.Clone();
        falseEof.FileSize = 45;
        Require(!NodeShapes.IsValid(falseEof), "read at file size must report EOF");
        empty.ClearData();
        Require(!NodeShapes.IsValid(empty), "read data presence even for empty bytes");
    }

    private static void Operations()
    {
        var operation = new FileOperation
        {
            CommandId = Id(), Kind = FileOperationKind.Write, State = FileOperationState.Prepared,
            RequestSha256 = Bytes(32), CreatedAt = new Instant { UnixSeconds = 100, Nanos = 0 },
            UpdatedAt = new Instant { UnixSeconds = 101, Nanos = 0 },
            WorkspacePath = Path(), Acknowledged = false, Held = true,
        };
        Require(NodeShapes.IsValid(operation), "prepared operation with no outcome");
        var invalid = operation.Clone();
        invalid.Acknowledged = true;
        Require(!NodeShapes.IsValid(invalid), "prepared operation cannot be acknowledged");
        operation.State = FileOperationState.Completed;
        operation.Held = false;
        operation.Mutation = new FileMutationResult { CommandId = Id(), SizeBytes = 0, Sha256 = Bytes(32) };
        Require(NodeShapes.IsValid(operation), "completed mutation with outcome and no hold");
        Require(NodeShapes.IsValid(FileOperation.Parser.ParseFrom(operation.ToByteArray())), "completed operation codec round trip");
        invalid = operation.Clone();
        invalid.ClearOutcome();
        Require(!NodeShapes.IsValid(invalid), "completed requires outcome");
        invalid = operation.Clone();
        invalid.Held = true;
        Require(!NodeShapes.IsValid(invalid), "completed cannot retain a hold");
        invalid = operation.Clone();
        invalid.Acknowledged = true;
        Require(!NodeShapes.IsValid(invalid), "completed cannot be acknowledged as unknown");
        invalid = operation.Clone();
        invalid.Kind = FileOperationKind.Removal;
        Require(!NodeShapes.IsValid(invalid), "removal cannot carry mutation result");

        operation.State = FileOperationState.Unknown;
        operation.Held = true;
        operation.Acknowledged = false;
        operation.Error = new ArcError
        {
            Code = "operation_failed", Category = ErrorCategory.Execution, MessageKey = "error.execution.operation_failed",
            Retry = new RetryAdvice { Mode = RetryMode.Never }, Effect = EffectCertainty.Unknown, CorrelationId = Id(),
        };
        Require(NodeShapes.IsValid(operation), "unknown carries uncertain error and active hold");
        invalid = operation.Clone();
        invalid.State = FileOperationState.Completed;
        invalid.Held = false;
        Require(!NodeShapes.IsValid(invalid), "completed operation cannot carry an UNKNOWN effect");
        invalid = operation.Clone();
        invalid.Held = false;
        Require(!NodeShapes.IsValid(invalid), "unacknowledged unknown cannot drop hold");
        invalid = operation.Clone();
        invalid.Acknowledged = true;
        Require(!NodeShapes.IsValid(invalid), "acknowledged unknown cannot retain hold");
        invalid = operation.Clone();
        invalid.Error.Effect = EffectCertainty.DidNotHappen;
        Require(!NodeShapes.IsValid(invalid), "unknown cannot claim DID_NOT_HAPPEN");
        invalid = operation.Clone();
        invalid.Mutation = new FileMutationResult { CommandId = Id(), SizeBytes = 0, Sha256 = Bytes(32) };
        Require(!NodeShapes.IsValid(invalid), "unknown cannot claim a mutation result");
        operation.Acknowledged = true;
        operation.Held = false;
        Require(NodeShapes.IsValid(operation) && operation.State == FileOperationState.Unknown, "acknowledgment releases hold without changing uncertainty");
        Require(FileOperation.Parser.ParseFrom(operation.ToByteArray()).State == FileOperationState.Unknown, "unknown state survives protobuf");
    }

    private static FileAuditObservation Observation(FileAuditKind kind) => new()
    {
        Kind = kind, SizeBytes = 0, Sha256 = Bytes(32), DigestInputBytes = 0, ItemCount = 0,
    };

    private static void Audit()
    {
        var audit = new FileAuditMetadata();
        audit.Observations.Add(Observation(FileAuditKind.ReadBytes));
        audit.Observations.Add(Observation(FileAuditKind.SearchTranscript));
        Require(NodeShapes.IsValid(audit), "distinct audit kinds");
        Require(NodeShapes.IsValid(FileAuditMetadata.Parser.ParseFrom(audit.ToByteArray())), "audit codec round trip");
        audit.Observations.Add(Observation(FileAuditKind.ReadBytes));
        Require(!NodeShapes.IsValid(audit), "duplicate audit kind refused");
        audit.Observations.Clear();
        audit.Observations.Add(Observation(FileAuditKind.ReadBytes));
        audit.Observations.Add(Observation(FileAuditKind.InputBytes));
        audit.Observations.Add(Observation(FileAuditKind.WrittenBytes));
        audit.Observations.Add(Observation(FileAuditKind.SearchTranscript));
        Require(NodeShapes.IsValid(audit), "four distinct audit observations");
        audit.Observations.Add(Observation(FileAuditKind.DirectoryMetadata));
        Require(!NodeShapes.IsValid(audit), "fifth audit observation refused");
        var item = Observation(FileAuditKind.ReadBytes);
        item.Sha256 = Bytes(31);
        Require(!NodeShapes.IsValid(item), "audit digest length");
        item = Observation(FileAuditKind.Unspecified);
        Require(!NodeShapes.IsValid(item), "audit kind is closed");

        // Independent empty-transcript vector from Design 06a, including the terminating NUL.
        var emptyTranscript = "ArcForges search-scan v1\0"u8.ToArray();
        var emptyDigest = SHA256.HashData(emptyTranscript);
        Require(emptyTranscript.Length == 25
            && Convert.ToHexStringLower(emptyDigest) == "3f0e0a01dc6c80ced277ce0283faa0a621a0be218e30d1759a19b07a49e7614c",
            "empty search transcript vector");
        var search = new FileServiceSearchFilesValue
        {
            VisitedEntries = 0, ScannedBytes = 0, SkippedFiles = 0, Truncated = false,
            ScanDigest = ByteString.CopyFrom(emptyDigest), ScanTranscriptBytes = 25, ScanFileCount = 0,
        };
        Require(NodeShapes.IsValid(search), "zero-byte search carries mandatory transcript digest and counts");
        var badSearch = search.Clone();
        badSearch.ClearScanDigest();
        Require(!NodeShapes.IsValid(badSearch), "search transcript digest presence");
        badSearch = search.Clone();
        badSearch.ScanDigest = Bytes(31);
        Require(!NodeShapes.IsValid(badSearch), "search transcript digest length");
        badSearch = search.Clone();
        badSearch.ScanTranscriptBytes = 24;
        Require(!NodeShapes.IsValid(badSearch), "search transcript includes domain and NUL");
        badSearch = search.Clone();
        badSearch.Truncated = true;
        Require(!NodeShapes.IsValid(badSearch), "truncated search must give a reason");
        badSearch.TruncationReason = "";
        Require(!NodeShapes.IsValid(badSearch), "truncated search reason cannot be empty");
        badSearch.TruncationReason = "byte_limit";
        Require(NodeShapes.IsValid(badSearch), "truncated search with explicit reason");

        var searchAudit = new FileAuditMetadata();
        searchAudit.Observations.Add(new FileAuditObservation
        {
            Kind = FileAuditKind.SearchTranscript, SizeBytes = 0, Sha256 = ByteString.CopyFrom(emptyDigest),
            DigestInputBytes = 25, ItemCount = 0,
        });
        var response = new FileServiceSearchFilesResponse { Value = search, Audit = searchAudit };
        Require(NodeShapes.IsValid(response), "successful search carries audit outside its outcome");
        response.Error = new ArcError
        {
            Code = "operation_failed", Category = ErrorCategory.Execution, MessageKey = "error.execution.operation_failed",
            Retry = new RetryAdvice { Mode = RetryMode.Never }, Effect = EffectCertainty.DidNotHappen, CorrelationId = Id(),
        };
        Require(NodeShapes.IsValid(response) && response.Audit is not null, "error may carry observed audit outside outcome");
        var decoded = FileServiceSearchFilesResponse.Parser.ParseFrom(response.ToByteArray());
        Require(NodeShapes.IsValid(decoded) && decoded.Audit.Observations.Count == 1, "error and audit codec round trip");
    }

    private static void RoutedRequests()
    {
        Routed(new FleetServiceReadNodeFileRequest(), FleetServiceReadNodeFileRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new FileServiceReadFileRequest { Path = Path(), Offset = 0, Length = 1 }, FileServiceReadFileRequest.Parser, NodeShapes.IsValid), false);
        Routed(new FleetServiceWriteNodeFileRequest(), FleetServiceWriteNodeFileRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new FileServiceWriteFileRequest { Meta = MutationMeta(), Path = Path(), Data = ByteString.Empty, ExpectedAbsent = true }, FileServiceWriteFileRequest.Parser, NodeShapes.IsValid), true);
        Routed(new FleetServiceEditNodeFileRequest(), FleetServiceEditNodeFileRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new FileServiceEditFileRequest { Meta = MutationMeta(), Path = Path(), OldText = "a", NewText = "b", ExpectedOccurrences = 1, ExpectedSha256 = Bytes(32) }, FileServiceEditFileRequest.Parser, NodeShapes.IsValid), true);
        Routed(new FleetServiceSearchNodeFilesRequest(), FleetServiceSearchNodeFilesRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new FileServiceSearchFilesRequest { Path = Path(""), Pattern = "a", Mode = FileSearchMode.Literal }, FileServiceSearchFilesRequest.Parser, NodeShapes.IsValid), false);
        Routed(new FleetServiceListNodeDirectoryRequest(), FleetServiceListNodeDirectoryRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new FileServiceListDirectoryRequest { Path = Path("") }, FileServiceListDirectoryRequest.Parser, NodeShapes.IsValid), false);
        Routed(new FleetServicePlanNodeRemovalRequest(), FleetServicePlanNodeRemovalRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new FileServicePlanRemovalRequest { Meta = MutationMeta(), WorkspacePath = Path() }, FileServicePlanRemovalRequest.Parser, NodeShapes.IsValid), true);
        Routed(new FleetServiceExecuteNodeRemovalRequest(), FleetServiceExecuteNodeRemovalRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new FileServiceExecuteRemovalRequest { Meta = MutationMeta(), PlanId = Id(), PlanDigest = Bytes(32) }, FileServiceExecuteRemovalRequest.Parser, NodeShapes.IsValid), true);
        Routed(new FleetServiceGetNodeFileOperationRequest(), FleetServiceGetNodeFileOperationRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new FileServiceGetFileOperationRequest { OperationCommandId = Id() }, FileServiceGetFileOperationRequest.Parser, NodeShapes.IsValid), false);
        Routed(new FleetServiceRegisterNodeWorkspaceRequest(), FleetServiceRegisterNodeWorkspaceRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new WorkspaceServiceRegisterWorkspaceRequest { Meta = MutationMeta(), Path = "/synthetic/test" }, WorkspaceServiceRegisterWorkspaceRequest.Parser, NodeShapes.IsValid), true);
        Routed(new FleetServiceUnregisterNodeWorkspaceRequest(), FleetServiceUnregisterNodeWorkspaceRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new WorkspaceServiceUnregisterWorkspaceRequest { Meta = MutationMeta(), WorkspaceId = Id() }, WorkspaceServiceUnregisterWorkspaceRequest.Parser, NodeShapes.IsValid), true);
        Routed(new FleetServiceListNodeWorkspacesRequest(), FleetServiceListNodeWorkspacesRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new WorkspaceServiceListWorkspacesRequest { Meta = new RequestMeta { CorrelationId = Id() } }, WorkspaceServiceListWorkspacesRequest.Parser, NodeShapes.IsValid), false);
        Routed(new FleetServiceGetNodeWorkspaceRequest(), FleetServiceGetNodeWorkspaceRequest.Parser, FleetShapes.IsValid,
            NodeBlob(new WorkspaceServiceGetWorkspaceRequest { WorkspaceId = Id() }, WorkspaceServiceGetWorkspaceRequest.Parser, NodeShapes.IsValid), false);
    }

    private static ByteString NodeBlob<T>(T value, MessageParser<T> parser, Func<T, bool> valid) where T : class, IMessage<T>
    {
        var label = ((IMessage)value).Descriptor.Name;
        Require(valid(value), label + ": valid typed node payload");
        var bytes = value.ToByteArray();
        Require(bytes.Length > 0, label + ": nonempty encoded node payload");
        var decoded = parser.ParseFrom(bytes);
        Require(valid(decoded) && decoded.Equals(value), label + ": typed node payload codec round trip");
        return ByteString.CopyFrom(bytes);
    }

    private static void Routed<T>(T request, MessageParser<T> parser, Func<T, bool> valid, ByteString nodePayload, bool mutation)
        where T : class, IMessage<T>
    {
        var descriptor = ((IMessage)request).Descriptor;
        var meta = descriptor.FindFieldByNumber(1).Accessor;
        var node = descriptor.FindFieldByNumber(10).Accessor;
        var caller = descriptor.FindFieldByNumber(11).Accessor;
        var payload = descriptor.FindFieldByNumber(12).Accessor;
        var assertion = descriptor.FindFieldByNumber(13).Accessor;
        var label = descriptor.Name;
        meta.SetValue(request, mutation ? MutationMeta() : new RequestMeta { CorrelationId = Id() });
        node.SetValue(request, Id());
        payload.SetValue(request, nodePayload);
        Require(valid(request), label + ": account session sends neither caller nor assertion");
        if (mutation)
        {
            meta.Clear(request);
            Require(!valid(request), label + ": mutation requires outer metadata");
            meta.SetValue(request, new RequestMeta { CorrelationId = Id() });
            Require(!valid(request), label + ": mutation requires outer command ID");
            meta.SetValue(request, MutationMeta());
            Require(valid(request), label + ": mutation with outer command ID");
        }
        else
        {
            meta.Clear(request);
            Require(valid(request), label + ": read may omit metadata");
            meta.SetValue(request, MutationMeta());
            Require(!valid(request), label + ": read cannot carry a command ID");
            meta.SetValue(request, new RequestMeta { CorrelationId = Id() });
            Require(valid(request), label + ": read with correlation and no command");
        }
        caller.SetValue(request, new RoutedCaller { Kind = CallerKind.NodeRelay, RelayingNodeId = Id(), LocalOrigin = Origin.Human });
        Require(!valid(request), label + ": caller without assertion refused");
        assertion.SetValue(request, Bytes(1));
        Require(valid(request), label + ": paired caller and assertion");
        var decoded = parser.ParseFrom(request.ToByteArray());
        Require(valid(decoded) && ((ByteString)payload.GetValue(decoded)).Equals(nodePayload),
            label + ": fleet codec preserves the exact generated node payload bytes");
        caller.Clear(request);
        Require(!valid(request), label + ": assertion without caller refused");
        caller.SetValue(request, new RoutedCaller { Kind = CallerKind.NodeRelay, RelayingNodeId = Id(), LocalOrigin = Origin.Human });
        assertion.SetValue(request, ByteString.Empty);
        Require(!valid(request), label + ": empty assertion refused");
        assertion.SetValue(request, Bytes(512));
        Require(valid(request), label + ": 512-byte assertion accepted");
        assertion.SetValue(request, Bytes(513));
        Require(!valid(request), label + ": 513-byte assertion refused");
        assertion.Clear(request);
        caller.Clear(request);
        payload.SetValue(request, ByteString.Empty);
        Require(!valid(request), label + ": empty node payload refused");
        payload.SetValue(request, Bytes(NodePayloadLimit));
        caller.SetValue(request, new RoutedCaller { Kind = CallerKind.NodeRelay, RelayingNodeId = Id(), LocalOrigin = Origin.Human });
        assertion.SetValue(request, Bytes(512));
        Require(valid(request), label + ": node payload maximum and maximum assertion accepted together");
        Require(request.CalculateSize() < ChannelCallLimit, label + ": outer envelope stays under channel call limit");
        payload.SetValue(request, Bytes(NodePayloadLimit + 1));
        Require(!valid(request), label + ": node payload above maximum refused");
        payload.SetValue(request, nodePayload);
        node.Clear(request);
        Require(!valid(request), label + ": target node required");
    }

    private static void RelayHeadersAndFrames(string root)
    {
        using var fixture = JsonDocument.Parse(File.ReadAllText(System.IO.Path.Combine(root, "fixtures/internal/af-ctr-05-relay-vectors.json")));
        var data = fixture.RootElement;
        var baseCall = CallHeader.Parser.ParseFrom(Hex(data.GetProperty("routedCall"), "callHeader"));
        var baseAssertion = RelayAssertion.Parser.ParseFrom(Hex(data.GetProperty("relayAssertions")[0], "assertion"));
        var baseResult = ResultHeader.Parser.ParseFrom(Hex(data.GetProperty("routedResult"), "resultHeader"));
        RoutedMethod[] methods =
        [
            RoutedMethod.ReadNodeFile, RoutedMethod.WriteNodeFile, RoutedMethod.EditNodeFile, RoutedMethod.SearchNodeFiles,
            RoutedMethod.ListNodeDirectory, RoutedMethod.PlanNodeRemoval, RoutedMethod.ExecuteNodeRemoval,
            RoutedMethod.GetNodeFileOperation, RoutedMethod.RegisterNodeWorkspace, RoutedMethod.UnregisterNodeWorkspace,
            RoutedMethod.ListNodeWorkspaces, RoutedMethod.GetNodeWorkspace,
        ];
        bool[] mutation = [false, true, true, false, false, true, true, false, true, true, false, false];
        for (var i = 0; i < mutation.Length; i++)
        {
            var method = methods[i];
            Require((int)method == 9 + i, method + ": fixed additive method number");
            var call = baseCall.Clone();
            call.Method = method;
            call.CommandId = mutation[i] ? Id() : null;
            Require(RelayShapes.IsValid(call), method + ": call command ID presence");
            Require(RelayShapes.IsValid(CallHeader.Parser.ParseFrom(call.ToByteArray())), method + ": call codec round trip");
            call.CommandId = mutation[i] ? null : Id();
            Require(!RelayShapes.IsValid(call), method + ": wrong call command ID presence refused");

            var assertion = baseAssertion.Clone();
            assertion.Method = method;
            assertion.TargetNodeId = Id();
            assertion.CommandId = mutation[i] ? Id() : null;
            Require(RelayShapes.IsValid(assertion), method + ": assertion command ID presence");
            Require(RelayShapes.IsValid(RelayAssertion.Parser.ParseFrom(assertion.ToByteArray())), method + ": assertion codec round trip");
            assertion.CommandId = mutation[i] ? null : Id();
            Require(!RelayShapes.IsValid(assertion), method + ": wrong assertion command ID presence refused");

            var result = baseResult.Clone();
            result.Method = method;
            result.CommandId = mutation[i] ? Id() : null;
            Require(RelayShapes.IsValid(result), method + ": verified result command ID presence");
            Require(RelayShapes.IsValid(ResultHeader.Parser.ParseFrom(result.ToByteArray())), method + ": result codec round trip");
            result.CommandId = mutation[i] ? null : Id();
            Require(!RelayShapes.IsValid(result), method + ": wrong verified result command ID presence refused");
        }
        // Historical result shapes 1..6 are unchanged; actual call/result equality is a runtime check.
        var legacyResult = baseResult.Clone();
        legacyResult.Method = RoutedMethod.SubmitNodeTask;
        legacyResult.CommandId = null;
        Require(RelayShapes.IsValid(legacyResult), "legacy mutation result shape is not tightened");
        legacyResult.Method = RoutedMethod.GetNodeTask;
        legacyResult.CommandId = Id();
        Require(RelayShapes.IsValid(legacyResult), "legacy read result shape is not tightened");

        var callFrame = RelayFrame.Parser.ParseFrom(Hex(data.GetProperty("routedCall"), "frame"));
        callFrame.Call.Header.Header = Bytes(2048);
        callFrame.Call.Header.Kid = new string('k', 64);
        callFrame.FrameSeq = ulong.MaxValue;
        callFrame.Call.Payload = Bytes(NodePayloadLimit);
        Require(RelayShapes.IsValid(callFrame), "largest file payload has valid channel frame shape");
        Require(callFrame.CalculateSize() <= FrameLimit, "largest file payload and maximum header fit 1 MiB frame");
        Require(RelayFrame.Parser.ParseFrom(callFrame.ToByteArray()).CalculateSize() == callFrame.CalculateSize(), "call frame codec round trip");
        callFrame.Call.Payload = Bytes(ChannelCallLimit);
        Require(RelayShapes.IsValid(callFrame) && callFrame.CalculateSize() <= FrameLimit, "existing maximum channel call fits 1 MiB");
        callFrame.Call.Payload = Bytes(ChannelCallLimit + 1);
        Require(!RelayShapes.IsValid(callFrame), "channel call payload bound");

        var resultFrame = RelayFrame.Parser.ParseFrom(Hex(data.GetProperty("routedResult"), "frame"));
        resultFrame.CallResult.Header.Header = Bytes(2048);
        resultFrame.FrameSeq = ulong.MaxValue;
        resultFrame.CallResult.Payload = Bytes(ChannelResultLimit);
        Require(RelayShapes.IsValid(resultFrame), "maximum result payload has valid frame shape");
        Require(resultFrame.CalculateSize() <= FrameLimit, "maximum result payload and maximum header fit 1 MiB");
        Require(RelayFrame.Parser.ParseFrom(resultFrame.ToByteArray()).CalculateSize() == resultFrame.CalculateSize(), "result frame codec round trip");
        resultFrame.CallResult.Payload = Bytes(ChannelResultLimit + 1);
        Require(!RelayShapes.IsValid(resultFrame), "channel result payload bound");
        var limits = new ChannelLimits
        {
            MaxFrameBytes = FrameLimit, MaxInFlightCalls = 8, HeartbeatIntervalMs = 25_000,
            HeartbeatDeadlineMs = 60_000, MaxRelayNonces = 8,
        };
        Require(RelayShapes.IsValid(limits), "frame limit exactly 1 MiB");
        limits.MaxFrameBytes = FrameLimit + 1;
        Require(!RelayShapes.IsValid(limits), "frame limit cannot be widened");
    }

    private static byte[] WithUnknownPayload(byte[] original, int targetLength)
    {
        // Field 100, length-delimited. The unknown field is intentionally retained by the real codec.
        for (var length = targetLength - original.Length - 7; length <= targetLength - original.Length; length++)
        {
            if (length < 0) continue;
            var prefix = Varint((uint)length);
            if (original.Length + 2 + prefix.Length + length != targetLength) continue;
            using var stream = new MemoryStream(targetLength);
            stream.Write(original);
            stream.WriteByte(0xa2);
            stream.WriteByte(0x06);
            stream.Write(prefix);
            stream.Write(new byte[length]);
            return stream.ToArray();
        }
        throw new InvalidOperationException("Cannot construct encoded request boundary");
    }

    private static byte[] Varint(uint value)
    {
        using var result = new MemoryStream();
        while (value >= 128)
        {
            result.WriteByte((byte)((value & 0x7f) | 0x80));
            value >>= 7;
        }
        result.WriteByte((byte)value);
        return result.ToArray();
    }

    private static byte[] Hex(JsonElement value, string property) => Convert.FromHexString(value.GetProperty(property).GetString()!);

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException("AF-CTR-06: " + message);
    }
}
