# inventario/tests.py
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from .models import Categoria, Producto, InventarioMovimiento
from .serializers import (
    ProductoSerializer, ProductoCreateSerializer,
    InventarioMovimientoCreateSerializer, StockUpdateSerializer
)

User = get_user_model()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def auth_client(user=None):
    client = APIClient()
    if user:
        client.force_authenticate(user)
    return client


def create_user(email="t@example.com", password="pass123", **extra):
    """
    Crea un usuario compatible con CustomUser basado en email.
    Si tu modelo requiere campos adicionales (p.ej. nombre), pásalos en **extra**.
    """
    return User.objects.create_user(email=email, password=password, **extra)


def create_producto(nombre="Prod A", sku="SKU-A", cat=None, **kwargs):
    if cat is None:
        cat = Categoria.objects.create(nombre="General")
    defaults = dict(
        nombre=nombre,
        referencia_codigo=sku,
        categoria=cat,
        stock=0,
        min_stock=5,
        max_stock=None,
        coste_precio=Decimal("1.00"),
        venta_precio=Decimal("2.00"),
        is_active=True,
    )
    defaults.update(kwargs)
    return Producto.objects.create(**defaults)


# ---------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------
class CategoriaModelTests(TestCase):
    def test_categoria_str_and_hierarchy(self):
        root = Categoria.objects.create(nombre="Raíz")
        child = Categoria.objects.create(nombre="Hija", parent=root)
        self.assertEqual(str(root), "Raíz")
        self.assertTrue(root.es_raiz)
        self.assertEqual(child.nivel, 1)

    def test_categoria_parent_not_self_constraint(self):
        cat = Categoria.objects.create(nombre="X")
        with self.assertRaises(Exception):
            # Violación del CheckConstraint (parent != self)
            cat.parent = cat
            cat.save(update_fields=["parent"])


class ProductoModelTests(TestCase):
    def test_constraints_min_and_max_stock(self):
        c = Categoria.objects.create(nombre="Cat")
        # ok: max_stock None
        Producto.objects.create(
            nombre="P",
            referencia_codigo="SKU-1",
            categoria=c,
            min_stock=2,
            max_stock=None,
            coste_precio=Decimal("1.00"),
            venta_precio=Decimal("2.00"),
        )
        # violación: max < min
        with self.assertRaises(Exception):
            Producto.objects.create(
                nombre="P2",
                referencia_codigo="SKU-2",
                categoria=c,
                min_stock=5,
                max_stock=3,
                coste_precio=Decimal("1.00"),
                venta_precio=Decimal("2.00"),
            )

    def test_estado_stock_and_bajo_stock(self):
        p = create_producto(stock=0, min_stock=3)
        self.assertEqual(p.estado_stock, "Agotado")
        p.stock = 2
        p.save()
        self.assertTrue(p.bajo_stock)
        self.assertEqual(p.estado_stock, "Bajo")
        p.stock = 10
        p.save()
        self.assertEqual(p.estado_stock, "Disponible")


class InventarioMovimientoModelTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.p = create_producto(stock=0)

    def test_apply_increases_stock_on_IN(self):
        mv = InventarioMovimiento.apply(
            producto=self.p, movimiento_tipo=InventarioMovimiento.IN,
            cantidad=7, user=self.user, operation_id="op-in-1"
        )
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 7)
        self.assertEqual(mv.cantidad, 7)
        self.assertEqual(mv.movimiento_tipo, "IN")

    def test_apply_out_requires_stock(self):
        with self.assertRaises(IntegrityError):
            InventarioMovimiento.apply(
                producto=self.p, movimiento_tipo=InventarioMovimiento.OUT,
                cantidad=1, user=self.user, operation_id="op-out-bad"
            )

    def test_apply_out_decreases_stock(self):
        InventarioMovimiento.apply(
            producto=self.p, movimiento_tipo=InventarioMovimiento.IN,
            cantidad=5, user=self.user, operation_id="op-in-2"
        )
        InventarioMovimiento.apply(
            producto=self.p, movimiento_tipo=InventarioMovimiento.OUT,
            cantidad=3, user=self.user, operation_id="op-out-1"
        )
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 2)

    def test_apply_adjust_sets_value(self):
        InventarioMovimiento.apply(
            producto=self.p, movimiento_tipo=InventarioMovimiento.IN,
            cantidad=3, user=self.user, operation_id="op-in-3"
        )
        InventarioMovimiento.apply(
            producto=self.p, movimiento_tipo=InventarioMovimiento.ADJ,
            cantidad=12, user=self.user, operation_id="op-adj-1"
        )
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 12)

    def test_idempotency_operation_id(self):
        InventarioMovimiento.apply(
            producto=self.p, movimiento_tipo=InventarioMovimiento.IN,
            cantidad=4, user=self.user, operation_id="op-dup"
        )
        # Repetimos misma operación → no duplica
        InventarioMovimiento.apply(
            producto=self.p, movimiento_tipo=InventarioMovimiento.IN,
            cantidad=4, user=self.user, operation_id="op-dup"
        )
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 4)
        self.assertEqual(InventarioMovimiento.objects.filter(operation_id="op-dup").count(), 1)


# ---------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------
class SerializerTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.c = Categoria.objects.create(nombre="General")
        self.p = create_producto(cat=self.c, stock=0, referencia_codigo="SKU-X")

    def test_producto_serializer_stock_read_only(self):
        data = {
            "referencia_codigo": self.p.referencia_codigo,
            "nombre": self.p.nombre,
            "descripcion": "Nueva desc",
            "categoria_id": self.c.id,
            "stock": 999,  # no debe aceptarse
        }
        ser = ProductoSerializer(instance=self.p, data=data, partial=True)
        self.assertTrue(ser.is_valid(), ser.errors)
        obj = ser.save()
        obj.refresh_from_db()
        self.assertNotEqual(obj.stock, 999)  # stock no se alteró

    def test_movimiento_create_serializer_success_and_idempotency(self):
        ser = InventarioMovimientoCreateSerializer(
            data={
                "producto": self.p.id,
                "movimiento_tipo": "IN",
                "cantidad": 10,
                "notas": "Carga inicial",
                "operation_id": "s-op-1"
            },
            context={"request": type("r", (), {"user": self.user, "method": "POST", "META": {}})()}
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        mv1 = ser.save()
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 10)

        # Idempotencia
        ser2 = InventarioMovimientoCreateSerializer(
            data={
                "producto": self.p.id,
                "movimiento_tipo": "IN",
                "cantidad": 10,
                "operation_id": "s-op-1"
            },
            context={"request": type("r", (), {"user": self.user})()}
        )
        self.assertTrue(ser2.is_valid(), ser2.errors)
        mv2 = ser2.save()
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 10)
        self.assertEqual(mv1.id, mv2.id)

    def test_stock_update_serializer_out_of_stock(self):
        ser = StockUpdateSerializer(
            data={"movimiento_tipo": "OUT", "cantidad": 1},
            context={"producto": self.p, "request": type("r", (), {"user": self.user})()}
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        with self.assertRaises(Exception):
            # save() elevará ValidationError mapeada desde IntegrityError
            ser.save()


# ---------------------------------------------------------------------
# API tests (DRF views)
# ---------------------------------------------------------------------
class InventarioAPITests(APITestCase):
    def setUp(self):
        self.user = create_user()
        self.client = auth_client(self.user)
        self.cat = Categoria.objects.create(nombre="General")
        self.prod = create_producto(nombre="Producto A", sku="SKU-A", cat=self.cat, stock=0)

    # ----------------------- Categorías -----------------------
    def test_categoria_crud_and_search(self):
        # create
        url_list = reverse("inventario:categoria-list-create")
        res = self.client.post(url_list, {"nombre": "Alimentos"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        cat_id = res.data["id"]

        # retrieve
        url_detail = reverse("inventario:categoria-detail", args=[cat_id])
        res2 = self.client.get(url_detail)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)

        # search
        url_search = reverse("inventario:categoria-search") + "?q=ali"
        res3 = self.client.get(url_search)
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res3.data), 1)

        # choices
        url_choices = reverse("inventario:categoria-choices")
        res4 = self.client.get(url_choices)
        self.assertEqual(res4.status_code, status.HTTP_200_OK)

        # categoria con productos
        url_cat_prod = reverse("inventario:categoria-con-productos", args=[self.cat.id])
        res5 = self.client.get(url_cat_prod)
        self.assertEqual(res5.status_code, status.HTTP_200_OK)

    # ----------------------- Productos -----------------------
    def test_producto_list_create_detail_update_filters(self):
        # list (paginado)
        url_list = reverse("inventario:producto-list-create")
        res = self.client.get(url_list)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("results", res.data)

        # create
        payload = {
            "referencia_codigo": "SKU-B",
            "nombre": "Producto B",
            "descripcion": "Desc",
            "categoria": self.cat.id,
            "min_stock": 3,
            "coste_precio": "1.50",
            "venta_precio": "3.20",
            "is_active": True
        }
        res_c = self.client.post(url_list, payload, format="json")
        self.assertEqual(res_c.status_code, status.HTTP_201_CREATED, res_c.data)
        p2_id = res_c.data["id"]

        # detail
        url_detail = reverse("inventario:producto-detail", args=[p2_id])
        res_d = self.client.get(url_detail)
        self.assertEqual(res_d.status_code, status.HTTP_200_OK)
        self.assertEqual(res_d.data["nombre"], "Producto B")

        # update (no debe permitir cambiar stock)
        res_u = self.client.patch(url_detail, {"stock": 999}, format="json")
        self.assertEqual(res_u.status_code, status.HTTP_200_OK)
        self.assertNotEqual(res_u.data["stock"], 999)

        # filtros
        res_f = self.client.get(url_list + f"?categoria={self.cat.id}&bajo_stock=true")
        self.assertEqual(res_f.status_code, status.HTTP_200_OK)

        # search endpoint
        url_search = reverse("inventario:producto-search") + "?q=SKU-"
        res_s = self.client.get(url_search)
        self.assertEqual(res_s.status_code, status.HTTP_200_OK)

        # low stock
        url_low = reverse("inventario:producto-low-stock")
        res_low = self.client.get(url_low)
        self.assertEqual(res_low.status_code, status.HTTP_200_OK)

    def test_producto_stock_update_view(self):
        url = reverse("inventario:producto-stock-update", args=[self.prod.id])

        # IN 8
        res_in = self.client.patch(url, {
            "movimiento_tipo": "IN",
            "cantidad": 8,
            "notas": "Carga por PATCH",
            "operation_id": "patch-001"
        }, format="json")
        self.assertEqual(res_in.status_code, status.HTTP_200_OK, res_in.data)
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.stock, 8)
        self.assertEqual(res_in.data["movimiento_tipo"], "IN")

        # OUT 3
        res_out = self.client.patch(url, {
            "movimiento_tipo": "OUT",
            "cantidad": 3,
            "operation_id": "patch-002"
        }, format="json")
        self.assertEqual(res_out.status_code, status.HTTP_200_OK, res_out.data)
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.stock, 5)

        # OUT insuficiente
        res_bad = self.client.patch(url, {
            "movimiento_tipo": "OUT",
            "cantidad": 9
        }, format="json")
        self.assertEqual(res_bad.status_code, status.HTTP_400_BAD_REQUEST)

    # ----------------------- Movimientos -----------------------
    def test_movimiento_list_create_filters_and_pagination(self):
        url = reverse("inventario:movimiento-list-create")

        # Crear algunos movimientos
        self.client.post(url, {
            "producto": self.prod.id, "movimiento_tipo": "IN", "cantidad": 10, "operation_id": "m-1"
        }, format="json")
        self.client.post(url, {
            "producto": self.prod.id, "movimiento_tipo": "OUT", "cantidad": 2, "operation_id": "m-2"
        }, format="json")
        self.client.post(url, {
            "producto": self.prod.id, "movimiento_tipo": "ADJ", "cantidad": 5, "operation_id": "m-3"
        }, format="json")

        # listado
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("results", res.data)
        self.assertGreaterEqual(res.data["count"], 3)

        # filtros por tipo
        res_tipo = self.client.get(url + "?tipo=OUT")
        self.assertEqual(res_tipo.status_code, status.HTTP_200_OK)
        self.assertTrue(all(m["movimiento_tipo"] == "OUT" for m in res_tipo.data["results"]))

        # filtros por usuario
        res_usr = self.client.get(url + f"?usuario={self.user.id}")
        self.assertEqual(res_usr.status_code, status.HTTP_200_OK)

        # filtros por fechas
        today = timezone.now().date().isoformat()
        res_fecha = self.client.get(url + f"?fecha_inicio={today}&fecha_fin={today}")
        self.assertEqual(res_fecha.status_code, status.HTTP_200_OK)

        # detalle
        mv_id = res.data["results"][0]["id"]
        url_detail = reverse("inventario:movimiento-detail", args=[mv_id])
        res_det = self.client.get(url_detail)
        self.assertEqual(res_det.status_code, status.HTTP_200_OK)

    def test_movimiento_create_idempotency(self):
        url = reverse("inventario:movimiento-list-create")
        payload = {
            "producto": self.prod.id,
            "movimiento_tipo": "IN",
            "cantidad": 4,
            "operation_id": "dup-001"
        }
        r1 = self.client.post(url, payload, format="json")
        r2 = self.client.post(url, payload, format="json")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.data)
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.stock, 4)
        self.assertEqual(InventarioMovimiento.objects.filter(operation_id="dup-001").count(), 1)
