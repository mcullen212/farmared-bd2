"""Fixtures de integración: necesitan MongoDB (replica set) y Neo4j corriendo.

Usan la base `farmared_demo` de MongoDB (la única que el loader permite
reiniciar) y el grafo de Neo4j, que se borra y se reconstruye en cada test.
Después de correr los tests hay que reconstruir el grafo de `farmared` con
`python -m src.proyeccion.construir --reset`.
"""

import os

import pytest

pytest.importorskip("neo4j")
pytest.importorskip("pymongo")


@pytest.fixture(scope="session")
def conexiones():
    faltantes = [v for v in ("MONGODB_URI", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")
                 if not os.environ.get(v)]
    if faltantes:
        pytest.skip(f"Faltan variables de entorno: {faltantes}")
    from pymongo import MongoClient

    from src.conexion_neo4j import abrir_driver

    cliente = MongoClient(os.environ["MONGODB_URI"])
    driver = abrir_driver()
    yield cliente["farmared_demo"], driver
    driver.close()
    cliente.close()


@pytest.fixture(scope="session")
def registros():
    from src.carga_mongo import preparar_datos

    return preparar_datos()


@pytest.fixture
def entorno(conexiones, registros):
    """Mongo recién cargado desde los CSV y el grafo reconstruido desde cero."""
    import copy

    from src.carga_mongo import cargar
    from src.proyeccion.construir import construir_grafo

    db, driver = conexiones
    cargar(db, copy.deepcopy(registros), reiniciar_demo=True)
    construir_grafo(db, driver, reset=True)
    return db, driver
