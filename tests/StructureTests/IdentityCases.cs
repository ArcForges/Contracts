// SPDX-License-Identifier: Apache-2.0
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using ArcForges.Contracts.Foundation.Serialization;
using ArcForges.Contracts.PublicApi.Http.V1.Browser;
using ArcForges.Contracts.PublicApi.Http.V1.NativeAuth;
using ArcForges.Contracts.PublicApi.V1;
using ArcForges.Contracts.Validation;
using Google.Protobuf;
using Google.Protobuf.Reflection;

/// <summary>CON.07 independent identity, workspace, device and authentication-exception vectors for generated C#.</summary>
internal static class IdentityCases
{
    private delegate bool TryParse<T>(ReadOnlyMemory<byte> input, out T? value, out ContractSerializationFailure failure) where T : class;

    private sealed record Outcome(bool Ok, string Failure, string? Canonical, bool Lossless);

    private static readonly Dictionary<string, Func<string, bool>> Shapes = new(StringComparer.Ordinal)
    {
        ["AccountProfile"] = Shape(AccountProfile.Parser, ContractShapeValidation.IsValid),
        ["ApiTokenView"] = Shape(ApiTokenView.Parser, ContractShapeValidation.IsValid),
        ["AuthChallenge"] = Shape(AuthChallenge.Parser, ContractShapeValidation.IsValid),
        ["AuthProof"] = Shape(AuthProof.Parser, ContractShapeValidation.IsValid),
        ["AuthProviderView"] = Shape(AuthProviderView.Parser, ContractShapeValidation.IsValid),
        ["CredentialReplacement"] = Shape(CredentialReplacement.Parser, ContractShapeValidation.IsValid),
        ["CredentialSummary"] = Shape(CredentialSummary.Parser, ContractShapeValidation.IsValid),
        ["DataDeletionPreview"] = Shape(DataDeletionPreview.Parser, ContractShapeValidation.IsValid),
        ["DataDeletionView"] = Shape(DataDeletionView.Parser, ContractShapeValidation.IsValid),
        ["DeletionCount"] = Shape(DeletionCount.Parser, ContractShapeValidation.IsValid),
        ["DeletionStatus"] = Shape(DeletionStatus.Parser, ContractShapeValidation.IsValid),
        ["DeviceCapabilityView"] = Shape(DeviceCapabilityView.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceGetCapabilitiesRequest"] = Shape(DeviceServiceGetCapabilitiesRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceGetCapabilitiesResponse"] = Shape(DeviceServiceGetCapabilitiesResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceGetCapabilitiesValue"] = Shape(DeviceServiceGetCapabilitiesValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceGetRemotePolicyRequest"] = Shape(DeviceServiceGetRemotePolicyRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceGetRemotePolicyResponse"] = Shape(DeviceServiceGetRemotePolicyResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceGetRemotePolicyValue"] = Shape(DeviceServiceGetRemotePolicyValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceListRequest"] = Shape(DeviceServiceListRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceListResponse"] = Shape(DeviceServiceListResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceListValue"] = Shape(DeviceServiceListValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRegisterRequest"] = Shape(DeviceServiceRegisterRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRegisterResponse"] = Shape(DeviceServiceRegisterResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRegisterValue"] = Shape(DeviceServiceRegisterValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRenameRequest"] = Shape(DeviceServiceRenameRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRenameResponse"] = Shape(DeviceServiceRenameResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRenameValue"] = Shape(DeviceServiceRenameValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRevokeRequest"] = Shape(DeviceServiceRevokeRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRevokeResponse"] = Shape(DeviceServiceRevokeResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceRevokeValue"] = Shape(DeviceServiceRevokeValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSetRemoteEnabledRequest"] = Shape(DeviceServiceSetRemoteEnabledRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSetRemoteEnabledResponse"] = Shape(DeviceServiceSetRemoteEnabledResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSetRemoteEnabledValue"] = Shape(DeviceServiceSetRemoteEnabledValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSetRemotePolicyRequest"] = Shape(DeviceServiceSetRemotePolicyRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSetRemotePolicyResponse"] = Shape(DeviceServiceSetRemotePolicyResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSetRemotePolicyValue"] = Shape(DeviceServiceSetRemotePolicyValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSetTrustRequest"] = Shape(DeviceServiceSetTrustRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSetTrustResponse"] = Shape(DeviceServiceSetTrustResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSetTrustValue"] = Shape(DeviceServiceSetTrustValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSignOutRequest"] = Shape(DeviceServiceSignOutRequest.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSignOutResponse"] = Shape(DeviceServiceSignOutResponse.Parser, ContractShapeValidation.IsValid),
        ["DeviceServiceSignOutValue"] = Shape(DeviceServiceSignOutValue.Parser, ContractShapeValidation.IsValid),
        ["DeviceView"] = Shape(DeviceView.Parser, ContractShapeValidation.IsValid),
        ["EnrollmentProof"] = Shape(EnrollmentProof.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginAuthenticationRequest"] = Shape(IdentityServiceBeginAuthenticationRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginAuthenticationResponse"] = Shape(IdentityServiceBeginAuthenticationResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginAuthenticationValue"] = Shape(IdentityServiceBeginAuthenticationValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginEmailChangeRequest"] = Shape(IdentityServiceBeginEmailChangeRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginEmailChangeResponse"] = Shape(IdentityServiceBeginEmailChangeResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginEmailChangeValue"] = Shape(IdentityServiceBeginEmailChangeValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginPasskeyRegistrationRequest"] = Shape(IdentityServiceBeginPasskeyRegistrationRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginPasskeyRegistrationResponse"] = Shape(IdentityServiceBeginPasskeyRegistrationResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginPasskeyRegistrationValue"] = Shape(IdentityServiceBeginPasskeyRegistrationValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginRecoveryRequest"] = Shape(IdentityServiceBeginRecoveryRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginRecoveryResponse"] = Shape(IdentityServiceBeginRecoveryResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginRecoveryValue"] = Shape(IdentityServiceBeginRecoveryValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginStepUpRequest"] = Shape(IdentityServiceBeginStepUpRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginStepUpResponse"] = Shape(IdentityServiceBeginStepUpResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceBeginStepUpValue"] = Shape(IdentityServiceBeginStepUpValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCancelAccountDeletionRequest"] = Shape(IdentityServiceCancelAccountDeletionRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCancelAccountDeletionResponse"] = Shape(IdentityServiceCancelAccountDeletionResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCancelAccountDeletionValue"] = Shape(IdentityServiceCancelAccountDeletionValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceChangePasswordRequest"] = Shape(IdentityServiceChangePasswordRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceChangePasswordResponse"] = Shape(IdentityServiceChangePasswordResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceChangePasswordValue"] = Shape(IdentityServiceChangePasswordValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteAuthenticationRequest"] = Shape(IdentityServiceCompleteAuthenticationRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteAuthenticationResponse"] = Shape(IdentityServiceCompleteAuthenticationResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteAuthenticationValue"] = Shape(IdentityServiceCompleteAuthenticationValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteEmailChangeRequest"] = Shape(IdentityServiceCompleteEmailChangeRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteEmailChangeResponse"] = Shape(IdentityServiceCompleteEmailChangeResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteEmailChangeValue"] = Shape(IdentityServiceCompleteEmailChangeValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteEnrollmentRequest"] = Shape(IdentityServiceCompleteEnrollmentRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteEnrollmentResponse"] = Shape(IdentityServiceCompleteEnrollmentResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteEnrollmentValue"] = Shape(IdentityServiceCompleteEnrollmentValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompletePasskeyRegistrationRequest"] = Shape(IdentityServiceCompletePasskeyRegistrationRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompletePasskeyRegistrationResponse"] = Shape(IdentityServiceCompletePasskeyRegistrationResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompletePasskeyRegistrationValue"] = Shape(IdentityServiceCompletePasskeyRegistrationValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteRecoveryRequest"] = Shape(IdentityServiceCompleteRecoveryRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteRecoveryResponse"] = Shape(IdentityServiceCompleteRecoveryResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteRecoveryValue"] = Shape(IdentityServiceCompleteRecoveryValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteStepUpRequest"] = Shape(IdentityServiceCompleteStepUpRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteStepUpResponse"] = Shape(IdentityServiceCompleteStepUpResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCompleteStepUpValue"] = Shape(IdentityServiceCompleteStepUpValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCreateApiTokenRequest"] = Shape(IdentityServiceCreateApiTokenRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCreateApiTokenResponse"] = Shape(IdentityServiceCreateApiTokenResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceCreateApiTokenValue"] = Shape(IdentityServiceCreateApiTokenValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceGenerateRecoveryCodesRequest"] = Shape(IdentityServiceGenerateRecoveryCodesRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceGenerateRecoveryCodesResponse"] = Shape(IdentityServiceGenerateRecoveryCodesResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceGenerateRecoveryCodesValue"] = Shape(IdentityServiceGenerateRecoveryCodesValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceGetAccountDeletionRequest"] = Shape(IdentityServiceGetAccountDeletionRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceGetAccountDeletionResponse"] = Shape(IdentityServiceGetAccountDeletionResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceGetAccountDeletionValue"] = Shape(IdentityServiceGetAccountDeletionValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceGetProfileRequest"] = Shape(IdentityServiceGetProfileRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceGetProfileResponse"] = Shape(IdentityServiceGetProfileResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceGetProfileValue"] = Shape(IdentityServiceGetProfileValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListApiTokensRequest"] = Shape(IdentityServiceListApiTokensRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListApiTokensResponse"] = Shape(IdentityServiceListApiTokensResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListApiTokensValue"] = Shape(IdentityServiceListApiTokensValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListAuthIdentitiesRequest"] = Shape(IdentityServiceListAuthIdentitiesRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListAuthIdentitiesResponse"] = Shape(IdentityServiceListAuthIdentitiesResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListAuthIdentitiesValue"] = Shape(IdentityServiceListAuthIdentitiesValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListAuthProvidersRequest"] = Shape(IdentityServiceListAuthProvidersRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListAuthProvidersResponse"] = Shape(IdentityServiceListAuthProvidersResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListAuthProvidersValue"] = Shape(IdentityServiceListAuthProvidersValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListSecurityActivityRequest"] = Shape(IdentityServiceListSecurityActivityRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListSecurityActivityResponse"] = Shape(IdentityServiceListSecurityActivityResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListSecurityActivityValue"] = Shape(IdentityServiceListSecurityActivityValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListSessionsRequest"] = Shape(IdentityServiceListSessionsRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListSessionsResponse"] = Shape(IdentityServiceListSessionsResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceListSessionsValue"] = Shape(IdentityServiceListSessionsValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRedeemEmailCodeRequest"] = Shape(IdentityServiceRedeemEmailCodeRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRedeemEmailCodeResponse"] = Shape(IdentityServiceRedeemEmailCodeResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRedeemEmailCodeValue"] = Shape(IdentityServiceRedeemEmailCodeValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRefreshSessionRequest"] = Shape(IdentityServiceRefreshSessionRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRefreshSessionResponse"] = Shape(IdentityServiceRefreshSessionResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRefreshSessionValue"] = Shape(IdentityServiceRefreshSessionValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRemoveAuthIdentityRequest"] = Shape(IdentityServiceRemoveAuthIdentityRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRemoveAuthIdentityResponse"] = Shape(IdentityServiceRemoveAuthIdentityResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRemoveAuthIdentityValue"] = Shape(IdentityServiceRemoveAuthIdentityValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRenameAuthIdentityRequest"] = Shape(IdentityServiceRenameAuthIdentityRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRenameAuthIdentityResponse"] = Shape(IdentityServiceRenameAuthIdentityResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRenameAuthIdentityValue"] = Shape(IdentityServiceRenameAuthIdentityValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRequestAccountDeletionRequest"] = Shape(IdentityServiceRequestAccountDeletionRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRequestAccountDeletionResponse"] = Shape(IdentityServiceRequestAccountDeletionResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRequestAccountDeletionValue"] = Shape(IdentityServiceRequestAccountDeletionValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRequestEmailCodeRequest"] = Shape(IdentityServiceRequestEmailCodeRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRequestEmailCodeResponse"] = Shape(IdentityServiceRequestEmailCodeResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRequestEmailCodeValue"] = Shape(IdentityServiceRequestEmailCodeValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRevokeAllSessionsRequest"] = Shape(IdentityServiceRevokeAllSessionsRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRevokeAllSessionsResponse"] = Shape(IdentityServiceRevokeAllSessionsResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRevokeAllSessionsValue"] = Shape(IdentityServiceRevokeAllSessionsValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRevokeApiTokenRequest"] = Shape(IdentityServiceRevokeApiTokenRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRevokeApiTokenResponse"] = Shape(IdentityServiceRevokeApiTokenResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRevokeApiTokenValue"] = Shape(IdentityServiceRevokeApiTokenValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRevokeSessionRequest"] = Shape(IdentityServiceRevokeSessionRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRevokeSessionResponse"] = Shape(IdentityServiceRevokeSessionResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceRevokeSessionValue"] = Shape(IdentityServiceRevokeSessionValue.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceUpdateProfileRequest"] = Shape(IdentityServiceUpdateProfileRequest.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceUpdateProfileResponse"] = Shape(IdentityServiceUpdateProfileResponse.Parser, ContractShapeValidation.IsValid),
        ["IdentityServiceUpdateProfileValue"] = Shape(IdentityServiceUpdateProfileValue.Parser, ContractShapeValidation.IsValid),
        ["InstallationClaim"] = Shape(InstallationClaim.Parser, ContractShapeValidation.IsValid),
        ["InstalledProduct"] = Shape(InstalledProduct.Parser, ContractShapeValidation.IsValid),
        ["NativeSession"] = Shape(NativeSession.Parser, ContractShapeValidation.IsValid),
        ["ProfileUpdate"] = Shape(ProfileUpdate.Parser, ContractShapeValidation.IsValid),
        ["RecoveryCodeSet"] = Shape(RecoveryCodeSet.Parser, ContractShapeValidation.IsValid),
        ["RemoteCapabilityPolicy"] = Shape(RemoteCapabilityPolicy.Parser, ContractShapeValidation.IsValid),
        ["SecurityActivity"] = Shape(SecurityActivity.Parser, ContractShapeValidation.IsValid),
        ["SessionSummary"] = Shape(SessionSummary.Parser, ContractShapeValidation.IsValid),
        ["SessionView"] = Shape(SessionView.Parser, ContractShapeValidation.IsValid),
        ["StepUpEvidence"] = Shape(StepUpEvidence.Parser, ContractShapeValidation.IsValid),
        ["WebAuthnAssertion"] = Shape(WebAuthnAssertion.Parser, ContractShapeValidation.IsValid),
        ["WebAuthnCreation"] = Shape(WebAuthnCreation.Parser, ContractShapeValidation.IsValid),
        ["WebAuthnOptions"] = Shape(WebAuthnOptions.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceHealth"] = Shape(WorkspaceHealth.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceGetDataDeletionRequest"] = Shape(WorkspaceServiceGetDataDeletionRequest.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceGetDataDeletionResponse"] = Shape(WorkspaceServiceGetDataDeletionResponse.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceGetDataDeletionValue"] = Shape(WorkspaceServiceGetDataDeletionValue.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceGetHealthRequest"] = Shape(WorkspaceServiceGetHealthRequest.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceGetHealthResponse"] = Shape(WorkspaceServiceGetHealthResponse.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceGetHealthValue"] = Shape(WorkspaceServiceGetHealthValue.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceGetRequest"] = Shape(WorkspaceServiceGetRequest.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceGetResponse"] = Shape(WorkspaceServiceGetResponse.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceGetValue"] = Shape(WorkspaceServiceGetValue.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceListRequest"] = Shape(WorkspaceServiceListRequest.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceListResponse"] = Shape(WorkspaceServiceListResponse.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceListValue"] = Shape(WorkspaceServiceListValue.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServicePreviewDataDeletionRequest"] = Shape(WorkspaceServicePreviewDataDeletionRequest.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServicePreviewDataDeletionResponse"] = Shape(WorkspaceServicePreviewDataDeletionResponse.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServicePreviewDataDeletionValue"] = Shape(WorkspaceServicePreviewDataDeletionValue.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceRequestDataDeletionRequest"] = Shape(WorkspaceServiceRequestDataDeletionRequest.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceRequestDataDeletionResponse"] = Shape(WorkspaceServiceRequestDataDeletionResponse.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceRequestDataDeletionValue"] = Shape(WorkspaceServiceRequestDataDeletionValue.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceUpdateSettingsRequest"] = Shape(WorkspaceServiceUpdateSettingsRequest.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceUpdateSettingsResponse"] = Shape(WorkspaceServiceUpdateSettingsResponse.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceServiceUpdateSettingsValue"] = Shape(WorkspaceServiceUpdateSettingsValue.Parser, ContractShapeValidation.IsValid),
        ["WorkspaceView"] = Shape(WorkspaceView.Parser, ContractShapeValidation.IsValid)
    };

    private static readonly Dictionary<string, MessageDescriptor> Records = new(StringComparer.Ordinal)
    {
        ["InstallationClaim"] = InstallationClaim.Descriptor,
        ["AuthChallenge"] = AuthChallenge.Descriptor,
        ["WebAuthnOptions"] = WebAuthnOptions.Descriptor,
        ["WebAuthnCreation"] = WebAuthnCreation.Descriptor,
        ["WebAuthnAssertion"] = WebAuthnAssertion.Descriptor,
        ["AuthProof"] = AuthProof.Descriptor,
        ["NativeSession"] = NativeSession.Descriptor,
        ["SessionView"] = SessionView.Descriptor,
        ["CredentialSummary"] = CredentialSummary.Descriptor,
        ["StepUpEvidence"] = StepUpEvidence.Descriptor,
        ["DeletionStatus"] = DeletionStatus.Descriptor,
        ["AccountProfile"] = AccountProfile.Descriptor,
        ["ProfileUpdate"] = ProfileUpdate.Descriptor,
        ["AuthProviderView"] = AuthProviderView.Descriptor,
        ["SessionSummary"] = SessionSummary.Descriptor,
        ["ApiTokenView"] = ApiTokenView.Descriptor,
        ["RecoveryCodeSet"] = RecoveryCodeSet.Descriptor,
        ["RemoteCapabilityPolicy"] = RemoteCapabilityPolicy.Descriptor,
        ["SecurityActivity"] = SecurityActivity.Descriptor,
        ["DataDeletionPreview"] = DataDeletionPreview.Descriptor,
        ["DeletionCount"] = DeletionCount.Descriptor,
        ["WorkspaceHealth"] = WorkspaceHealth.Descriptor,
        ["DataDeletionView"] = DataDeletionView.Descriptor,
        ["WorkspaceView"] = WorkspaceView.Descriptor,
        ["DeviceView"] = DeviceView.Descriptor,
        ["InstalledProduct"] = InstalledProduct.Descriptor,
        ["DeviceCapabilityView"] = DeviceCapabilityView.Descriptor,
        ["CredentialReplacement"] = CredentialReplacement.Descriptor,
        ["EnrollmentProof"] = EnrollmentProof.Descriptor
    };

    private static readonly Dictionary<string, Func<byte[], Outcome>> Codecs = new(StringComparer.Ordinal)
    {
        ["BrowserAuthChallenge"] = Codec<BrowserAuthChallenge>(BrowserAuthChallengeJson.TryParse, BrowserAuthChallengeJson.Serialize),
        ["BrowserBeginAuthenticationRequest"] = Codec<BrowserBeginAuthenticationRequest>(BrowserBeginAuthenticationRequestJson.TryParse, BrowserBeginAuthenticationRequestJson.Serialize),
        ["BrowserBeginRecoveryRequest"] = Codec<BrowserBeginRecoveryRequest>(BrowserBeginRecoveryRequestJson.TryParse, BrowserBeginRecoveryRequestJson.Serialize),
        ["BrowserBeginStepUpRequest"] = Codec<BrowserBeginStepUpRequest>(BrowserBeginStepUpRequestJson.TryParse, BrowserBeginStepUpRequestJson.Serialize),
        ["BrowserBootstrapResponse"] = Codec<BrowserBootstrapResponse>(BrowserBootstrapResponseJson.TryParse, BrowserBootstrapResponseJson.Serialize),
        ["BrowserCompleteAuthenticationRequest"] = Codec<BrowserCompleteAuthenticationRequest>(BrowserCompleteAuthenticationRequestJson.TryParse, BrowserCompleteAuthenticationRequestJson.Serialize),
        ["BrowserCompleteEnrollmentRequest"] = Codec<BrowserCompleteEnrollmentRequest>(BrowserCompleteEnrollmentRequestJson.TryParse, BrowserCompleteEnrollmentRequestJson.Serialize),
        ["BrowserCompleteRecoveryRequest"] = Codec<BrowserCompleteRecoveryRequest>(BrowserCompleteRecoveryRequestJson.TryParse, BrowserCompleteRecoveryRequestJson.Serialize),
        ["BrowserCompleteStepUpRequest"] = Codec<BrowserCompleteStepUpRequest>(BrowserCompleteStepUpRequestJson.TryParse, BrowserCompleteStepUpRequestJson.Serialize),
        ["BrowserOidcCallbackFailure"] = Codec<BrowserOidcCallbackFailure>(BrowserOidcCallbackFailureForm.TryParse, BrowserOidcCallbackFailureForm.Serialize),
        ["BrowserOidcCallbackSuccess"] = Codec<BrowserOidcCallbackSuccess>(BrowserOidcCallbackSuccessForm.TryParse, BrowserOidcCallbackSuccessForm.Serialize),
        ["BrowserReceipt"] = Codec<BrowserReceipt>(BrowserReceiptJson.TryParse, BrowserReceiptJson.Serialize),
        ["BrowserSessionView"] = Codec<BrowserSessionView>(BrowserSessionViewJson.TryParse, BrowserSessionViewJson.Serialize),
        ["BrowserStepUpEvidence"] = Codec<BrowserStepUpEvidence>(BrowserStepUpEvidenceJson.TryParse, BrowserStepUpEvidenceJson.Serialize),
        ["NativeAuthorizeCallbackFailure"] = Codec<NativeAuthorizeCallbackFailure>(NativeAuthorizeCallbackFailureForm.TryParse, NativeAuthorizeCallbackFailureForm.Serialize),
        ["NativeAuthorizeCallbackSuccess"] = Codec<NativeAuthorizeCallbackSuccess>(NativeAuthorizeCallbackSuccessForm.TryParse, NativeAuthorizeCallbackSuccessForm.Serialize),
        ["NativeAuthorizeRequest"] = Codec<NativeAuthorizeRequest>(NativeAuthorizeRequestForm.TryParse, NativeAuthorizeRequestForm.Serialize),
        ["NativeTokenRequest"] = Codec<NativeTokenRequest>(NativeTokenRequestForm.TryParse, NativeTokenRequestForm.Serialize),
        ["NativeTokenResponse"] = Codec<NativeTokenResponse>(NativeTokenResponseJson.TryParse, NativeTokenResponseJson.Serialize)
    };

    internal static void Run(string root)
    {
        using var fixtureDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "fixtures/public/con-07-identity.json")));
        using var exportDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "eng/operations/con-07.json")));
        var fixture = fixtureDocument.RootElement;
        var operations = fixture.GetProperty("operations").EnumerateArray().ToArray();
        Require(operations.Length == 49, "exact operation count");

        var services = IdentityReflection.Descriptor.Services.ToDictionary(service => service.FullName);
        Require(services.Count == 3, "exact three identity services");
        foreach (var expected in fixture.GetProperty("services").EnumerateObject())
        {
            Require(services.TryGetValue(expected.Name, out var service), "service " + expected.Name);
            Require(service!.Methods.Select(method => method.Name).SequenceEqual(expected.Value.EnumerateArray().Select(value => value.GetString()!)),
                "exact method order " + expected.Name);
        }

        var exports = exportDocument.RootElement.GetProperty("operations").EnumerateArray().ToDictionary(row => row.GetProperty("operationId").GetString()!);
        Require(exports.Count == operations.Length, "operation export count");
        foreach (var row in operations)
        {
            var id = row.GetProperty("id").GetString()!;
            var serviceName = "arcforges.publicapi.v1." + row.GetProperty("service").GetString();
            var methodName = row.GetProperty("method").GetString()!;
            var method = services[serviceName].FindMethodByName(methodName);
            Require(method is not null && !method.IsClientStreaming && !method.IsServerStreaming, id + " unary method");
            Require(method!.InputType.Name == row.GetProperty("service").GetString() + methodName + "Request", id + " request type");
            Require(method.OutputType.Name == row.GetProperty("service").GetString() + methodName + "Response", id + " response type");
            Require(Shape(method.InputType) == row.GetProperty("requestTags").GetString(), id + " request tags");
            var value = method.OutputType.FindFieldByNumber(2)!.MessageType;
            Require(Shape(value) == row.GetProperty("valueTags").GetString(), id + " value tags");
            Require(method.OutputType.FindFieldByNumber(1)?.MessageType == ArcForges.Contracts.Foundation.V1.ResponseMeta.Descriptor, id + " response metadata");
            Require(method.OutputType.FindFieldByNumber(3)?.MessageType == ArcForges.Contracts.Foundation.V1.ArcError.Descriptor, id + " typed error");
            Require(method.OutputType.FindFieldByNumber(2)?.ContainingOneof?.Name == "outcome" && method.OutputType.FindFieldByNumber(3)?.ContainingOneof?.Name == "outcome", id + " outcome oneof");
            Require((method.OutputType.FindFieldByNumber(4) is not null) == row.GetProperty("encodedBody").GetBoolean(), id + " encoded body");
            for (var tag = 2; tag <= 9; tag++) Require(method.InputType.FindFieldByNumber(tag) is null, id + " reserved request tag");
            for (var tag = 5; tag <= 9; tag++) Require(method.OutputType.FindFieldByNumber(tag) is null, id + " reserved response tag");

            var export = exports[id];
            var auth = export.GetProperty("authorization");
            Require(export.GetProperty("binding").GetString() == serviceName + "/" + methodName && export.GetProperty("kind").GetString() == "proto" &&
                export.GetProperty("surface").GetString() == "public" && export.GetProperty("scope").GetString() == row.GetProperty("scope").GetString() &&
                export.GetProperty("profile").GetString() == row.GetProperty("profile").GetString() &&
                export.GetProperty("idempotency").GetString() == row.GetProperty("idempotency").GetString(), id + " export identity");
            Require(auth.EnumerateObject().Count() == 8 && auth.GetProperty("capability").ValueKind == JsonValueKind.Null &&
                auth.GetProperty("risk").GetString() == row.GetProperty("risk").GetString() && auth.GetProperty("approval").GetString() == "none" &&
                auth.GetProperty("stepUp").GetBoolean() == row.GetProperty("stepUp").GetBoolean() && !auth.GetProperty("localPresence").GetBoolean() &&
                auth.GetProperty("egress").GetString() == "none" && auth.GetProperty("patEligible").GetBoolean() == row.GetProperty("patEligible").GetBoolean() &&
                auth.GetProperty("actorKinds").EnumerateArray().Select(actor => actor.GetString()).SequenceEqual(row.GetProperty("actorKinds").EnumerateArray().Select(actor => actor.GetString())),
                id + " exact eight authorization fields");
        }

        foreach (var record in fixture.GetProperty("records").EnumerateObject())
            Require(Shape(Records[record.Name]) == record.Value.GetString(), record.Name + " exact tags");
        Require(Records.Count == fixture.GetProperty("records").EnumerateObject().Count(), "record inventory");

        // Independent Registry04-derived oracle: number, name, JSON name, type, repetition and presence of all 176 messages.
        var fieldOracle = fixture.GetProperty("fields");
        var messageTypes = IdentityReflection.Descriptor.MessageTypes.ToDictionary(item => item.Name, StringComparer.Ordinal);
        Require(fieldOracle.EnumerateObject().Count() == 176 && messageTypes.Count == 176, "exact 176 message inventory");
        foreach (var message in fieldOracle.EnumerateObject())
        {
            Require(messageTypes.TryGetValue(message.Name, out var messageDescriptor), "message " + message.Name);
            var actualFields = messageDescriptor!.Fields.InFieldNumberOrder().Select(DescribeField).ToArray();
            var expectedFields = message.Value.EnumerateArray().Select(item => item.GetString()!)
                .OrderBy(item => int.Parse(item[..item.IndexOf(':')])).ToArray();
            Require(actualFields.SequenceEqual(expectedFields), message.Name + " exact field oracle: " + string.Join(" | ", actualFields) + " != " + string.Join(" | ", expectedFields));
        }
        foreach (var enumeration in fixture.GetProperty("enums").EnumerateObject())
        {
            var descriptor = IdentityReflection.Descriptor.EnumTypes.Single(item => item.Name == enumeration.Name);
            var prefix = UpperSnake(enumeration.Name);
            var expected = new[] { prefix + "_UNSPECIFIED" }.Concat(enumeration.Value.EnumerateArray().Select(member => prefix + "_" + UpperSnake(member.GetString()!)));
            Require(descriptor.Values.Select(value => value.Name).SequenceEqual(expected), enumeration.Name + " exact values");
            Require(descriptor.Values.Select(value => value.Number).SequenceEqual(Enumerable.Range(0, descriptor.Values.Count)), enumeration.Name + " exact numbers");
        }
        foreach (var oneof in fixture.GetProperty("oneofs").EnumerateObject())
        {
            // proto3 optional presence adds synthetic oneofs that are not part of the registry contract.
            var real = Records[oneof.Name].Oneofs.Where(group => !group.IsSynthetic).ToArray();
            Require(real.Length == 1 && real[0].Name == oneof.Value.GetProperty("group").GetString() &&
                real[0].Fields.Select(field => field.JsonName).SequenceEqual(oneof.Value.GetProperty("members").EnumerateArray().Select(member => member.GetString()!)),
                oneof.Name + " exact oneof members");
        }
        Require(DeviceView.Descriptor.Fields.InDeclarationOrder().Select(field => field.FieldNumber).SequenceEqual(new[] { 1, 2, 3, 4, 5, 6, 8, 10 }), "DeviceView reserves tags 7, 9 and 11");

        var shapeCases = fixture.GetProperty("cases").EnumerateArray().ToArray();
        Require(shapeCases.Length >= 1000, "shape vector coverage");
        var minimal = shapeCases.Select(item => (Id: item.GetProperty("id").GetString()!, Target: item.GetProperty("target").GetString()!))
            .Where(item => item.Id.StartsWith("auto.", StringComparison.Ordinal) && item.Id.EndsWith(".minimal", StringComparison.Ordinal))
            .Select(item => item.Target).ToHashSet(StringComparer.Ordinal);
        Require(minimal.SetEquals(fieldOracle.EnumerateObject().Select(message => message.Name)), "every constraint message has a minimal valid vector");
        foreach (var item in shapeCases)
        {
            var target = item.GetProperty("target").GetString()!;
            Require(Shapes.TryGetValue(target, out var validate), "shape target " + target);
            var actual = validate!(ExpandNode(JsonNode.Parse(item.GetProperty("value").GetRawText()))!.ToJsonString());
            Require(actual == item.GetProperty("valid").GetBoolean(), item.GetProperty("id").GetString()!);
        }

        var httpVectors = fixture.GetProperty("httpVectors").EnumerateArray().ToArray();
        Require(httpVectors.Length >= 100, "HTTP vector coverage");
        foreach (var item in httpVectors) RunHttpVector(item);
        RunBounds();
        RunRoutes(fixture.GetProperty("routes"));
        RunJourneys(fixture, operations);
        Console.WriteLine($"CON.07: 3 services, {operations.Length} operations, {shapeCases.Length} shape and {httpVectors.Length} HTTP exception vectors passed.");
    }

    private static Func<string, bool> Shape<T>(MessageParser<T> parser, Func<T, bool> validate) where T : class, IMessage<T>, new() => json =>
    {
        var message = JsonParser.Default.Parse<T>(json);
        var valid = validate(message);
        if (valid) Require(validate(parser.ParseFrom(message.ToByteArray())), "binary round-trip");
        return valid;
    };

    private static Func<byte[], Outcome> Codec<T>(TryParse<T> tryParse, Func<T, byte[]> serialize) where T : class => bytes =>
    {
        if (!tryParse(bytes, out var value, out var failure))
        {
            var name = failure.ToString();
            return new Outcome(false, char.ToLowerInvariant(name[0]) + name[1..], null, false);
        }
        var canonical = serialize(value!);
        var again = tryParse(canonical, out var reparsed, out _);
        return new Outcome(true, "", Encoding.UTF8.GetString(canonical), again && serialize(reparsed!).AsSpan().SequenceEqual(canonical));
    };

    private static void RunHttpVector(JsonElement item)
    {
        var id = item.GetProperty("id").GetString()!;
        Require(Codecs.TryGetValue(item.GetProperty("root").GetString()!, out var codec), id + " codec");
        var outcome = codec!(Encoding.UTF8.GetBytes(item.GetProperty("text").GetString()!));
        Require(outcome.Ok == item.GetProperty("valid").GetBoolean(), id);
        if (outcome.Ok)
        {
            if (item.TryGetProperty("canonical", out var canonical)) Require(outcome.Canonical == canonical.GetString(), id + " canonical");
            Require(outcome.Lossless, id + " lossless round-trip");
        }
        else Require(outcome.Failure == item.GetProperty("failure").GetString(), id + " failure kind");
    }

    private static void RunBounds()
    {
        Require(NativeTokenRequestForm.MaxBytes == 16384 && NativeAuthorizeRequestForm.MaxBytes == 16384, "specified 16 KiB form bound");
        Require(BrowserAuthChallengeJson.MaxBytes == 65536 && BrowserAuthChallengeJson.MaxDepth == 32, "strict JSON bound and depth");
        const string form = "grant_type=authorization_code&code=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopq&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk&client_id=arcscope.desktop&redirect_uri=com.arcforges.arcscope%3A%2Fauth%2Fcallback&installationId=11223344-5566-4788-99aa-bbccddeeff00";
        var bytes = Encoding.ASCII.GetBytes(form);
        Require(NativeTokenRequestForm.TryParse(bytes, out var parsed, out _) && parsed!.ClientId == "arcscope.desktop" &&
            parsed.RedirectUri == "com.arcforges.arcscope:/auth/callback", "native token form decodes percent escapes");
        Require(!NativeTokenRequestForm.TryParse(Encoding.ASCII.GetBytes(form + "&x=" + new string('a', 16384)), out _, out var tooLarge) && tooLarge == ContractSerializationFailure.TooLarge, "form above 16 KiB");
        Require(!NativeTokenRequestForm.TryParse(new byte[] { 0xff, 0x3d, 0x61 }, out _, out var raw) && raw == ContractSerializationFailure.Malformed, "raw non-ASCII form byte");
        Require(!NativeTokenRequestForm.TryParse(Encoding.ASCII.GetBytes(form.Replace("&", "\n")), out _, out _), "raw control in form");
        Require(NativeTokenRequestForm.Serialize(parsed!).AsSpan().SequenceEqual(bytes), "native token form serializes deterministically");
        var thrown = false;
        try { NativeTokenRequestForm.Parse(Encoding.ASCII.GetBytes("grant_type=authorization_code")); }
        catch (ContractSerializationException) { thrown = true; }
        Require(thrown, "incomplete form is refused with a typed exception");
        var duplicateParsed = BrowserSessionViewJson.TryParse(Encoding.UTF8.GetBytes("{\"sessionId\":\"11223344-5566-4788-99aa-bbccddeeff00\",\"sessionId\":\"11223344-5566-4788-99aa-bbccddeeff00\"}"), out _, out var duplicate);
        Require(!duplicateParsed && duplicate == ContractSerializationFailure.Malformed, "duplicate JSON property is malformed");
    }

    private static void RunRoutes(JsonElement routes)
    {
        AssertRoutes(BrowserSessionRoutes.All.Select(Describe).ToArray(), routes.GetProperty("BrowserSession"), "BrowserSession");
        AssertRoutes(NativeAuthRoutes.All.Select(Describe).ToArray(), routes.GetProperty("NativeAuth"), "NativeAuth");
        var all = BrowserSessionRoutes.All.Select(route => (route.Id, route.Method, route.Path, route.Cache, route.Csrf, route.Origin, route.SetCookie))
            .Concat(NativeAuthRoutes.All.Select(route => (route.Id, route.Method, route.Path, route.Cache, route.Csrf, route.Origin, route.SetCookie))).ToArray();
        Require(all.Select(route => route.Method + " " + route.Path).Distinct().Count() == all.Length, "unique method and path");
        Require(all.All(route => route.Cache == "no-store" && route.Path.StartsWith("/session/v1/", StringComparison.Ordinal)), "no-store session routes");
        Require(all.Count(route => route.Id.StartsWith("browser.", StringComparison.Ordinal) && route.Method == "POST") == 8 &&
            all.Where(route => route.Id.StartsWith("browser.", StringComparison.Ordinal) && route.Method == "POST").All(route => route.Csrf == "required" && route.Origin == "exact-configured"), "every browser POST requires Origin and CSRF");
        Require(all.Where(route => route.SetCookie == "session").Select(route => route.Id).SequenceEqual(new[] { "browser.completeAuthentication", "browser.completeEnrollment" }), "session cookie only from completion routes");
    }

    private static string Describe(BrowserSessionRoute route) =>
        string.Join("|", route.Id, route.Method, route.Path, route.Credential, route.Origin, route.Csrf, route.SetCookie, route.Cache, route.RequestWire, string.Join(",", route.RequestRoots), route.ResponseWire, string.Join(",", route.ResponseRoots));

    private static string Describe(NativeAuthRoute route) =>
        string.Join("|", route.Id, route.Method, route.Path, route.Credential, route.Origin, route.Csrf, route.SetCookie, route.Cache, route.RequestWire, string.Join(",", route.RequestRoots), route.ResponseWire, string.Join(",", route.ResponseRoots));

    private static void AssertRoutes(string[] actual, JsonElement expected, string bundle)
    {
        var rows = expected.EnumerateArray().Select(route => string.Join("|", route.GetProperty("id").GetString(), route.GetProperty("method").GetString(), route.GetProperty("path").GetString(),
            route.GetProperty("credential").GetString(), route.GetProperty("origin").GetString(), route.GetProperty("csrf").GetString(), route.GetProperty("setCookie").GetString(),
            route.GetProperty("cache").GetString(), route.GetProperty("requestWire").GetString(), string.Join(",", route.GetProperty("requestRoots").EnumerateArray().Select(value => value.GetString())),
            route.GetProperty("responseWire").GetString(), string.Join(",", route.GetProperty("responseRoots").EnumerateArray().Select(value => value.GetString())))).ToArray();
        Require(actual.SequenceEqual(rows), bundle + " exact route table");
    }

    private static void RunJourneys(JsonElement fixture, JsonElement[] operations)
    {
        var steps = operations.ToDictionary(row => row.GetProperty("id").GetString()!, row => row.GetProperty("stepUp").GetBoolean());
        var routeIds = BrowserSessionRoutes.All.Select(route => route.Id).Concat(NativeAuthRoutes.All.Select(route => route.Id)).ToHashSet();
        var journeys = fixture.GetProperty("journeys").EnumerateArray().ToArray();
        var frozenExpectations = JsonNode.Parse(FrozenJourneyExpectations)!.AsObject();
        Require(journeys.Length == 14, "exact journey inventory");
        foreach (var journey in journeys)
        {
            var id = journey.GetProperty("id").GetString()!;
            Require(journey.GetProperty("evidenceClass").GetString() == "declarative-owner-runtime-vector-not-executed-by-con07", id + " evidence class");
            Require(JsonNode.DeepEquals(JsonNode.Parse(journey.GetProperty("expect").GetRawText()), frozenExpectations[id]), id + " exact frozen expectations");
            var credits = 0;
            foreach (var step in journey.GetProperty("steps").EnumerateArray())
            {
                var stepId = step.GetProperty("id").GetString()!;
                if (step.GetProperty("kind").GetString() == "route") { Require(routeIds.Contains(stepId), id + " route " + stepId); continue; }
                Require(steps.TryGetValue(stepId, out var needsStepUp), id + " operation " + stepId);
                if (stepId == "identity.completeStepUp") credits++;
                if (needsStepUp) { Require(credits > 0, id + " " + stepId + " needs fresh step-up"); credits--; }
            }
        }
    }

    private static string DescribeField(FieldDescriptor field)
    {
        var type = field.FieldType switch
        {
            FieldType.String => "string",
            FieldType.Bytes => "bytes",
            FieldType.Bool => "bool",
            FieldType.Int32 => "int32",
            FieldType.Int64 => "int64",
            FieldType.UInt32 => "uint32",
            FieldType.UInt64 => "uint64",
            FieldType.SInt32 => "sint32",
            FieldType.Enum => field.EnumType.Name,
            FieldType.Message => field.MessageType.FullName.StartsWith("arcforges.publicapi.v1.", StringComparison.Ordinal) ? field.MessageType.Name : field.MessageType.FullName,
            _ => "unsupported:" + field.FieldType,
        };
        var modifier = field.ContainingOneof is { IsSynthetic: false } ? "oneof"
            : field.IsRepeated ? "repeated"
            : field.FieldType == FieldType.Message ? ""
            : field.ContainingOneof is { IsSynthetic: true } ? "optional"
            : "implicit";
        return $"{field.FieldNumber}:{field.Name}:{field.JsonName}:{type}:{modifier}";
    }

    // Compact vector markers: $bytes (n bytes of 0x01 as standard base64), $str ([prefix, char, count]), $unique (n distinct keys), $repeat ([n, item]).
    private static JsonNode? ExpandNode(JsonNode? node)
    {
        if (node is JsonArray array)
        {
            var expanded = new JsonArray();
            foreach (var item in array) expanded.Add(ExpandNode(item));
            return expanded;
        }
        if (node is JsonObject obj)
        {
            if (obj.Count == 1)
            {
                var (key, inner) = obj.First();
                switch (key)
                {
                    case "$bytes":
                        return JsonValue.Create(Convert.ToBase64String(Enumerable.Repeat((byte)1, inner!.GetValue<int>()).ToArray()));
                    case "$str":
                        var text = inner!.AsArray();
                        return JsonValue.Create(text[0]!.GetValue<string>() + new string(text[1]!.GetValue<string>()[0], text[2]!.GetValue<int>()));
                    case "$unique":
                        var keys = new JsonArray();
                        for (var index = 0; index < inner!.GetValue<int>(); index++) keys.Add((JsonNode?)JsonValue.Create("k" + index));
                        return keys;
                    case "$repeat":
                        var repeat = inner!.AsArray();
                        var items = new JsonArray();
                        for (var index = 0; index < repeat[0]!.GetValue<int>(); index++) items.Add(ExpandNode(repeat[1]!.DeepClone()));
                        return items;
                }
            }
            var copy = new JsonObject();
            foreach (var (name, child) in obj) copy[name] = ExpandNode(child);
            return copy;
        }
        return node?.DeepClone();
    }

    private static string Shape(MessageDescriptor descriptor) =>
        string.Join(",", descriptor.Fields.InDeclarationOrder().Select(field => $"{field.FieldNumber}:{field.Name}"));

    private const string FrozenJourneyExpectations = """
{
  "account-creation": {
    "usedOrExpiredProofReplaysSession": false,
    "freshAuthenticationRecoversCreatedAccount": true,
    "duplicateWorkspaceOrInitialGrant": false,
    "emailOnlyAccountCanAddPasskeyAfterLogin": true
  },
  "email-login": {
    "redeemAndCompleteAreExclusive": true,
    "badOrUnknownAccountProofSameBoundedDenialShape": true,
    "unknownProviderDeliveryAuthorizesDuplicateAccountCreation": false
  },
  "passkey-login": {
    "validatesChallengeOriginRpUserVerificationSignatureCredentialBindingAndReplay": true,
    "unsupportedPlatformOffersAnotherEnabledMethod": true,
    "weakerFakePasskeyOffered": false
  },
  "passkey-management": {
    "completeIsOneUseProofConsumption": true,
    "removingLastUsableCredentialOrRecoveryRouteRefused": true,
    "refusalCode": "identity.last_credential"
  },
  "self-host-password-enrollment": {
    "officialRealmRejectsPasswordProvider": true,
    "grantPossessionResetsExistingAccount": false
  },
  "oidc-login-enrollment-link": {
    "receiptBoundToOriginalFlowAndInstallation": true,
    "callerSuppliedRedirectAccepted": false,
    "sameEmailMergesAccounts": false,
    "callbackCarriesProviderAccessOrRefreshToken": false,
    "linkingRequiresStepUpAndBothAuthenticatedIdentities": true
  },
  "recovery": {
    "commitConsumesProofAndInvalidatesRecoveryCodeSet": true,
    "revokesSessionsPatAndPendingNativeAuthorizationCodes": true,
    "changesCredentialAtomically": true,
    "returnsReceiptOnly": true,
    "oldCredentialsSupplyReplacementPublicKeyWithoutProof": false
  },
  "step-up": {
    "evidenceBindsActorSessionGenerationClassAndTargetHash": true,
    "maximumMinutes": 5,
    "oneSensitiveActionOnly": true,
    "differentProposalOrSessionReusesEvidence": false,
    "biometricAppUnlockIsStepUp": false
  },
  "refresh": {
    "singleFlightPerInstallation": true,
    "oldTokenReuseRevokesFamily": true,
    "lostRotationResponseRequiresLogin": true,
    "automaticRetryWithOldToken": false,
    "browserCookieUsesRefreshToken": false
  },
  "logout": {
    "localCredentialsInvalidatedBeforeCallbacks": true,
    "deviceRevocationRemovesTrustRemoteAuthorityAndPush": true,
    "signOutRetainsRegistration": true,
    "pendingWorkQuarantined": true
  },
  "native-browser-authorization": {
    "wrongVerifierConsumesValidCode": false,
    "attemptsCappedAt": 5,
    "redeemedOrExpiredCodeIssuesSession": false,
    "lostTokenResponseRequiresFreshAuthorization": true,
    "callbackCarriesOnlyCodeAndState": true,
    "browserCookiesCopiedToApp": false
  },
  "api-token": {
    "secretDisplayedOnceHashOnly": true,
    "duplicateCreateReturnsSafeSummaryWithoutSecret": true,
    "tokenManagesAuthentication": false,
    "patEligibleOperations": [
      "workspace.get",
      "workspace.list"
    ]
  },
  "account-deletion": {
    "graceSessionQueriesOrdinaryContent": false,
    "oldOrdinarySessionsRemainRevokedAfterCancel": true,
    "paidSubscriptionCancelledImplicitly": false
  },
  "browser-session": {
    "everyResponseNoStore": true,
    "sessionSecretOnlyInSetCookie": true,
    "nativeSessionReturnedToBrowser": false,
    "logoutByGet": false
  }
}
""";

    private static string UpperSnake(string value) => Regex.Replace(value, "([a-z0-9])([A-Z])", "$1_$2").ToUpperInvariant();

    private static void Require(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("CON.07 fixture: " + name);
    }
}
