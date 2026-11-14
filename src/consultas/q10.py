"""q10 · Clientes atendidos en una sucursal (Neo4j)."""

SUCURSAL = "MATCH (s:Sucursal {id: $id_sucursal}) RETURN s.id AS id"

CONSULTA = """
MATCH (s:Sucursal {id: $id_sucursal})<-[:TRABAJA_EN]-(f:Farmaceutico)
      <-[:ATENDIDA_POR]-(v:Venta)<-[:REALIZO]-(c:Cliente)
RETURN DISTINCT c.id AS id_cliente, c.nombre AS nombre, c.apellido AS apellido,
       c.activo AS activo
ORDER BY id_cliente
"""


def q10(driver, id_sucursal):
    """Devuelve los clientes distintos atendidos en una sucursal.

    Motor: Neo4j. Recorre Sucursal <-TRABAJA_EN- Farmacéutico <-ATENDIDA_POR-
    Venta <-REALIZO- Cliente. No filtra por el estado del farmacéutico: cuenta
    las ventas de farmacéuticos activos e inactivos.

    Parámetros:
        driver: driver de Neo4j.
        id_sucursal: id de la sucursal, p. ej. "S002".

    Devuelve:
        [{id_cliente, nombre, apellido, activo}] ordenados por id.

    Lanza LookupError si la sucursal no existe en el grafo.
    """
    with driver.session() as session:
        if session.run(SUCURSAL, id_sucursal=id_sucursal).single() is None:
            raise LookupError(f"No existe la sucursal {id_sucursal}")
        return [r.data() for r in session.run(CONSULTA, id_sucursal=id_sucursal)]
    return None
