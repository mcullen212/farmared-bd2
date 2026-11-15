"""Casos de Q13 en una base temporal con MongoDB replica set."""

import pytest

from src.consultas.q13 import crear_cliente, dar_de_baja_cliente, modificar_cliente


@pytest.fixture
def db(base_mongo):
    base_mongo.clientes.create_index("id_cliente", unique=True)
    base_mongo.clientes.create_index("dni", unique=True)
    return base_mongo


def estado(db):
    return (
        list(db.clientes.find().sort("_id", 1)),
        list(db.proyeccion_pendiente.find().sort("_id", 1)),
    )


def test_crear_cliente_con_dni_numerico_persiste_dni_como_texto(db):
    datos = {"nombre": "Ana", "apellido": "Gil", "dni": 40111222}

    cliente = crear_cliente(db, datos)

    assert cliente["dni"] == "40111222"
    assert db.clientes.find_one({"dni": "40111222"}, {"_id": 0}) == cliente


def test_crear_cliente_con_dni_duplicado_conserva_estado(db):
    datos = {"nombre": "Ana", "apellido": "Gil", "dni": "40111222"}
    crear_cliente(db, datos)
    antes = estado(db)

    with pytest.raises(ValueError, match="Ya existe un cliente con DNI 40111222"):
        crear_cliente(db, {**datos, "dni": " 40111222 "})

    assert estado(db) == antes


@pytest.mark.parametrize(
    "cambios, mensaje",
    [({"obra_social": "OSDE"}, "hace falta nro_afiliado"), ({"dni": "1"}, "Solo se pueden modificar")],
    ids=["cobertura-sin-afiliado", "cambio-de-dni"],
)
def test_modificar_cliente_con_cambios_invalidos_conserva_estado(db, cambios, mensaje):
    cliente = crear_cliente(db, {"nombre": "Ana", "apellido": "Gil", "dni": "40111222"})
    antes = estado(db)

    with pytest.raises(ValueError, match=mensaje):
        modificar_cliente(db, cliente["id_cliente"], cambios)

    assert estado(db) == antes


def test_modificar_cliente_inexistente_conserva_estado(db):
    antes = estado(db)

    with pytest.raises(LookupError, match="No existe el cliente C999"):
        modificar_cliente(db, "C999", {"email": "x@example.com"})

    assert estado(db) == antes


def test_dar_de_baja_cliente_con_id_invalido_conserva_estado(db):
    crear_cliente(db, {"nombre": "Ana", "apellido": "Gil", "dni": "40111222"})
    antes = estado(db)

    with pytest.raises(ValueError, match="id_cliente debe ser un texto no vacío"):
        dar_de_baja_cliente(db, {})

    assert estado(db) == antes


def test_modificar_cliente_sin_campos_opcionales_normaliza_telefono(db):
    db.clientes.insert_one({"id_cliente": "C001", "dni": "40111222", "activo": True})

    cliente = modificar_cliente(db, "C001", {"telefono": " 11-5555-0000 "})

    assert cliente["telefono"] == "11-5555-0000"
    assert "email" not in cliente
    assert db.clientes.find_one({"id_cliente": "C001"}, {"_id": 0}) == cliente
    assert db.proyeccion_pendiente.count_documents({"operacion": "q13.modificacion"}) == 1


def test_dar_de_baja_cliente_ya_inactivo_conserva_estado(db):
    cliente = crear_cliente(db, {"nombre": "Ana", "apellido": "Gil", "dni": "40111222"})
    id_cliente = cliente["id_cliente"]
    dar_de_baja_cliente(db, id_cliente)
    antes = estado(db)

    baja = dar_de_baja_cliente(db, id_cliente)

    assert baja == {**cliente, "activo": False}
    assert estado(db) == antes
    assert db.proyeccion_pendiente.count_documents({"operacion": "q13.baja"}) == 1
