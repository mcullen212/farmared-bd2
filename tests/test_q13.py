"""Casos de Q13 en una base temporal con MongoDB replica set."""

import os
from uuid import uuid4

import pytest
from pymongo import MongoClient

from src.consultas.q13 import crear_cliente, dar_de_baja_cliente, modificar_cliente


@pytest.fixture
def db():
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        pytest.skip("Se requiere MONGODB_URI (MongoDB replica set)")
    with MongoClient(uri, serverSelectionTimeoutMS=5000) as cliente:
        base = cliente[f"farmared_test_q13_{uuid4().hex}"]
        try:
            base.clientes.create_index("id_cliente", unique=True)
            base.clientes.create_index("dni", unique=True)
            yield base
        finally:
            cliente.drop_database(base.name)


def test_rechazos_conservan_cliente_y_eventos(db):
    datos = {"nombre": "Ana", "apellido": "Gil", "dni": 40111222}
    cliente = crear_cliente(db, datos)
    filtro = {"id_cliente": cliente["id_cliente"]}
    assert cliente["dni"] == "40111222"
    with pytest.raises(ValueError, match="Ya existe un cliente con DNI"):
        crear_cliente(db, {**datos, "dni": " 40111222 "})
    with pytest.raises(ValueError, match="nro_afiliado"):
        modificar_cliente(db, cliente["id_cliente"], {"obra_social": "OSDE"})
    with pytest.raises(ValueError, match="id_cliente"):
        dar_de_baja_cliente(db, {})
    assert db.clientes.count_documents({}) == 1
    assert db.clientes.find_one(filtro, {"_id": 0}) == cliente
    assert db.proyeccion_pendiente.count_documents({}) == 1


def test_contacto_en_documento_con_campos_opcionales_ausentes(db):
    db.clientes.insert_one({"id_cliente": "C001", "dni": "40111222", "activo": True})
    cliente = modificar_cliente(db, "C001", {"telefono": " 11-5555-0000 "})
    assert cliente["telefono"] == "11-5555-0000"
    assert "email" not in cliente
    assert db.proyeccion_pendiente.count_documents({"operacion": "q13.modificacion"}) == 1


def test_baja_repetida_conserva_documento_y_evento(db):
    cliente = crear_cliente(db, {"nombre": "Ana", "apellido": "Gil", "dni": "40111222"})
    id_cliente = cliente["id_cliente"]
    baja = dar_de_baja_cliente(db, id_cliente)
    assert baja == {**cliente, "activo": False}
    assert dar_de_baja_cliente(db, id_cliente) == baja
    assert db.clientes.count_documents({"id_cliente": id_cliente}) == 1
    assert db.proyeccion_pendiente.count_documents({"operacion": "q13.baja"}) == 1
