def relacion(coleccion, campo, destino, nombre):
    """Devuelve las etapas para incorporar una referencia obligatoria."""
    return [
        {"$lookup": {
            "from": coleccion,
            "localField": campo,
            "foreignField": destino,
            "as": nombre,
        }},
        {"$unwind": f"${nombre}"},
    ]
