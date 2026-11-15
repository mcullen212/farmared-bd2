"""Pruebas unitarias de la carga inicial y el acceso al stock de P1."""

import csv
from datetime import datetime, timezone
from shutil import copytree
from unittest.mock import MagicMock, sentinel

import pytest

from src.carga_mongo import DATA, cargar, convertir, preparar_datos
from src.repositorio_mongo import RepositorioMongo


@pytest.mark.parametrize(
    "campo,valor,esperado",
    [
        ("dni", "00123456", "00123456"),
        ("id_receta", "", None),
        ("unidades", "0", 0),
        ("cantidad", "2", 2),
        ("activo", "True", True),
        ("activo", "False", False),
        ("fecha", "2024-02-29", datetime(2024, 2, 29, tzinfo=timezone.utc)),
    ],
)
def test_convertir_tipos_csv(campo, valor, esperado):
    resultado = convertir(campo, valor)

    assert type(resultado) is type(esperado)
    assert resultado == esperado


@pytest.mark.parametrize("campo,valor", [("cantidad", "0"), ("unidades", "-1"), ("fecha", "2025-02-29")])
def test_convertir_rechaza_valores_invalidos(campo, valor):
    with pytest.raises(ValueError):
        convertir(campo, valor)


def test_preparar_datos_embebe_detalles_y_preserva_saldos():
    registros = preparar_datos()

    assert "detalle_ventas" not in registros
    for carpeta in ("original", "extra"):
        with (DATA / carpeta / "stock_lotes.csv").open(encoding="utf-8-sig", newline="") as archivo:
            for lote in csv.DictReader(archivo):
                assert registros["stock_lotes"][lote["id_lote"]]["unidades"] == int(lote["unidades"])
        with (DATA / carpeta / "detalle_ventas.csv").open(encoding="utf-8-sig", newline="") as archivo:
            for detalle in csv.DictReader(archivo):
                assert {
                    "id_detalle": detalle["id_detalle"],
                    "id_producto": detalle["id_producto"],
                    "cantidad": int(detalle["cantidad"]),
                    "precio_unit": int(detalle["precio_unit"]),
                } in registros["ventas"][detalle["id_venta"]]["detalle"]

    for venta in registros["ventas"].values():
        farmac = registros["farmaceuticos"][venta["id_farmaceutico"]]
        assert venta["id_sucursal"] == farmac["id_sucursal"]
        assert venta["movimiento_stock"] == {
            "estado": "historico" if venta["estado"] == "Completada" else "sin_aplicar",
        }


@pytest.mark.parametrize(
    "archivo,campo,cambio,error",
    [
        ("productos", "id_producto", "duplicar", "ID vacío o duplicado"),
        ("productos", "id_proveedor", "PRV-INEXISTENTE", "Referencia inexistente id_proveedor"),
        ("ventas", "total", "0", "Detalle vacío o total incorrecto"),
    ],
)
def test_preparar_datos_rechaza_csv_inconsistente(tmp_path, archivo, campo, cambio, error):
    datos = copytree(DATA, tmp_path / "data")
    ruta = datos / "original" / f"{archivo}.csv"
    with ruta.open(encoding="utf-8-sig", newline="") as entrada:
        lector = csv.DictReader(entrada)
        filas = list(lector)
        encabezados = lector.fieldnames
    filas[0][campo] = filas[1][campo] if cambio == "duplicar" else cambio
    with ruta.open("w", encoding="utf-8", newline="") as salida:
        escritor = csv.DictWriter(salida, encabezados)
        escritor.writeheader()
        escritor.writerows(filas)

    with pytest.raises(ValueError, match=error):
        preparar_datos(datos)


def test_cargar_protege_la_base_habitual():
    db = MagicMock()
    db.name = "farmared"

    with pytest.raises(ValueError, match="farmared_demo"):
        cargar(db, {}, reiniciar_demo=True)

    assert db.mock_calls == []


def test_cargar_inserta_por_id_sin_sobrescribir_en_la_misma_sesion():
    from pymongo import UpdateOne

    db = MagicMock()
    sesion = db.client.start_session.return_value.__enter__.return_value
    sesion.with_transaction.side_effect = lambda operacion: operacion(sesion)
    productos = db["productos"]
    productos.bulk_write.return_value.upserted_count = 1
    producto = {"id_producto": "PRD001", "activo": True}

    assert cargar(db, {"productos": {"PRD001": producto}}) == {"productos": 1}

    productos.create_index.assert_called_once_with("id_producto", unique=True)
    productos.bulk_write.assert_called_once_with([
        UpdateOne({"id_producto": "PRD001"}, {"$setOnInsert": producto}, upsert=True),
    ], session=sesion)
    productos.delete_many.assert_not_called()


def test_lotes_fefo_filtra_disponibilidad_y_ordena_por_vencimiento(db_stock):
    dia = datetime(2026, 11, 12, tzinfo=timezone.utc)
    repo = RepositorioMongo(db_stock)

    resultado = repo.lotes_fefo("PRD001", "S001", dia, session=sentinel.sesion)

    db_stock.stock_lotes.find.assert_called_once_with({
        "id_producto": "PRD001",
        "id_sucursal": "S001",
        "vencimiento": {"$gte": dia},
        "unidades": {"$gt": 0},
    }, session=sentinel.sesion)
    cursor = db_stock.stock_lotes.find.return_value
    cursor.sort.assert_called_once_with([("vencimiento", 1), ("id_lote", 1)])
    assert resultado is cursor.sort.return_value


@pytest.fixture
def db_stock():
    return MagicMock()


@pytest.mark.parametrize("cantidad", [0, -1, 1.5, True])
def test_decrementar_lote_rechaza_cantidades_invalidas(db_stock, cantidad):
    with pytest.raises(ValueError, match="entero positivo"):
        RepositorioMongo(db_stock).decrementar_lote("L001", cantidad)

    db_stock.stock_lotes.update_one.assert_not_called()


@pytest.mark.parametrize("modificados,esperado", [(0, False), (1, True)])
def test_decrementar_lote_condiciona_el_decremento_al_saldo(db_stock, modificados, esperado):
    actualizar = db_stock.stock_lotes.update_one
    actualizar.return_value.modified_count = modificados

    assert RepositorioMongo(db_stock).decrementar_lote("L001", 3, session=sentinel.sesion) is esperado

    actualizar.assert_called_once_with(
        {"id_lote": "L001", "unidades": {"$gte": 3}},
        {"$inc": {"unidades": -3}},
        session=sentinel.sesion,
    )
