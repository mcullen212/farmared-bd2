"""q13 · ABM de clientes (MongoDB).

Cada operación escribe el cliente y registra el evento de proyección en la
misma transacción de MongoDB. Neo4j se actualiza después, con el consumidor.
"""

import re

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ..proyeccion.eventos import registrar_evento

OBRAS_SOCIALES = {"OSDE", "Swiss Medical", "PAMI", "IOMA", "Galeno", "Sin cobertura"}
SIN_COBERTURA = "Sin cobertura"
OBLIGATORIOS = ("nombre", "apellido", "dni")
CONTACTO_Y_COBERTURA = ("email", "telefono", "ciudad", "provincia", "obra_social", "nro_afiliado")
CAMPOS_ALTA = ("id_cliente", *OBLIGATORIOS, *CONTACTO_Y_COBERTURA)


def _normalizar_campo(campo, valor):
    if valor is None:
        return None
    if campo == "dni" and type(valor) is int:
        valor = str(valor)
    if not isinstance(valor, str):
        raise ValueError(f"{campo} debe ser texto")
    return valor.strip() or None


def _validar_id_cliente(id_cliente):
    if not isinstance(id_cliente, str) or not id_cliente.strip():
        raise ValueError("id_cliente debe ser un texto no vacío")


def _normalizar_cobertura(doc):
    """Valida obra_social y nro_afiliado. Sin cobertura implica nro_afiliado null."""
    obra = doc.get("obra_social") or SIN_COBERTURA
    if obra not in OBRAS_SOCIALES:
        raise ValueError(f"Obra social inválida: {obra}. Opciones: {sorted(OBRAS_SOCIALES)}")
    doc["obra_social"] = obra
    if obra == SIN_COBERTURA:
        doc["nro_afiliado"] = None
    elif not doc.get("nro_afiliado"):
        raise ValueError("Con obra social hace falta nro_afiliado")


def _siguiente_id(db, session):
    numeros = [
        int(m.group(1))
        for d in db.clientes.find({}, {"id_cliente": 1}, session=session)
        if (m := re.fullmatch(r"C(\d+)", d["id_cliente"]))
    ]
    return f"C{max(numeros, default=0) + 1:03d}"


def _en_transaccion(db, funcion):
    with db.client.start_session() as session:
        return session.with_transaction(funcion)


def crear_cliente(db, datos):
    """Alta de un cliente activo.

    Parámetros:
        datos: dict con nombre, apellido y dni (obligatorios) y, opcionalmente,
               id_cliente, email, telefono, ciudad, provincia, obra_social y
               nro_afiliado. Si falta id_cliente se genera el siguiente.

    Devuelve el documento insertado (sin _id).
    Lanza ValueError si faltan datos, la cobertura es inválida o el DNI ya existe.
    El DNI único lo garantiza el índice único de clientes.dni, no una lectura previa.
    """
    if not isinstance(datos, dict):
        raise ValueError("Los datos del alta deben ser un objeto")
    desconocidos = set(datos) - set(CAMPOS_ALTA)
    if desconocidos:
        raise ValueError(f"Campos no permitidos en el alta: {sorted(desconocidos)}")
    doc = {campo: _normalizar_campo(campo, datos.get(campo)) for campo in CAMPOS_ALTA}
    faltantes = [campo for campo in OBLIGATORIOS if not doc[campo]]
    if faltantes:
        raise ValueError(f"Faltan datos obligatorios: {faltantes}")
    _normalizar_cobertura(doc)
    doc["activo"] = True

    def alta(session):
        id_cliente = doc["id_cliente"] or _siguiente_id(db, session)
        nuevo = {**doc, "id_cliente": id_cliente}
        db.clientes.insert_one(nuevo.copy(), session=session)
        registrar_evento(db, "q13.alta", [{"entidad": "cliente", "id": id_cliente}],
                         session=session)
        return nuevo

    try:
        return _en_transaccion(db, alta)
    except DuplicateKeyError as error:
        campo = next(iter((error.details or {}).get("keyPattern", {})), "dni")
        if campo == "dni":
            raise ValueError(f"Ya existe un cliente con DNI {doc['dni']}") from None
        valor = (error.details or {}).get("keyValue", {}).get(campo, doc.get(campo))
        raise ValueError(f"Ya existe un cliente con {campo} {valor}") from None


def modificar_cliente(db, id_cliente, cambios):
    """Modifica datos de contacto y cobertura de un cliente.

    Parámetros:
        id_cliente: id del cliente.
        cambios: dict con alguno de email, telefono, ciudad, provincia,
                 obra_social, nro_afiliado. Cualquier otro campo se rechaza.

    Devuelve el documento actualizado (sin _id).
    Lanza ValueError si hay campos no permitidos y LookupError si no existe.
    """
    _validar_id_cliente(id_cliente)
    if not isinstance(cambios, dict) or not cambios:
        raise ValueError("Los cambios deben ser un objeto no vacío")
    no_permitidos = set(cambios) - set(CONTACTO_Y_COBERTURA)
    if no_permitidos:
        raise ValueError(f"Solo se pueden modificar {CONTACTO_Y_COBERTURA}; "
                         f"no permitidos: {sorted(no_permitidos)}")
    cambios = {campo: _normalizar_campo(campo, valor) for campo, valor in cambios.items()}

    def modificar(session):
        actual = db.clientes.find_one({"id_cliente": id_cliente}, {"_id": 0}, session=session)
        if actual is None:
            raise LookupError(f"No existe el cliente {id_cliente}")
        nuevo = {**actual, **cambios}
        _normalizar_cobertura(nuevo)
        a_guardar = {**cambios, "obra_social": nuevo["obra_social"],
                     "nro_afiliado": nuevo["nro_afiliado"]}
        resultado = db.clientes.find_one_and_update(
            {"id_cliente": id_cliente}, {"$set": a_guardar},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER, session=session,
        )
        registrar_evento(db, "q13.modificacion", [{"entidad": "cliente", "id": id_cliente}],
                         session=session)
        return resultado

    return _en_transaccion(db, modificar)


def dar_de_baja_cliente(db, id_cliente):
    """Baja lógica: pone activo = False y conserva el historial del cliente.

    Devuelve el documento actualizado (sin _id). Es idempotente.
    Lanza LookupError si el cliente no existe.
    """
    _validar_id_cliente(id_cliente)

    def baja(session):
        resultado = db.clientes.find_one_and_update(
            {"id_cliente": id_cliente, "activo": {"$ne": False}}, {"$set": {"activo": False}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER, session=session,
        )
        if resultado is None:
            actual = db.clientes.find_one({"id_cliente": id_cliente}, {"_id": 0}, session=session)
            if actual is None:
                raise LookupError(f"No existe el cliente {id_cliente}")
            return actual
        registrar_evento(db, "q13.baja", [{"entidad": "cliente", "id": id_cliente}],
                         session=session)
        return resultado

    return _en_transaccion(db, baja)
