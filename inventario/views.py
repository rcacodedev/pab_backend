# inventory/views.py
from django.db.models import F, Q
import datetime
from django.utils import timezone as djtz
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import generics, status, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError

from .models import Categoria, Producto, InventarioMovimiento
from .serializers import (
    CategoriaSerializer, CategoriaChoiceSerializer, CategoriaProductosSerializer,
    ProductoSerializer, ProductoCreateSerializer, ProductoListSerializer,
    ProductoSearchSerializer, StockUpdateSerializer,
    InventarioMovimientoSerializer, InventarioMovimientoCreateSerializer
)


# --------------------------
# PAGINACIÓN
# --------------------------
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


# --------------------------
#  CATEGORÍAS
# --------------------------
class CategoriaListCreateView(generics.ListCreateAPIView):
    """
    GET: Listar categorías (opcional: ?q=) (soporta jerarquía).
    POST: Crear categoría.
    """
    queryset = Categoria.objects.all().select_related("parent").prefetch_related("children")
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "descripcion"]
    ordering_fields = ["nombre", "created_at", "updated_at"]
    ordering = ["nombre"]

    def get_queryset(self):
        qs = super().get_queryset()
        root = self.request.query_params.get("root")
        if root and root.lower() == "true":
            qs = qs.filter(parent__isnull=True)
        return qs


class CategoriaDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Categoria.objects.all().select_related("parent")
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]


class CategoriaChoiceView(generics.ListAPIView):
    """GET: Listado simplificado de categorías (para dropdowns)."""
    queryset = Categoria.objects.all().order_by("nombre")
    serializer_class = CategoriaChoiceSerializer
    permission_classes = [IsAuthenticated]


class CategoriaConProductosView(generics.RetrieveAPIView):
    """GET: Categoría con sus productos y subcategorías."""
    queryset = Categoria.objects.all().prefetch_related("productos", "children")
    serializer_class = CategoriaProductosSerializer
    permission_classes = [IsAuthenticated]


class CategoriaSearchView(generics.ListAPIView):
    """GET: Búsqueda simple por nombre (?q=)."""
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        search = self.request.query_params.get("q", "")
        return Categoria.objects.filter(nombre__icontains=search).order_by("nombre")


# --------------------------
#  PRODUCTOS
# --------------------------
class ProductoListCreateView(generics.ListCreateAPIView):
    queryset = Producto.objects.select_related("categoria").all()
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "referencia_codigo", "barcode", "descripcion"]
    ordering_fields = ["nombre", "created_at", "updated_at", "stock", "min_stock", "venta_precio"]
    ordering = ["nombre"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProductoCreateSerializer
        return ProductoListSerializer

    def _parse_bool(self, value):
        if value is None:
            return None
        return value.lower() in ("true", "1", "yes", "y", "t")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        # Filtros dinámicos
        categoria_id = params.get("categoria")
        activo = self._parse_bool(params.get("is_active"))
        bajo_stock = self._parse_bool(params.get("bajo_stock"))
        min_stock = params.get("min_stock")
        max_stock = params.get("max_stock")
        q = params.get("q")

        if categoria_id:
            qs = qs.filter(categoria_id=categoria_id)
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) |
                Q(referencia_codigo__icontains=q) |
                Q(barcode__icontains=q)
            )
        if activo is not None:
            qs = qs.filter(is_active=activo)
        if bajo_stock is True:
            qs = qs.filter(stock__lte=F("min_stock"))
        if min_stock:
            try:
                qs = qs.filter(stock__gte=int(min_stock))
            except ValueError:
                raise ValidationError({"min_stock": "Debe ser un entero"})
        if max_stock:
            try:
                qs = qs.filter(stock__lte=int(max_stock))
            except ValueError:
                raise ValidationError({"max_stock": "Debe ser un entero"})

        return qs


class ProductoDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Detalle de producto (vista completa).
    PUT/PATCH: Editar producto (usa ProductoSerializer que ya permite categoria_id write-only).
    DELETE: Eliminar producto.
    """
    queryset = Producto.objects.select_related("categoria").all()
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated]


class ProductoSearchView(generics.ListAPIView):
    """GET: Buscar productos por nombre o código (?q=)."""
    serializer_class = ProductoSearchSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Producto.objects.select_related("categoria").all()
        search = self.request.query_params.get("q")
        if search:
            qs = qs.filter(
                Q(nombre__icontains=search) |
                Q(referencia_codigo__icontains=search) |
                Q(barcode__icontains=search)
            )
        return qs.order_by("nombre")


class ProductoStockUpdateView(generics.UpdateAPIView):
    """
    PATCH: Actualización de stock generando un movimiento.
    Acepta: movimiento_tipo, cantidad, notas, (opcional) operation_id, performed_at
    """
    queryset = Producto.objects.all()
    serializer_class = StockUpdateSerializer
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        producto = self.get_object()
        serializer = self.get_serializer(
            data=request.data,
            context={"producto": producto, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        movimiento = serializer.save()
        data = InventarioMovimientoSerializer(movimiento).data
        return Response(data, status=status.HTTP_200_OK)


class ProductoLowStockView(generics.ListAPIView):
    """GET: Productos con stock bajo (stock <= min_stock)."""
    serializer_class = ProductoListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Producto.objects.filter(stock__lte=F("min_stock")).select_related("categoria").order_by("nombre")


# --------------------------
#  MOVIMIENTOS DE INVENTARIO
# --------------------------
class MovimientoListCreateView(generics.ListCreateAPIView):
    """
    GET: Listar movimientos (filtros por producto, usuario, tipo, fecha).
    POST: Crear movimiento (usa InventarioMovimiento.apply vía serializer).
    """
    queryset = InventarioMovimiento.objects.select_related("producto", "user").all()
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    # Búsqueda textual sobre producto y notas
    search_fields = ["producto__nombre", "producto__referencia_codigo", "notas", "operation_id"]
    ordering_fields = ["created_at", "performed_at", "cantidad", "movimiento_tipo"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InventarioMovimientoCreateSerializer
        return InventarioMovimientoSerializer

    def _parse_date_or_dt(self, val, field_name):
        """
        Devuelve:
          - datetime aware si entra un datetime
          - (start_aware, end_aware) si entra un date
        """
        if not val:
            return None
        dt = parse_datetime(val)
        if dt:
            if djtz.is_naive(dt):
                dt = djtz.make_aware(dt, djtz.get_current_timezone())
            return dt
        d = parse_date(val)
        if d:
            start = datetime.datetime.combine(d, datetime.time.min)
            end = datetime.datetime.combine(d, datetime.time.max)
            start = djtz.make_aware(start, djtz.get_current_timezone())
            end = djtz.make_aware(end, djtz.get_current_timezone())
            return (start, end)
        raise ValidationError({field_name: "Formato inválido. Usa YYYY-MM-DD o ISO 8601 con tz."})

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        producto_id = params.get("producto")
        usuario_id = params.get("usuario")
        tipo = params.get("tipo")  # IN | OUT | ADJ
        desde = self._parse_date_or_dt(params.get("fecha_inicio"), "fecha_inicio")
        hasta = self._parse_date_or_dt(params.get("fecha_fin"), "fecha_fin")

        if producto_id:
            qs = qs.filter(producto_id=producto_id)
        if usuario_id:
            qs = qs.filter(user_id=usuario_id)
        if tipo:
            qs = qs.filter(movimiento_tipo=tipo)

        # Fecha inicio
        if desde:
            if isinstance(desde, tuple):  # (start_of_day, end_of_day)
                qs = qs.filter(created_at__gte=desde[0])
            else:
                qs = qs.filter(created_at__gte=desde)

        # Fecha fin
        if hasta:
            if isinstance(hasta, tuple):
                qs = qs.filter(created_at__lte=hasta[1])
            else:
                qs = qs.filter(created_at__lte=hasta)

        return qs

    def perform_create(self, serializer):
        # El serializer ya usa InventarioMovimiento.apply(...) con idempotencia y lock.
        serializer.save()


class MovimientoDetailView(generics.RetrieveAPIView):
    """GET: Detalle de un movimiento."""
    queryset = InventarioMovimiento.objects.select_related("producto", "user").all()
    serializer_class = InventarioMovimientoSerializer
    permission_classes = [IsAuthenticated]
