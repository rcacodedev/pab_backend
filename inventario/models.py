from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción")
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='children', verbose_name="Categoría padre")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado en")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado en")

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def get_all_children(self):
        """Obtiene todas las subcategorías recursivamente"""
        children = list(self.children.all())
        for child in self.children.all():
            children.extend(child.get_all_children())
        return children

    def get_all_parents(self):
        """Obtiene todos los padres hasta la raíz"""
        parents = []
        if self.parent:
            parents.append(self.parent)
            parents.extend(self.parent.get_all_parents())
        return parents

    @property
    def es_raiz(self):
        """Indica si es una categoría raíz"""
        return self.parent is None

    @property
    def nivel(self):
        """Nivel de profundidad en la jerarquía"""
        if self.parent is None:
            return 0
        # Evita recursión usando aproximación iterativa
        nivel = 0
        current = self
        while current.parent:
            nivel += 1
            current = current.parent
        return nivel

class Producto(models.Model):
    # Información básica
    referencia_codigo = models.CharField(max_length=50, unique=True, verbose_name="Código de referencia")
    nombre = models.CharField(max_length=200, verbose_name="Nombre")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción")

    # Relaciones
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='productos', verbose_name="Categoría")

    # Inventario
    stock = models.PositiveIntegerField(default=0, verbose_name="Stock actual")
    min_stock = models.PositiveIntegerField(default=5, verbose_name="Stock mínimo")
    max_stock = models.PositiveIntegerField(null=True, blank=True, verbose_name="Stock máximo")

    # Precios
    coste_precio = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de coste")
    venta_precio = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de venta")

    # Ubicación
    localizacion = models.CharField(max_length=100, blank=True, null=True, verbose_name="Ubicación")
    barcode = models.CharField(max_length=100, blank=True, null=True, unique=True, verbose_name="Código de barras")

    # Estado
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    # Fechas
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado en")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado en")

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['nombre', 'referencia_codigo']),
            models.Index(fields=['categoria']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.referencia_codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        # Validaciones de stock
        if self.stock < 0:
            raise ValidationError("El stock no puede ser negativo")

        if self.min_stock > self.max_stock and self.max_stock is not None:
            raise ValidationError("Stock mínimo no puede ser mayor que máximo")

        # Validaciones de precio
        if self.venta_precio <= self.coste_precio:
            raise ValidationError({
                'venta_precio': _('El precio de venta debe ser mayor al precio de coste')
            })

        # Validación stock máximo
        if self.max_stock is not None and self.stock > self.max_stock:
            raise ValidationError({
                'stock': _(f'El stock no puede exceder el máximo de {self.max_stock}')
            })

    @property
    def bajo_stock(self):
        """Propiedad que indica si el stock es bajo"""
        return self.stock <= self.min_stock

    @property
    def estado_stock(self):
        """Estado textual del stock"""
        if self.stock == 0:
            return "Agotado"
        elif self.bajo_stock:
            return "Bajo"
        else:
            return "Disponible"

class InventarioMovimiento(models.Model):
    MOVEMENT_TYPES = (
        ('IN', 'Entrada'),
        ('OUT', 'Salida'),
        ('ADJ', 'Ajuste'),
    )

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='movimientos', verbose_name="Producto")
    movimiento_tipo = models.CharField(max_length=3, choices=MOVEMENT_TYPES, verbose_name="Tipo de movimiento")
    cantidad = models.IntegerField(verbose_name="Cantidad")
    notas = models.TextField(blank=True, null=True, verbose_name="Notas")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Usuario")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado en")

    class Meta:
        verbose_name = "Movimiento de inventario"
        verbose_name_plural = "Movimientos de inventario"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_movimiento_tipo_display()} - {self.producto.nombre}"

    def clean(self):
        super().clean()
        if self.cantidad <= 0:
            raise ValidationError({'cantidad': _('La cantidad debe ser mayor a cero')})

        if self.movimiento_tipo == 'OUT' and self.cantidad > self.producto.stock:
            raise ValidationError({
                'cantidad': _('No hay suficiente stock para esta salida')
            })