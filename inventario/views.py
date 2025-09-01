from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import F, Q
from rest_framework.pagination import PageNumberPagination
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
    page_size_query_param = 'page_size'
    max_page_size = 100

# --------------------------
#  CATEGORÍAS
# --------------------------
class CategoriaListCreateView(generics.ListCreateAPIView):
    """
    GET: Listar todas las categorías (jerárquicas incluidas).
    POST: Crear una nueva categoría.
    """
    queryset = Categoria.objects.all().prefetch_related("children")
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("q")
        parent = self.request.query_params.get("parent")
        if search:
            queryset = queryset.filter(nombre__icontains=search)
        if parent:
            queryset = queryset.filter(parent_id=parent)
        return queryset


class CategoriaDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Detalle de una categoría
    PUT/PATCH: Actualizar categoría
    DELETE: Eliminar categoría
    """
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]


class CategoriaChoiceView(generics.ListAPIView):
    """
    GET: Listado simplificado de categorías (para dropdowns).
    """
    queryset = Categoria.objects.all()
    serializer_class = CategoriaChoiceSerializer
    permission_classes = [IsAuthenticated]


class CategoriaConProductosView(generics.RetrieveAPIView):
    """
    GET: Categoría con sus productos y subcategorías.
    """
    queryset = Categoria.objects.all().prefetch_related("productos", "children")
    serializer_class = CategoriaProductosSerializer
    permission_classes = [IsAuthenticated]


class CategoriaSearchView(generics.ListAPIView):
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        search = self.request.query_params.get("q", "")
        return Categoria.objects.filter(nombre__icontains=search)


# --------------------------
#  PRODUCTOS
# --------------------------
class ProductoListCreateView(generics.ListCreateAPIView):
    queryset = Producto.objects.select_related("categoria").all()
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProductoCreateSerializer
        return ProductoListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        # Filtros dinámicos
        categoria_id = params.get("categoria")
        search = params.get("q")
        activo = params.get("is_active")
        bajo_stock = params.get("bajo_stock")
        min_stock = params.get("min_stock")
        max_stock = params.get("max_stock")

        if categoria_id:
            queryset = queryset.filter(categoria_id=categoria_id)
        if search:
            queryset = queryset.filter(
                Q(nombre__icontains=search) |
                Q(referencia_codigo__icontains=search) |
                Q(barcode__icontains=search)
            )
        if activo is not None:
            queryset = queryset.filter(is_active=activo.lower() == "true")
        if bajo_stock is not None and bajo_stock.lower() == "true":
            queryset = queryset.filter(stock__lte=F("min_stock"))
        if min_stock:
            queryset = queryset.filter(stock__gte=min_stock)
        if max_stock:
            queryset = queryset.filter(stock__lte=max_stock)

        return queryset


class ProductoDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Detalle de producto (vista completa).
    PUT/PATCH: Editar producto.
    DELETE: Eliminar producto.
    """
    queryset = Producto.objects.select_related("categoria").all()
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated]


class ProductoSearchView(generics.ListAPIView):
    """
    GET: Buscar productos por nombre o código.
    """
    serializer_class = ProductoSearchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Producto.objects.select_related("categoria").all()
        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(
                Q(nombre__icontains=search) |
                Q(referencia_codigo__icontains=search) |
                Q(barcode__icontains=search)
            )
        return queryset


class ProductoStockUpdateView(generics.UpdateAPIView):
    """
    PATCH: Actualización rápida de stock con movimientos.
    """
    queryset = Producto.objects.all()
    serializer_class = StockUpdateSerializer
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        producto = self.get_object()
        serializer = self.get_serializer(data=request.data, context={"producto": producto})
        serializer.is_valid(raise_exception=True)

        movimiento_tipo = serializer.validated_data["movimiento_tipo"]
        cantidad = serializer.validated_data["cantidad"]
        notas = serializer.validated_data.get("notas", "")

        # Aplicar movimiento
        if movimiento_tipo == "IN":
            producto.stock += cantidad
        elif movimiento_tipo == "OUT":
            producto.stock -= cantidad
        elif movimiento_tipo == "ADJ":
            producto.stock = cantidad

        producto.save()

        # Guardar movimiento en historial
        InventarioMovimiento.objects.create(
            producto=producto,
            movimiento_tipo=movimiento_tipo,
            cantidad=cantidad,
            notas=notas,
            user=request.user,
        )

        return Response({"detail": "Stock actualizado correctamente"}, status=status.HTTP_200_OK)


class ProductoLowStockView(generics.ListAPIView):
    serializer_class = ProductoListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Producto.objects.filter(stock__lte=F("min_stock"))


# --------------------------
#  MOVIMIENTOS DE INVENTARIO
# --------------------------
class MovimientoListCreateView(generics.ListCreateAPIView):
    """
    GET: Listar movimientos de inventario.
    POST: Crear movimiento (y actualizar stock automáticamente).
    """
    queryset = InventarioMovimiento.objects.select_related("producto", "user").all()
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InventarioMovimientoCreateSerializer
        return InventarioMovimientoSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        producto_id = params.get("producto")
        usuario_id = params.get("usuario")
        tipo = params.get("tipo")
        fecha_inicio = params.get("fecha_inicio")
        fecha_fin = params.get("fecha_fin")

        if producto_id:
            queryset = queryset.filter(producto_id=producto_id)
        if usuario_id:
            queryset = queryset.filter(user_id=usuario_id)
        if tipo:
            queryset = queryset.filter(movimiento_tipo=tipo)
        if fecha_inicio:
            queryset = queryset.filter(created_at__gte=fecha_inicio)
        if fecha_fin:
            queryset = queryset.filter(created_at__lte=fecha_fin)

        return queryset

    def perform_create(self, serializer):
        movimiento = serializer.save(user=self.request.user)
        producto = movimiento.producto

        # Aplicar movimiento
        if movimiento.movimiento_tipo == "IN":
            producto.stock += movimiento.cantidad
        elif movimiento.movimiento_tipo == "OUT":
            producto.stock -= movimiento.cantidad
        elif movimiento.movimiento_tipo == "ADJ":
            producto.stock = movimiento.cantidad

        producto.save()


class MovimientoDetailView(generics.RetrieveAPIView):
    """
    GET: Detalle de un movimiento de inventario.
    """
    queryset = InventarioMovimiento.objects.select_related("producto", "user").all()
    serializer_class = InventarioMovimientoSerializer
    permission_classes = [IsAuthenticated]
