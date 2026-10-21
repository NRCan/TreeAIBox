from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="field_etl_index"),
    path("api/list-layers/", views.api_list_layers, name="field_etl_list_layers"),
    path("api/pick/", views.api_pick, name="field_etl_pick"),
    path("api/process/", views.api_process, name="field_etl_process"),
    path("api/boundary/", views.api_boundary, name="field_etl_boundary"),
    path("export/gpkg/", views.export_gpkg, name="field_etl_export_gpkg"),
    path("export/geojson/", views.export_geojson, name="field_etl_export_geojson"),
    path("export/csv/", views.export_csv, name="field_etl_export_csv"),
]
