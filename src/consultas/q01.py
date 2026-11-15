def q01(db):
    """Devuelve los productos activos con el documento completo de su proveedor."""
    return list(db.productos.aggregate([
        {"$match": {"activo": True}},
        {"$lookup": {
            "from": "proveedores",
            "localField": "id_proveedor",
            "foreignField": "id_proveedor",
            "as": "proveedor",
        }},
        {"$unwind": "$proveedor"},
        {"$sort": {"id_producto": 1}},
    ]))
