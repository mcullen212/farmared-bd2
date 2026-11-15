"""Pruebas de integración de q15. Requieren MongoDB replica set y MONGODB_URI.

Cada test crea y elimina una base temporal independiente, sin tocar farmared.
Ejecutar: python -m pytest -v tests/test_q15.py
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from pymongo import MongoClient

from src.consultas.q15 import descontar_stock

HOY = date(2026, 11, 12)


def test_descontar_stock_con_sesion_sin_transaccion_rechaza_llamada():
    # No hay acceso a MongoDB antes de verificar que la sesión sea transaccional.
    with MongoClient(connect=False) as cliente, cliente.start_session() as sesion:
        with pytest.raises(ValueError, match="transacción activa"):
            descontar_stock(None, "VTEST", hoy=HOY, session=sesion)


@pytest.fixture
def db(base_mongo):
    base_mongo.farmaceuticos.insert_one({"id_farmaceutico": "F1", "id_sucursal": "S1"})
    vencimiento = lambda dias: datetime.combine(HOY + timedelta(days=dias), datetime.min.time(), timezone.utc)
    base_mongo.stock_lotes.insert_many([
        {"id_lote": "L_VENCIDO", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(-1), "unidades": 50},
        {"id_lote": "L_HOY", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(0), "unidades": 2},
        {"id_lote": "L_PROXIMO", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(5), "unidades": 3},
        {"id_lote": "L_LEJANO", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 5},
        {"id_lote": "L_OTRA_SUCURSAL", "id_producto": "P1", "id_sucursal": "S2", "vencimiento": vencimiento(1), "unidades": 100},
        {"id_lote": "L_P2", "id_producto": "P2", "id_sucursal": "S1", "vencimiento": vencimiento(10), "unidades": 3},
    ])
    base_mongo.ventas.insert_one({"id_venta": "VTEST", "id_farmaceutico": "F1", "id_sucursal": "S1",
                            "estado": "Completada", "detalle": [{"id_producto": "P1", "cantidad": 1}],
                            "movimiento_stock": {"estado": "sin_aplicar"}})
    return base_mongo


def foto(db):
    return {
        "lotes": {d["id_lote"]: d["unidades"] for d in db.stock_lotes.find()},
        "ventas": [(d["id_venta"], d.get("movimiento_stock")) for d in db.ventas.find().sort("id_venta", 1)],
    }


def imprimir_resultado(caso, antes, despues):
    print(f"\nQ15 · {caso}\n")
    print(f"| Dato | Antes | Después del {caso} |")
    print("| --- | --- | --- |")
    lotes = {
        "L_VENCIDO": "Lote vencido de `P1`",
        "L_HOY": "Lote de `P1` que vence el día de la prueba",
        "L_PROXIMO": "Siguiente lote vigente de `P1`",
        "L_P2": "Lote vigente de `P2`",
    }
    for id_lote, nombre in lotes.items():
        print(f"| {nombre} | {antes['lotes'][id_lote]} | {despues['lotes'][id_lote]} |")
    inicial = dict(antes["ventas"])["VTEST"]["estado"]
    final = dict(despues["ventas"])["VTEST"]["estado"]
    print(f"| Movimiento de la venta | `{inicial}` | `{final}` |")


def rechazar_sin_cambios(db, *, mensaje):
    antes = foto(db)
    with pytest.raises(ValueError, match=mensaje):
        descontar_stock(db, "VTEST", hoy=HOY)
    assert foto(db) == antes, "Q15 dejó descuentos parciales ante un rechazo"


def actualizar_venta(db, **campos):
    db.ventas.update_one({"id_venta": "VTEST"}, {"$set": campos})


def detalle(*items):
    return [{"id_producto": p, "cantidad": n} for p, n in items]


def test_descontar_stock_con_venta_inexistente_rechaza_movimiento(db):
    antes = foto(db)
    with pytest.raises(LookupError, match="No existe la venta NO_EXISTE"):
        descontar_stock(db, "NO_EXISTE", hoy=HOY)
    assert foto(db) == antes


@pytest.mark.parametrize("estado", ["Pendiente", "Anulada"])
def test_descontar_stock_con_venta_no_completada_conserva_saldos(db, estado):
    actualizar_venta(db, estado=estado)
    rechazar_sin_cambios(db, mensaje="Solo se descuenta stock de ventas Completada")


def test_descontar_stock_con_farmaceutico_inexistente_rechaza_movimiento(db):
    actualizar_venta(db, id_farmaceutico="NO_EXISTE")
    rechazar_sin_cambios(db, mensaje="El farmacéutico de la venta no existe")


def test_descontar_stock_con_sucursal_ajena_al_farmaceutico_rechaza_movimiento(db):
    actualizar_venta(db, id_sucursal="S2")
    rechazar_sin_cambios(db, mensaje="La sucursal de la venta no coincide")


def test_descontar_stock_con_detalle_vacio_rechaza_movimiento(db):
    actualizar_venta(db, detalle=[])
    rechazar_sin_cambios(db, mensaje="La venta no tiene productos")


@pytest.mark.parametrize("cantidad", [0, -1, 1.5, "2", None, True])
def test_descontar_stock_con_cantidad_invalida_rechaza_movimiento(db, cantidad):
    actualizar_venta(db, detalle=detalle(("P1", cantidad)))
    rechazar_sin_cambios(db, mensaje="cantidad inválidos")


def test_descontar_stock_con_producto_sin_lotes_rechaza_movimiento(db):
    actualizar_venta(db, detalle=detalle(("P_INEXISTENTE", 1)))
    rechazar_sin_cambios(db, mensaje="Stock vigente insuficiente para P_INEXISTENTE: faltan 1 unidades")


def test_descontar_stock_con_saldo_total_insuficiente_revierte_descuentos(db):
    # Hay 10 unidades vigentes en S1; 50 vencidas y 100 de S2 no cuentan.
    actualizar_venta(db, detalle=detalle(("P1", 11)))
    rechazar_sin_cambios(db, mensaje="Stock vigente insuficiente para P1: faltan 1 unidades")


def test_descontar_stock_con_segundo_producto_sin_stock_revierte_primer_descuento(db):
    actualizar_venta(db, detalle=detalle(("P1", 4), ("P2", 4)))
    antes = foto(db)
    rechazar_sin_cambios(db, mensaje="Stock vigente insuficiente para P2: faltan 1 unidades")
    imprimir_resultado("rechazo", antes, foto(db))


def test_descontar_stock_con_dos_lotes_vigentes_prioriza_el_mas_proximo(db):
    actualizar_venta(db, detalle=detalle(("P1", 4)))
    antes = foto(db)
    venta = descontar_stock(db, "VTEST", hoy=HOY)
    assert [(a["id_lote"], a["cantidad"]) for a in venta["movimiento_stock"]["asignaciones"]] == [
        ("L_HOY", 2), ("L_PROXIMO", 2)]
    assert db.stock_lotes.find_one({"id_lote": "L_LEJANO"})["unidades"] == 5
    imprimir_resultado("éxito", antes, foto(db))


def test_descontar_stock_con_lote_vencido_conserva_su_saldo(db):
    descontar_stock(db, "VTEST", hoy=HOY)
    assert db.stock_lotes.find_one({"id_lote": "L_VENCIDO"})["unidades"] == 50


def test_descontar_stock_con_lote_que_vence_hoy_descuenta_unidades(db):
    descontar_stock(db, "VTEST", hoy=HOY)
    assert db.stock_lotes.find_one({"id_lote": "L_HOY"})["unidades"] == 1


def test_descontar_stock_con_lote_de_otra_sucursal_conserva_su_saldo(db):
    actualizar_venta(db, detalle=detalle(("P1", 7)))
    descontar_stock(db, "VTEST", hoy=HOY)
    assert db.stock_lotes.find_one({"id_lote": "L_OTRA_SUCURSAL"})["unidades"] == 100


def test_descontar_stock_con_cantidad_igual_al_saldo_agota_lotes_vigentes(db):
    actualizar_venta(db, detalle=detalle(("P1", 10)))
    descontar_stock(db, "VTEST", hoy=HOY)
    saldos = foto(db)["lotes"]
    assert {lote: saldos[lote] for lote in ("L_HOY", "L_PROXIMO", "L_LEJANO")} == {
        "L_HOY": 0, "L_PROXIMO": 0, "L_LEJANO": 0,
    }


def test_descontar_stock_con_producto_repetido_suma_cantidades(db):
    actualizar_venta(db, detalle=detalle(("P1", 3), ("P1", 4)))
    venta = descontar_stock(db, "VTEST", hoy=HOY)
    assert sum(a["cantidad"] for a in venta["movimiento_stock"]["asignaciones"]) == 7


def test_descontar_stock_en_segunda_ejecucion_conserva_saldos(db):
    actualizar_venta(db, detalle=detalle(("P1", 4)))
    descontar_stock(db, "VTEST", hoy=HOY)
    antes = foto(db)
    descontar_stock(db, "VTEST", hoy=HOY)
    despues = foto(db)
    assert antes == despues
    imprimir_resultado("reintento", antes, despues)


@pytest.mark.parametrize("estado", ["aplicado", "historico"])
def test_descontar_stock_con_movimiento_finalizado_conserva_saldos(db, estado):
    actualizar_venta(db, movimiento_stock={"estado": estado})
    antes = foto(db)
    descontar_stock(db, "VTEST", hoy=HOY)
    assert foto(db) == antes


def test_descontar_stock_con_estado_movimiento_desconocido_rechaza_movimiento(db):
    actualizar_venta(db, movimiento_stock={"estado": "desconocido"})
    rechazar_sin_cambios(db, mensaje="Estado de movimiento_stock desconocido")


def test_descontar_stock_con_fallo_en_segundo_lote_revierte_primer_descuento(db, monkeypatch):
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
    rechazar_sin_cambios(db, mensaje="El lote L_PROXIMO cambió durante la venta")
