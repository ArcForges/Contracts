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

    def test_current_profile_preserves_reviewed_resources_and_retires_native_client(self):
        root = Path(__file__).resolve().parents[2]
        previous = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r5.json").read_bytes())
        current = json.loads((root / documentation.PROFILE).read_bytes())
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
                | con09_proto_pages | con10_proto_pages if module == "contracts-proto" else (
                    clients | set(con08_client_pages) | set(con09_client_pages)
                    | set(con10_client_pages)
                    if module == "contracts-connect-client" else set())
            self.assertEqual(additions, permitted)
            for name in additions:
                if module == "contracts-proto":
                    self.assertIn('anchor-label="parser"', actual[name])
                    if name in con09_proto_pages:
                        self.assertTrue(any(marker.startswith('anchor-label="get') or marker.startswith("get")
                                            for marker in actual[name]), name)
                    else:
                        self.assertTrue(any(marker.startswith('anchor-label="get') for marker in actual[name]), name)
                else:
                    expected_methods = set(con10_client_pages[name]) if name in con10_client_pages else (
                        con09_client_pages[name] if name in con09_client_pages else (
                        con08_client_pages[name] if name in con08_client_pages else {
                        operation[0].lower() + operation[1:] for operation in operations
                    }))
                    self.assertEqual(set(actual[name]), expected_methods)
        self.assertFalse(any("/contracts-client/" in name for name in current["inputs"]))
        proto_pages = current["modules"]["contracts-proto"]["publicApi"]
        self.assertTrue(any("foundation.v1" in name for name in proto_pages))
        self.assertTrue(any("events.v1" in name for name in proto_pages))
        self.assertTrue(any("publicapi.v1/-aggregate-body/" in name for name in proto_pages))
        self.assertFalse(any("publicapi.v1/-notes-query/" in name for name in proto_pages))
        self.assertTrue(any("publicapi.v1/-measurement-result/" in name for name in proto_pages))

    def test_con10_dokka_r15_is_only_the_frozen_r14_successor_delta(self):
        root = Path(__file__).resolve().parents[2]
        previous = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r14.json").read_bytes())
        current = json.loads((root / "eng/provenance/artifact-profiles/dokka-2-2-0-r15.json").read_bytes())
        self.assertEqual(documentation.PROFILE, "eng/provenance/artifact-profiles/dokka-2-2-0-r15.json")

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
