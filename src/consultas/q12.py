from calendar import monthrange

from .fechas import dia_de_negocio, rango_hasta_hoy


def q12(db, *, hoy=None):
    """Devuelve clientes sin ventas registradas en el último año calendario móvil."""
    hoy = hoy or dia_de_negocio()
    anio_anterior = hoy.year - 1
    dia = min(hoy.day, monthrange(anio_anterior, hoy.month)[1])
    desde = hoy.replace(year=anio_anterior, day=dia)
    return list(db.clientes.aggregate([
        {"$lookup": {
            "from": "ventas",
            "localField": "id_cliente",
            "foreignField": "id_cliente",
            "pipeline": [{"$match": {"fecha": rango_hasta_hoy(desde, hoy)}}, {"$limit": 1}],
            "as": "ventas_recientes",
        }},
        {"$match": {"ventas_recientes.0": {"$exists": False}}},
        {"$unset": "ventas_recientes"},
        {"$sort": {"id_cliente": 1}},
    ]))
