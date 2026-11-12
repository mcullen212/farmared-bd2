from datetime import timedelta

from .fechas import dia_de_negocio, rango_hasta_hoy


def q05(db, *, hoy=None):
    """Devuelve farmacéuticos activos con su conteo en los últimos 60 días."""
    hoy = hoy or dia_de_negocio()
    fechas = rango_hasta_hoy(hoy - timedelta(days=59), hoy)
    return list(db.farmaceuticos.aggregate([
        {"$match": {"activo": True}},
        {"$lookup": {
            "from": "ventas",
            "localField": "id_farmaceutico",
            "foreignField": "id_farmaceutico",
            "pipeline": [
                {"$match": {"fecha": fechas, "estado": {"$ne": "Anulada"}}},
                {"$count": "cantidad"},
            ],
            "as": "conteo",
        }},
        {"$set": {"cantidad_ventas": {"$ifNull": [{"$first": "$conteo.cantidad"}, 0]}}},
        {"$unset": "conteo"},
        {"$sort": {"id_farmaceutico": 1}},
    ]))
