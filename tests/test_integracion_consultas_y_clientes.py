"""Integración de consultas en MongoDB y Neo4j y del ABM de clientes."""

from datetime import date, datetime

import pytest

from src.consultas.q03 import q03
from src.consultas.q04 import q04
from src.consultas.q06 import q06
from src.consultas.q08 import q08
from src.consultas.q10 import q10
from src.consultas.q11 import crear_vista_ingresos, q11
from src.consultas.q13 import crear_cliente, dar_de_baja_cliente, modificar_cliente
from src.proyeccion.consumidor import procesar_pendientes


def test_q04_con_recetas_de_varios_clientes_devuelve_quienes_tienen_mas_de_una(entorno):
    _, driver = entorno

    resultado = q04(driver)

    assert [(r["id_cliente"], r["cantidad_recetas"]) for r in resultado] == [
        ("C001", 2), ("C002", 2), ("C006", 2), ("C101", 2),
    ]


def test_q10_en_sucursal_con_farmaceutico_inactivo_incluye_sus_clientes(entorno):
    _, driver = entorno

    resultado = q10(driver, "S002")

    assert [r["id_cliente"] for r in resultado] == ["C001", "C004"]


def test_q10_con_sucursal_inexistente_lanza_lookup_error(entorno):
    with pytest.raises(LookupError, match="No existe la sucursal S999"):
        q10(entorno[1], "S999")


def test_q03_con_ventas_y_recetas_devuelve_historial_ordenado(entorno):
    _, driver = entorno
    resultado = q03(driver, "C001")
    historial = resultado["historial"]
    assert resultado["cliente"]["id"] == "C001"
    assert {"venta", "receta"} <= {item["evento"] for item in historial}
    fechas = [item["fecha"] for item in historial]
    assert fechas == sorted(fechas)


def test_q03_con_cliente_sin_movimientos_devuelve_historial_vacio(entorno):
    _, driver = entorno
    with driver.session() as session:
        session.run("CREATE (:Cliente {id: 'C-SIN-MOVIMIENTOS'})").consume()

    resultado = q03(driver, "C-SIN-MOVIMIENTOS")

    assert resultado["cliente"]["id"] == "C-SIN-MOVIMIENTOS"
    assert resultado["historial"] == []


def test_q06_con_dispensas_alrededor_del_corte_devuelve_solo_atrasadas_en_orden(base_mongo):
    base_mongo.clientes.insert_one({"id_cliente": "C1", "nombre": "Ana"})
    receta = {"id_cliente": "C1", "estado": "Vigente", "tipo": "Tratamiento prolongado"}
    ayer = datetime(2026, 10, 12)
    base_mongo.recetas.insert_many([
        {**receta, "id_receta": "R3", "proxima_dispensa": ayer},
        {**receta, "id_receta": "R2", "proxima_dispensa": ayer},
        {**receta, "id_receta": "R1", "proxima_dispensa": datetime(2026, 10, 11)},
        {**receta, "id_receta": "R4", "proxima_dispensa": datetime(2026, 10, 13)},
        {**receta, "id_receta": "R5", "proxima_dispensa": ayer, "estado": "Completada"},
        {**receta, "id_receta": "R6", "proxima_dispensa": ayer, "tipo": "Simple"},
    ])

    resultado = q06(base_mongo, hoy=date(2026, 10, 13))

    assert [r["id_receta"] for r in resultado] == ["R1", "R2", "R3"]
    assert [r["cliente"]["nombre"] for r in resultado] == ["Ana", "Ana", "Ana"]


def test_q08_con_lotes_de_49_y_50_unidades_devuelve_solo_los_menores_ordenados(base_mongo):
    base_mongo.proveedores.insert_one({"id_proveedor": "PR1"})
    base_mongo.productos.insert_one({"id_producto": "P1", "id_proveedor": "PR1"})
    base_mongo.sucursales.insert_one({"id_sucursal": "S1"})
    lote = {"id_producto": "P1", "id_sucursal": "S1"}
    base_mongo.stock_lotes.insert_many([
        {**lote, "id_lote": "L2", "unidades": 49},
        {**lote, "id_lote": "L3", "unidades": 50},
        {**lote, "id_lote": "L1", "unidades": 12},
    ])

    resultado = q08(base_mongo)

    assert [(r["id_lote"], r["unidades"]) for r in resultado] == [("L1", 12), ("L2", 49)]
    assert resultado[0]["producto"]["id_producto"] == "P1"
    assert resultado[0]["sucursal"]["id_sucursal"] == "S1"
    assert resultado[0]["proveedor"]["id_proveedor"] == "PR1"


def test_crear_vista_con_vista_equivalente_conserva_ingresos(base_mongo):
    base_mongo.ventas.insert_many([
        {"id_farmaceutico": "F1", "fecha": datetime(2026, 10, 12), "estado": "Completada", "total": 250},
        {"id_farmaceutico": "F1", "fecha": datetime(2026, 10, 13), "estado": "Completada", "total": 150},
        {"id_farmaceutico": "F1", "fecha": datetime(2026, 10, 14), "estado": "Anulada", "total": 999},
        {"id_farmaceutico": "F1", "fecha": datetime(2026, 11, 1), "estado": "Completada", "total": 750},
    ])
    crear_vista_ingresos(base_mongo)

    crear_vista_ingresos(base_mongo)

    resultado = q11(base_mongo, hoy=date(2026, 10, 15))
    assert [(r["id_farmaceutico"], r["ingresos_totales"]) for r in resultado] == [("F1", 400)]


def test_procesar_pendientes_tras_abm_proyecta_cliente_inactivo(entorno):
    db, driver = entorno
    nuevo = crear_cliente(db, {"nombre": "Ana", "apellido": "Gil", "dni": "40111222",
                               "obra_social": "OSDE", "nro_afiliado": "OS-1"})
    id_cliente = nuevo["id_cliente"]
    modificado = modificar_cliente(db, id_cliente, {"obra_social": "Sin cobertura"})
    dar_de_baja_cliente(db, id_cliente)

    resultado = procesar_pendientes(db, driver)

    assert resultado == {"procesados": 3, "fallidos": 0}
    assert modificado["nro_afiliado"] is None
    assert q03(driver, id_cliente)["cliente"] == {
        "id": id_cliente, "nombre": "Ana", "apellido": "Gil", "activo": False,
    }
