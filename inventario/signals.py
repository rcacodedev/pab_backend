from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from .models import InventarioMovimiento, Producto

@receiver(pre_save, sender=InventarioMovimiento)
def validar_movimiento_antes_de_guardar(sender, instance, **kwargs):
    """
    Valida el movimiento antes de guardar (usando clean)
    """
    instance.clean()

@receiver(post_save, sender=InventarioMovimiento)
def actualizar_stock_desde_movimiento(sender, instance, created, **kwargs):
    """
    Actualiza automáticamente el stock del producto cuando se crea un movimiento
    """
    if created:
        producto = instance.producto
        try:
            if instance.movimiento_tipo == 'IN':
                producto.stock += instance.cantidad
            elif instance.movimiento_tipo == 'OUT':
                producto.stock -= instance.cantidad
                if producto.stock < 0:
                    producto.stock = 0  # Prevenir stock negativo
            elif instance.movimiento_tipo == 'ADJ':
                producto.stock = instance.cantidad

            # Validar el producto antes de guardar
            producto.full_clean()
            producto.save(update_fields=['stock'])

        except ValidationError as e:
            # Manejar error de validación (opcional: loggear el error)
            raise ValidationError(f"Error al actualizar stock: {e}")

@receiver(pre_save, sender=Producto)
def validar_producto_antes_de_guardar(sender, instance, **kwargs):
    """
    Valida el producto antes de guardar
    """
    instance.clean()