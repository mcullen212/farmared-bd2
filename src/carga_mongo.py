"""Importa los CSV de FarmaRed en un replica set MongoDB."""

import argparse
import csv
import os
from collections import defaultdict
from datetime import date, datetime, time, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

IDS = {
    "clientes": "id_cliente",
    "sucursales": "id_sucursal",
    "farmaceuticos": "id_farmaceutico",
    "proveedores": "id_proveedor",
    "productos": "id_producto",
    "recetas": "id_receta",
    "stock_lotes": "id_lote",
    "ventas": "id_venta",
    "detalle_ventas": "id_detalle",
}
ENTEROS = {
    "precio_unit", "total", "cantidad", "unidades",
    "dispensas_autorizadas", "dispensas_realizadas",
}
FECHAS = {"fecha", "fecha_emision", "proxima_dispensa", "vencimiento"}


def convertir(campo, valor):
    if valor == "":
        return None
    if campo in ENTEROS:
        numero = int(valor)
        if numero < 0 or (campo == "cantidad" and numero == 0):
            raise ValueError(f"{campo} fuera de rango: {valor}")
        return numero
    if campo in FECHAS:
        return datetime.combine(date.fromisoformat(valor), time.min, timezone.utc)
    if campo == "activo":
        return {"True": True, "False": False}[valor]
    return valor


def preparar_datos(data=DATA):
    registros = {}
    for coleccion, clave in IDS.items():
        filas = {}
        original = data / "original" / f"{coleccion}.csv"
        extra = data / "extra" / original.name
        for archivo in (original, extra):
            if archivo == extra and not extra.exists():
                continue
            with archivo.open(encoding="utf-8-sig", newline="") as entrada:
                lector = csv.DictReader(entrada)
                for fila in lector:
                    try:
                        documento = {campo: convertir(campo, valor) for campo, valor in fila.items()}
                        identificador = documento[clave]
                        if not identificador or identificador in filas:
                            raise ValueError(f"ID vacío o duplicado: {identificador}")
                    except (KeyError, TypeError, ValueError) as error:
                        raise ValueError(f"{archivo}:{lector.line_num}: {error}") from error
                    filas[identificador] = documento
        registros[coleccion] = filas

    def referencia(documento, campo, destino):
        valor = documento[campo]
        if valor not in registros[destino]:
            raise ValueError(f"Referencia inexistente {campo}={valor}: {documento}")
        return registros[destino][valor]

    for coleccion, campo in (("clientes", "dni"), ("farmaceuticos", "matricula")):
        vistos = set()
        for documento in registros[coleccion].values():
            valor = documento[campo]
            if not valor or valor in vistos:
                raise ValueError(f"{campo} vacío o duplicado: {valor}")
            vistos.add(valor)

    referencias = {
        "farmaceuticos": (("id_sucursal", "sucursales"),),
        "productos": (("id_proveedor", "proveedores"),),
        "recetas": (("id_cliente", "clientes"),),
        "stock_lotes": (("id_producto", "productos"), ("id_sucursal", "sucursales")),
    }
    for coleccion, campos in referencias.items():
        for documento in registros[coleccion].values():
            for campo, destino in campos:
                referencia(documento, campo, destino)

    detalles = defaultdict(list)
    for detalle in registros["detalle_ventas"].values():
        referencia(detalle, "id_venta", "ventas")
        referencia(detalle, "id_producto", "productos")
        detalle = detalle.copy()
        detalles[detalle.pop("id_venta")].append(detalle)

    for venta in registros["ventas"].values():
        referencia(venta, "id_cliente", "clientes")
        farmaceutico = referencia(venta, "id_farmaceutico", "farmaceuticos")
        if venta["id_receta"] is not None:
            receta = referencia(venta, "id_receta", "recetas")
            if receta["id_cliente"] != venta["id_cliente"]:
                raise ValueError(f"La receta no corresponde al cliente de {venta['id_venta']}")
        items = detalles[venta["id_venta"]]
        if not items or venta["total"] != sum(item["cantidad"] * item["precio_unit"] for item in items):
            raise ValueError(f"Detalle vacío o total incorrecto en {venta['id_venta']}")
        venta["detalle"] = items
        venta["id_sucursal"] = farmaceutico["id_sucursal"]
        estado_stock = "historico" if venta["estado"] == "Completada" else "sin_aplicar"
        venta["movimiento_stock"] = {"estado": estado_stock}

    del registros["detalle_ventas"]
    return registros


def cargar(db, registros, *, reiniciar_demo=False):
    from pymongo import UpdateOne

    from .consultas.q11 import crear_vista_ingresos

    if reiniciar_demo and db.name != "farmared_demo":
        raise ValueError("El reinicio solo está habilitado para farmared_demo.")

    for coleccion in registros:
        db[coleccion].create_index(IDS[coleccion], unique=True)
    db.clientes.create_index("dni", unique=True)
    db.farmaceuticos.create_index("matricula", unique=True)
    for campo in ("id_cliente", "id_farmaceutico"):
        db.ventas.create_index([(campo, 1), ("fecha", 1)])
    db.stock_lotes.create_index([
        ("id_producto", 1), ("id_sucursal", 1), ("vencimiento", 1), ("id_lote", 1),
    ])

    crear_vista_ingresos(db)

    def insertar(session):
        if reiniciar_demo:
            for coleccion in (*registros, "proyeccion_pendiente"):
                db[coleccion].delete_many({}, session=session)
        nuevos = {}
        for coleccion, filas in registros.items():
            operaciones = [
                UpdateOne({IDS[coleccion]: clave}, {"$setOnInsert": documento}, upsert=True)
                for clave, documento in filas.items()
            ]
            nuevos[coleccion] = (
                db[coleccion].bulk_write(operaciones, session=session).upserted_count
                if operaciones else 0
            )
        return nuevos

    with db.client.start_session() as session:
        return session.with_transaction(insertar)


def main():
    from pymongo import MongoClient

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reiniciar-demo", action="store_true",
                        help="Reemplaza los datos de MongoDB en farmared_demo")
    args = parser.parse_args()
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise SystemExit("Definí MONGODB_URI con el nombre de la base de datos.")
    registros = preparar_datos()
    with MongoClient(uri) as cliente:
        db = cliente.get_default_database()
        nuevos = cargar(db, registros, reiniciar_demo=args.reiniciar_demo)
    for coleccion, cantidad in nuevos.items():
        print(f"{coleccion}: {cantidad} nuevos")


if __name__ == "__main__":
    main()
