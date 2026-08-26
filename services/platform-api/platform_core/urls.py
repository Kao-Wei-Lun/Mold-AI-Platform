from django.urls import path

from .views import (
    ArtifactVersionDownloadView,
    CADArtifactDetailView,
    CADArtifactListCreateView,
    JobDetailView,
    LiveView,
    ReadyView,
    SimilaritySearchDetailView,
    SimilaritySearchListCreateView,
    SystemInfoView,
)

app_name = "platform_core"

urlpatterns = [
    path("health/live", LiveView.as_view(), name="health-live"),
    path("health/ready", ReadyView.as_view(), name="health-ready"),
    path("system/info", SystemInfoView.as_view(), name="system-info"),
    path("cad-artifacts", CADArtifactListCreateView.as_view(), name="cad-artifact-list-create"),
    path(
        "cad-artifacts/<uuid:artifact_id>",
        CADArtifactDetailView.as_view(),
        name="cad-artifact-detail",
    ),
    path("jobs/<uuid:job_id>", JobDetailView.as_view(), name="job-detail"),
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
