"""Ejecuta las consultas de FarmaRed que leen del grafo de Neo4j (q03, q04, q10)."""

import argparse
import json

from .conexion_neo4j import abrir_neo4j_driver
from .consultas.q03 import q03
from .consultas.q04 import q04
from .consultas.q10 import q10


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="consulta", required=True)
    sub.add_parser("q03", help="Historial de un cliente").add_argument("id_cliente")
    sub.add_parser("q04", help="Clientes con más de una receta")
    sub.add_parser("q10", help="Clientes atendidos en una sucursal").add_argument("id_sucursal")
    args = parser.parse_args()

    with abrir_neo4j_driver() as driver:
        try:
            if args.consulta == "q03":
                resultado = q03(driver, args.id_cliente)
            elif args.consulta == "q04":
                resultado = q04(driver)
            else:
                resultado = q10(driver, args.id_sucursal)
        except LookupError as error:
            raise SystemExit(str(error)) from None
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
