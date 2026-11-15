"""Procesa los eventos de proyeccion_pendiente y actualiza Neo4j.

Uso: python -m src.proyeccion.consumidor [--limite N]

Para cada evento pendiente (del más viejo al más nuevo):
  1. relee de MongoDB el estado ACTUAL de cada registro referenciado,
  2. lo proyecta en Neo4j en una sola transacción (MERGE, idempotente),
  3. recién entonces marca el evento como procesado.
Si algo falla, el evento queda pendiente con intentos + 1 y el error guardado,
para reintentarlo en la próxima corrida. Si Neo4j no responde, se corta la
corrida sin tocar los eventos siguientes.

Si un evento falla MAX_INTENTOS veces por un error que no es de conexión
(por ejemplo, apunta a un registro que no existe en MongoDB), pasa a
estado "error" y deja de reintentarse. Para volver a intentarlo, una vez
arreglado el problema, hay que ponerlo otra vez en "pendiente" con 0 intentos:
  db.proyeccion_pendiente.updateOne({_id: ...}, {$set: {estado: "pendiente", intentos: 0}})
Que Neo4j esté caído no cuenta para pasar a "error": eso no es culpa del evento.

Supone un único consumidor a la vez.
"""

import argparse
from datetime import datetime, timezone

from .cypher import PROYECTORES

MAX_INTENTOS = 5


class ReferenciaInexistente(Exception):
    pass


def _leer_documentos(db, refs):
    """Agrupa por entidad los documentos actuales de MongoDB, en orden de dependencias."""
    por_entidad = {}
    for ref in refs:
        coleccion, campo_id, _ = PROYECTORES[ref["entidad"]]
        doc = db[coleccion].find_one({campo_id: ref["id"]}, {"_id": 0})
        if doc is None:
            raise ReferenciaInexistente(f"No existe {ref['entidad']} {ref['id']} en MongoDB")
        por_entidad.setdefault(ref["entidad"], []).append(doc)
    return [(PROYECTORES[e][2], por_entidad[e]) for e in PROYECTORES if e in por_entidad]


def _proyectar_todo(tx, lotes):
    for proyectar, docs in lotes:
        proyectar(tx, docs)


def procesar_pendientes(db, driver, limite=None):
    """Procesa eventos pendientes y devuelve {"procesados": n, "fallidos": m}."""
    from neo4j.exceptions import ServiceUnavailable, SessionExpired

    pendientes = db.proyeccion_pendiente.find({"estado": "pendiente"}).sort([("creado", 1), ("_id", 1)])
    if limite is not None:
        pendientes = pendientes.limit(limite)

    resumen = {"procesados": 0, "fallidos": 0}
    for evento in pendientes:
        try:
            lotes = _leer_documentos(db, evento["refs"])
            with driver.session() as session:
                session.execute_write(_proyectar_todo, lotes)
        except Exception as error:  # se guarda cualquier error para reintentar
            neo4j_caido = isinstance(error, (ServiceUnavailable, SessionExpired))
            intentos = evento.get("intentos", 0) + 1
            cambios = {"ultimo_error": f"{type(error).__name__}: {error}"}
            if not neo4j_caido and intentos >= MAX_INTENTOS:
                cambios["estado"] = "error"  # no se reintenta más hasta revisarlo a mano
            db.proyeccion_pendiente.update_one(
                {"_id": evento["_id"]}, {"$inc": {"intentos": 1}, "$set": cambios}
            )
            resumen["fallidos"] += 1
            if neo4j_caido:
                break  # Neo4j caído: no tiene sentido seguir con los demás
            continue

        db.proyeccion_pendiente.update_one(
            {"_id": evento["_id"]},
            {"$set": {"estado": "procesado", "procesado_en": datetime.now(timezone.utc),
                      "ultimo_error": None}},
        )
        resumen["procesados"] += 1
    return resumen


def main():
    from ..conexion_neo4j import abrir_neo4j_driver, abrir_mongo

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limite", type=int, help="Máximo de eventos a procesar")
    args = parser.parse_args()

    cliente, db = abrir_mongo()
    with cliente, abrir_neo4j_driver() as driver:
        resumen = procesar_pendientes(db, driver, limite=args.limite)
    print(f"procesados: {resumen['procesados']}, fallidos: {resumen['fallidos']}")


if __name__ == "__main__":
    main()
