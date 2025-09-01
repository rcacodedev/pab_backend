from django.urls import path
from . import views

urlpatterns = [
    # Categorías
    path("categorias/", views.CategoriaListCreateView.as_view(), name="categoria-list-create"),
    path("categorias/<int:pk>/", views.CategoriaDetailView.as_view(), name="categoria-detail"),
    path("categorias/choices/", views.CategoriaChoiceView.as_view(), name="categoria-choices"),
    path("categorias/<int:pk>/productos/", views.CategoriaConProductosView.as_view(), name="categoria-con-productos"),
    path("categorias/search/", views.CategoriaSearchView.as_view(), name="categoria-search"),

    # Productos
    path("productos/", views.ProductoListCreateView.as_view(), name="producto-list-create"),
    path("productos/<int:pk>/", views.ProductoDetailView.as_view(), name="producto-detail"),
    path("productos/search/", views.ProductoSearchView.as_view(), name="producto-search"),
    path("productos/low-stock/", views.ProductoLowStockView.as_view(), name="producto-low-stock"),
    path("productos/<int:pk>/stock/", views.ProductoStockUpdateView.as_view(), name="producto-stock-update"),

    # Movimientos
    path("movimientos/", views.MovimientoListCreateView.as_view(), name="movimiento-list-create"),
    path("movimientos/<int:pk>/", views.MovimientoDetailView.as_view(), name="movimiento-detail"),
]

