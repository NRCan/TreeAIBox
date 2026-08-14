from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/list-layers/', views.list_layers, name='list_layers'),
    path('api/scan-csvs/', views.scan_csvs, name='scan_csvs'),
    path('api/run-match/', views.run_match, name='run_match'),
    path('api/download/', views.download_file, name='download_file'),
]
