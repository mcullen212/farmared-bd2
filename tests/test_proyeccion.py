"""Idempotencia y reintentos de la proyección MongoDB → Neo4j."""

from neo4j import GraphDatabase

from src.proyeccion.construir import construir_grafo, contar
from src.proyeccion.consumidor import procesar_pendientes
from src.proyeccion.eventos import registrar_evento


def test_construir_coincide_con_mongo(entorno):
    db, driver = entorno
    nodos = contar(driver)["nodos"]
    assert nodos["Cliente"] == db.clientes.count_documents({})
    assert nodos["Venta"] == db.ventas.count_documents({})
    assert nodos["Receta"] == db.recetas.count_documents({})
    assert nodos["Farmaceutico"] == db.farmaceuticos.count_documents({})
    assert nodos["Sucursal"] == db.sucursales.count_documents({})
    relaciones = contar(driver)["relaciones"]
    assert relaciones["REALIZO"] == db.ventas.count_documents({})
    assert relaciones["USA_RECETA"] == db.ventas.count_documents({"id_receta": {"$ne": None}})


def test_construir_dos_veces_no_duplica(entorno):
    db, driver = entorno
    antes = contar(driver)
    assert construir_grafo(db, driver) == antes


def test_reprocesar_evento_no_duplica(entorno):
    db, driver = entorno
    antes = contar(driver)
    refs = [{"entidad": "venta", "id": "V001"}, {"entidad": "receta", "id": "RC001"}]
    registrar_evento(db, "test", refs)
    registrar_evento(db, "test", refs)
    assert procesar_pendientes(db, driver) == {"procesados": 2, "fallidos": 0}
    assert contar(driver) == antes


def test_cambio_de_sucursal_reemplaza_la_relacion(entorno):
    db, driver = entorno
    db.farmaceuticos.update_one({"id_farmaceutico": "F001"}, {"$set": {"id_sucursal": "S002"}})
    registrar_evento(db, "test", [{"entidad": "farmaceutico", "id": "F001"}])
    procesar_pendientes(db, driver)
    with driver.session() as session:
        sucursales = session.run(
            "MATCH (:Farmaceutico {id: 'F001'})-[:TRABAJA_EN]->(s) RETURN collect(s.id) AS ids"
        ).single()["ids"]
    assert sucursales == ["S002"]


def test_neo4j_caido_deja_el_evento_pendiente(entorno):
    db, driver = entorno
    db.clientes.update_one({"id_cliente": "C001"}, {"$set": {"activo": False}})
    id_evento = registrar_evento(db, "test", [{"entidad": "cliente", "id": "C001"}])

    caido = GraphDatabase.driver("bolt://127.0.0.1:1", auth=("neo4j", "x"),
                                 connection_timeout=1, max_transaction_retry_time=0)
    with caido:
        assert procesar_pendientes(db, caido) == {"procesados": 0, "fallidos": 1}
    evento = db.proyeccion_pendiente.find_one({"_id": id_evento})
    assert evento["estado"] == "pendiente"
    assert evento["intentos"] == 1
    assert evento["ultimo_error"]

    # Con Neo4j disponible, el reintento lo procesa.
    assert procesar_pendientes(db, driver) == {"procesados": 1, "fallidos": 0}
    with driver.session() as session:
        assert session.run("MATCH (c:Cliente {id: 'C001'}) RETURN c.activo AS a").single()["a"] is False


def test_referencia_inexistente_queda_con_error(entorno):
    db, driver = entorno
    registrar_evento(db, "test", [{"entidad": "cliente", "id": "C999"}])
    assert procesar_pendientes(db, driver) == {"procesados": 0, "fallidos": 1}
    evento = db.proyeccion_pendiente.find_one({"refs.id": "C999"})
    assert "C999" in evento["ultimo_error"]
