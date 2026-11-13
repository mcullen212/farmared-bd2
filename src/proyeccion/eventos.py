"""Registro de cambios pendientes de proyectar en Neo4j (colección proyeccion_pendiente).

Los servicios que escriben en MongoDB (q13, q14) llaman a registrar_evento con
la MISMA sesión de su transacción: si la transacción se aborta, el evento
tampoco queda. El evento solo dice qué cambió; el consumidor relee los datos
actuales de MongoDB, así que reprocesarlo nunca pisa información más nueva.
"""

from datetime import datetime, timezone

from .cypher import PROYECTORES


def registrar_evento(db, operacion, refs, *, session=None):
    """Inserta un evento pendiente y devuelve su _id.

    Parámetros:
        operacion: texto que identifica qué la originó, p. ej. "q13.alta" o "q14.venta".
        refs: lista de {"entidad": ..., "id": ...}; entidad es una de
              sucursal, farmaceutico, cliente, receta o venta.
        session: sesión de PyMongo de la transacción que hace el cambio.
    """
    if not refs:
        raise ValueError("El evento necesita al menos una referencia")
    for ref in refs:
        if ref.get("entidad") not in PROYECTORES or not ref.get("id"):
            raise ValueError(f"Referencia inválida: {ref}")
    resultado = db.proyeccion_pendiente.insert_one(
        {
            "operacion": operacion,
            "refs": [{"entidad": r["entidad"], "id": r["id"]} for r in refs],
            "estado": "pendiente",
            "intentos": 0,
            "creado": datetime.now(timezone.utc),
            "procesado_en": None,
            "ultimo_error": None,
        },
        session=session,
    )
    return resultado.inserted_id
