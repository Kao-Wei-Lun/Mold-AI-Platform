from django.urls import path

from .views import (
    ArtifactVersionDownloadView,
    CADArtifactDetailView,
    CADArtifactListCreateView,
    JobDetailView,
    LiveView,
    ReadyView,
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
        "artifact-versions/<uuid:artifact_version_id>/download",
        ArtifactVersionDownloadView.as_view(),
        name="artifact-version-download",
    ),
]
