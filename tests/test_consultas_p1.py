"""Pruebas unitarias del contrato de las consultas P1 con PyMongo."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
from pymongo.errors import OperationFailure

from src.consultas.q01 import q01
from src.consultas.q02 import q02
from src.consultas.q05 import q05
from src.consultas.q07 import q07
from src.consultas.q08 import q08
from src.consultas.q09 import q09
from src.consultas.q11 import crear_vista_ingresos, q11
from src.consultas.q12 import q12


@pytest.fixture
def db():
    return MagicMock()


@pytest.mark.parametrize(
    "consulta,coleccion,filtro,referencias,orden",
    [
        (q01, "productos", {"activo": True}, [
            ("proveedores", "id_proveedor", "id_proveedor", "proveedor"),
        ], "id_producto"),
        (q02, "ventas", {"estado": "Pendiente"}, [
            ("farmaceuticos", "id_farmaceutico", "id_farmaceutico", "farmaceutico"),
            ("sucursales", "id_sucursal", "id_sucursal", "sucursal"),
        ], "id_venta"),
        (q08, "stock_lotes", {"unidades": {"$lt": 50}}, [
            ("productos", "id_producto", "id_producto", "producto"),
            ("sucursales", "id_sucursal", "id_sucursal", "sucursal"),
            ("proveedores", "producto.id_proveedor", "id_proveedor", "proveedor"),
        ], "id_lote"),
    ],
    ids=["q01", "q02", "q08"],
)
def test_consultas_con_referencias(db, consulta, coleccion, filtro, referencias, orden):
    aggregate = getattr(db, coleccion).aggregate
    documentos = [{orden: "ID de prueba"}]
    aggregate.return_value = iter(documentos)

    assert consulta(db) == documentos

    aggregate.assert_called_once()
    filtro_enviado, *relaciones, orden_enviado = aggregate.call_args.args[0]
    assert filtro_enviado == {"$match": filtro}
    assert orden_enviado == {"$sort": {orden: 1}}
    assert len(relaciones) == 2 * len(referencias)
    for indice, (origen, local, externo, alias) in enumerate(referencias):
        assert relaciones[2 * indice:2 * indice + 2] == [
            {"$lookup": {
                "from": origen, "localField": local, "foreignField": externo, "as": alias,
            }},
            {"$unwind": f"${alias}"},
        ]


def test_q05_ventana_inclusiva_de_60_dias_y_conteo_cero(db):
    q05(db, hoy=date(2026, 1, 1))
    filtro, relacion, conteo, *_ = db.farmaceuticos.aggregate.call_args.args[0]

    assert filtro == {"$match": {"activo": True}}
    assert relacion["$lookup"]["from"] == "ventas"
    assert relacion["$lookup"]["localField"] == relacion["$lookup"]["foreignField"] == "id_farmaceutico"
    assert relacion["$lookup"]["pipeline"] == [
        {"$match": {
            "fecha": {
                "$gte": datetime(2025, 11, 3, tzinfo=timezone.utc),
                "$lt": datetime(2026, 1, 2, tzinfo=timezone.utc),
            },
            "estado": {"$ne": "Anulada"},
        }},
        {"$count": "cantidad"},
    ]
    assert conteo == {"$set": {"cantidad_ventas": {"$ifNull": [{"$first": "$conteo.cantidad"}, 0]}}}


def test_q07_ranking_por_unidades_con_desempate(db):
    db.ventas.aggregate.return_value = iter([])

    assert q07(db) == []

    etapas = db.ventas.aggregate.call_args.args[0]
    assert etapas[:5] == [
        {"$match": {"estado": "Completada"}},
        {"$unwind": "$detalle"},
        {"$group": {"_id": "$detalle.id_producto", "unidades_vendidas": {"$sum": "$detalle.cantidad"}}},
        {"$sort": {"unidades_vendidas": -1, "_id": 1}},
        {"$limit": 5},
    ]
    assert etapas[5]["$lookup"]["from"] == "productos"


def test_q09_venta_libre_con_limite_estricto_y_orden(db):
    documentos = [{"id_venta": "V001", "total": 4999, "detalle": [{"cantidad": 1}]}]
    cursor = db.ventas.find.return_value
    cursor.sort.return_value = iter(documentos)

    assert q09(db) == documentos

    db.ventas.find.assert_called_once_with({
        "tipo": "Venta libre", "total": {"$lt": 5000}, "estado": {"$ne": "Anulada"},
    })
    cursor.sort.assert_called_once_with("id_venta", 1)


def test_q11_filtra_anio_y_mes_en_la_vista(db):
    vista = db["vista_ingresos_por_farmaceutico"]
    cursor = vista.find.return_value
    documentos = [{"id_farmaceutico": "F001", "ingresos_totales": 4800}]
    cursor.sort.return_value = iter(documentos)

    assert q11(db, hoy=date(2026, 1, 15)) == documentos

    db.__getitem__.assert_called_with("vista_ingresos_por_farmaceutico")
    vista.find.assert_called_once_with({"anio": 2026, "mes": 1})
    cursor.sort.assert_called_once_with("id_farmaceutico", 1)


def test_crear_vista_suma_ventas_completadas_por_farmaceutico_y_mes(db):
    crear_vista_ingresos(db)

    db.create_collection.assert_called_once()
    args, opciones = db.create_collection.call_args
    assert args == ("vista_ingresos_por_farmaceutico",)
    assert opciones["viewOn"] == "ventas"
    assert opciones["check_exists"] is False
    filtro, agrupacion, proyeccion = opciones["pipeline"]
    assert filtro == {"$match": {"estado": "Completada"}}
    assert agrupacion == {"$group": {
        "_id": {
            "id_farmaceutico": "$id_farmaceutico",
            "anio": {"$year": "$fecha"},
            "mes": {"$month": "$fecha"},
        },
        "ingresos_totales": {"$sum": "$total"},
    }}
    assert proyeccion["$project"]["ingresos_totales"] == 1


@pytest.mark.parametrize("tipo", ["view", "collection"])
def test_crear_vista_solo_acepta_una_vista_existente_equivalente(db, tipo):
    from src.consultas.q11 import AGRUPACION

    db.create_collection.side_effect = OperationFailure("Ya existe", code=48)
    db.list_collections.return_value = iter([
        {"type": tipo, "options": {"viewOn": "ventas", "pipeline": AGRUPACION}},
    ])

    if tipo == "view":
        crear_vista_ingresos(db)
    else:
        with pytest.raises(OperationFailure, match="Ya existe"):
            crear_vista_ingresos(db)
    db.list_collections.assert_called_once_with(filter={"name": "vista_ingresos_por_farmaceutico"})


@pytest.mark.parametrize(
    "hoy,desde,hasta",
    [
        (date(2024, 2, 29), datetime(2023, 2, 28), datetime(2024, 3, 1)),
        (date(2026, 11, 12), datetime(2025, 11, 12), datetime(2026, 11, 13)),
    ],
)
def test_q12_aniversario_inclusivo_y_ventas_de_cualquier_estado(db, hoy, desde, hasta):
    q12(db, hoy=hoy)

    relacion, filtro, *_ = db.clientes.aggregate.call_args.args[0]
    assert relacion["$lookup"] == {
        "from": "ventas",
        "localField": "id_cliente",
        "foreignField": "id_cliente",
        "pipeline": [
            {"$match": {"fecha": {
                "$gte": desde.replace(tzinfo=timezone.utc),
                "$lt": hasta.replace(tzinfo=timezone.utc),
            }}},
            {"$limit": 1},
        ],
        "as": "ventas_recientes",
    }
    assert filtro == {"$match": {"ventas_recientes.0": {"$exists": False}}}
