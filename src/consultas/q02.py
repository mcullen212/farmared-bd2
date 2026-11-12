from .relaciones import relacion


def q02(db):
    """Devuelve las ventas pendientes con su farmacéutico y sucursal."""
    return list(db.ventas.aggregate([
        {"$match": {"estado": "Pendiente"}},
        *relacion("farmaceuticos", "id_farmaceutico", "id_farmaceutico", "farmaceutico"),
        *relacion("sucursales", "id_sucursal", "id_sucursal", "sucursal"),
        {"$sort": {"id_venta": 1}},
    ]))
