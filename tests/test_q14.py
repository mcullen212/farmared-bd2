"""Pruebas de integración de q14. Requieren MongoDB replica set y MONGODB_URI.

Cada test utiliza una base temporal propia, que se elimina al finalizar. Nunca
modifica la base indicada en MONGODB_URI (por ejemplo, farmared).

Ejecutar: python -m pytest -v tests/test_q14.py
"""

import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

pymongo = pytest.importorskip("pymongo")
from src.consultas.q14 import registrar_venta

HOY = date.today()


@pytest.fixture
def db():
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        pytest.skip("Se requiere MONGODB_URI (MongoDB replica set)")
    cliente = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
    nombre = f"farmared_test_q14_{uuid4().hex}"
    base = cliente[nombre]
    try:
        cliente.admin.command("ping")
        base.ventas.create_index("id_venta", unique=True)
        base.clientes.insert_many([
            {"id_cliente": "C1", "activo": True},
            {"id_cliente": "C2", "activo": True},
            {"id_cliente": "CI", "activo": False},
        ])
        base.sucursales.insert_many([
            {"id_sucursal": "S1", "tipo": "Farmacia", "activo": True},
            {"id_sucursal": "SD", "tipo": "Droguería", "activo": True},
            {"id_sucursal": "SI", "tipo": "Farmacia", "activo": False},
        ])
        base.farmaceuticos.insert_many([
            {"id_farmaceutico": "F1", "id_sucursal": "S1", "activo": True},
            {"id_farmaceutico": "FI", "id_sucursal": "S1", "activo": False},
            {"id_farmaceutico": "FD", "id_sucursal": "SD", "activo": True},
            {"id_farmaceutico": "FSI", "id_sucursal": "SI", "activo": True},
        ])
        base.productos.insert_many([
            {"id_producto": "P1", "activo": True, "condicion_venta": "Venta libre", "precio_unit": 2800},
            {"id_producto": "P2", "activo": True, "condicion_venta": "Venta libre", "precio_unit": 3500},
            {"id_producto": "PR", "activo": True, "condicion_venta": "Bajo receta", "precio_unit": 9800},
            {"id_producto": "PA", "activo": True, "condicion_venta": "Bajo receta archivada", "precio_unit": 12000},
            {"id_producto": "PI", "activo": False, "condicion_venta": "Venta libre", "precio_unit": 500},
        ])
        base.recetas.insert_many([
            {"id_receta": "R1", "id_cliente": "C1", "tipo": "Simple", "estado": "Vigente",
             "dispensas_autorizadas": 1, "dispensas_realizadas": 0, "proxima_dispensa": None},
            {"id_receta": "R2", "id_cliente": "C2", "tipo": "Simple", "estado": "Vigente",
             "dispensas_autorizadas": 1, "dispensas_realizadas": 0, "proxima_dispensa": None},
            {"id_receta": "RV", "id_cliente": "C1", "tipo": "Simple", "estado": "Vencida",
             "dispensas_autorizadas": 1, "dispensas_realizadas": 0, "proxima_dispensa": None},
            {"id_receta": "RC", "id_cliente": "C1", "tipo": "Simple", "estado": "Completada",
             "dispensas_autorizadas": 1, "dispensas_realizadas": 1, "proxima_dispensa": None},
            {"id_receta": "RX", "id_cliente": "C1", "tipo": "Simple", "estado": "Vigente",
             "dispensas_autorizadas": 1, "dispensas_realizadas": 1, "proxima_dispensa": None},
            {"id_receta": "RA", "id_cliente": "C1", "tipo": "Archivada", "estado": "Vigente",
             "dispensas_autorizadas": 1, "dispensas_realizadas": 0, "proxima_dispensa": None},
            {"id_receta": "RP", "id_cliente": "C1", "tipo": "Tratamiento prolongado", "estado": "Vigente",
             "dispensas_autorizadas": 3, "dispensas_realizadas": 1, "proxima_dispensa": None},
            {"id_receta": "RPULT", "id_cliente": "C1", "tipo": "Tratamiento prolongado", "estado": "Vigente",
             "dispensas_autorizadas": 3, "dispensas_realizadas": 2, "proxima_dispensa": None},
        ])
        vencimiento = lambda dias: datetime.combine(HOY + timedelta(days=dias), datetime.min.time(), timezone.utc)
        base.stock_lotes.insert_many([
            {"id_lote": "L1", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(5), "unidades": 4},
            {"id_lote": "L2", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 10},
            {"id_lote": "L3", "id_producto": "P2", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 3},
            {"id_lote": "LR", "id_producto": "PR", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 5},
            {"id_lote": "LA", "id_producto": "PA", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 5},
        ])
        yield base
    finally:
        cliente.drop_database(nombre)
        cliente.close()


def entrada(**cambios):
    datos = {"id_cliente": "C1", "id_farmaceutico": "F1", "medio_pago": "Efectivo",
             "detalle": [{"id_producto": "P1", "cantidad": 1}]}
    datos.update(cambios)
    return datos


def foto(db):
    """Permite verificar que el rechazo sea totalmente atómico."""
    return {
        "ventas": db.ventas.count_documents({}),
        "eventos": db.proyeccion_pendiente.count_documents({}),
        "stock": {d["id_lote"]: d["unidades"] for d in db.stock_lotes.find()},
        "recetas": {d["id_receta"]: (d["estado"], d["dispensas_realizadas"], d["proxima_dispensa"])
                    for d in db.recetas.find()},
    }


def rechazar_sin_cambios(db, datos, excepcion=ValueError, *, mensaje=None):
    antes = foto(db)
    with pytest.raises(excepcion, match=mensaje):
        registrar_venta(db, datos, hoy=HOY)
    assert foto(db) == antes, "Una venta rechazada dejó cambios parciales"


def test_registro_valido_crea_venta_total_detalle_y_evento(db):
    venta = registrar_venta(db, entrada(), hoy=HOY)
    assert venta["estado"] == "Completada"
    assert venta["tipo"] == "Venta libre"
    assert venta["id_sucursal"] == "S1"
    assert venta["total"] == 2800
    assert venta["detalle"][0]["precio_unit"] == 2800
    assert db.ventas.count_documents({"id_venta": venta["id_venta"]}) == 1
    assert db.stock_lotes.find_one({"id_lote": "L1"})["unidades"] == 3
    evento = db.proyeccion_pendiente.find_one({"operacion": "q14.venta"})
    assert evento["estado"] == "pendiente"
    assert evento["refs"] == [{"entidad": "venta", "id": venta["id_venta"]}]


def test_cliente_inexistente(db):
    rechazar_sin_cambios(db, entrada(id_cliente="NO_EXISTE"))


def test_cliente_inactivo(db):
    rechazar_sin_cambios(db, entrada(id_cliente="CI"))


def test_farmaceutico_inexistente(db):
    rechazar_sin_cambios(db, entrada(id_farmaceutico="NO_EXISTE"))


def test_farmaceutico_inactivo(db):
    rechazar_sin_cambios(db, entrada(id_farmaceutico="FI"))


def test_farmaceutico_de_drogueria(db):
    rechazar_sin_cambios(db, entrada(id_farmaceutico="FD"))


def test_sucursal_inactiva(db):
    rechazar_sin_cambios(db, entrada(id_farmaceutico="FSI"))


def test_producto_inexistente(db):
    rechazar_sin_cambios(db, entrada(detalle=[{"id_producto": "NO_EXISTE", "cantidad": 1}]))


def test_producto_inactivo(db):
    rechazar_sin_cambios(db, entrada(detalle=[{"id_producto": "PI", "cantidad": 1}]))


def test_producto_bajo_receta_sin_receta(db):
    rechazar_sin_cambios(db, entrada(detalle=[{"id_producto": "PR", "cantidad": 1}]))


def test_receta_inexistente(db):
    rechazar_sin_cambios(db, entrada(id_receta="NO_EXISTE", detalle=[{"id_producto": "PR", "cantidad": 1}]))


def test_receta_de_otro_cliente(db):
    rechazar_sin_cambios(db, entrada(id_receta="R2", detalle=[{"id_producto": "PR", "cantidad": 1}]))


def test_receta_vencida(db):
    rechazar_sin_cambios(db, entrada(id_receta="RV", detalle=[{"id_producto": "PR", "cantidad": 1}]))


def test_receta_completada(db):
    rechazar_sin_cambios(db, entrada(id_receta="RC", detalle=[{"id_producto": "PR", "cantidad": 1}]))


def test_receta_sin_dispensas_disponibles(db):
    rechazar_sin_cambios(db, entrada(id_receta="RX", detalle=[{"id_producto": "PR", "cantidad": 1}]))


def test_receta_archivada_incompatible(db):
    rechazar_sin_cambios(db, entrada(id_receta="R1", detalle=[{"id_producto": "PA", "cantidad": 1}]))


def test_receta_archivada_correcta_se_completa(db):
    registrar_venta(db, entrada(id_receta="RA", detalle=[{"id_producto": "PA", "cantidad": 1}]), hoy=HOY)
    receta = db.recetas.find_one({"id_receta": "RA"})
    assert receta["estado"] == "Completada"
    assert receta["dispensas_realizadas"] == 1
    assert receta["proxima_dispensa"] is None


def test_receta_simple_se_completa(db):
    venta = registrar_venta(db, entrada(id_venta="VTEST", id_receta="R1", detalle=[
        {"id_producto": "PR", "cantidad": 1}, {"id_producto": "P2", "cantidad": 2}]), hoy=HOY)
    assert venta["total"] == 16800
    assert venta["movimiento_stock"]["estado"] == "aplicado"
    assert db.stock_lotes.find_one({"id_lote": "LR"})["unidades"] == 4
    assert db.stock_lotes.find_one({"id_lote": "L3"})["unidades"] == 1
    receta = db.recetas.find_one({"id_receta": "R1"})
    assert (receta["estado"], receta["dispensas_realizadas"]) == ("Completada", 1)
    assert receta["proxima_dispensa"] is None
    assert {"entidad": "receta", "id": "R1"} in db.proyeccion_pendiente.find_one(
        {"refs.id": venta["id_venta"]})["refs"]


def test_tratamiento_prolongado_programa_siguiente_dispensa(db):
    registrar_venta(db, entrada(id_receta="RP", fecha=HOY.isoformat(),
                               detalle=[{"id_producto": "PR", "cantidad": 1}]), hoy=HOY)
    receta = db.recetas.find_one({"id_receta": "RP"})
    assert receta["estado"] == "Vigente"
    assert receta["dispensas_realizadas"] == 2
    assert receta["proxima_dispensa"].date() == HOY + timedelta(days=30)


def test_ultima_dispensa_completa_tratamiento(db):
    registrar_venta(db, entrada(id_receta="RPULT", detalle=[{"id_producto": "PR", "cantidad": 1}]), hoy=HOY)
    receta = db.recetas.find_one({"id_receta": "RPULT"})
    assert (receta["estado"], receta["dispensas_realizadas"], receta["proxima_dispensa"]) == (
        "Completada", 3, None)


def test_total_calculado_y_precio_del_catalogo(db):
    venta = registrar_venta(db, entrada(detalle=[{"id_producto": "P1", "cantidad": 2},
                                                   {"id_producto": "P2", "cantidad": 1}]), hoy=HOY)
    assert venta["total"] == 2 * 2800 + 3500
    assert [i["precio_unit"] for i in venta["detalle"]] == [2800, 3500]


def test_detalle_vacio(db):
    rechazar_sin_cambios(db, entrada(detalle=[]))


@pytest.mark.parametrize("cantidad", [0, -1, 1.5, "2", True])
def test_cantidad_no_entera_positiva(db, cantidad):
    rechazar_sin_cambios(db, entrada(detalle=[{"id_producto": "P1", "cantidad": cantidad}]))


def test_medio_de_pago_invalido(db):
    rechazar_sin_cambios(db, entrada(medio_pago="Criptomonedas"))


def test_venta_sin_stock_revierte_venta_receta_stock_y_evento(db):
    rechazar_sin_cambios(db, entrada(id_venta="VTEST", id_receta="R1", detalle=[
        {"id_producto": "PR", "cantidad": 1}, {"id_producto": "P2", "cantidad": 99}]),
        mensaje="Stock vigente insuficiente para P2: faltan 96 unidades")


def test_venta_con_segundo_producto_sin_stock_revierte_primer_descuento(db):
    rechazar_sin_cambios(db, entrada(detalle=[
        {"id_producto": "P1", "cantidad": 2}, {"id_producto": "P2", "cantidad": 99}]))


def test_venta_descuenta_fefo_en_varios_lotes(db):
    venta = registrar_venta(db, entrada(detalle=[{"id_producto": "P1", "cantidad": 6}]), hoy=HOY)
    assert db.stock_lotes.find_one({"id_lote": "L1"})["unidades"] == 0
    assert db.stock_lotes.find_one({"id_lote": "L2"})["unidades"] == 8
    assert venta["movimiento_stock"]["estado"] == "aplicado"


def test_id_venta_duplicado_no_altera_datos(db):
    datos = entrada(id_venta="VTEST")
    registrar_venta(db, datos, hoy=HOY)
    rechazar_sin_cambios(db, datos)
