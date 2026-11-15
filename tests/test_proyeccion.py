"""Idempotencia y reintentos de la proyección MongoDB → Neo4j."""

import pytest
from neo4j import GraphDatabase

from src.proyeccion.construir import construir_grafo, contar
from src.proyeccion.consumidor import MAX_INTENTOS, procesar_pendientes
from src.proyeccion.eventos import registrar_evento


def test_construir_grafo_con_csv_cargados_proyecta_nodos_y_relaciones(grafo_pruebas, base_con_csv):
    db = base_con_csv

    conteos = construir_grafo(db, grafo_pruebas)

    assert contar(grafo_pruebas) == conteos
    nodos = conteos["nodos"]
    assert nodos["Cliente"] == db.clientes.count_documents({})
    assert nodos["Venta"] == db.ventas.count_documents({})
    assert nodos["Receta"] == db.recetas.count_documents({})
    assert nodos["Farmaceutico"] == db.farmaceuticos.count_documents({})
    assert nodos["Sucursal"] == db.sucursales.count_documents({})
    relaciones = conteos["relaciones"]
    assert relaciones["REALIZO"] == db.ventas.count_documents({})
    assert relaciones["USA_RECETA"] == db.ventas.count_documents({"id_receta": {"$ne": None}})


def test_construir_grafo_con_proyeccion_existente_conserva_conteos(entorno):
    db, driver = entorno
    antes = contar(driver)
    assert construir_grafo(db, driver) == antes


def test_procesar_pendientes_con_eventos_duplicados_conserva_conteos(entorno):
    db, driver = entorno
    antes = contar(driver)
    refs = [{"entidad": "venta", "id": "V001"}, {"entidad": "receta", "id": "RC001"}]
    registrar_evento(db, "test", refs)
    registrar_evento(db, "test", refs)
    assert procesar_pendientes(db, driver) == {"procesados": 2, "fallidos": 0}
    assert contar(driver) == antes


def test_procesar_pendientes_con_cambio_de_sucursal_reemplaza_relacion(entorno):
    db, driver = entorno
    db.farmaceuticos.update_one({"id_farmaceutico": "F001"}, {"$set": {"id_sucursal": "S002"}})
    registrar_evento(db, "test", [{"entidad": "farmaceutico", "id": "F001"}])
    procesar_pendientes(db, driver)
    with driver.session() as session:
        sucursales = session.run(
            "MATCH (:Farmaceutico {id: 'F001'})-[:TRABAJA_EN]->(s) RETURN collect(s.id) AS ids"
        ).single()["ids"]
    assert sucursales == ["S002"]


@pytest.mark.parametrize("intentos", [0, MAX_INTENTOS], ids=["primer-intento", "sobre-el-limite"])
def test_procesar_pendientes_con_neo4j_caido_conserva_evento_pendiente(entorno, intentos):
    db, _ = entorno
    id_evento = registrar_evento(db, "test", [{"entidad": "cliente", "id": "C001"}])
    db.proyeccion_pendiente.update_one({"_id": id_evento}, {"$set": {"intentos": intentos}})

    with GraphDatabase.driver(
        "bolt://127.0.0.1:1", auth=("neo4j", "x"),
        connection_timeout=1, max_transaction_retry_time=0,
    ) as caido:
        resultado = procesar_pendientes(db, caido)

    assert resultado == {"procesados": 0, "fallidos": 1}
    evento = db.proyeccion_pendiente.find_one({"_id": id_evento})
    assert evento["estado"] == "pendiente"
    assert evento["intentos"] == intentos + 1
    assert "ServiceUnavailable" in evento["ultimo_error"]


def test_procesar_pendientes_con_evento_reintentable_proyecta_cambio(entorno):
    db, driver = entorno
    db.clientes.update_one({"id_cliente": "C001"}, {"$set": {"activo": False}})
    id_evento = registrar_evento(db, "test", [{"entidad": "cliente", "id": "C001"}])
    db.proyeccion_pendiente.update_one(
        {"_id": id_evento}, {"$set": {"intentos": 1, "ultimo_error": "ServiceUnavailable"}},
    )

    resultado = procesar_pendientes(db, driver)

    assert resultado == {"procesados": 1, "fallidos": 0}
    evento = db.proyeccion_pendiente.find_one({"_id": id_evento})
    assert evento["estado"] == "procesado"
    assert evento["ultimo_error"] is None
    with driver.session() as session:
        nodo = session.run("MATCH (c:Cliente {id: 'C001'}) RETURN c.activo AS activo").single()
    assert nodo["activo"] is False


@pytest.mark.parametrize(
    "intentos, estado_esperado",
    [(0, "pendiente"), (MAX_INTENTOS - 1, "error")],
    ids=["primer-intento", "ultimo-intento"],
)
def test_procesar_pendientes_con_referencia_inexistente_registra_fallo(entorno, intentos, estado_esperado):
    db, driver = entorno
    id_evento = registrar_evento(db, "test", [{"entidad": "cliente", "id": "C999"}])
    db.proyeccion_pendiente.update_one({"_id": id_evento}, {"$set": {"intentos": intentos}})

    resultado = procesar_pendientes(db, driver)

    assert resultado == {"procesados": 0, "fallidos": 1}
    evento = db.proyeccion_pendiente.find_one({"_id": id_evento})
    assert evento["estado"] == estado_esperado
    assert evento["intentos"] == intentos + 1
    assert "No existe cliente C999 en MongoDB" in evento["ultimo_error"]


def test_procesar_pendientes_con_evento_en_error_conserva_evento(entorno):
    db, driver = entorno
    id_evento = registrar_evento(db, "test", [{"entidad": "cliente", "id": "C999"}])
    filtro = {"_id": id_evento}
    db.proyeccion_pendiente.update_one(filtro, {"$set": {"estado": "error", "intentos": MAX_INTENTOS}})
    antes = db.proyeccion_pendiente.find_one(filtro)

    resultado = procesar_pendientes(db, driver)

    assert resultado == {"procesados": 0, "fallidos": 0}
    assert db.proyeccion_pendiente.find_one(filtro) == antes
