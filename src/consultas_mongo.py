"""Ejecuta consultas de lectura de FarmaRed en MongoDB."""

import argparse
import os
from datetime import date

from bson import json_util
from pymongo import MongoClient


from .consultas.q01 import q01
from .consultas.q02 import q02
from .consultas.q05 import q05
from .consultas.q07 import q07
from .consultas.q08 import q08
from .consultas.q09 import q09
from .consultas.q11 import q11
from .consultas.q12 import q12


def main():
    consultas = {consulta.__name__: consulta for consulta in (q01, q02, q05, q07, q08, q09, q11, q12)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("consulta", choices=consultas)
    parser.add_argument("--hoy", type=date.fromisoformat, metavar="AAAA-MM-DD",
                        help="Fecha de referencia para reproducir q05, q11 o q12")
    args = parser.parse_args()
    if args.hoy is not None and args.consulta not in {"q05", "q11", "q12"}:
        parser.error("--hoy solo se aplica a q05, q11 y q12")

    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise SystemExit("Definí MONGODB_URI con el nombre de la base de datos.")

    with MongoClient(uri) as cliente:
        opciones = {"hoy": args.hoy} if args.hoy is not None else {}
        resultado = consultas[args.consulta](cliente.get_default_database(), **opciones)
    print(json_util.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
