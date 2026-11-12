from pymongo.errors import OperationFailure

from .fechas import dia_de_negocio

VISTA = "vista_ingresos_por_farmaceutico"
AGRUPACION = [
    {"$match": {"estado": "Completada"}},
    {"$group": {
        "_id": {
            "id_farmaceutico": "$id_farmaceutico",
            "anio": {"$year": "$fecha"},
            "mes": {"$month": "$fecha"},
        },
        "ingresos_totales": {"$sum": "$total"},
    }},
    {"$project": {
        "_id": 0,
        "id_farmaceutico": "$_id.id_farmaceutico",
        "anio": "$_id.anio",
        "mes": "$_id.mes",
        "ingresos_totales": 1,
    }},
]


def crear_vista_ingresos(db):
    """Instala la vista de ingresos en MongoDB durante la carga."""
    try:
        db.create_collection(VISTA, viewOn="ventas", pipeline=AGRUPACION, check_exists=False)
    except OperationFailure as error:
        if error.code != 48:
            raise
        existente = next(db.list_collections(filter={"name": VISTA}), {})
        opciones = existente.get("options", {})
        if (existente.get("type") != "view" or opciones.get("viewOn") != "ventas"
                or opciones.get("pipeline") != AGRUPACION):
            raise


def q11(db, *, hoy=None):
    """Devuelve desde la vista los ingresos por farmacéutico en el mes actual."""
    hoy = hoy or dia_de_negocio()
    return list(db[VISTA].find({"anio": hoy.year, "mes": hoy.month}).sort("id_farmaceutico", 1))
