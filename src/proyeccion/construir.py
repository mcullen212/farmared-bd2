"""Construye el grafo de Neo4j a partir de los datos actuales de MongoDB.

Uso: python -m src.proyeccion.construir [--reset]

Sin --reset agrega o actualiza lo que falte (correrlo dos veces no duplica nada).
Con --reset borra el grafo entero y lo rearma: el grafo es una copia que se
puede reconstruir en cualquier momento desde MongoDB.
"""

import argparse

from .cypher import PROYECTORES
from .esquema import crear_restricciones

LOTE = 500


def contar(driver):
    """Devuelve la cantidad de nodos por etiqueta y de relaciones por tipo."""
    with driver.session() as session:
        nodos = {
            r["etiqueta"]: r["cantidad"]
            for r in session.run(
                "MATCH (n) RETURN labels(n)[0] AS etiqueta, count(*) AS cantidad"
            )
        }
        relaciones = {
            r["tipo"]: r["cantidad"]
            for r in session.run(
                "MATCH ()-[r]->() RETURN type(r) AS tipo, count(*) AS cantidad"
            )
        }
    return {"nodos": dict(sorted(nodos.items())), "relaciones": dict(sorted(relaciones.items()))}


def construir_grafo(db, driver, *, reset=False):
    """Proyecta todas las entidades del grafo y devuelve los conteos resultantes."""
    if reset:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n").consume()
    crear_restricciones(driver)

    with driver.session() as session:
        for coleccion, campo_id, proyectar in PROYECTORES.values():
            docs = list(db[coleccion].find({}, {"_id": 0}).sort(campo_id, 1))
            for inicio in range(0, len(docs), LOTE):
                session.execute_write(proyectar, docs[inicio:inicio + LOTE])
    return contar(driver)


def main():
    from ..conexion_neo4j import abrir_neo4j_driver, abrir_mongo

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="Borra el grafo antes de construirlo")
    args = parser.parse_args()

    cliente, db = abrir_mongo()
    with cliente, abrir_neo4j_driver() as driver:
        conteos = construir_grafo(db, driver, reset=args.reset)
    for grupo, valores in conteos.items():
        print(f"{grupo}:")
        for nombre, cantidad in valores.items():
            print(f"  {nombre}: {cantidad}")


if __name__ == "__main__":
    main()
