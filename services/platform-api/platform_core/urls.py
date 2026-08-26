from django.urls import path

from .views import LiveView, ReadyView, SystemInfoView

app_name = "platform_core"

urlpatterns = [
    path("health/live", LiveView.as_view(), name="health-live"),
    path("health/ready", ReadyView.as_view(), name="health-ready"),
    path("system/info", SystemInfoView.as_view(), name="system-info"),
]
