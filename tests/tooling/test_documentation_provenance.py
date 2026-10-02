# SPDX-License-Identifier: Apache-2.0
"""Resource admission and semantic checks against the actual Maven candidate."""

import copy
import json
import re
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
import documentation_tools as documentation
from maven_tools import zip_contents


CON10_PUBLIC_SERVICE_METHODS = {
    "AgentService": ["deleteProfile", "deleteSkill", "getUsage", "listModels", "listProfiles", "putProfile", "putSkill"],
    "ApprovalService": ["decide", "list"],
    "AutomationService": ["create", "delete", "get", "list", "resolveMissed", "runNow", "setEnabled",
                          "submitEvent", "update"],
    "BridgeService": ["getRequestState", "pullRequests", "submitResult"],
    "ChatService": ["appendMessage", "cancelTurn", "closeTemporary", "createBranch", "createConversation",
                    "deleteMemory", "deleteProject", "getConversation", "getMemory", "getProject", "getTurn",
                    "listConversations", "listMemories", "listProjects", "previewPromotion", "promoteTurn",
                    "putMemory", "putProject", "requestExport", "saveTemporary", "updateConversation"],
    "SearchService": ["query"],
    "SourceService": ["clearPolicy", "createConsent", "getPolicy", "revokeConsent", "setPolicy"],
    "TaskService": ["cancel", "create", "get", "getDetails", "list", "pause", "resume", "retryAttempt", "steer"],
}

CON21_RECORD_MESSAGE_NAMES = {
    "SimulationDefinition", "ScenarioVersion", "SimulationRun", "SimulationSegment", "SimulationProfile",
    "ScenarioSpec", "ScenarioExpression", "AstNode", "UnaryExpression", "BinaryExpression",
    "FunctionExpression", "GeneratorSpec", "PulseSpec", "StepPoint", "FaultSpec", "CsvReplaySchema", "CsvColumn",
}
CON21_PUBLIC_SERVICE_METHODS = {
    "SimulationService": ["listDefinitions", "getDefinition", "createDefinition", "publishScenarioVersion",
                           "startRun", "pauseRun", "resumeRun", "cancelRun", "getRun", "listRuns",
                           "listSegments", "getSegmentTicket", "pollState"],
}
CON11_PUBLIC_SERVICE_METHODS = {
    "ApplicationService": ["list", "heartbeat", "disconnect"],
    "HistoryService": ["beginImport", "finalizeImport", "getImport", "cancelImport"],
    "ExecutionService": ["startTransientTurn", "readOutput", "watchOutput", "acknowledgeOutput",
                         "purgeTransient"],
    "EventService": ["poll", "watch"],
}


class DocumentationAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"index.html": b"API 1.0.0-ci.1.1", "script.js": b"reviewed script",
                    "ui-kit/ui-kit.min.css": b"@font-face{src:url(font.woff)}body{font-family:system-ui}",
                    "ui-kit/fonts/font.woff": b"excluded font"}
        self.policy = {"fixed": {
            "script.js": {"upstreamSha256": documentation.sha(self.raw["script.js"]),
                          "distributedSha256": documentation.sha(self.raw["script.js"])},
            "ui-kit/ui-kit.min.css": {"upstreamSha256": documentation.sha(self.raw["ui-kit/ui-kit.min.css"]),
                                      "distributedSha256": documentation.sha(b"body{font-family:system-ui}")}},
            "excluded": {"ui-kit/fonts/font.woff": documentation.sha(b"excluded font")},
            "modules": {"fixture": {"pages": {"index.html": documentation.sha(b"API {version}")}, "publicApi": {}}},
            "fontTransform": {"declarations": 1}}

    def test_known_transform_retains_api_and_uses_system_fonts(self):
        result = documentation.admit(self.raw, "fixture", "1.0.0-ci.1.1", self.policy)
        self.assertNotIn("ui-kit/fonts/font.woff", result)
        self.assertEqual(result["ui-kit/ui-kit.min.css"], b"body{font-family:system-ui}")
        self.assertEqual(result["index.html"], b"API 1.0.0-ci.1.1")
        self.raw["index.html"] = b"API 1.0.0-ci.999.2"
        documentation.admit(self.raw, "fixture", "1.0.0-ci.999.2", self.policy)

    def test_unknown_missing_and_changed_resources_fail(self):
        changes = [lambda d: d.update({"extra.js": b"unreviewed"}), lambda d: d.pop("index.html"),
                   lambda d: d.update({"script.js": b"changed code"}),
                   lambda d: d.update({"index.html": b"incomplete API 1.0.0-ci.1.1"}),
                   lambda d: d.update({"ui-kit/fonts/font.woff": b"new font"})]
        for change in changes:
            with self.subTest(change=change):
                raw = copy.deepcopy(self.raw)
                change(raw)
                with self.assertRaises(ValueError):
                    documentation.admit(raw, "fixture", "1.0.0-ci.1.1", self.policy)

    def test_reviewed_page_cannot_restore_an_inherited_parser_alias(self):
        page = b'Id <a anchor-label="getValue"></a><a anchor-label="hasValue"></a>'
        raw = {"index.html": page}
        policy = {"fixed": {}, "excluded": {}, "modules": {"contracts-proto": {
            "pages": {"index.html": documentation.sha(page)},
            "publicApi": {"index.html": ["Id", 'anchor-label="getValue"', 'anchor-label="hasValue"']}}}}
        documentation.admit(raw, "contracts-proto", "1.0.0-SNAPSHOT", policy)
        raw["index.html"] += b'<a anchor-label="getParserForType" href="../unrelated/index.html"></a>'
        policy["modules"]["contracts-proto"]["pages"]["index.html"] = documentation.sha(raw["index.html"])
        with self.assertRaisesRegex(ValueError, "inherited parser alias"):
            documentation.admit(raw, "contracts-proto", "1.0.0-SNAPSHOT", policy)

    def test_public_api_marker_field_cannot_be_omitted(self):
        del self.policy["modules"]["fixture"]["publicApi"]
        with self.assertRaisesRegex(ValueError, "no public API marker field"):
            documentation.admit(self.raw, "fixture", "1.0.0-ci.1.1", self.policy)

    def test_r18_profile_preserves_reviewed_resources_and_retires_native_client(self):
        root = Path(__file__).resolve().parents[2]
        previous = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r5.json").read_bytes())
        current = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r18.json").read_bytes())
        self.assertEqual(set(current["modules"]),
                         {"contracts-proto", "contracts-connect-client", "contract-fixtures"})
        self.assertEqual(set(documentation.MODULES), set(current["modules"]))
        slug = lambda name: '-' + re.sub(r'(?<!^)([A-Z])', r'-\1', name).lower()
        con08_message_names = {
            "AttemptCharge", "BillingItem", "Capacity", "ChargeExplanation", "CheckoutView",
            "CommerceServiceAuthoriseExtraUsageRequest", "CommerceServiceAuthoriseExtraUsageResponse",
            "CommerceServiceAuthoriseExtraUsageValue", "CommerceServiceCancelSubscriptionRequest",
            "CommerceServiceCancelSubscriptionResponse", "CommerceServiceCancelSubscriptionValue",
            "CommerceServiceCreateCheckoutAttemptRequest", "CommerceServiceCreateCheckoutAttemptResponse",
            "CommerceServiceCreateCheckoutAttemptValue", "CommerceServiceCreatePurchaseIntentRequest",
            "CommerceServiceCreatePurchaseIntentResponse", "CommerceServiceCreatePurchaseIntentValue",
            "CommerceServiceExplainChargeRequest", "CommerceServiceExplainChargeResponse",
            "CommerceServiceExplainChargeValue", "CommerceServiceExportEvidenceRequest",
            "CommerceServiceExportEvidenceResponse", "CommerceServiceExportEvidenceValue",
            "CommerceServiceGetCatalogueRequest", "CommerceServiceGetCatalogueResponse",
            "CommerceServiceGetCatalogueValue", "CommerceServiceGetCreditsRequest",
            "CommerceServiceGetCreditsResponse", "CommerceServiceGetCreditsValue",
            "CommerceServiceGetPurchaseStateRequest", "CommerceServiceGetPurchaseStateResponse",
            "CommerceServiceGetPurchaseStateValue", "CommerceServiceGetSubscriptionRequest",
            "CommerceServiceGetSubscriptionResponse", "CommerceServiceGetSubscriptionValue",
            "CommerceServiceListBillingHistoryRequest", "CommerceServiceListBillingHistoryResponse",
            "CommerceServiceListBillingHistoryValue", "CommerceServiceReactivateSubscriptionRequest",
            "CommerceServiceReactivateSubscriptionResponse", "CommerceServiceReactivateSubscriptionValue",
            "CommerceServiceRequestRefundRequest", "CommerceServiceRequestRefundResponse",
            "CommerceServiceRequestRefundValue", "CommerceServiceRevokeExtraUsageRequest",
            "CommerceServiceRevokeExtraUsageResponse", "CommerceServiceRevokeExtraUsageValue",
            "CreditLot", "CreditPool", "EntitlementServiceCheckRequest", "EntitlementServiceCheckResponse",
            "EntitlementServiceCheckValue", "EntitlementServiceGetCapacityRequest",
            "EntitlementServiceGetCapacityResponse", "EntitlementServiceGetCapacityValue",
            "EntitlementServiceGetServiceTermRequest", "EntitlementServiceGetServiceTermResponse",
            "EntitlementServiceGetServiceTermValue", "EntitlementServiceGetSnapshotRequest",
            "EntitlementServiceGetSnapshotResponse", "EntitlementServiceGetSnapshotValue",
            "EntitlementServiceGetUsageRequest", "EntitlementServiceGetUsageResponse",
            "EntitlementServiceGetUsageValue", "EntitlementServiceListGrantsRequest",
            "EntitlementServiceListGrantsResponse", "EntitlementServiceListGrantsValue",
            "EntitlementSnapshot", "ExportJob", "Grant", "ModelUsage", "Offer", "PurchaseView",
            "QuotaUsage", "RefundView", "ServiceTerm", "SpendBudget", "SubscriptionView",
        }
        con08_constraints = json.loads(
            (root / "public/proto/constraints/con-08-entitlement-commerce.json").read_bytes())
        self.assertEqual(len(con08_message_names), 78)
        self.assertEqual({name.rsplit(".", 1)[-1] for name in con08_constraints["messages"]},
                         con08_message_names)
        con08_proto_pages = {
            "contracts-proto/io.github.arcforges.contracts.publicapi.v1/" + slug(name) + "/index.html"
            for name in con08_message_names
        }
        con08_entitlement_methods = {
            "getSnapshot", "getServiceTerm", "getCapacity", "listGrants", "getUsage", "check"
        }
        con08_commerce_methods = {
            "authoriseExtraUsage", "revokeExtraUsage", "explainCharge", "getCatalogue",
            "createPurchaseIntent", "createCheckoutAttempt", "getPurchaseState", "getSubscription",
            "cancelSubscription", "reactivateSubscription", "getCredits", "listBillingHistory",
            "requestRefund", "exportEvidence",
        }
        self.assertEqual(len(con08_entitlement_methods), 6)
        self.assertEqual(len(con08_commerce_methods), 14)
        con08_client_pages = {}
        for service, methods in (("EntitlementService", con08_entitlement_methods),
                                 ("CommerceService", con08_commerce_methods)):
            for suffix in ("Client", "ClientInterface"):
                page = ("contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/" +
                        slug(service + suffix) + "/index.html")
                con08_client_pages[page] = methods
        con09_client_pages = {
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/-resource-service-client/index.html": {
                "beginUpload", "completeUpload", "getDownloadTicket", "getMetadata", "release",
                "getUploadStatus", "renewUploadTicket",
            },
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/-resource-service-client-interface/index.html": {
                "beginUpload", "completeUpload", "getDownloadTicket", "getMetadata", "release",
                "getUploadStatus", "renewUploadTicket",
            },
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/-sync-service-client/index.html": {
                "listScopes", "setScope", "pullChanges", "pushChange", "pushBatch", "getAggregate",
                "listConflicts", "resolveConflict", "requestFullResync", "getBootstrapPage",
            },
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/-sync-service-client-interface/index.html": {
                "listScopes", "setScope", "pullChanges", "pushChange", "pushBatch", "getAggregate",
                "listConflicts", "resolveConflict", "requestFullResync", "getBootstrapPage",
            },
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/-transfer-service-client/index.html": {
                "requestExport", "previewImport", "commitImport", "get", "list", "cancel",
            },
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/-transfer-service-client-interface/index.html": {
                "requestExport", "previewImport", "commitImport", "get", "list", "cancel",
            },
        }
        self.assertEqual(len(con09_client_pages), 6)
        con10_message_names = {name.rsplit(".", 1)[-1] for name in json.loads(
            (root / "public/proto/constraints/con-10-chat-task-agent.json").read_bytes())["messages"]}
        self.assertEqual(len(con10_message_names), 191)
        con10_proto_pages = {
            "contracts-proto/io.github.arcforges.contracts.publicapi.v1/" + slug(name) + "/index.html"
            for name in con10_message_names
        }
        con10_client_pages = {
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/" + slug(service + suffix) + "/index.html": methods
            for service, methods in CON10_PUBLIC_SERVICE_METHODS.items()
            for suffix in ("Client", "ClientInterface")
        }
        self.assertEqual(len(con10_client_pages), 16)
        self.assertEqual(sum(len(methods) for methods in CON10_PUBLIC_SERVICE_METHODS.values()), 57)
        con22_message_names = {
            "DataServiceGetExportStateRequest", "DataServiceGetExportStateResponse", "DataServiceGetExportStateValue",
            "DataServiceRequestExportRequest", "DataServiceRequestExportResponse", "DataServiceRequestExportValue",
            "ExportServiceCancelRequest", "ExportServiceCancelResponse", "ExportServiceCancelValue",
            "ExportServiceGetDownloadRequest", "ExportServiceGetDownloadResponse", "ExportServiceGetDownloadValue",
            "ExportServiceGetStatusRequest", "ExportServiceGetStatusResponse", "ExportServiceGetStatusValue",
            "NotificationServiceAcknowledgeRequest", "NotificationServiceAcknowledgeResponse",
            "NotificationServiceAcknowledgeValue", "NotificationServiceListRequest",
            "NotificationServiceListResponse", "NotificationServiceListValue",
            "NotificationServiceRegisterPushRequest", "NotificationServiceRegisterPushResponse",
            "NotificationServiceRegisterPushValue", "NotificationServiceUnregisterPushRequest",
            "NotificationServiceUnregisterPushResponse", "NotificationServiceUnregisterPushValue",
            "NotificationView", "PolicyBundle", "PolicyServiceGetBundleRequest", "PolicyServiceGetBundleResponse",
            "PolicyServiceGetBundleValue", "PreferenceServicePutRequest", "PreferenceServicePutResponse",
            "PreferenceServicePutValue", "SupportCase", "SupportMessage", "SupportServiceAppendMessageRequest",
            "SupportServiceAppendMessageResponse", "SupportServiceAppendMessageValue",
            "SupportServiceCreateCaseRequest", "SupportServiceCreateCaseResponse", "SupportServiceCreateCaseValue",
            "SupportServiceDecideAccessRequest", "SupportServiceDecideAccessResponse",
            "SupportServiceDecideAccessValue", "SupportServiceListCasesRequest",
            "SupportServiceListCasesResponse", "SupportServiceListCasesValue",
        }
        self.assertEqual(len(con22_message_names), 49)
        con22_schema_message_names = {name.rsplit(".", 1)[-1] for name in json.loads(
            (root / "public/proto/constraints/con-22-account-support.json").read_bytes())["messages"]}
        self.assertEqual(con22_schema_message_names, con22_message_names)
        con22_proto_pages = {
            "contracts-proto/io.github.arcforges.contracts.publicapi.v1/" + slug(name) + "/index.html"
            for name in con22_message_names
        }
        con22_public_service_methods = {
            "DataService": {"requestExport", "getExportState"},
            "ExportService": {"getStatus", "cancel", "getDownload"},
            "NotificationService": {"list", "acknowledge", "registerPush", "unregisterPush"},
            "PolicyService": {"getBundle"},
            "PreferenceService": {"put"},
            "SupportService": {"createCase", "listCases", "appendMessage", "decideAccess"},
        }
        self.assertEqual(len(con22_public_service_methods), 6)
        self.assertEqual(sum(len(methods) for methods in con22_public_service_methods.values()), 15)
        con22_client_pages = {
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/" + slug(service + suffix) + "/index.html": methods
            for service, methods in con22_public_service_methods.items()
            for suffix in ("Client", "ClientInterface")
        }
        self.assertEqual(len(con22_client_pages), 12)
        con21_shard = json.loads((root / "public/proto/constraints/con-21-simulation.json").read_bytes())
        con21_methods = CON21_PUBLIC_SERVICE_METHODS["SimulationService"]
        con21_message_names = CON21_RECORD_MESSAGE_NAMES | {
            "SimulationService" + method[0].upper() + method[1:] + suffix
            for method in con21_methods for suffix in ("Request", "Value", "Response")
        }
        self.assertEqual(len(CON21_RECORD_MESSAGE_NAMES), 17)
        self.assertEqual(len(con21_message_names), 56)
        self.assertEqual({name.rsplit(".", 1)[-1] for name in con21_shard["messages"]}, con21_message_names)
        con21_proto_pages = {
            "contracts-proto/io.github.arcforges.contracts.simulation.v1/" + slug(name) + "/index.html"
            for name in con21_message_names
        }
        con21_client_pages = {
            "contracts-connect-client/io.github.arcforges.contracts.simulation.v1/" +
            slug("SimulationService" + suffix) + "/index.html": con21_methods
            for suffix in ("Client", "ClientInterface")
        }
        self.assertEqual(len(con21_client_pages), 2)
        con24_shard = json.loads((root / "public/proto/constraints/con-24-scope-library.json").read_bytes())
        con24_message_names = {name.rsplit(".", 1)[-1] for name in con24_shard["messages"]}
        self.assertEqual(len(con24_message_names), 11)
        con24_message_pages = {
            "contracts-proto/io.github.arcforges.contracts.publicapi.v1/" + slug(name) + "/index.html": name
            for name in con24_message_names
        }
        con24_proto_pages = set(con24_message_pages)
        con24_methods = ["listProjects", "listSessions", "getSession"]
        con24_client_pages = {
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/" +
            slug("ScopeService" + suffix) + "/index.html": con24_methods
            for suffix in ("Client", "ClientInterface")
        }
        for section in ("source", "fixed", "excluded", "components", "fontTransform"):
            self.assertEqual(current[section], previous[section], section)
        for module in current["modules"]:
            from check_foundation import RETIRED_MESSAGES, RETIRED_FIELDS
            expected = {}
            for name, markers in previous["modules"][module]["publicApi"].items():
                if any('/' + slug(record) + '/' in name for record in RETIRED_MESSAGES):
                    continue
                retired_markers = set()
                for record, fields in RETIRED_FIELDS.items():
                    if '/' + slug(record) + '/' in name:
                        for field in fields:
                            suffix = ''.join(word.title() for word in field['name'].split('_'))
                            retired_markers.update('anchor-label="' + prefix + suffix + '"' for prefix in ('get', 'has'))
                expected[name] = [marker for marker in markers if marker not in retired_markers]
                if name == "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-aggregate-body/index.html":
                    expected[name].extend(['anchor-label="getScopeProjectMetadata"',
                                           'anchor-label="hasScopeProjectMetadata"'])
            actual = current["modules"][module]["publicApi"]
            self.assertEqual({name: actual[name] for name in expected}, expected,
                             "Only explicitly retired message/field markers may be removed")
            additions = set(actual) - set(expected)
            descriptors = {"OperationBinding", "CancelSupport", "CapabilityLimits", "CapabilityDescriptor",
                           "ActionDescriptor", "ContractVersion", "ContractCompatibility", "FeatureSet",
                           "CompatibilityDescriptor", "InstanceReadiness", "HealthSnapshot", "EncodedBodyRef",
                           "ContextProvider", "ContextDescriptor"}
            descriptor_pages = {
                "contracts-proto/io.github.arcforges.contracts." +
                ("publicapi" if name.startswith("Context") else "foundation") + ".v1/" + slug(name) + "/index.html"
                for name in descriptors
            }
            operations = {"RegisterPublisher", "VerifyPublisher", "Search", "GetPackage",
                          "ListVersions", "SubmitVersion", "GetSubmission"}
            catalog_messages = {"PublisherView", "CatalogPackageView", "CatalogVersionView", "CatalogSubmissionView"}
            catalog_messages |= {"CatalogService" + operation + suffix for operation in operations
                                 for suffix in ("Request", "Response", "Value")}
            catalog_pages = {"contracts-proto/io.github.arcforges.contracts.catalog.v1/" + slug(name) + "/index.html"
                             for name in catalog_messages}
            inprocess_messages = {"ContextRequest", "ContextContribution", "ContextItem", "Availability",
                                  "PreviewRequest", "ResourceMetadata", "ApprovalView", "TurnOptions",
                                  "KnowledgePolicy", "KnowledgePolicyPatch", "SourcePolicyView", "SourceConsentSpec",
                                  "ScopeProjectMetadata"}
            inprocess_pages = {"contracts-proto/io.github.arcforges.contracts.publicapi.v1/" + slug(name) + "/index.html"
                               for name in inprocess_messages}
            con09_proto_pages = {
                "contracts-proto/io.github.arcforges.contracts.foundation.v1/-transfer-ticket/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-aggregate-view/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-bootstrap-manifest/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-change-proposal/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-change-receipt/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-conflict-resolution/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-conflict-view/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-part-receipt/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-begin-upload-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-begin-upload-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-begin-upload-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-complete-upload-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-complete-upload-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-complete-upload-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-get-download-ticket-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-get-download-ticket-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-get-download-ticket-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-get-metadata-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-get-metadata-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-get-metadata-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-get-upload-status-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-get-upload-status-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-get-upload-status-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-release-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-release-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-release-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-renew-upload-ticket-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-renew-upload-ticket-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-resource-service-renew-upload-ticket-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-change/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-scope/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-get-aggregate-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-get-aggregate-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-get-aggregate-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-get-bootstrap-page-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-get-bootstrap-page-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-get-bootstrap-page-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-list-conflicts-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-list-conflicts-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-list-conflicts-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-list-scopes-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-list-scopes-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-list-scopes-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-pull-changes-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-pull-changes-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-pull-changes-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-push-batch-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-push-batch-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-push-batch-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-push-change-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-push-change-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-push-change-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-request-full-resync-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-request-full-resync-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-request-full-resync-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-resolve-conflict-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-resolve-conflict-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-resolve-conflict-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-set-scope-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-set-scope-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-sync-service-set-scope-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-issue/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-job/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-manifest/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-mapping/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-root/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-cancel-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-cancel-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-cancel-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-commit-import-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-commit-import-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-commit-import-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-get-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-get-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-get-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-list-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-list-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-list-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-preview-import-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-preview-import-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-preview-import-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-request-export-request/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-request-export-response/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-transfer-service-request-export-value/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-upload-status/index.html",
                "contracts-proto/io.github.arcforges.contracts.publicapi.v1/-upload-ticket/index.html",
            }
            self.assertEqual(len(con09_proto_pages), 86)
            clients = {"contracts-connect-client/io.github.arcforges.contracts.catalog.v1/" + slug(name) + "/index.html"
                       for name in ("CatalogServiceClient", "CatalogServiceClientInterface")}
            permitted = descriptor_pages | catalog_pages | inprocess_pages | con08_proto_pages \
                | con09_proto_pages | con10_proto_pages | con22_proto_pages | con21_proto_pages \
                | con24_proto_pages if module == "contracts-proto" else (
                    clients | set(con08_client_pages) | set(con09_client_pages)
                    | set(con10_client_pages) | set(con22_client_pages) | set(con21_client_pages)
                    | set(con24_client_pages)
                    if module == "contracts-connect-client" else set())
            self.assertEqual(additions, permitted)
            for name in additions:
                if module == "contracts-proto":
                    self.assertIn('anchor-label="parser"', actual[name])
                    if name in con24_proto_pages:
                        self.assertIn(con24_message_pages[name], actual[name])
                    if name in con09_proto_pages:
                        self.assertTrue(any(marker.startswith('anchor-label="get') or marker.startswith("get")
                                            for marker in actual[name]), name)
                    else:
                        self.assertTrue(any(marker.startswith('anchor-label="get') for marker in actual[name]), name)
                else:
                    if name in con24_client_pages:
                        expected_methods = set(con24_client_pages[name])
                    elif name in con21_client_pages:
                        expected_methods = set(con21_client_pages[name])
                    elif name in con22_client_pages:
                        expected_methods = set(con22_client_pages[name])
                    elif name in con10_client_pages:
                        expected_methods = set(con10_client_pages[name])
                    elif name in con09_client_pages:
                        expected_methods = con09_client_pages[name]
                    elif name in con08_client_pages:
                        expected_methods = con08_client_pages[name]
                    else:
                        expected_methods = {operation[0].lower() + operation[1:] for operation in operations}
                    self.assertEqual(set(actual[name]), expected_methods)
        self.assertFalse(any("/contracts-client/" in name for name in current["inputs"]))
        proto_pages = current["modules"]["contracts-proto"]["publicApi"]
        self.assertTrue(any("foundation.v1" in name for name in proto_pages))
        self.assertTrue(any("events.v1" in name for name in proto_pages))
        self.assertTrue(any("publicapi.v1/-aggregate-body/" in name for name in proto_pages))
        self.assertFalse(any("publicapi.v1/-notes-query/" in name for name in proto_pages))
        self.assertTrue(any("publicapi.v1/-measurement-result/" in name for name in proto_pages))

    def test_con21_dokka_r17_is_only_the_frozen_r16_successor_delta(self):
        root = Path(__file__).resolve().parents[2]
        previous = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r16.json").read_bytes())
        current = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r17.json").read_bytes())
        resource_record = json.loads((root / "eng/provenance/records/dokka-documentation-resources-r17.json").read_bytes())
        inventory = json.loads((root / "eng/provenance/files.json").read_bytes())

        self.assertEqual(resource_record["id"], "dokka-documentation-resources-r17")
        self.assertEqual(resource_record["supersedes"], "dokka-documentation-resources-r16")
        self.assertIn("r17 successor supersedes r16", resource_record["review"]["rationale"])
        self.assertIn("ORG_GRADLE_PROJECT_releaseVersion=1.0.0-ci.999.1", resource_record["verification"]["command"])
        self.assertIn("eng/provenance/artifact-profiles/dokka-2-2-0-r18.json", inventory["firstParty"])
        self.assertIn("eng/provenance/records/dokka-documentation-resources-r18.json", inventory["firstParty"])
        self.assertIn("eng/provenance/artifact-profiles/dokka-2-2-0-r17.json", inventory["firstParty"])
        self.assertIn("eng/provenance/records/dokka-documentation-resources-r17.json", inventory["firstParty"])

        def key_fingerprint(keys):
            return documentation.sha(("".join(key + "\n" for key in sorted(keys))).encode("utf-8"))

        def row_fingerprint(rows):
            return documentation.sha(("".join(row + "\n" for row in sorted(rows))).encode("utf-8"))

        def slug(name):
            return "-" + re.sub(r"(?<!^)([A-Z])", r"-\1", name).lower()

        for section in ("source", "fixed", "excluded", "components", "fontTransform"):
            self.assertEqual(current[section], previous[section], section)
        self.assertEqual(set(previous["inputs"]) - set(current["inputs"]), set())
        self.assertEqual({key for key in previous["inputs"] if current["inputs"][key] != previous["inputs"][key]}, set())
        added_inputs = set(current["inputs"]) - set(previous["inputs"])
        self.assertEqual(len(added_inputs), 59)
        self.assertEqual(key_fingerprint(added_inputs),
                         "baf5d22395919487acb3cb16adf5a85e9937ee6ff38feef465c39c1aeff98421")
        self.assertTrue(all("/simulation/v1/" in name for name in added_inputs))

        expected_page_deltas = {
            "contracts-proto": (3626, "46b335390a4f8e8ec040e5256073d712b84fd3492330bb1de7e5815b8112b08d",
                                {"contracts-proto/package-list", "index.html", "navigation.html", "scripts/pages.json"},
                                "81e143bbd67bbb205d1530595de3a31db3d11b866ac7fcc78295ccab8c1cd66d",
                                "762f8d51352acc113f4e091888bfbd526ffdc82084657050d8e65cc48aa5ee15"),
            "contracts-connect-client": (30, "66445da165db73bbad92b362386bd0d59b30a2cf94a72fdf107aca72831c305c",
                                          {"contracts-connect-client/package-list", "index.html", "navigation.html",
                                           "scripts/pages.json"},
                                          "eafdffbbb9ac95c22e07fc6de1efab2fbacfcf43fd797a66435a325c0d4c3ea6",
                                          "795acfc6481c63e6724784df37a0db9f89c5b0e7a27ca48b5fd9d54738549f84"),
            "contract-fixtures": (0, None, set(), None, None),
        }
        for module, (count, added_hash, expected_changed, changed_hash, changed_rows_hash) in expected_page_deltas.items():
            old_pages = previous["modules"][module]["pages"]
            new_pages = current["modules"][module]["pages"]
            added = set(new_pages) - set(old_pages)
            removed = set(old_pages) - set(new_pages)
            changed = {key for key in set(old_pages) & set(new_pages) if old_pages[key] != new_pages[key]}
            self.assertEqual(len(added), count, module)
            self.assertEqual(removed, set(), module)
            self.assertEqual(changed, expected_changed, module)
            if added_hash is not None:
                self.assertEqual(key_fingerprint(added), added_hash, module)
            if changed_hash is not None:
                self.assertEqual(key_fingerprint(changed), changed_hash, module)
                self.assertEqual(row_fingerprint([f"{key}\t{old_pages[key]}\t{new_pages[key]}" for key in changed]),
                                 changed_rows_hash, module)

        proto_names = CON21_RECORD_MESSAGE_NAMES | {
            "SimulationService" + method[0].upper() + method[1:] + suffix
            for method in CON21_PUBLIC_SERVICE_METHODS["SimulationService"]
            for suffix in ("Request", "Value", "Response")
        }
        expected_proto_api = {
            "contracts-proto/io.github.arcforges.contracts.simulation.v1/" + slug(name) + "/index.html"
            for name in proto_names
        }
        previous_proto_api = previous["modules"]["contracts-proto"]["publicApi"]
        current_proto_api = current["modules"]["contracts-proto"]["publicApi"]
        added_proto_api = set(current_proto_api) - set(previous_proto_api)
        self.assertEqual(added_proto_api, expected_proto_api)
        self.assertEqual(key_fingerprint(added_proto_api),
                         "680330d03723c45f1d9889b80b9788665171116508e8811c08fccbe663307e72")
        self.assertEqual(sum(len(current_proto_api[page]) for page in added_proto_api), 622)
        proto_rows = [page + "\t" + "\t".join(sorted(current_proto_api[page])) for page in added_proto_api]
        self.assertEqual(row_fingerprint(proto_rows),
                         "c47e27998253044c13cb549bb73dd7df74052d2b34c95d7c8f636cd84d5f7225")
        for name in proto_names:
            page = "contracts-proto/io.github.arcforges.contracts.simulation.v1/" + slug(name) + "/index.html"
            markers = current_proto_api[page]
            self.assertIn(name, markers)
            self.assertIn('anchor-label="parser"', markers)
            self.assertTrue(any(marker.startswith('anchor-label="get') for marker in markers), page)

        method_leaves = ["list-definitions", "get-definition", "create-definition", "publish-scenario-version",
                         "start-run", "pause-run", "resume-run", "cancel-run", "get-run", "list-runs",
                         "list-segments", "get-segment-ticket", "poll-state"]
        namespace = "contracts-connect-client/io.github.arcforges.contracts.simulation.v1/"
        expected_connect_pages = {namespace + "index.html"}
        for suffix in ("Client", "ClientInterface"):
            client = "SimulationService" + suffix
            directory = namespace + slug(client) + "/"
            expected_connect_pages.add(directory + "index.html")
            expected_connect_pages.update(directory + method + ".html" for method in method_leaves)
            if suffix == "Client":
                expected_connect_pages.add(directory + slug(client) + ".html")
        old_connect_pages = previous["modules"]["contracts-connect-client"]["pages"]
        new_connect_pages = current["modules"]["contracts-connect-client"]["pages"]
        added_connect_pages = set(new_connect_pages) - set(old_connect_pages)
        self.assertEqual(added_connect_pages, expected_connect_pages)
        old_connect_api = previous["modules"]["contracts-connect-client"]["publicApi"]
        new_connect_api = current["modules"]["contracts-connect-client"]["publicApi"]
        expected_connect_api = {
            namespace + slug("SimulationService" + suffix) + "/index.html"
            for suffix in ("Client", "ClientInterface")
        }
        added_connect_api = set(new_connect_api) - set(old_connect_api)
        self.assertEqual(added_connect_api, expected_connect_api)
        self.assertEqual(key_fingerprint(added_connect_api),
                         "b45da723a92548283ba3eaadf0311159537e9763ee1292d228d3c9aa7233d3c4")
        connect_rows = [page + "\t" + "\t".join(sorted(new_connect_api[page])) for page in added_connect_api]
        self.assertEqual(row_fingerprint(connect_rows),
                         "44b87adda0914a6ae45e97d2a8808b217ef8e81f316aee247041b90c9578e578")
        for page in expected_connect_api:
            self.assertEqual(set(new_connect_api[page]), set(CON21_PUBLIC_SERVICE_METHODS["SimulationService"]))
        self.assertEqual(current["modules"]["contract-fixtures"]["publicApi"],
                         previous["modules"]["contract-fixtures"]["publicApi"])

    def test_con24_dokka_r18_is_only_the_frozen_r17_successor_delta(self):
        root = Path(__file__).resolve().parents[2]
        previous = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r17.json").read_bytes())
        current_path = "eng/provenance/artifact-profiles/dokka-2-2-0-r18.json"
        current = json.loads((root / current_path).read_bytes())
        resource_record = json.loads((root / "eng/provenance/records/dokka-documentation-resources-r18.json").read_bytes())
        inventory = json.loads((root / "eng/provenance/files.json").read_bytes())

        def key_fingerprint(keys):
            return documentation.sha(("".join(key + "\n" for key in sorted(keys))).encode("utf-8"))

        def row_fingerprint(rows):
            return documentation.sha(("".join(row + "\n" for row in sorted(rows))).encode("utf-8"))

        def slug(name):
            return "-" + re.sub(r"(?<!^)([A-Z])", r"-\1", name).lower()

        self.assertEqual(resource_record["id"], "dokka-documentation-resources-r18")
        self.assertEqual(resource_record["supersedes"], "dokka-documentation-resources-r17")
        self.assertIn(current_path, inventory["firstParty"])
        self.assertIn("eng/provenance/records/dokka-documentation-resources-r18.json", inventory["firstParty"])
        self.assertIn("ScopeService client/interface roots", resource_record["review"]["rationale"])
        profile_bytes = (root / current_path).read_bytes()
        profile_hash = documentation.sha(profile_bytes.replace(b"\r\n", b"\n"))
        self.assertTrue(all(target["profile"] == current_path and target["sha256"] == profile_hash
                            for target in resource_record["artifactTargets"]))
        self.assertEqual(resource_record["generation"]["inputs"][1]["commit"],
                         "d29ca2156f33d18052bb448ecc86661d96f30610")
        self.assertEqual(len(resource_record["generation"]["inputs"][1]["paths"]), 1487)

        for section in ("source", "fixed", "excluded", "components", "fontTransform"):
            self.assertEqual(current[section], previous[section], section)
        self.assertEqual(set(previous["inputs"]) - set(current["inputs"]), set())
        self.assertEqual({name for name in previous["inputs"] if previous["inputs"][name] != current["inputs"][name]}, set())
        added_inputs = set(current["inputs"]) - set(previous["inputs"])
        self.assertEqual(len(added_inputs), 14)
        self.assertEqual(key_fingerprint(added_inputs),
                         "1336d1702df9d22608d12e675c86c7f64b3340a519823f47e2acdfa42c18d049")
        self.assertEqual(sum("contracts-proto/generated/kotlin/" in path for path in added_inputs), 12)
        self.assertEqual(sum("contracts-connect-client/generated/kotlin/" in path for path in added_inputs), 2)
        self.assertTrue(all("/publicapi/v1/Scope" in path for path in added_inputs))

        expected_page_deltas = {
            "contracts-proto": (761, "bc46b5e7f75c2677aa5c8bfdd0407a399d1e8c6a661d667770e93756c0cc7d24",
                                {"contracts-proto/io.github.arcforges.contracts.publicapi.v1/copy.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/encoded-body-or-null.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/error-or-null.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/index.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/meta-or-null.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/min-revision-or-null.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/page-or-null.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/project-id-or-null.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/revision-or-null.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/session-id-or-null.html",
                                 "contracts-proto/io.github.arcforges.contracts.publicapi.v1/value-or-null.html",
                                 "contracts-proto/package-list", "navigation.html", "scripts/pages.json"},
                                "44c79c02b5a899344659264cf166b0e8f268824f58bd33143fdf6d465ce35d13",
                                "a22d860f683279b279fdd166ba86b0061bccfa454237d4df7123254280226ca3"),
            "contracts-connect-client": (9, "992036edadca2775a6423d68356a04601d1a7915eb0fa1988a866222ecab627d",
                                          {"contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/index.html",
                                           "contracts-connect-client/package-list", "navigation.html", "scripts/pages.json"},
                                          "22df5067ed7b3d4cc68b208d5fc85b26cec76af496776eda49eac131136145e6",
                                          "c9316d5f53fbf547146f82eb3d0036f8dddf29e94d1f3e189c48336ca890e367"),
            "contract-fixtures": (0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                                  set(), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                                  "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        }
        for module, (count, added_hash, expected_changed, changed_hash, changed_rows_hash) in expected_page_deltas.items():
            old_pages = previous["modules"][module]["pages"]
            new_pages = current["modules"][module]["pages"]
            added = set(new_pages) - set(old_pages)
            removed = set(old_pages) - set(new_pages)
            changed = {name for name in set(old_pages) & set(new_pages) if old_pages[name] != new_pages[name]}
            self.assertEqual(len(added), count, module)
            self.assertEqual(removed, set(), module)
            self.assertEqual(changed, expected_changed, module)
            self.assertEqual(key_fingerprint(added), added_hash, module)
            self.assertEqual(key_fingerprint(changed), changed_hash, module)
            self.assertEqual(row_fingerprint([f"{name}\t{old_pages[name]}\t{new_pages[name]}" for name in changed]),
                             changed_rows_hash, module)

        shard = json.loads((root / "public/proto/constraints/con-24-scope-library.json").read_bytes())
        expected_proto_api = {
            "contracts-proto/io.github.arcforges.contracts.publicapi.v1/" + slug(name.rsplit(".", 1)[-1]) + "/index.html"
            for name in shard["messages"]
        }
        old_proto_api = previous["modules"]["contracts-proto"]["publicApi"]
        proto_api = current["modules"]["contracts-proto"]["publicApi"]
        added_proto_api = set(proto_api) - set(old_proto_api)
        self.assertEqual(added_proto_api, expected_proto_api)
        self.assertEqual(key_fingerprint(added_proto_api),
                         "5ed44f5cf5b181b0ea24820a0c3567e5cc675ecdb501589db11a60fcb7a6aa68")
        proto_rows = [page + "\t" + "\t".join(sorted(proto_api[page])) for page in added_proto_api]
        self.assertEqual(row_fingerprint(proto_rows),
                         "34f9debc9c3062dd4b8761b6bc4ce036864bf919171d34324ad718fbc62968c0")
        for name, message in shard["messages"].items():
            message_name = name.rsplit(".", 1)[-1]
            page = "contracts-proto/io.github.arcforges.contracts.publicapi.v1/" + slug(message_name) + "/index.html"
            markers = proto_api[page]
            self.assertIn(message_name, markers)
            self.assertIn('anchor-label="parser"', markers)
            for field in message["fields"]:
                self.assertIn('anchor-label="get' + field[0].upper() + field[1:] + '"', markers, page)

        methods = {"listProjects", "listSessions", "getSession"}
        namespace = "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/"
        expected_connect_api = {
            namespace + slug("ScopeService" + suffix) + "/index.html"
            for suffix in ("Client", "ClientInterface")
        }
        old_connect_api = previous["modules"]["contracts-connect-client"]["publicApi"]
        connect_api = current["modules"]["contracts-connect-client"]["publicApi"]
        added_connect_api = set(connect_api) - set(old_connect_api)
        self.assertEqual(added_connect_api, expected_connect_api)
        self.assertEqual(key_fingerprint(added_connect_api),
                         "2d7d1d2b3a85cdb353e0c68947711f2f88178f2d621ccf7264666faf97cedf2f")
        connect_rows = [page + "\t" + "\t".join(sorted(connect_api[page])) for page in added_connect_api]
        self.assertEqual(row_fingerprint(connect_rows),
                         "f6cfa17cb5dd69d9908a3a5d5d61861591f15f0b41b372eeaa751d3087573a02")
        for page in expected_connect_api:
            self.assertEqual(set(connect_api[page]), methods)
        self.assertEqual(current["modules"]["contract-fixtures"]["publicApi"],
                         previous["modules"]["contract-fixtures"]["publicApi"])

    def test_con11_dokka_r19_is_only_the_frozen_r18_successor_delta(self):
        root = Path(__file__).resolve().parents[2]
        previous_path = "eng/provenance/artifact-profiles/dokka-2-2-0-r18.json"
        current_path = "eng/provenance/artifact-profiles/dokka-2-2-0-r19.json"
        previous = json.loads((root / previous_path).read_bytes())
        current = json.loads((root / current_path).read_bytes())
        previous_record = json.loads(
            (root / "eng/provenance/records/dokka-documentation-resources-r18.json").read_bytes())
        resource_record = json.loads(
            (root / "eng/provenance/records/dokka-documentation-resources-r19.json").read_bytes())
        inventory = json.loads((root / "eng/provenance/files.json").read_bytes())

        self.assertEqual(resource_record["id"], "dokka-documentation-resources-r19")
        self.assertEqual(resource_record["supersedes"], previous_record["id"])
        for path in (previous_path, current_path,
                     "eng/provenance/records/dokka-documentation-resources-r18.json",
                     "eng/provenance/records/dokka-documentation-resources-r19.json"):
            self.assertIn(path, inventory["firstParty"])
        profile_hash = documentation.sha((root / current_path).read_bytes().replace(b"\r\n", b"\n"))
        self.assertEqual(len(resource_record["artifactTargets"]), 3)
        self.assertTrue(all(target["profile"] == current_path and target["sha256"] == profile_hash
                            for target in resource_record["artifactTargets"]))

        for section in ("source", "fixed", "excluded", "components", "fontTransform"):
            self.assertEqual(current[section], previous[section], section)
        self.assertEqual(len(current["inputs"]), 2046)

        shard = json.loads((root / "public/proto/constraints/con-11-application-streams.json").read_bytes())
        self.assertEqual(len(shard["messages"]), 73)
        expected_added_inputs = set()
        expected_proto_api = {}
        for full_name in shard["messages"]:
            parts = full_name.split(".")
            namespace = "/".join(parts[1:3])
            message = parts[-1]
            java_base = ("src/public/kotlin/contracts-proto/generated/java/io/github/arcforges/contracts/" +
                         namespace + "/" + message)
            kotlin_path = ("src/public/kotlin/contracts-proto/generated/kotlin/io/github/arcforges/contracts/" +
                           namespace + "/" + message + "Kt.kt")
            expected_added_inputs.update({java_base + ".java", java_base + "OrBuilder.java", kotlin_path})
            page = ("contracts-proto/io.github.arcforges.contracts." + ".".join(parts[1:3]) + "/" +
                    "-" + re.sub(r"(?<!^)([A-Z])", r"-\1", message).lower() + "/index.html")
            expected_proto_api[page] = message

        expected_connect_api = {}
        for service, methods in CON11_PUBLIC_SERVICE_METHODS.items():
            namespace = "events" if service in {"EventService", "ExecutionService"} else "publicapi"
            source_base = ("src/public/kotlin/contracts-connect-client/generated/kotlin/io/github/arcforges/" +
                           "contracts/" + namespace + "/v1/" + service)
            expected_added_inputs.update({source_base + "Client.kt", source_base + "ClientInterface.kt"})
            for suffix in ("Client", "ClientInterface"):
                client = service + suffix
                page = ("contracts-connect-client/io.github.arcforges.contracts." + namespace + ".v1/" +
                        "-" + re.sub(r"(?<!^)([A-Z])", r"-\1", client).lower() + "/index.html")
                expected_connect_api[page] = methods

        expected_added_inputs.update({
            "src/public/kotlin/contracts-proto/generated/java/io/github/arcforges/contracts/publicapi/v1/ApplicationProto.java",
            "src/public/kotlin/contracts-proto/generated/java/io/github/arcforges/contracts/publicapi/v1/TranscriptRole.java",
            "src/public/kotlin/contracts-proto/generated/kotlin/io/github/arcforges/contracts/publicapi/v1/ApplicationProtoKt.proto.kt",
        })
        self.assertEqual(len(expected_added_inputs), 230)
        added_inputs = set(current["inputs"]) - set(previous["inputs"])
        changed_inputs = {path for path in set(current["inputs"]) & set(previous["inputs"])
                          if current["inputs"][path] != previous["inputs"][path]}
        removed_inputs = set(previous["inputs"]) - set(current["inputs"])
        expected_changed_inputs = {
            "src/public/kotlin/contracts-proto/generated/java/io/github/arcforges/contracts/events/v1/EntitlementChanged.java",
            "src/public/kotlin/contracts-proto/generated/kotlin/io/github/arcforges/contracts/events/v1/EntitlementChangedKt.kt",
        }
        self.assertEqual(added_inputs, expected_added_inputs)
        self.assertEqual(changed_inputs, expected_changed_inputs)
        self.assertEqual(removed_inputs, set())
        input_delta = {
            "added": [[path, current["inputs"][path]] for path in sorted(added_inputs)],
            "changed": [[path, previous["inputs"][path], current["inputs"][path]]
                        for path in sorted(changed_inputs)],
            "removed": [],
        }
        self.assertEqual(documentation.sha(json.dumps(input_delta, separators=(",", ":")).encode("utf-8")),
                         "159fea34de87c6b9cadb3a906a833a66405d84232945fb905d2d7dd8690f34ff")
        old_generation_paths = set(previous_record["generation"]["inputs"][1]["paths"])
        new_generation_paths = set(resource_record["generation"]["inputs"][1]["paths"])
        new_kotlin_sources = {path for path in expected_added_inputs if path.endswith(".kt")}
        self.assertEqual(len(new_generation_paths), 1569)
        self.assertEqual(new_generation_paths - old_generation_paths, new_kotlin_sources)
        self.assertEqual(len(new_kotlin_sources), 82)
        self.assertEqual(resource_record["generation"]["inputs"][1]["commit"],
                         "1ea545850b73705a5c37ab9d69184ed2c7df013c")

        expected_page_deltas = {
            "contracts-proto": (5231, 29, 0,
                                "93640434ab1fcc6b81e4b187f1a9f9db4c25b875b34c052b417982e1f868197e"),
            "contracts-connect-client": (41, 5, 0,
                                         "d66bbd8db688d3301bdf8d216c7c9405aff60e7745aff1bb6306f971d1815e51"),
            "contract-fixtures": (0, 0, 0,
                                  "4ddf799a685fa12b294e2c099c52d3b1d9f31b615b2be3e8d93de5b44a45ae8f"),
        }
        page_added_total = page_changed_total = page_removed_total = 0
        for module, (added_count, changed_count, removed_count, fingerprint) in expected_page_deltas.items():
            old_pages = previous["modules"][module]["pages"]
            new_pages = current["modules"][module]["pages"]
            added = [[page, new_pages[page]] for page in sorted(set(new_pages) - set(old_pages))]
            changed = [[page, old_pages[page], new_pages[page]]
                       for page in sorted(set(old_pages) & set(new_pages))
                       if old_pages[page] != new_pages[page]]
            removed = [[page, old_pages[page]] for page in sorted(set(old_pages) - set(new_pages))]
            self.assertEqual((len(added), len(changed), len(removed)),
                             (added_count, changed_count, removed_count), module)
            delta = {"added": added, "changed": changed, "removed": removed}
            encoded = json.dumps(delta, separators=(",", ":")).encode("utf-8")
            self.assertEqual(documentation.sha(encoded), fingerprint, module)
            page_added_total += len(added)
            page_changed_total += len(changed)
            page_removed_total += len(removed)
        self.assertEqual((page_added_total, page_changed_total, page_removed_total), (5272, 34, 0))

        old_proto_api = previous["modules"]["contracts-proto"]["publicApi"]
        current_proto_api = current["modules"]["contracts-proto"]["publicApi"]
        added_proto_api = set(current_proto_api) - set(old_proto_api)
        self.assertEqual(added_proto_api, set(expected_proto_api))
        self.assertEqual(len(added_proto_api), 73)
        for page, message in expected_proto_api.items():
            self.assertEqual(current_proto_api[page], [message, 'anchor-label="parser"'])

        old_connect_api = previous["modules"]["contracts-connect-client"]["publicApi"]
        current_connect_api = current["modules"]["contracts-connect-client"]["publicApi"]
        added_connect_api = set(current_connect_api) - set(old_connect_api)
        self.assertEqual(added_connect_api, set(expected_connect_api))
        self.assertEqual(len(added_connect_api), 8)
        self.assertEqual(sum(len(methods) for methods in CON11_PUBLIC_SERVICE_METHODS.values()), 14)
        for page, methods in expected_connect_api.items():
            self.assertEqual(current_connect_api[page], methods)
        self.assertEqual(len(added_proto_api) + len(added_connect_api), 81)
        self.assertFalse(any("RunStream" in page for page in added_proto_api | added_connect_api))
        self.assertEqual(current["modules"]["contract-fixtures"]["pages"],
                         previous["modules"]["contract-fixtures"]["pages"])
        self.assertEqual(current["modules"]["contract-fixtures"]["publicApi"],
                         previous["modules"]["contract-fixtures"]["publicApi"])

    def test_con07_dokka_r20_is_only_the_frozen_r19_successor_delta(self):
        root = Path(__file__).resolve().parents[2]
        previous_path = "eng/provenance/artifact-profiles/dokka-2-2-0-r19.json"
        current_path = "eng/provenance/artifact-profiles/dokka-2-2-0-r20.json"
        previous = json.loads((root / previous_path).read_bytes())
        current = json.loads((root / current_path).read_bytes())
        previous_record = json.loads(
            (root / "eng/provenance/records/dokka-documentation-resources-r19.json").read_bytes())
        resource_record = json.loads(
            (root / "eng/provenance/records/dokka-documentation-resources-r20.json").read_bytes())
        inventory = json.loads((root / "eng/provenance/files.json").read_bytes())

        def slug(name):
            return "-" + re.sub(r"(?<!^)([A-Z])", r"-\1", name).lower()

        self.assertEqual(documentation.PROFILE, current_path)
        self.assertEqual(resource_record["id"], "dokka-documentation-resources-r20")
        self.assertEqual(resource_record["supersedes"], previous_record["id"])
        self.assertEqual(inventory["artifacts"], [resource_record["id"]])
        for path in (previous_path, current_path,
                     "eng/provenance/records/dokka-documentation-resources-r19.json",
                     "eng/provenance/records/dokka-documentation-resources-r20.json"):
            self.assertIn(path, inventory["firstParty"])
        profile_hash = documentation.sha((root / current_path).read_bytes().replace(b"\r\n", b"\n"))
        self.assertEqual(len(resource_record["artifactTargets"]), 3)
        self.assertTrue(all(target["profile"] == current_path and target["sha256"] == profile_hash
                            for target in resource_record["artifactTargets"]))

        for section in ("source", "fixed", "excluded", "components", "fontTransform"):
            self.assertEqual(current[section], previous[section], section)
        self.assertEqual(len(previous["inputs"]), 2046)
        self.assertEqual(len(current["inputs"]), 2587)

        shard = json.loads((root / "public/proto/constraints/con-07-identity.json").read_bytes())
        self.assertEqual(len(shard["messages"]), 176)
        java_root = "src/public/kotlin/contracts-proto/generated/java/io/github/arcforges/contracts/publicapi/v1/"
        kotlin_root = "src/public/kotlin/contracts-proto/generated/kotlin/io/github/arcforges/contracts/publicapi/v1/"
        client_root = ("src/public/kotlin/contracts-connect-client/generated/kotlin/io/github/arcforges/"
                       "contracts/publicapi/v1/")
        expected_added_inputs = set()
        expected_proto_api = {}
        for full_name in shard["messages"]:
            parts = full_name.split(".")
            self.assertEqual(parts[1:3], ["publicapi", "v1"])
            message = parts[-1]
            expected_added_inputs.update({java_root + message + ".java", java_root + message + "OrBuilder.java",
                                          kotlin_root + message + "Kt.kt"})
            expected_proto_api["contracts-proto/io.github.arcforges.contracts.publicapi.v1/" +
                               slug(message) + "/index.html"] = message
        for enum in ("AuthMethod", "AuthPurpose", "ProtectionProfile", "RecoveryMethod", "TrustLevel"):
            expected_added_inputs.add(java_root + enum + ".java")
        expected_added_inputs.update({java_root + "IdentityProto.java", kotlin_root + "IdentityProtoKt.proto.kt"})
        services = ("IdentityService", "WorkspaceService", "DeviceService")
        for service in services:
            expected_added_inputs.update({client_root + service + "Client.kt",
                                          client_root + service + "ClientInterface.kt"})
        self.assertEqual(len(expected_added_inputs), 541)
        added_inputs = set(current["inputs"]) - set(previous["inputs"])
        changed_inputs = {path for path in set(current["inputs"]) & set(previous["inputs"])
                          if current["inputs"][path] != previous["inputs"][path]}
        self.assertEqual(added_inputs, expected_added_inputs)
        self.assertEqual(changed_inputs, {"build.gradle.kts"})
        self.assertEqual(set(previous["inputs"]) - set(current["inputs"]), set())
        input_delta = {"added": [[path, current["inputs"][path]] for path in sorted(added_inputs)],
                       "changed": [], "removed": []}
        self.assertEqual(documentation.sha(json.dumps(input_delta, separators=(",", ":")).encode("utf-8")),
                         "50d25058cae7227669a1f59e478398d1419923c9e45542e2ab699d27bb0416de")
        old_generation_paths = set(previous_record["generation"]["inputs"][1]["paths"])
        new_generation_paths = set(resource_record["generation"]["inputs"][1]["paths"])
        new_kotlin_sources = {path for path in expected_added_inputs if path.endswith(".kt")}
        self.assertEqual(len(new_kotlin_sources), 183)
        self.assertEqual(len(new_generation_paths), 1752)
        self.assertEqual(new_generation_paths - old_generation_paths, new_kotlin_sources)
        self.assertEqual(old_generation_paths - new_generation_paths, set())

        expected_page_deltas = {
            "contracts-proto": (10241, 28, 0,
                                "ae7c457995898c84917f7728b66c730dd1feb83ca84ca8883fc3525039eb4961"),
            "contracts-connect-client": (107, 4, 0,
                                         "36ef03351687f98ee1b920e1f83ab2e81a96837d190fc0bcad674f9d370f24a3"),
            "contract-fixtures": (0, 0, 0,
                                  "4ddf799a685fa12b294e2c099c52d3b1d9f31b615b2be3e8d93de5b44a45ae8f"),
        }
        for module, (added_count, changed_count, removed_count, fingerprint) in expected_page_deltas.items():
            old_pages = previous["modules"][module]["pages"]
            new_pages = current["modules"][module]["pages"]
            added = [[page, new_pages[page]] for page in sorted(set(new_pages) - set(old_pages))]
            changed = [[page, old_pages[page], new_pages[page]]
                       for page in sorted(set(old_pages) & set(new_pages))
                       if old_pages[page] != new_pages[page]]
            removed = [[page, old_pages[page]] for page in sorted(set(old_pages) - set(new_pages))]
            self.assertEqual((len(added), len(changed), len(removed)),
                             (added_count, changed_count, removed_count), module)
            delta = {"added": added, "changed": changed, "removed": removed}
            self.assertEqual(documentation.sha(json.dumps(delta, separators=(",", ":")).encode("utf-8")),
                             fingerprint, module)

        old_proto_api = previous["modules"]["contracts-proto"]["publicApi"]
        current_proto_api = current["modules"]["contracts-proto"]["publicApi"]
        added_proto_api = set(current_proto_api) - set(old_proto_api)
        self.assertEqual(added_proto_api, set(expected_proto_api))
        self.assertEqual(len(added_proto_api), 176)
        for page, message in expected_proto_api.items():
            self.assertIn(message, current_proto_api[page])
            self.assertIn('anchor-label="parser"', current_proto_api[page])

        fixture = json.loads((root / "fixtures/public/con-07-identity.json").read_bytes())
        fixture_services = {name.rsplit(".", 1)[-1]: methods for name, methods in fixture["services"].items()}
        old_connect_api = previous["modules"]["contracts-connect-client"]["publicApi"]
        current_connect_api = current["modules"]["contracts-connect-client"]["publicApi"]
        added_connect_api = set(current_connect_api) - set(old_connect_api)
        self.assertEqual(len(added_connect_api), 6)
        total_methods = 0
        for service in services:
            methods = {method[:1].lower() + method[1:] for method in fixture_services[service]}
            total_methods += len(methods)
            for suffix in ("Client", "ClientInterface"):
                page = ("contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/" +
                        slug(service + suffix) + "/index.html")
                self.assertIn(page, added_connect_api)
                self.assertEqual(set(current_connect_api[page]), methods)
        self.assertEqual(total_methods, 49)
        self.assertEqual(current["modules"]["contract-fixtures"]["pages"],
                         previous["modules"]["contract-fixtures"]["pages"])
        self.assertEqual(current["modules"]["contract-fixtures"]["publicApi"],
                         previous["modules"]["contract-fixtures"]["publicApi"])

    def test_con10_dokka_r15_is_only_the_frozen_r14_successor_delta(self):
        root = Path(__file__).resolve().parents[2]
        previous = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r14.json").read_bytes())
        current = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r15.json").read_bytes())

        def key_fingerprint(keys):
            return documentation.sha(("".join(key + "\n" for key in sorted(keys))).encode("utf-8"))

        def row_fingerprint(rows):
            return documentation.sha(("".join(row + "\n" for row in sorted(rows))).encode("utf-8"))

        def slug(name):
            return "-" + re.sub(r"(?<!^)([A-Z])", r"-\1", name).lower()

        for section in ("source", "fixed", "excluded", "components", "fontTransform"):
            self.assertEqual(current[section], previous[section], section)
        self.assertEqual(set(previous["inputs"]) - set(current["inputs"]), set())
        self.assertEqual({key for key in previous["inputs"] if current["inputs"][key] != previous["inputs"][key]}, set())
        added_inputs = set(current["inputs"]) - set(previous["inputs"])
        self.assertEqual(len(added_inputs), 593)
        self.assertEqual(key_fingerprint(added_inputs),
                         "6f6d3c245464b992b42854d2a9db4e7ba81e2e911fc3e892c071f03e8493fb73")

        expected_page_deltas = {
            "contracts-proto": (11092, "3bfbc4bc5408b6d2ab40283e6b9b0d44e8f3f3414daaf3ef7fb58d49ba242e66"),
            "contracts-connect-client": (138, "f204448d1cedbae377907d6ada5708d3bf08947eae9ae35e66532b0979845059"),
            "contract-fixtures": (0, None),
        }
        for module, (expected_added_count, expected_added_hash) in expected_page_deltas.items():
            old_pages = previous["modules"][module]["pages"]
            new_pages = current["modules"][module]["pages"]
            added = set(new_pages) - set(old_pages)
            removed = set(old_pages) - set(new_pages)
            changed = {key for key in set(old_pages) & set(new_pages) if old_pages[key] != new_pages[key]}
            self.assertEqual(len(added), expected_added_count, module)
            self.assertEqual(removed, set(), module)
            if expected_added_hash is not None:
                self.assertEqual(key_fingerprint(added), expected_added_hash, module)

            if module == "contracts-proto":
                navigation = {
                    "contracts-proto/io.github.arcforges.contracts.publicapi.v1/index.html",
                    "contracts-proto/package-list", "navigation.html", "scripts/pages.json",
                }
                self.assertEqual(changed & navigation, navigation)
                helpers = changed - navigation
                self.assertEqual(len(helpers), 45)
                self.assertEqual(key_fingerprint(helpers),
                                 "0cc2b363d57649e759c7dcfe3fb11abc013ef72d1388e8defdfa3f698bd70df8")
                self.assertEqual(row_fingerprint([f"{key}\t{old_pages[key]}\t{new_pages[key]}" for key in helpers]),
                                 "23b33af3ca8b66aeaca29507a5168069d0c18487a2ca43a17f6468fc3439012e")
                self.assertEqual(len(navigation), 4)
                self.assertEqual(key_fingerprint(navigation),
                                 "1e58942c13917382318dd90004308d4580a9e93101a8093afd757dacb2704ea2")
                self.assertEqual(row_fingerprint([f"{key}\t{old_pages[key]}\t{new_pages[key]}" for key in navigation]),
                                 "ac594eb5c0d5991c4614a3137fe41c413657aa3214b48519ceb6dbe4952ad3e0")
            elif module == "contracts-connect-client":
                self.assertEqual(len(changed), 4)
                self.assertEqual(key_fingerprint(changed),
                                 "22df5067ed7b3d4cc68b208d5fc85b26cec76af496776eda49eac131136145e6")
                self.assertEqual(row_fingerprint([f"{key}\t{old_pages[key]}\t{new_pages[key]}" for key in changed]),
                                 "f93e35b73f8fcedd0d880bf034ca8cf1896bf7cf8b55483a551c4453c6158e98")
            else:
                self.assertEqual(changed, set(), module)

        previous_proto_api = previous["modules"]["contracts-proto"]["publicApi"]
        current_proto_api = current["modules"]["contracts-proto"]["publicApi"]
        shard = json.loads((root / "public/proto/constraints/con-10-chat-task-agent.json").read_bytes())
        full_names = set(shard["messages"])
        self.assertEqual(len(full_names), 191)
        self.assertTrue(all(name.startswith("arcforges.publicapi.v1.") for name in full_names))
        message_names = {name.rsplit(".", 1)[-1] for name in full_names}
        expected_proto_pages = {
            "contracts-proto/io.github.arcforges.contracts.publicapi.v1/" + slug(name) + "/index.html"
            for name in message_names
        }
        self.assertEqual(len(expected_proto_pages), 191)
        self.assertEqual(key_fingerprint(expected_proto_pages),
                         "269804486cd1b9fcd720314bb86e21a0d56676f254afe097a46f19f51d758684")
        added_proto_api = set(current_proto_api) - set(previous_proto_api)
        self.assertEqual(added_proto_api, expected_proto_pages)
        proto_markers = [f"{page}\t" + "\t".join(sorted(current_proto_api[page])) for page in added_proto_api]
        self.assertEqual(sum(len(current_proto_api[page]) for page in added_proto_api), 1673)
        self.assertEqual(row_fingerprint(proto_markers),
                         "77b075a8b8847f736629c0fe2c6e1d247b7b181cb0c024dbb46f6961d2e8bcad")

        previous_connect_api = previous["modules"]["contracts-connect-client"]["publicApi"]
        current_connect_api = current["modules"]["contracts-connect-client"]["publicApi"]
        expected_connect_pages = {
            "contracts-connect-client/io.github.arcforges.contracts.publicapi.v1/" + slug(service + suffix) + "/index.html": methods
            for service, methods in CON10_PUBLIC_SERVICE_METHODS.items()
            for suffix in ("Client", "ClientInterface")
        }
        added_connect_api = set(current_connect_api) - set(previous_connect_api)
        self.assertEqual(added_connect_api, set(expected_connect_pages))
        self.assertEqual(len(added_connect_api), 16)
        self.assertEqual(sum(len(methods) for methods in CON10_PUBLIC_SERVICE_METHODS.values()), 57)
        for page, expected_methods in expected_connect_pages.items():
            self.assertEqual(len(current_connect_api[page]), len(expected_methods), page)
            self.assertEqual(set(current_connect_api[page]), set(expected_methods), page)
        connect_markers = [page + "\t" + "\t".join(sorted(current_connect_api[page]))
                           for page in added_connect_api]
        self.assertEqual(row_fingerprint(connect_markers),
                         "65ffed3465912724cac3460d9554e262c077b5bc200ae65601e4d091029217ff")
        self.assertEqual(current["modules"]["contract-fixtures"]["publicApi"],
                         previous["modules"]["contract-fixtures"]["publicApi"])

    def test_distinct_npm_names_cannot_share_a_normalized_record_id(self):
        # object-assign and object.assign are different MIT implementations.
        # A punctuation-normalized slug must never discard either obligation.
        policy = {"components": [{"name": "object-assign", "version": "4.1.1", "record": "same-r1"},
                                 {"name": "object.assign", "version": "4.1.7", "record": "same-r1"}]}
        with self.assertRaisesRegex(ValueError, "duplicate provenance IDs"):
            documentation.verify_components(policy, {})


class DocumentationArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        directory = cls.root / "artifacts/packages"
        cls.manifest = json.loads((directory / "manifest.json").read_bytes())
        bundle = next(row for row in cls.manifest["files"] if row["kind"] == "maven")
        cls.files = zip_contents((directory / bundle["name"]).read_bytes())

    def fixture(self, module):
        name = f"io/github/arcforges/{module}/{self.manifest.get('mavenVersion', self.manifest['version'])}/{module}-{self.manifest.get('mavenVersion', self.manifest['version'])}-javadoc.jar"
        return self.files[name], zip_contents(self.files[name])

    def test_actual_archive_resource_mutations_fail_semantic_checks(self):
        archive, original = self.fixture("contract-fixtures")
        changes = [lambda d: d.update({"script.js": b"GPL replacement"}),
                   lambda d: d.update({"ui-kit/fonts/extra.woff2": b"font"}),
                   lambda d: d.update({"scripts/main.js": d["scripts/main.js"] + b"/* changed */"}),
                   lambda d: d.pop("index.html"),
                   lambda d: d.update({"NOTICE": d["NOTICE"].replace(b"webpack", b"missing", 1)}),
                   lambda d: d.update({"META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\nExtra: changed\n\n"})]
        for change in changes:
            with self.subTest(change=change):
                docs = copy.deepcopy(original)
                change(docs)
                with self.assertRaises(ValueError):
                    documentation.verify(docs, "contract-fixtures", self.manifest, archive)


if __name__ == "__main__":
    unittest.main()
