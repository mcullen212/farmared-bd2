"""Consultas de P2: q03, q04, q10 (Neo4j), q06 y q13 (MongoDB)."""

from datetime import date

import pytest

from src.consultas.q03 import q03
from src.consultas.q04 import q04
from src.consultas.q06 import q06
from src.consultas.q10 import q10
from src.consultas.q13 import crear_cliente, dar_de_baja_cliente, modificar_cliente
from src.proyeccion.consumidor import procesar_pendientes


def test_q04_clientes_con_mas_de_una_receta(entorno):
    _, driver = entorno
    resultado = {r["id_cliente"]: r["cantidad_recetas"] for r in q04(driver)}
    for id_cliente in ("C001", "C002", "C006"):
        assert resultado[id_cliente] >= 2
    assert all(cantidad > 1 for cantidad in resultado.values())


def test_q10_incluye_clientes_de_farmaceutico_inactivo(entorno):
    _, driver = entorno
    ids = [r["id_cliente"] for r in q10(driver, "S002")]
    assert {"C001", "C004"} <= set(ids)
    assert len(ids) == len(set(ids))


def test_q10_sucursal_inexistente(entorno):
    with pytest.raises(LookupError):
        q10(entorno[1], "S999")


def test_q03_historial_ordenado(entorno):
    _, driver = entorno
    resultado = q03(driver, "C001")
    historial = resultado["historial"]
    assert resultado["cliente"]["id"] == "C001"
    assert {"venta", "receta"} <= {item["evento"] for item in historial}
    fechas = [item["fecha"] for item in historial]
    assert fechas == sorted(fechas)


def test_q06_dispensas_atrasadas(entorno):
    db, _ = entorno
    resultado = q06(db, hoy=date(2026, 10, 13))
    assert resultado, "los CSV tienen tratamientos con la dispensa atrasada al 13/10/2026"
    for receta in resultado:
        assert receta["tipo"] == "Tratamiento prolongado"
        assert receta["estado"] == "Vigente"
        assert receta["proxima_dispensa"].date() < date(2026, 10, 13)
        assert receta["cliente"]["id_cliente"] == receta["id_cliente"]


def test_q13_abm_completo(entorno):
    db, driver = entorno
    nuevo = crear_cliente(db, {"nombre": "Ana", "apellido": "Gil", "dni": "40111222",
                               "obra_social": "OSDE", "nro_afiliado": "OS-1"})
    assert nuevo["activo"] is True

    with pytest.raises(ValueError, match="DNI"):
        crear_cliente(db, {"nombre": "Otra", "apellido": "Persona", "dni": "40111222"})
    assert db.clientes.count_documents({"dni": "40111222"}) == 1

    with pytest.raises(ValueError):
        modificar_cliente(db, nuevo["id_cliente"], {"dni": "1"})
    modificado = modificar_cliente(db, nuevo["id_cliente"], {"obra_social": "Sin cobertura"})
    assert modificado["nro_afiliado"] is None

    dar_de_baja_cliente(db, nuevo["id_cliente"])
    assert procesar_pendientes(db, driver)["fallidos"] == 0
    assert q03(driver, nuevo["id_cliente"])["cliente"]["activo"] is False


def test_q13_modificar_inexistente(entorno):
    with pytest.raises(LookupError):
        modificar_cliente(entorno[0], "C999", {"email": "x@example.com"})
