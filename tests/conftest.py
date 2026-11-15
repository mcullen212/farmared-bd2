"""Conexiones compartidas y datos descartables para las pruebas de integración."""

import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest


@pytest.fixture(scope="session")
def cliente_mongo():
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        pytest.skip("Se requiere MONGODB_URI (MongoDB replica set)")
    from pymongo import MongoClient

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as cliente:
        cliente.admin.command("ping")
        yield cliente


@pytest.fixture
def base_mongo(cliente_mongo):
    base = cliente_mongo[f"farmared_test_{uuid4().hex}"]
    try:
        yield base
    finally:
        cliente_mongo.drop_database(base.name)


@pytest.fixture(scope="session")
def driver_pruebas():
    uri = os.environ.get("NEO4J_TEST_URI")
    if not uri:
        pytest.skip("Se requiere NEO4J_TEST_URI (instancia descartable de Neo4j)")
    uri_habitual = os.environ.get("NEO4J_URI", "")
    destino = urlsplit(uri)
    habitual = urlsplit(uri_habitual)
    if (destino.hostname, destino.port or 7687) == (habitual.hostname, habitual.port or 7687):
        pytest.fail("NEO4J_TEST_URI debe apuntar a una instancia distinta de NEO4J_URI")

    from neo4j import GraphDatabase

    auth = (
        os.environ.get("NEO4J_TEST_USER", "neo4j"),
        os.environ.get("NEO4J_TEST_PASSWORD", "farmared-test"),
    )
    with GraphDatabase.driver(uri, auth=auth) as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            if session.run("MATCH (n) RETURN n LIMIT 1").single() is not None:
                pytest.fail("La instancia de Neo4j para pruebas debe estar vacía")
        yield driver


@pytest.fixture
def base_con_csv(base_mongo):
    from src.carga_mongo import cargar, preparar_datos

    cargar(base_mongo, preparar_datos())
    return base_mongo


@pytest.fixture
def grafo_pruebas(driver_pruebas):
    try:
        yield driver_pruebas
    finally:
        with driver_pruebas.session() as session:
            session.run("MATCH (n) DETACH DELETE n").consume()


@pytest.fixture
def entorno(grafo_pruebas, base_con_csv):
    """Carga los CSV en una base temporal y proyecta sus datos al grafo de pruebas."""
    from src.proyeccion.construir import construir_grafo

    construir_grafo(base_con_csv, grafo_pruebas)
    return base_con_csv, grafo_pruebas
