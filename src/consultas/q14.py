"""q14 · Registro atómico de venta completada, receta y stock (MongoDB).

Parámetros: db y datos con id_cliente, id_farmaceutico, medio_pago, detalle
(lista de {id_producto, cantidad}), opcionalmente id_receta, id_venta y fecha.
Devuelve la venta creada sin _id. El precio se toma siempre del catálogo.
Registra en la misma transacción un evento para la proyección eventual a Neo4j.
"""

import argparse
import re
from datetime import date, datetime, time, timezone, timedelta

from bson import json_util
from pymongo.errors import DuplicateKeyError

from ..proyeccion.eventos import registrar_evento
from .fechas import dia_de_negocio
from .q15 import descontar_stock

MEDIOS_PAGO = {"Efectivo", "Débito", "Crédito", "Transferencia", "Obra social"}
CONDICIONES = {"Venta libre", "Bajo receta", "Bajo receta archivada"}
CAMPOS = {"id_venta", "id_cliente", "id_farmaceutico", "id_receta", "fecha", "medio_pago", "detalle"}


def _dia(valor):
    if valor is None:
        return dia_de_negocio()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        return date.fromisoformat(valor)
    raise ValueError("fecha debe ser AAAA-MM-DD o date")


def _siguiente_id(db, session):
    numeros = (
        int(m.group(1))
        for doc in db.ventas.find({}, {"id_venta": 1}, session=session)
        if (m := re.fullmatch(r"V(\d+)", doc["id_venta"]))
    )
    return f"V{max(numeros, default=0) + 1:03d}"


def registrar_venta(db, datos, *, hoy=None):
    """Valida y registra una venta, ante cualquier error revierte todo.

    'hoy' se usa para FEFO, normalmente es el día de negocio actual.
    'fecha' permite registrar una fecha explícita de venta, sin alterar FEFO.
    """
    if not isinstance(datos, dict) or set(datos) - CAMPOS:
        raise ValueError(f"Datos inválidos. Campos permitidos: {sorted(CAMPOS)}")
    for campo in ("id_cliente", "id_farmaceutico", "medio_pago"):
        if not isinstance(datos.get(campo), str) or not datos[campo].strip():
            raise ValueError(f"Falta {campo}")
    if datos["medio_pago"] not in MEDIOS_PAGO:
        raise ValueError("Medio de pago inválido")
    entrada = datos.get("detalle")
    if not isinstance(entrada, list) or not entrada:
        raise ValueError("detalle debe ser una lista no vacía")
    for item in entrada:
        if (not isinstance(item, dict) or set(item) != {"id_producto", "cantidad"}
                or not isinstance(item["id_producto"], str) or not item["id_producto"]
                or type(item["cantidad"]) is not int or item["cantidad"] <= 0):
            raise ValueError("Cada ítem requiere id_producto y cantidad entera positiva")
    id_receta = datos.get("id_receta") or None
    if id_receta is not None and not isinstance(id_receta, str):
        raise ValueError("id_receta inválido")
    fecha = _dia(datos.get("fecha"))
    hoy = _dia(hoy)
    fecha_bson = datetime.combine(fecha, time.min, timezone.utc)

    def transaccion(session):
        cliente = db.clientes.find_one({"id_cliente": datos["id_cliente"], "activo": True},
                                      session=session)
        if cliente is None:
            raise ValueError("El cliente no existe o está inactivo")
        farmaceutico = db.farmaceuticos.find_one(
            {"id_farmaceutico": datos["id_farmaceutico"], "activo": True}, session=session
        )
        if farmaceutico is None:
            raise ValueError("El farmacéutico no existe o está inactivo")
        sucursal = db.sucursales.find_one(
            {"id_sucursal": farmaceutico["id_sucursal"], "tipo": "Farmacia", "activo": True},
            session=session,
        )
        if sucursal is None:
            raise ValueError("El farmacéutico no pertenece a una farmacia activa")

        detalle = []
        requiere_receta = False
        requiere_archivada = False
        for item in entrada:
            producto = db.productos.find_one(
                {"id_producto": item["id_producto"], "activo": True}, session=session
            )
            if producto is None:
                raise ValueError(f"El producto {item['id_producto']} no existe o está inactivo")
            condicion = producto.get("condicion_venta")
            if condicion not in CONDICIONES:
                raise ValueError(f"Condición de venta desconocida en {item['id_producto']}")
            requiere_receta |= condicion != "Venta libre"
            requiere_archivada |= condicion == "Bajo receta archivada"
            precio = producto["precio_unit"]
            if type(precio) is not int or precio < 0:
                raise ValueError(f"Precio inválido en {item['id_producto']}")
            detalle.append({"id_detalle": None, "id_producto": item["id_producto"],
                            "cantidad": item["cantidad"], "precio_unit": precio})

        receta = None
        if requiere_receta and not id_receta:
            raise ValueError("La venta de estos productos requiere receta")
        if id_receta:
            receta = db.recetas.find_one({"id_receta": id_receta, "id_cliente": datos["id_cliente"],
                                         "estado": "Vigente"}, session=session)
            if receta is None:
                raise ValueError("La receta no existe, no está vigente o pertenece a otro cliente")
            if requiere_archivada and receta["tipo"] != "Archivada":
                raise ValueError("Los productos bajo receta archivada requieren receta Archivada")
            if (type(receta.get("dispensas_autorizadas")) is not int
                    or type(receta.get("dispensas_realizadas")) is not int
                    or receta["dispensas_realizadas"] >= receta["dispensas_autorizadas"]):
                raise ValueError("La receta no tiene dispensas disponibles")

        id_venta = datos.get("id_venta") or _siguiente_id(db, session)
        if not isinstance(id_venta, str) or not id_venta.strip():
            raise ValueError("id_venta inválido")
        for numero, item in enumerate(detalle, 1):
            item["id_detalle"] = f"{id_venta}-D{numero:03d}"
        venta = {
            "id_venta": id_venta, "id_cliente": datos["id_cliente"],
            "id_farmaceutico": datos["id_farmaceutico"], "id_sucursal": sucursal["id_sucursal"],
            "id_receta": id_receta, "fecha": fecha_bson,
            "tipo": "Con receta" if id_receta else "Venta libre",
            "medio_pago": datos["medio_pago"],
            "total": sum(item["cantidad"] * item["precio_unit"] for item in detalle),
            "estado": "Completada", "detalle": detalle,
            "movimiento_stock": {"estado": "sin_aplicar"},
        }
        db.ventas.insert_one(venta, session=session)
        descontar_stock(db, id_venta, hoy=hoy, session=session)

        if receta is not None:
            realizadas = receta["dispensas_realizadas"] + 1
            cambios = {"dispensas_realizadas": realizadas}
            if realizadas == receta["dispensas_autorizadas"]:
                cambios.update({"estado": "Completada", "proxima_dispensa": None})
            elif receta["tipo"] == "Tratamiento prolongado":
                proxima = fecha + timedelta(days=30)
                cambios["proxima_dispensa"] = datetime.combine(proxima, time.min, timezone.utc)
            resultado = db.recetas.update_one(
                {"id_receta": id_receta, "estado": "Vigente",
                 "dispensas_realizadas": receta["dispensas_realizadas"]},
                {"$set": cambios}, session=session,
            )
            if resultado.modified_count != 1:
                raise ValueError("No se pudo actualizar la receta")

        refs = [{"entidad": "venta", "id": id_venta}]
        if id_receta:
            refs.append({"entidad": "receta", "id": id_receta})
        registrar_evento(db, "q14.venta", refs, session=session)
        resultado = db.ventas.find_one({"id_venta": id_venta}, {"_id": 0}, session=session)
        return resultado

    try:
        with db.client.start_session() as session:
            return session.with_transaction(transaccion)
    except DuplicateKeyError as error:
        raise ValueError("El ID de venta ya existe: Elegí otro o reintentá") from error


q14 = registrar_venta


def main():
    from ..conexion_neo4j import abrir_mongo

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, type=__import__("json").loads)
    parser.add_argument("--hoy", type=date.fromisoformat, help="Fecha FEFO para pruebas")
    args = parser.parse_args()
    cliente, db = abrir_mongo()
    with cliente:
        resultado = registrar_venta(db, args.json, hoy=args.hoy)
    print(json_util.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
