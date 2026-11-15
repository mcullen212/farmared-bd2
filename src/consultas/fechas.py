from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def dia_de_negocio():
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def rango_hasta_hoy(desde, hoy):
    """Representa el intervalo inclusivo de días del negocio en BSON."""
    return {
        "$gte": datetime.combine(desde, time.min, timezone.utc),
        "$lt": datetime.combine(hoy + timedelta(days=1), time.min, timezone.utc),
    }
