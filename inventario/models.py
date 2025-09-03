from django.db import models, transaction, IntegrityError
from django.conf import settings
from django.utils import timezone
import uuid

# --------------------------
# CATEGORÍA
# --------------------------
class Categoria(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children"
    )
    created_at = models.DateTimeField(auto_now_add=True)  # antes: default=timezone.now
    updated_at = models.DateTimeField(auto_now=True)      # antes: default=timezone.now

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ['nombre']
        constraints = [
            models.CheckConstraint(check=~models.Q(parent=models.F("id")), name="categoria_parent_not_self"),
        ]

    def __str__(self):
        return self.nombre

    @property
    def es_raiz(self):
        return self.parent is None

    @property
    def nivel(self):
        nivel = 0
        current = self
        while current.parent:
            nivel += 1
            current = current.parent
        return nivel

# --------------------------
# PRODUCTO
# --------------------------
class Producto(models.Model):
    nombre = models.CharField(max_length=255, db_index=True)
    referencia_codigo = models.CharField(max_length=100, unique=True)
    barcode = models.CharField(max_length=100, blank=True, null=True, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="productos"
    )
    stock = models.PositiveIntegerField(default=0)  # antes: IntegerField
    min_stock = models.PositiveIntegerField(default=5)
    max_stock = models.PositiveIntegerField(null=True, blank=True)
    coste_precio = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # + precisión
    venta_precio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    localizacion = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['nombre']
        constraints = [
            models.CheckConstraint(check=models.Q(min_stock__gte=0), name="producto_min_stock_nonneg"),
            models.CheckConstraint(
                check=models.Q(max_stock__isnull=True) | models.Q(max_stock__gte=models.F("min_stock")),
                name="producto_max_ge_min_or_null"
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.referencia_codigo})"

    @property
    def bajo_stock(self):
        return self.stock <= self.min_stock

    @property
    def estado_stock(self):
        if self.stock == 0:
            return "Agotado"
        elif self.bajo_stock:
            return "Bajo"
        else:
            return "Disponible"

# --------------------------
# INVENTARIO MOVIMIENTO
# --------------------------
class InventarioMovimiento(models.Model):
    IN = "IN"
    OUT = "OUT"
    ADJ = "ADJ"
    MOVEMENT_TYPES = (
        (IN, "Entrada"),
        (OUT, "Salida"),
        (ADJ, "Ajuste"),
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="movimientos"
    )
    movimiento_tipo = models.CharField(max_length=3, choices=MOVEMENT_TYPES)
    cantidad = models.PositiveIntegerField()  # antes: IntegerField
    notas = models.TextField(blank=True, null=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    operation_id = models.CharField(max_length=64, unique=True, default=None, null=True, blank=True)
    performed_at = models.DateTimeField(default=timezone.now)  # fecha efectiva
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Movimiento de Inventario"
        verbose_name_plural = "Movimientos de Inventario"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["producto", "created_at"]),
            models.Index(fields=["movimiento_tipo"]),
        ]

    def __str__(self):
        return f"{self.get_movimiento_tipo_display()} - {self.producto.nombre} ({self.cantidad})"

    def clean(self):
        # Reglas mínimas por tipo
        if self.movimiento_tipo in (self.IN, self.OUT) and self.cantidad <= 0:
            raise IntegrityError("La cantidad debe ser > 0 para entradas/salidas.")
        if self.movimiento_tipo == self.ADJ and self.cantidad < 0:
            raise IntegrityError("El ajuste no puede ser negativo (interpreta 'set to').")

    @classmethod
    def apply(cls, *, producto, movimiento_tipo, cantidad, user=None, notas="", operation_id=None, performed_at=None):
        """
        Aplica un movimiento de forma atómica, con bloqueo e idempotencia.
        ADJ se interpreta como 'fijar el stock a `cantidad`'.
        """
        if not operation_id:
            # si no viene del cliente, no hacemos idempotencia fuerte
            operation_id = str(uuid.uuid4())

        with transaction.atomic():
            # Idempotencia
            existing = cls.objects.filter(operation_id=operation_id).first()
            if existing:
                return existing

            # Lock del producto
            p = Producto.objects.select_for_update().get(pk=producto.pk)

            if movimiento_tipo == cls.IN:
                p.stock = p.stock + int(cantidad)
            elif movimiento_tipo == cls.OUT:
                if p.stock < int(cantidad):
                    raise IntegrityError("Stock insuficiente para salida.")
                p.stock = p.stock - int(cantidad)
            elif movimiento_tipo == cls.ADJ:
                p.stock = int(cantidad)
            else:
                raise IntegrityError("Tipo de movimiento no soportado.")

            p.save(update_fields=["stock", "updated_at"])

            mv = cls.objects.create(
                producto=p,
                movimiento_tipo=movimiento_tipo,
                cantidad=int(cantidad),
                notas=notas,
                user=user,
                operation_id=operation_id,
                performed_at=performed_at or timezone.now(),
            )
            return mv
