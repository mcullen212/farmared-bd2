"""q03 · Historial completo de un cliente (Neo4j)."""

CLIENTE = """
MATCH (c:Cliente {id: $id_cliente})
RETURN c {.id, .nombre, .apellido, .activo} AS cliente
"""

HISTORIAL = """
MATCH (c:Cliente {id: $id_cliente})
CALL (c) {
  MATCH (c)-[:REALIZO]->(v:Venta)
  OPTIONAL MATCH (v)-[:ATENDIDA_POR]->(f:Farmaceutico)
  OPTIONAL MATCH (f)-[:TRABAJA_EN]->(s:Sucursal)
  OPTIONAL MATCH (v)-[:USA_RECETA]->(r:Receta)
  RETURN {
    evento: "venta", id: v.id, fecha: v.fecha, estado: v.estado, tipo: v.tipo,
    total: v.total, id_receta: r.id,
    farmaceutico: f.nombre + " " + f.apellido, sucursal: s.nombre
  } AS item
  UNION
  MATCH (c)-[:TIENE_RECETA]->(r:Receta)
  RETURN {
    evento: "receta", id: r.id, fecha: r.fecha_emision, estado: r.estado, tipo: r.tipo
  } AS item
}
RETURN item
ORDER BY item.fecha, item.evento, item.id
"""

CAMPOS = ("fecha", "evento", "id", "tipo", "estado", "total", "id_receta",
          "farmaceutico", "sucursal")


def q03(driver, id_cliente):
    """Devuelve las ventas y recetas de un cliente ordenadas cronológicamente.

    Motor: Neo4j. Recorre (Cliente)-[:REALIZO]->(Venta) y
    (Cliente)-[:TIENE_RECETA]->(Receta); para cada venta suma el farmacéutico,
    su sucursal y la receta usada, si hay.

    Parámetros:
        driver: driver de Neo4j.
        id_cliente: id del cliente, p. ej. "C001".

    Devuelve:
        {"cliente": {id, nombre, apellido, activo},
         "historial": [{evento: "venta"|"receta", id, fecha, estado, tipo, ...}]}
        La fecha es la de la venta o la de emisión de la receta (datetime.date).

    Lanza LookupError si el cliente no existe en el grafo.
    """
    with driver.session() as session:
        registro = session.run(CLIENTE, id_cliente=id_cliente).single()
        if registro is None:
            raise LookupError(f"No existe el cliente {id_cliente}")
        historial = []
        for r in session.run(HISTORIAL, id_cliente=id_cliente):
            item = r["item"]
            item["fecha"] = item["fecha"].to_native()  # neo4j Date -> datetime.date
            historial.append({k: item[k] for k in CAMPOS if k in item})
    return {"cliente": registro["cliente"], "historial": historial}
