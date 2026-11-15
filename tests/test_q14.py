"""Pruebas de integración de q14. Requieren MongoDB replica set y MONGODB_URI.

Cada test utiliza una base temporal propia, que se elimina al finalizar. Nunca
modifica la base indicada en MONGODB_URI (por ejemplo, farmared).

Ejecutar: python -m pytest -v tests/test_q14.py
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.consultas.q14 import registrar_venta

HOY = date(2026, 11, 12)


@pytest.fixture
def db(base_mongo):
    base_mongo.ventas.create_index("id_venta", unique=True)
    base_mongo.clientes.insert_many([
        {"id_cliente": "C1", "activo": True},
        {"id_cliente": "C2", "activo": True},
        {"id_cliente": "CI", "activo": False},
    ])
    base_mongo.sucursales.insert_many([
        {"id_sucursal": "S1", "tipo": "Farmacia", "activo": True},
        {"id_sucursal": "SD", "tipo": "Droguería", "activo": True},
        {"id_sucursal": "SI", "tipo": "Farmacia", "activo": False},
    ])
    base_mongo.farmaceuticos.insert_many([
        {"id_farmaceutico": "F1", "id_sucursal": "S1", "activo": True},
        {"id_farmaceutico": "FI", "id_sucursal": "S1", "activo": False},
        {"id_farmaceutico": "FD", "id_sucursal": "SD", "activo": True},
        {"id_farmaceutico": "FSI", "id_sucursal": "SI", "activo": True},
    ])
    base_mongo.productos.insert_many([
        {"id_producto": "P1", "activo": True, "condicion_venta": "Venta libre", "precio_unit": 2800},
        {"id_producto": "P2", "activo": True, "condicion_venta": "Venta libre", "precio_unit": 3500},
        {"id_producto": "PR", "activo": True, "condicion_venta": "Bajo receta", "precio_unit": 9800},
        {"id_producto": "PA", "activo": True, "condicion_venta": "Bajo receta archivada", "precio_unit": 12000},
        {"id_producto": "PI", "activo": False, "condicion_venta": "Venta libre", "precio_unit": 500},
    ])
    base_mongo.recetas.insert_many([
        {"id_receta": "R1", "id_cliente": "C1", "tipo": "Simple", "estado": "Vigente",
         "dispensas_autorizadas": 1, "dispensas_realizadas": 0, "proxima_dispensa": None},
        {"id_receta": "R2", "id_cliente": "C2", "tipo": "Simple", "estado": "Vigente",
         "dispensas_autorizadas": 1, "dispensas_realizadas": 0, "proxima_dispensa": None},
        {"id_receta": "RV", "id_cliente": "C1", "tipo": "Simple", "estado": "Vencida",
         "dispensas_autorizadas": 1, "dispensas_realizadas": 0, "proxima_dispensa": None},
        {"id_receta": "RC", "id_cliente": "C1", "tipo": "Simple", "estado": "Completada",
         "dispensas_autorizadas": 1, "dispensas_realizadas": 1, "proxima_dispensa": None},
        {"id_receta": "RX", "id_cliente": "C1", "tipo": "Simple", "estado": "Vigente",
         "dispensas_autorizadas": 1, "dispensas_realizadas": 1, "proxima_dispensa": None},
        {"id_receta": "RA", "id_cliente": "C1", "tipo": "Archivada", "estado": "Vigente",
         "dispensas_autorizadas": 1, "dispensas_realizadas": 0, "proxima_dispensa": None},
        {"id_receta": "RP", "id_cliente": "C1", "tipo": "Tratamiento prolongado", "estado": "Vigente",
         "dispensas_autorizadas": 3, "dispensas_realizadas": 1, "proxima_dispensa": None},
        {"id_receta": "RPULT", "id_cliente": "C1", "tipo": "Tratamiento prolongado", "estado": "Vigente",
         "dispensas_autorizadas": 3, "dispensas_realizadas": 2, "proxima_dispensa": None},
    ])
    vencimiento = lambda dias: datetime.combine(HOY + timedelta(days=dias), datetime.min.time(), timezone.utc)
    base_mongo.stock_lotes.insert_many([
        {"id_lote": "L1", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(5), "unidades": 4},
        {"id_lote": "L2", "id_producto": "P1", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 10},
        {"id_lote": "L3", "id_producto": "P2", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 3},
        {"id_lote": "LR", "id_producto": "PR", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 5},
        {"id_lote": "LA", "id_producto": "PA", "id_sucursal": "S1", "vencimiento": vencimiento(30), "unidades": 5},
    ])
    return base_mongo


def entrada(**cambios):
    datos = {"id_cliente": "C1", "id_farmaceutico": "F1", "medio_pago": "Efectivo", "fecha": HOY.isoformat(),
             "detalle": [{"id_producto": "P1", "cantidad": 1}]}
    datos.update(cambios)
    return datos


def foto(db):
    """Permite verificar que el rechazo sea totalmente atómico."""
    return {
        "ventas": list(db.ventas.find().sort("_id", 1)),
        "eventos": list(db.proyeccion_pendiente.find().sort("_id", 1)),
        "stock": list(db.stock_lotes.find().sort("_id", 1)),
        "recetas": list(db.recetas.find().sort("_id", 1)),
    }


def rechazar_sin_cambios(db, datos, *, mensaje):
    antes = foto(db)
    with pytest.raises(ValueError, match=mensaje):
        registrar_venta(db, datos, hoy=HOY)
    assert foto(db) == antes, "Una venta rechazada dejó cambios parciales"


def estado_para_informe(db):
    venta = db.ventas.find_one({"id_venta": "VTEST"})
    receta = db.recetas.find_one({"id_receta": "R1"})
    lotes = {lote["id_lote"]: lote["unidades"] for lote in db.stock_lotes.find()}
    estado_venta = "Ausente"
    if venta:
        estado_venta = f"{venta['estado']}, ARS {venta['total']}, stock {venta['movimiento_stock']['estado']}"
    return {
        "Venta de prueba (`VTEST`)": estado_venta,
        "Stock del producto bajo receta (`PR`, lote `LR`)": lotes["LR"],
        "Stock del segundo producto (`P2`, lote `L3`)": lotes["L3"],
        "Estado y dispensas de la receta (`R1`)": (
            f"{receta['estado']}, {receta['dispensas_realizadas']}/{receta['dispensas_autorizadas']}"
        ),
        "Cantidad de eventos de proyección": db.proyeccion_pendiente.count_documents({}),
    }


def imprimir_resultado(caso, antes, despues):
    print(f"\nQ14 · {caso}\n")
    print(f"| Registro evaluado | Antes | Después del {caso} |")
    print("| --- | --- | --- |")
    for registro in antes:
        print(f"| {registro} | {antes[registro]} | {despues[registro]} |")


def test_registrar_venta_libre_valida_persiste_venta_y_evento(db):
    venta = registrar_venta(db, entrada(), hoy=HOY)
    assert venta["estado"] == "Completada"
    assert venta["tipo"] == "Venta libre"
    assert venta["id_sucursal"] == "S1"
    assert venta["total"] == 2800
    assert venta["detalle"][0]["precio_unit"] == 2800
    assert db.ventas.count_documents({"id_venta": venta["id_venta"]}) == 1
    assert db.stock_lotes.find_one({"id_lote": "L1"})["unidades"] == 3
    evento = db.proyeccion_pendiente.find_one({"operacion": "q14.venta"})
    assert evento["estado"] == "pendiente"
    assert evento["refs"] == [{"entidad": "venta", "id": venta["id_venta"]}]


@pytest.mark.parametrize("valor", ['NO_EXISTE', 'CI'], ids=['inexistente', 'inactivo'])
def test_registrar_venta_con_cliente_inexistente_o_inactivo_rechaza_venta(db, valor):
    datos = entrada(id_cliente=valor)

    rechazar_sin_cambios(db, datos, mensaje="El cliente no existe o está inactivo")


@pytest.mark.parametrize("valor", ['NO_EXISTE', 'FI'], ids=['inexistente', 'inactivo'])
def test_registrar_venta_con_farmaceutico_inexistente_o_inactivo_rechaza_venta(db, valor):
    datos = entrada(id_farmaceutico=valor)

    rechazar_sin_cambios(db, datos, mensaje="El farmacéutico no existe o está inactivo")


@pytest.mark.parametrize("valor", ['FD', 'FSI'], ids=['drogueria', 'sucursal-inactiva'])
def test_registrar_venta_con_farmacia_no_habilitada_rechaza_venta(db, valor):
    datos = entrada(id_farmaceutico=valor)

    rechazar_sin_cambios(db, datos, mensaje="El farmacéutico no pertenece a una farmacia activa")


@pytest.mark.parametrize("valor", ['NO_EXISTE', 'PI'], ids=['inexistente', 'inactivo'])
def test_registrar_venta_con_producto_inexistente_o_inactivo_rechaza_venta(db, valor):
    datos = entrada(detalle=[{"id_producto": valor, "cantidad": 1}])

    rechazar_sin_cambios(db, datos, mensaje=f"El producto {valor} no existe o está inactivo")


def test_registrar_venta_con_producto_bajo_receta_sin_receta_rechaza_venta(db):
    rechazar_sin_cambios(db, entrada(detalle=[{"id_producto": "PR", "cantidad": 1}]), mensaje="requiere receta")


@pytest.mark.parametrize(
    "id_receta", ["NO_EXISTE", "R2", "RV", "RC"],
    ids=["inexistente", "otro-cliente", "vencida", "completada"],
)
def test_registrar_venta_con_receta_no_habilitada_rechaza_venta(db, id_receta):
    datos = entrada(id_receta=id_receta, detalle=[{"id_producto": "PR", "cantidad": 1}])

    rechazar_sin_cambios(db, datos, mensaje="La receta no existe, no está vigente o pertenece a otro cliente")


def test_registrar_venta_con_receta_sin_dispensas_disponibles_rechaza_venta(db):
    rechazar_sin_cambios(db, entrada(id_receta="RX", detalle=[{"id_producto": "PR", "cantidad": 1}]), mensaje="no tiene dispensas disponibles")


def test_registrar_venta_con_receta_archivada_incompatible_rechaza_venta(db):
    rechazar_sin_cambios(db, entrada(id_receta="R1", detalle=[{"id_producto": "PA", "cantidad": 1}]), mensaje="requieren receta Archivada")


def test_registrar_venta_con_receta_archivada_completa_receta(db):
    registrar_venta(db, entrada(id_receta="RA", detalle=[{"id_producto": "PA", "cantidad": 1}]), hoy=HOY)
    receta = db.recetas.find_one({"id_receta": "RA"})
    assert receta["estado"] == "Completada"
    assert receta["dispensas_realizadas"] == 1
    assert receta["proxima_dispensa"] is None


def test_registrar_venta_con_receta_simple_completa_receta(db):
    antes = estado_para_informe(db)
    venta = registrar_venta(db, entrada(id_venta="VTEST", id_receta="R1", detalle=[
        {"id_producto": "PR", "cantidad": 1}, {"id_producto": "P2", "cantidad": 2}]), hoy=HOY)
    assert venta["total"] == 16800
    assert venta["movimiento_stock"]["estado"] == "aplicado"
    assert db.stock_lotes.find_one({"id_lote": "LR"})["unidades"] == 4
    assert db.stock_lotes.find_one({"id_lote": "L3"})["unidades"] == 1
    receta = db.recetas.find_one({"id_receta": "R1"})
    assert (receta["estado"], receta["dispensas_realizadas"]) == ("Completada", 1)
    assert receta["proxima_dispensa"] is None
    assert {"entidad": "receta", "id": "R1"} in db.proyeccion_pendiente.find_one(
        {"refs.id": venta["id_venta"]})["refs"]
    imprimir_resultado("éxito", antes, estado_para_informe(db))


def test_registrar_venta_con_tratamiento_prolongado_programa_siguiente_dispensa(db):
    registrar_venta(db, entrada(id_receta="RP",
                               detalle=[{"id_producto": "PR", "cantidad": 1}]), hoy=HOY)
    receta = db.recetas.find_one({"id_receta": "RP"})
    assert receta["estado"] == "Vigente"
    assert receta["dispensas_realizadas"] == 2
    assert receta["proxima_dispensa"].date() == date(2026, 12, 12)


def test_registrar_venta_con_ultima_dispensa_completa_tratamiento(db):
    registrar_venta(db, entrada(id_receta="RPULT", detalle=[{"id_producto": "PR", "cantidad": 1}]), hoy=HOY)
    receta = db.recetas.find_one({"id_receta": "RPULT"})
    assert (receta["estado"], receta["dispensas_realizadas"], receta["proxima_dispensa"]) == (
        "Completada", 3, None)


def test_registrar_venta_con_dos_productos_calcula_total_con_precios_del_catalogo(db):
    venta = registrar_venta(db, entrada(detalle=[{"id_producto": "P1", "cantidad": 2},
                                                   {"id_producto": "P2", "cantidad": 1}]), hoy=HOY)
    assert venta["total"] == 2 * 2800 + 3500
    assert [i["precio_unit"] for i in venta["detalle"]] == [2800, 3500]


def test_registrar_venta_con_detalle_vacio_rechaza_venta(db):
    rechazar_sin_cambios(db, entrada(detalle=[]), mensaje="detalle debe ser una lista no vacía")


@pytest.mark.parametrize("cantidad", [0, -1, 1.5, "2", True])
def test_registrar_venta_con_cantidad_no_entera_positiva_rechaza_venta(db, cantidad):
    datos = entrada(detalle=[{"id_producto": "P1", "cantidad": cantidad}])

    rechazar_sin_cambios(db, datos, mensaje="cantidad entera positiva")


def test_registrar_venta_con_medio_de_pago_invalido_rechaza_venta(db):
    rechazar_sin_cambios(db, entrada(medio_pago="Criptomonedas"), mensaje="Medio de pago inválido")


def test_registrar_venta_con_receta_y_stock_insuficiente_conserva_estado(db):
    antes = estado_para_informe(db)
    rechazar_sin_cambios(db, entrada(id_venta="VTEST", id_receta="R1", detalle=[
        {"id_producto": "PR", "cantidad": 1}, {"id_producto": "P2", "cantidad": 99}]),
        mensaje="Stock vigente insuficiente para P2: faltan 96 unidades")
    imprimir_resultado("rechazo", antes, estado_para_informe(db))


def test_registrar_venta_con_segundo_producto_sin_stock_revierte_primer_descuento(db):
    rechazar_sin_cambios(db, entrada(detalle=[
        {"id_producto": "P1", "cantidad": 2}, {"id_producto": "P2", "cantidad": 99}]),
        mensaje="Stock vigente insuficiente para P2: faltan 96 unidades")


def test_registrar_venta_con_un_lote_insuficiente_descuenta_fefo_en_varios_lotes(db):
    venta = registrar_venta(db, entrada(detalle=[{"id_producto": "P1", "cantidad": 6}]), hoy=HOY)
    assert db.stock_lotes.find_one({"id_lote": "L1"})["unidades"] == 0
    assert db.stock_lotes.find_one({"id_lote": "L2"})["unidades"] == 8
    assert venta["movimiento_stock"]["estado"] == "aplicado"


def test_registrar_venta_con_id_duplicado_conserva_estado(db):
    datos = entrada(id_venta="VTEST")
    registrar_venta(db, datos, hoy=HOY)
    rechazar_sin_cambios(db, datos, mensaje="El ID de venta ya existe")
