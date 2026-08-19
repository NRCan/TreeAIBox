from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/list-layers/', views.list_layers, name='list_layers'),
    path('api/scan-csvs/', views.scan_csvs, name='scan_csvs'),
    path('api/pick-path/', views.pick_path, name='pick_path'),
    path('api/run-match/', views.run_match, name='run_match'),
    path('api/boundary/', views.boundary_preview, name='boundary_preview'),
    path('api/load-custom-layer/', views.load_custom_layer, name='load_custom_layer'),
    path('api/download/', views.download_file, name='download_file'),
]
