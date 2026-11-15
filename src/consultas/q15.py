"""q15 · Descuento atómico de stock de una venta completada (MongoDB).

Parámetros: db, id_venta, hoy (fecha de negocio opcional), session (sesión
transaccional opcional). Devuelve la venta con movimiento_stock aplicado.
Si session no se proporciona, se abre una transacción propia, q14 le pasa la
suya. No proyecta el stock a Neo4j.
"""

import argparse
from datetime import date, datetime, time, timezone

from bson import json_util

from ..repositorio_mongo import RepositorioMongo
from .fechas import dia_de_negocio


def _descontar(db, id_venta, hoy, session):
    repo = RepositorioMongo(db)
    venta = db.ventas.find_one({"id_venta": id_venta}, session=session)
    if venta is None:
        raise LookupError(f"No existe la venta {id_venta}")
    if venta.get("estado") != "Completada":
        raise ValueError("Solo se descuenta stock de ventas Completada")

    movimiento = venta.get("movimiento_stock") or {}
    if movimiento.get("estado") in {"aplicado", "historico"}:
        return venta  # Idempotencia: nunca descontar dos veces.
    if movimiento.get("estado") != "sin_aplicar":
        raise ValueError("Estado de movimiento_stock desconocido o no disponible")

    farmaceutico = db.farmaceuticos.find_one(
        {"id_farmaceutico": venta["id_farmaceutico"]}, session=session
    )
    if farmaceutico is None:
        raise ValueError("El farmacéutico de la venta no existe")
    sucursal = farmaceutico["id_sucursal"]
    if venta.get("id_sucursal") != sucursal:
        raise ValueError("La sucursal de la venta no coincide con el farmacéutico")
    if not venta.get("detalle"):
        raise ValueError("La venta no tiene productos")

    cantidades = {}
    for item in venta["detalle"]:
        producto = item.get("id_producto")
        cantidad = item.get("cantidad")
        if not producto or type(cantidad) is not int or cantidad <= 0:
            raise ValueError("El detalle contiene un producto o cantidad inválidos")
        cantidades[producto] = cantidades.get(producto, 0) + cantidad

    dia = datetime.combine(hoy, time.min, timezone.utc)
    asignaciones = []
    for producto, cantidad in cantidades.items():
        restante = cantidad
        for lote in repo.lotes_fefo(producto, sucursal, dia, session=session):
            tomar = min(restante, lote["unidades"])
            if tomar <= 0:
                continue
            if not repo.decrementar_lote(lote["id_lote"], tomar, session=session):
                raise ValueError(f"El lote {lote['id_lote']} cambió durante la venta")
            asignaciones.append({"id_producto": producto, "id_lote": lote["id_lote"],
                                  "cantidad": tomar})
            restante -= tomar
            if restante == 0:
                break
        if restante:
            raise ValueError(f"Stock vigente insuficiente para {producto}: faltan {restante} unidades")

    resultado = db.ventas.update_one(
        {"id_venta": id_venta, "movimiento_stock.estado": "sin_aplicar"},
        {"$set": {"movimiento_stock": {"estado": "aplicado", "asignaciones": asignaciones}}},
        session=session,
    )
    if resultado.modified_count != 1:
        raise ValueError("No se pudo marcar el descuento de stock. Operación abortada")
    return db.ventas.find_one({"id_venta": id_venta}, session=session)


def descontar_stock(db, id_venta, *, hoy=None, session=None):
    """Aplica FEFO (vencimiento >= hoy) sin lotes vencidos ni saldos negativos.

    Un fallo en cualquier producto aborta TODOS los descuentos. Las ventas
    históricas importadas y las ya aplicadas se reconocen sin duplicar cargos.
    """
    hoy = hoy or dia_de_negocio()
    if isinstance(hoy, datetime) or not isinstance(hoy, date):
        raise ValueError("hoy debe ser una fecha (date)")
    if session is not None:
        return _descontar(db, id_venta, hoy, session)
    with db.client.start_session() as nueva_sesion:
        return nueva_sesion.with_transaction(lambda s: _descontar(db, id_venta, hoy, s))


q15 = descontar_stock


def main():
    from ..conexion_neo4j import abrir_mongo

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id_venta")
    parser.add_argument("--hoy", type=date.fromisoformat, help="Fecha para pruebas, AAAA-MM-DD")
    args = parser.parse_args()
    cliente, db = abrir_mongo()
    with cliente:
        resultado = descontar_stock(db, args.id_venta, hoy=args.hoy)
    resultado.pop("_id", None)
    print(json_util.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
