from .relaciones import relacion


def q08(db):
    """Devuelve los lotes de menos de 50 unidades con sus referencias."""
    return list(db.stock_lotes.aggregate([
        {"$match": {"unidades": {"$lt": 50}}},
        *relacion("productos", "id_producto", "id_producto", "producto"),
        *relacion("sucursales", "id_sucursal", "id_sucursal", "sucursal"),
        *relacion("proveedores", "producto.id_proveedor", "id_proveedor", "proveedor"),
        {"$sort": {"id_lote": 1}},
    ]))
