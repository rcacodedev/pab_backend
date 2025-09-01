from rest_framework import serializers
from .models import Categoria, Producto, InventarioMovimiento
from django.contrib.auth.models import User

class RecursiveField(serializers.Serializer):
    """Campo recursivo para manejar jerarquías de categorías"""
    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data

class UserSerializer(serializers.ModelSerializer):
    """Serializer para el usuario"""
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']
        read_only_fields = fields

class CategoriaSerializer(serializers.ModelSerializer):
    """Serializer para Categoria con soporte jerárquico"""
    children = RecursiveField(many=True, required=False, read_only=True)
    parent_nombre = serializers.CharField(source='parent.nombre', read_only=True)
    nivel = serializers.IntegerField(read_only=True)
    es_raiz = serializers.BooleanField(read_only=True)

    class Meta:
        model = Categoria
        fields = [
            'id', 'nombre', 'descripcion', 'parent', 'parent_nombre',
            'children', 'nivel', 'es_raiz', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

class CategoriaChoiceSerializer(serializers.ModelSerializer):
    """Serializer simplificado para dropdowns/choices"""
    class Meta:
        model = Categoria
        fields = ['id', 'nombre']

class ProductoSerializer(serializers.ModelSerializer):
    """Serializer completo para Producto"""
    categoria = CategoriaChoiceSerializer(read_only=True)
    categoria_id = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.all(),
        source='categoria',
        write_only=True,
        required=False,
        allow_null=True
    )
    bajo_stock = serializers.BooleanField(read_only=True)
    estado_stock = serializers.CharField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            'id', 'referencia_codigo', 'nombre', 'descripcion',
            'categoria', 'categoria_id', 'stock', 'min_stock', 'max_stock',
            'coste_precio', 'venta_precio', 'localizacion', 'barcode',
            'is_active', 'bajo_stock', 'estado_stock', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

class ProductoCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear/actualizar Producto (sin relaciones anidadas)"""
    class Meta:
        model = Producto
        fields = [
            'referencia_codigo', 'nombre', 'descripcion', 'categoria',
            'stock', 'min_stock', 'max_stock', 'coste_precio', 'venta_precio',
            'localizacion', 'barcode', 'is_active'
        ]

class ProductoListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listar productos"""
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    bajo_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            'id', 'referencia_codigo', 'nombre', 'categoria_nombre',
            'stock', 'min_stock', 'venta_precio', 'bajo_stock', 'is_active'
        ]

class InventarioMovimientoSerializer(serializers.ModelSerializer):
    """Serializer para InventarioMovimiento"""
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    producto_referencia = serializers.CharField(source='producto.referencia_codigo', read_only=True)
    usuario = UserSerializer(source='user', read_only=True)
    movimiento_tipo_display = serializers.CharField(source='get_movimiento_tipo_display', read_only=True)

    class Meta:
        model = InventarioMovimiento
        fields = [
            'id', 'producto', 'producto_nombre', 'producto_referencia',
            'movimiento_tipo', 'movimiento_tipo_display', 'cantidad',
            'notas', 'user', 'usuario', 'created_at'
        ]
        read_only_fields = ['created_at']

class InventarioMovimientoCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear movimientos de inventario"""
    class Meta:
        model = InventarioMovimiento
        fields = ['producto', 'movimiento_tipo', 'cantidad', 'notas']

    def validate(self, data):
        """Validación personalizada para movimientos"""
        producto = data.get('producto')
        movimiento_tipo = data.get('movimiento_tipo')
        cantidad = data.get('cantidad')

        if movimiento_tipo == 'OUT' and cantidad > producto.stock:
            raise serializers.ValidationError({
                'cantidad': 'No hay suficiente stock para esta salida'
            })

        if cantidad <= 0:
            raise serializers.ValidationError({
                'cantidad': 'La cantidad debe ser mayor a cero'
            })

        return data

class StockUpdateSerializer(serializers.Serializer):
    """Serializer para actualizaciones rápidas de stock"""
    movimiento_tipo = serializers.ChoiceField(choices=InventarioMovimiento.MOVEMENT_TYPES)
    cantidad = serializers.IntegerField(min_value=1)
    notas = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        movimiento_tipo = data['movimiento_tipo']
        cantidad = data['cantidad']

        if movimiento_tipo == 'OUT' and cantidad > self.context['producto'].stock:
            raise serializers.ValidationError({
                'cantidad': 'No hay suficiente stock para esta salida'
            })

        return data

class ProductoSearchSerializer(serializers.ModelSerializer):
    """Serializer para búsqueda de productos"""
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)

    class Meta:
        model = Producto
        fields = [
            'id', 'referencia_codigo', 'nombre', 'categoria_nombre',
            'stock', 'venta_precio', 'localizacion', 'is_active'
        ]

class CategoriaProductosSerializer(serializers.ModelSerializer):
    """Serializer para categorías con sus productos"""
    productos = ProductoListSerializer(many=True, read_only=True)
    children = RecursiveField(many=True, required=False, read_only=True)

    class Meta:
        model = Categoria
        fields = ['id', 'nombre', 'descripcion', 'productos', 'children']