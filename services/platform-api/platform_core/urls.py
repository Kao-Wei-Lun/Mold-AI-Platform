from django.urls import path

from .views import (
    ArtifactVersionDownloadView,
    AssistantCapabilitiesView,
    AssistantMessageView,
    CADArtifactDetailView,
    CADArtifactListCreateView,
    DesignReviewDetailView,
    DesignReviewListCreateView,
    JobDetailView,
    KnowledgeDocumentDetailView,
    KnowledgeDocumentListCreateView,
    KnowledgeSearchDetailView,
    KnowledgeSearchListCreateView,
    LiveView,
    ReadyView,
    ReviewFindingDecisionCreateView,
    RuleProfileListView,
    SimilaritySearchDetailView,
    SimilaritySearchListCreateView,
    SystemInfoView,
)

app_name = "platform_core"

urlpatterns = [
    path("health/live", LiveView.as_view(), name="health-live"),
    path("health/ready", ReadyView.as_view(), name="health-ready"),
    path("system/info", SystemInfoView.as_view(), name="system-info"),
    path(
        "assistant/capabilities",
        AssistantCapabilitiesView.as_view(),
        name="assistant-capabilities",
    ),
    path("assistant/messages", AssistantMessageView.as_view(), name="assistant-messages"),
    path("cad-artifacts", CADArtifactListCreateView.as_view(), name="cad-artifact-list-create"),
    path(
        "cad-artifacts/<uuid:artifact_id>",
        CADArtifactDetailView.as_view(),
        name="cad-artifact-detail",
    ),
    path("jobs/<uuid:job_id>", JobDetailView.as_view(), name="job-detail"),
    path(
        "knowledge-documents",
        KnowledgeDocumentListCreateView.as_view(),
        name="knowledge-document-list-create",
    ),
    path(
        "knowledge-documents/<uuid:document_id>",
        KnowledgeDocumentDetailView.as_view(),
        name="knowledge-document-detail",
    ),
    path(
        "knowledge-searches",
        KnowledgeSearchListCreateView.as_view(),
        name="knowledge-search-list-create",
    ),
    path(
        "knowledge-searches/<uuid:search_id>",
        KnowledgeSearchDetailView.as_view(),
        name="knowledge-search-detail",
    ),
    path("rule-profiles", RuleProfileListView.as_view(), name="rule-profile-list"),
    path(
        "design-reviews",
        DesignReviewListCreateView.as_view(),
        name="design-review-list-create",
    ),
    path(
        "design-reviews/<uuid:review_id>",
        DesignReviewDetailView.as_view(),
        name="design-review-detail",
    ),
    path(
        "design-reviews/<uuid:review_id>/findings/<uuid:finding_id>/decisions",
        ReviewFindingDecisionCreateView.as_view(),
        name="review-finding-decision-create",
    ),
    path(
        "similarity-searches",
        SimilaritySearchListCreateView.as_view(),
        name="similarity-search-list-create",
    ),
    path(
        "similarity-searches/<uuid:search_id>",
        SimilaritySearchDetailView.as_view(),
        name="similarity-search-detail",
    ),
    path(
        "artifact-versions/<uuid:artifact_version_id>/download",
        ArtifactVersionDownloadView.as_view(),
        name="artifact-version-download",
    ),
]
