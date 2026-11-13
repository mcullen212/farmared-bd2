"""q04 · Clientes con más de una receta registrada (Neo4j)."""

CONSULTA = """
MATCH (c:Cliente)-[:TIENE_RECETA]->(r:Receta)
WITH c, count(r) AS cantidad_recetas
WHERE cantidad_recetas > 1
RETURN c.id AS id_cliente, c.nombre AS nombre, c.apellido AS apellido, cantidad_recetas
ORDER BY cantidad_recetas DESC, id_cliente
"""


def q04(driver):
    """Devuelve los clientes con más de una receta y cuántas tiene cada uno.

    Motor: Neo4j. Cuenta las relaciones (Cliente)-[:TIENE_RECETA]->(Receta)
    de cada cliente y se queda con los que tienen más de una.

    Devuelve:
        [{id_cliente, nombre, apellido, cantidad_recetas}], de mayor a menor cantidad.
    """
    with driver.session() as session:
        return [r.data() for r in session.run(CONSULTA)]
