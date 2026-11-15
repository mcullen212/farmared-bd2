def q09(db):
    """Devuelve ventas libres menores a ARS 5.000, salvo las anuladas."""
    return list(db.ventas.find({
        "tipo": "Venta libre",
        "total": {"$lt": 5000},
        "estado": {"$ne": "Anulada"},
    }).sort("id_venta", 1))
