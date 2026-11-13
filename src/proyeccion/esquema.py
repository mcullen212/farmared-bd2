"""Restricciones de unicidad del grafo de FarmaRed."""

ETIQUETAS = ("Cliente", "Venta", "Receta", "Farmaceutico", "Sucursal")


def crear_restricciones(driver):
    """Crea una restricción única sobre `id` para cada etiqueta (idempotente).

    La restricción funciona como clave primaria: Neo4j rechaza dos nodos con el
    mismo id y crea un índice que acelera los MATCH/MERGE por id.
    """
    with driver.session() as session:
        for etiqueta in ETIQUETAS:
            session.run(
                f"CREATE CONSTRAINT {etiqueta.lower()}_id IF NOT EXISTS "
                f"FOR (n:{etiqueta}) REQUIRE n.id IS UNIQUE"
            ).consume()
