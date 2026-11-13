"""Escritura de cada entidad de MongoDB en el grafo de Neo4j.

Cada función recibe una transacción de Neo4j y una lista de documentos tal como
salen de MongoDB. La usan tanto la construcción completa (muchos documentos)
como el consumidor de eventos (uno o pocos). Todas son idempotentes:

- MERGE por `id` busca el nodo y solo lo crea si no existe.
- SET pisa las propiedades con el valor actual de MongoDB.
- Las relaciones que tienen un único destino (por ejemplo, la sucursal de un
  farmacéutico) primero borran la relación vieja si apunta a otro nodo y
  después hacen MERGE de la correcta. Así, reprocesar después de un cambio
  nunca deja dos relaciones.

Los nodos vecinos se crean por `id` si todavía no existen; sus propiedades las
completa su propia proyección.
"""

from datetime import datetime


def _fecha(valor):
    """MongoDB guarda fechas como datetime a las 00:00 UTC; el grafo usa Date."""
    return valor.date() if isinstance(valor, datetime) else valor


def _filas(docs, campos):
    """Convierte documentos de Mongo en diccionarios con solo los campos del grafo.

    `campos` mapea nombre_en_grafo -> nombre_en_mongo.
    """
    return [
        {destino: _fecha(doc.get(origen)) for destino, origen in campos.items()}
        for doc in docs
    ]


def proyectar_sucursales(tx, docs):
    filas = _filas(docs, {"id": "id_sucursal", "nombre": "nombre"})
    tx.run(
        """
        UNWIND $filas AS f
        MERGE (s:Sucursal {id: f.id})
        SET s.nombre = f.nombre
        """,
        filas=filas,
    ).consume()


def proyectar_farmaceuticos(tx, docs):
    filas = _filas(docs, {
        "id": "id_farmaceutico", "nombre": "nombre", "apellido": "apellido",
        "activo": "activo", "id_sucursal": "id_sucursal",
    })
    tx.run(
        """
        UNWIND $filas AS f
        MERGE (n:Farmaceutico {id: f.id})
        SET n.nombre = f.nombre, n.apellido = f.apellido, n.activo = f.activo
        WITH n, f
        OPTIONAL MATCH (n)-[viejo:TRABAJA_EN]->(otra:Sucursal)
          WHERE otra.id <> f.id_sucursal
        DELETE viejo
        WITH DISTINCT n, f
        MERGE (s:Sucursal {id: f.id_sucursal})
        MERGE (n)-[:TRABAJA_EN]->(s)
        """,
        filas=filas,
    ).consume()


def proyectar_clientes(tx, docs):
    filas = _filas(docs, {
        "id": "id_cliente", "nombre": "nombre", "apellido": "apellido", "activo": "activo",
    })
    tx.run(
        """
        UNWIND $filas AS f
        MERGE (c:Cliente {id: f.id})
        SET c.nombre = f.nombre, c.apellido = f.apellido, c.activo = f.activo
        """,
        filas=filas,
    ).consume()


def proyectar_recetas(tx, docs):
    filas = _filas(docs, {
        "id": "id_receta", "fecha_emision": "fecha_emision", "estado": "estado",
        "tipo": "tipo", "id_cliente": "id_cliente",
    })
    tx.run(
        """
        UNWIND $filas AS f
        MERGE (r:Receta {id: f.id})
        SET r.fecha_emision = f.fecha_emision, r.estado = f.estado, r.tipo = f.tipo
        WITH r, f
        OPTIONAL MATCH (otro:Cliente)-[viejo:TIENE_RECETA]->(r)
          WHERE otro.id <> f.id_cliente
        DELETE viejo
        WITH DISTINCT r, f
        MERGE (c:Cliente {id: f.id_cliente})
        MERGE (c)-[:TIENE_RECETA]->(r)
        """,
        filas=filas,
    ).consume()


def proyectar_ventas(tx, docs):
    filas = _filas(docs, {
        "id": "id_venta", "fecha": "fecha", "estado": "estado", "tipo": "tipo",
        "total": "total", "id_cliente": "id_cliente",
        "id_farmaceutico": "id_farmaceutico", "id_receta": "id_receta",
    })
    tx.run(
        """
        UNWIND $filas AS f
        MERGE (v:Venta {id: f.id})
        SET v.fecha = f.fecha, v.estado = f.estado, v.tipo = f.tipo, v.total = f.total

        // Cliente que hizo la venta (uno solo)
        WITH v, f
        OPTIONAL MATCH (otro:Cliente)-[viejo:REALIZO]->(v) WHERE otro.id <> f.id_cliente
        DELETE viejo
        WITH DISTINCT v, f
        MERGE (c:Cliente {id: f.id_cliente})
        MERGE (c)-[:REALIZO]->(v)

        // Farmacéutico que la atendió (uno solo)
        WITH v, f
        OPTIONAL MATCH (v)-[viejo:ATENDIDA_POR]->(otro:Farmaceutico)
          WHERE otro.id <> f.id_farmaceutico
        DELETE viejo
        WITH DISTINCT v, f
        MERGE (fa:Farmaceutico {id: f.id_farmaceutico})
        MERGE (v)-[:ATENDIDA_POR]->(fa)

        // Receta usada (opcional, como mucho una)
        WITH v, f
        OPTIONAL MATCH (v)-[viejo:USA_RECETA]->(otra:Receta)
          WHERE f.id_receta IS NULL OR otra.id <> f.id_receta
        DELETE viejo
        WITH DISTINCT v, f
        FOREACH (_ IN CASE WHEN f.id_receta IS NULL THEN [] ELSE [1] END |
          MERGE (r:Receta {id: f.id_receta})
          MERGE (v)-[:USA_RECETA]->(r)
        )
        """,
        filas=filas,
    ).consume()


# entidad del evento -> (colección de Mongo, campo id, función que proyecta)
# El orden es el de dependencias: lo usa construir.py para recorrerlas.
PROYECTORES = {
    "sucursal": ("sucursales", "id_sucursal", proyectar_sucursales),
    "farmaceutico": ("farmaceuticos", "id_farmaceutico", proyectar_farmaceuticos),
    "cliente": ("clientes", "id_cliente", proyectar_clientes),
    "receta": ("recetas", "id_receta", proyectar_recetas),
    "venta": ("ventas", "id_venta", proyectar_ventas),
}
