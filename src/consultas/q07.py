from .relaciones import relacion


def q07(db):
    """Devuelve hasta cinco productos por unidades vendidas en ventas completadas."""
    return list(db.ventas.aggregate([
        {"$match": {"estado": "Completada"}},
        {"$unwind": "$detalle"},
        {"$group": {"_id": "$detalle.id_producto", "unidades_vendidas": {"$sum": "$detalle.cantidad"}}},
        {"$sort": {"unidades_vendidas": -1, "_id": 1}},
        {"$limit": 5},
        *relacion("productos", "_id", "id_producto", "producto"),
        {"$project": {"_id": 0, "id_producto": "$_id", "producto": 1, "unidades_vendidas": 1}},
    ]))
