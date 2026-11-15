"""q06 · Tratamientos prolongados con la dispensa atrasada (MongoDB)."""

from datetime import datetime, time, timezone

from .fechas import dia_de_negocio
from .relaciones import relacion


def q06(db, *, hoy=None):
    """Devuelve recetas de tratamiento prolongado vigentes con la próxima dispensa vencida.

    Motor: MongoDB. Filtra recetas con tipo 'Tratamiento prolongado', estado
    'Vigente' y proxima_dispensa anterior a hoy; incorpora el cliente con $lookup.

    Parámetros:
        db: base de MongoDB.
        hoy: fecha de referencia (date). Por defecto, el día de negocio en Buenos Aires.

    Devuelve:
        Lista de recetas con el documento del cliente en `cliente`, ordenadas por
        proxima_dispensa e id_receta.
    """
    hoy = hoy or dia_de_negocio()
    return list(db.recetas.aggregate([
        {"$match": {
            "tipo": "Tratamiento prolongado",
            "estado": "Vigente",
            "proxima_dispensa": {"$lt": datetime.combine(hoy, time.min, timezone.utc)},
        }},
        *relacion("clientes", "id_cliente", "id_cliente", "cliente"),
        {"$unset": ["_id", "cliente._id"]},
        {"$sort": {"proxima_dispensa": 1, "id_receta": 1}},
    ]))
