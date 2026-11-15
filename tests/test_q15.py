"""Pruebas de integración de q15. Requieren MongoDB replica set y MONGODB_URI.

Cada test crea y elimina una base temporal independiente, sin tocar farmared.
Ejecutar: python -m pytest -v tests/test_q15.py
"""

import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

pymongo = pytest.importorskip("pymongo")
from src.consultas.q15 import descontar_stock

HOY = date.today()


@pytest.fixture
def db():
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        pytest.skip("Se requiere MONGODB_URI (MongoDB replica set)")
    cliente = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
    nombre = f"farmared_test_q15_{uuid4().hex}"
    base = cliente[nombre]
    try:
        cliente.admin.command("ping")
        base.farmaceuticos.insert_one({"id_farmaceutico": "F1", "id_sucursal": "S1"})
        vencimiento = lambda dias: datetime.combine(HOY + timedelta(days=dias), datetime.min.time(), timezone.utc)
        base.stock_lotes.insert_many([
            {"id_lote": "L_VENCIDO", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(-1), "unidades": 50},
            {"id_lote": "L_HOY", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(0), "unidades": 2},
            {"id_lote": "L_PROXIMO", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(5), "unidades": 3},
            {"id_lote": "L_LEJANO", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 5},
            {"id_lote": "L_OTRA_SUCURSAL", "id_producto": "P1", "id_sucursal": "S2", "vencimiento": vencimiento(1), "unidades": 100},
            {"id_lote": "L_P2", "id_producto": "P2", "id_sucursal": "S1", "vencimiento": vencimiento(10), "unidades": 3},
        ])
        base.ventas.insert_one({"id_venta": "VTEST", "id_farmaceutico": "F1", "id_sucursal": "S1",
                                "estado": "Completada", "detalle": [{"id_producto": "P1", "cantidad": 1}],
                                "movimiento_stock": {"estado": "sin_aplicar"}})
        yield base
    finally:
        cliente.drop_database(nombre)
        cliente.close()


def foto(db):
    return {
        "lotes": {d["id_lote"]: d["unidades"] for d in db.stock_lotes.find()},
        "ventas": [(d["id_venta"], d.get("movimiento_stock")) for d in db.ventas.find().sort("id_venta", 1)],
    }


def rechazar_sin_cambios(db, excepcion=ValueError):
    antes = foto(db)
    with pytest.raises(excepcion):
        descontar_stock(db, "VTEST", hoy=HOY)
    assert foto(db) == antes, "Q15 dejó descuentos parciales ante un rechazo"


def actualizar_venta(db, **campos):
    db.ventas.update_one({"id_venta": "VTEST"}, {"$set": campos})


def detalle(*items):
    return [{"id_producto": p, "cantidad": n} for p, n in items]


def test_venta_inexistente(db):
    antes = foto(db)
    with pytest.raises(LookupError):
        descontar_stock(db, "NO_EXISTE", hoy=HOY)
    assert foto(db) == antes


@pytest.mark.parametrize("estado", ["Pendiente", "Anulada"])
def test_venta_no_completada_no_descuenta(db, estado):
    actualizar_venta(db, estado=estado)
    rechazar_sin_cambios(db)


def test_farmaceutico_inexistente(db):
    actualizar_venta(db, id_farmaceutico="NO_EXISTE")
    rechazar_sin_cambios(db)


def test_sucursal_de_venta_distinta_de_la_del_farmaceutico(db):
    actualizar_venta(db, id_sucursal="S2")
    rechazar_sin_cambios(db)


def test_detalle_vacio(db):
    actualizar_venta(db, detalle=[])
    rechazar_sin_cambios(db)


@pytest.mark.parametrize("cantidad", [0, -1, 1.5, "2", None, True])
def test_cantidad_invalida(db, cantidad):
    actualizar_venta(db, detalle=detalle(("P1", cantidad)))
    rechazar_sin_cambios(db)


def test_producto_sin_stock(db):
    actualizar_venta(db, detalle=detalle(("P_INEXISTENTE", 1)))
    rechazar_sin_cambios(db)


def test_stock_total_insuficiente_rechaza_sin_modificar(db):
    # Hay 10 unidades vigentes en S1; 50 vencidas y 100 de S2 no cuentan.
    actualizar_venta(db, detalle=detalle(("P1", 11)))
    rechazar_sin_cambios(db)


def test_fallo_segundo_producto_revierte_descuento_del_primero(db):
    actualizar_venta(db, detalle=detalle(("P1", 4), ("P2", 4)))
    rechazar_sin_cambios(db)


def test_fefo_descontar_primero_lote_mas_proximo(db):
    actualizar_venta(db, detalle=detalle(("P1", 4)))
    venta = descontar_stock(db, "VTEST", hoy=HOY)
    assert [(a["id_lote"], a["cantidad"]) for a in venta["movimiento_stock"]["asignaciones"]] == [
        ("L_HOY", 2), ("L_PROXIMO", 2)]
    assert db.stock_lotes.find_one({"id_lote": "L_LEJANO"})["unidades"] == 5


def test_lote_vencido_se_omite(db):
    descontar_stock(db, "VTEST", hoy=HOY)
    assert db.stock_lotes.find_one({"id_lote": "L_VENCIDO"})["unidades"] == 50


def test_lote_que_vence_hoy_es_valido(db):
    descontar_stock(db, "VTEST", hoy=HOY)
    assert db.stock_lotes.find_one({"id_lote": "L_HOY"})["unidades"] == 1


def test_no_descontar_stock_de_otra_sucursal(db):
    actualizar_venta(db, detalle=detalle(("P1", 7)))
    descontar_stock(db, "VTEST", hoy=HOY)
    assert db.stock_lotes.find_one({"id_lote": "L_OTRA_SUCURSAL"})["unidades"] == 100


def test_stock_nunca_negativo(db):
    actualizar_venta(db, detalle=detalle(("P1", 10)))
    descontar_stock(db, "VTEST", hoy=HOY)
    assert all(doc["unidades"] >= 0 for doc in db.stock_lotes.find())
    assert sum(
        d["unidades"]
        for d in db.stock_lotes.find({
            "id_producto": "P1",
            "id_sucursal": "S1",
            "vencimiento": {"$gte": datetime.combine(HOY, datetime.min.time())}
        })
    ) == 0


def test_item_repetido_suma_cantidades(db):
    actualizar_venta(db, detalle=detalle(("P1", 3), ("P1", 4)))
    venta = descontar_stock(db, "VTEST", hoy=HOY)
    assert sum(a["cantidad"] for a in venta["movimiento_stock"]["asignaciones"]) == 7


def test_segunda_ejecucion_no_duplica_el_descuento(db):
    descontar_stock(db, "VTEST", hoy=HOY)
    despues = foto(db)
    descontar_stock(db, "VTEST", hoy=HOY)
    assert foto(db) == despues


@pytest.mark.parametrize("estado", ["aplicado", "historico"])
def test_movimiento_ya_aplicado_no_se_repite(db, estado):
    actualizar_venta(db, movimiento_stock={"estado": estado})
    antes = foto(db)
    descontar_stock(db, "VTEST", hoy=HOY)
    assert foto(db) == antes


def test_estado_movimiento_desconocido_se_rechaza(db):
    actualizar_venta(db, movimiento_stock={"estado": "desconocido"})
    rechazar_sin_cambios(db)


def test_si_falla_actualizacion_de_lote_hace_rollback(db, monkeypatch):
    from src.repositorio_mongo import RepositorioMongo

    original = RepositorioMongo.decrementar_lote
    contador = {"n": 0}

    def fallo_en_segundo_lote(self, id_lote, cantidad, *, session=None):
        contador["n"] += 1
        if contador["n"] == 2:
            return False
        return original(self, id_lote, cantidad, session=session)

    monkeypatch.setattr(RepositorioMongo, "decrementar_lote", fallo_en_segundo_lote)
    actualizar_venta(db, detalle=detalle(("P1", 4)))
    rechazar_sin_cambios(db)
