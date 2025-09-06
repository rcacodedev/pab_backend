# inventory/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from .models import Categoria, Producto, InventarioMovimiento

User = get_user_model()


class RecursiveField(serializers.Serializer):
    """Campo recursivo para manejar jerarquías de categorías"""
    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data


class UserSerializer(serializers.ModelSerializer):
    """Serializer para el usuario con fallback de nombre completo."""
    nombre_completo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'nombre_completo']
        read_only_fields = fields

    def get_nombre_completo(self, obj):
        # Ajusta estos atributos si tu User tiene otros nombres de campo.
        parts = []
        for attr in ("nombre", "first_name"):
            if getattr(obj, attr, None):
                parts.append(getattr(obj, attr))
                break
        for attr in ("primer_apellido", "last_name"):
            if getattr(obj, attr, None):
                parts.append(getattr(obj, attr))
                break
        if getattr(obj, "segundo_apellido", None):
            parts.append(getattr(obj, "segundo_apellido"))
        full = " ".join(p for p in parts if p)
        return full or getattr(obj, "get_full_name", lambda: "")() or (obj.email or str(obj.pk))


class CategoriaSerializer(serializers.ModelSerializer):
    """Serializer para Categoria con soporte jerárquico"""
    children = RecursiveField(many=True, required=False, read_only=True)
    parent_nombre = serializers.CharField(source='parent.nombre', read_only=True)

    class Meta:
        model = Categoria
        fields = ['id', 'nombre', 'descripcion', 'parent', 'parent_nombre', 'children']


class CategoriaChoiceSerializer(serializers.ModelSerializer):
    """Serializer simplificado para dropdowns/choices"""
    class Meta:
        model = Categoria
        fields = ['id', 'nombre']


class ProductoSerializer(serializers.ModelSerializer):
    """Serializer completo para Producto (stock es solo lectura: se modifica vía movimientos)."""
    categoria = CategoriaChoiceSerializer(read_only=True)
    categoria_id = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.all(),
        source='categoria',
        write_only=True,
        required=False,
        allow_null=True
    )
    bajo_stock = serializers.ReadOnlyField()
    estado_stock = serializers.ReadOnlyField()

    class Meta:
        model = Producto
        fields = [
            'id', 'referencia_codigo', 'nombre', 'descripcion',
            'categoria', 'categoria_id',
            'stock', 'min_stock', 'max_stock',
            'coste_precio', 'venta_precio', 'localizacion', 'barcode',
            'is_active', 'bajo_stock', 'estado_stock',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['bajo_stock', 'estado_stock', 'created_at', 'updated_at']

    def validate_stock(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("El stock no puede ser negativo")
        return value

class ProductoCreateSerializer(serializers.ModelSerializer):
    """
    Serializer para crear/actualizar Producto, sin relaciones anidadas.
    (No permite setear stock directamente; usar movimientos.)
    """
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            'id','referencia_codigo', 'nombre', 'descripcion', 'categoria', 'stock',
            'min_stock', 'max_stock', 'coste_precio', 'venta_precio',
            'localizacion', 'barcode', 'is_active'
        ]

    def validate_stock(self, value):
        if value is None:
            return 0
        if value < 0:
            raise serializers.ValidationError("El stock no puede ser negativo")
        return value
class ProductoListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listar productos"""
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    estado_stock = serializers.ReadOnlyField()

    class Meta:
        model = Producto
        fields = [
            'id', 'referencia_codigo', 'nombre', 'categoria_nombre',
            'stock', 'min_stock', 'venta_precio', 'is_active', 'estado_stock'
        ]

class CategoriaProductosSerializer(serializers.ModelSerializer):
    """Serializer para categorías con sus productos y subcategorías"""
    productos = ProductoListSerializer(many=True, read_only=True)
    children = RecursiveField(many=True, required=False, read_only=True)

    class Meta:
        model = Categoria
        fields = ['id', 'nombre', 'descripcion', 'productos', 'children']


class ProductoSearchSerializer(serializers.ModelSerializer):
    """Serializer para búsqueda de productos"""
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)

    class Meta:
        model = Producto
        fields = [
            'id', 'referencia_codigo', 'nombre', 'categoria_nombre',
            'stock', 'venta_precio', 'localizacion', 'is_active'
        ]


class InventarioMovimientoSerializer(serializers.ModelSerializer):
    """Detalle de movimiento (lectura)"""
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    producto_referencia = serializers.CharField(source='producto.referencia_codigo', read_only=True)
    usuario = UserSerializer(source='user', read_only=True)
    movimiento_tipo_display = serializers.CharField(source='get_movimiento_tipo_display', read_only=True)

    class Meta:
        model = InventarioMovimiento
        fields = [
            'id', 'producto', 'producto_nombre', 'producto_referencia',
            'movimiento_tipo', 'movimiento_tipo_display', 'cantidad',
            'notas', 'usuario', 'operation_id', 'performed_at', 'created_at'
        ]
        read_only_fields = [
            'id', 'producto_nombre', 'producto_referencia', 'movimiento_tipo_display',
            'usuario', 'created_at'
        ]


class InventarioMovimientoCreateSerializer(serializers.ModelSerializer):
    """
    Crear movimientos de inventario usando la lógica de dominio:
    - Atómico con transaction + select_for_update
    - Idempotente por operation_id
    - OUT valida stock y lanza error si no alcanza
    - ADJ interpreta cantidad como 'fijar a'
    """
    # Permite que el cliente envíe operation_id (recomendado para idempotencia).
    operation_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    performed_at = serializers.DateTimeField(required=False)

    class Meta:
        model = InventarioMovimiento
        fields = ['producto', 'movimiento_tipo', 'cantidad', 'notas', 'operation_id', 'performed_at']

    def validate(self, data):
        # Validaciones ligeras de forma para dar errores tempranos y claros.
        cantidad = data.get('cantidad')
        movimiento_tipo = data.get('movimiento_tipo')

        if movimiento_tipo in (InventarioMovimiento.IN, InventarioMovimiento.OUT):
            if cantidad is None or int(cantidad) <= 0:
                raise serializers.ValidationError({'cantidad': 'La cantidad debe ser mayor a cero.'})
        if movimiento_tipo == InventarioMovimiento.ADJ and int(data.get('cantidad', 0)) < 0:
            raise serializers.ValidationError({'cantidad': 'El ajuste no puede ser negativo.'})
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request and request.user and request.user.is_authenticated else None

        try:
            mv = InventarioMovimiento.apply(
                producto=validated_data['producto'],
                movimiento_tipo=validated_data['movimiento_tipo'],
                cantidad=int(validated_data['cantidad']),
                user=user,
                notas=validated_data.get('notas', ''),
                operation_id=validated_data.get('operation_id') or None,
                performed_at=validated_data.get('performed_at')
            )
            return mv
        except IntegrityError as e:
            # Errores de dominio/DB → DRF ValidationError
            raise serializers.ValidationError({'detail': str(e)})


class StockUpdateSerializer(serializers.Serializer):
    """
    Conservamos tu endpoint de “actualizar stock” pero ahora
    delega en InventarioMovimiento.apply (ya no en signals).
    """
    movimiento_tipo = serializers.ChoiceField(choices=InventarioMovimiento.MOVEMENT_TYPES)
    cantidad = serializers.IntegerField(min_value=1)
    notas = serializers.CharField(required=False, allow_blank=True)
    operation_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    performed_at = serializers.DateTimeField(required=False)

    def validate(self, data):
        # Validaciones ligeras (la verificación final ocurre en apply con lock).
        if data['movimiento_tipo'] == InventarioMovimiento.ADJ and data['cantidad'] < 0:
            raise serializers.ValidationError({'cantidad': 'El ajuste no puede ser negativo.'})
        return data

    def save(self):
        producto = self.context['producto']
        request = self.context.get('request')
        user = request.user if request and request.user and request.user.is_authenticated else None

        try:
            mv = InventarioMovimiento.apply(
                producto=producto,
                movimiento_tipo=self.validated_data['movimiento_tipo'],
                cantidad=int(self.validated_data['cantidad']),
                notas=self.validated_data.get('notas', ''),
                user=user,
                operation_id=self.validated_data.get('operation_id') or None,
                performed_at=self.validated_data.get('performed_at')
            )
            return mv
        except IntegrityError as e:
            raise serializers.ValidationError({'detail': str(e)})
