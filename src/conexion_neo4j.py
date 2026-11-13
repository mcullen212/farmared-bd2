"""Conexión a Neo4j a partir de las variables de entorno del docker-compose."""

import os


def abrir_driver():
    """Devuelve un driver de Neo4j configurado con NEO4J_URI, NEO4J_USER y NEO4J_PASSWORD."""
    from neo4j import GraphDatabase

    faltantes = [v for v in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD") if not os.environ.get(v)]
    if faltantes:
        raise SystemExit(f"Definí {', '.join(faltantes)} para conectarte a Neo4j.")
    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )


def abrir_mongo():
    """Devuelve (cliente, db) de MongoDB a partir de MONGODB_URI."""
    from pymongo import MongoClient

    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise SystemExit("Definí MONGODB_URI con el nombre de la base de datos.")
    cliente = MongoClient(uri)
    return cliente, cliente.get_default_database()
