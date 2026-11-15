"""Acceso a las colecciones de FarmaRed con las sesiones nativas de PyMongo."""


class RepositorioMongo:
    """P3 puede pasar session= a find_one, insert_one y update_one.

    El servicio llama a with_transaction y pasa la misma sesión a cada
    operación, incluida la escritura de proyeccion_pendiente.
    """

    def __init__(self, db):
        self.db = db
        self.clientes = db.clientes
        self.sucursales = db.sucursales
        self.ventas = db.ventas
        self.recetas = db.recetas
        self.farmaceuticos = db.farmaceuticos
        self.productos = db.productos
        self.stock_lotes = db.stock_lotes
        self.proyeccion_pendiente = db.proyeccion_pendiente

    def iniciar_sesion(self):
        return self.db.client.start_session()

    def lotes_fefo(self, id_producto, id_sucursal, dia, *, session=None):
        """Busca lotes disponibles desde el día de negocio, expresado a medianoche UTC."""
        return self.stock_lotes.find(
            {
                "id_producto": id_producto,
                "id_sucursal": id_sucursal,
                "vencimiento": {"$gte": dia},
                "unidades": {"$gt": 0},
            },
            session=session,
        ).sort([("vencimiento", 1), ("id_lote", 1)])

    def decrementar_lote(self, id_lote, cantidad, *, session=None):
        """Devuelve True si el saldo alcanzó y se aplicó el decremento."""
        if type(cantidad) is not int or cantidad <= 0:
            raise ValueError("La cantidad debe ser un entero positivo")
        resultado = self.stock_lotes.update_one(
            {"id_lote": id_lote, "unidades": {"$gte": cantidad}},
            {"$inc": {"unidades": -cantidad}},
            session=session,
        )
        return resultado.modified_count == 1
