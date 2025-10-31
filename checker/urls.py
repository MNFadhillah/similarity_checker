from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_view, name='upload'),
    path('download/<str:filename>/', views.download_result_view, name='download'),
]
