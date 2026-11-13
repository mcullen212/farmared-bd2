"""ABM de clientes (q13) desde la terminal.

Ejemplos:
  python -m src.abm_clientes ver C001
  python -m src.abm_clientes alta --json '{"nombre": "Ana", "apellido": "Gil", "dni": "40111222"}'
  python -m src.abm_clientes modificar C001 --json '{"telefono": "11-5555-0000"}'
  python -m src.abm_clientes baja C001

Cada cambio deja un evento en proyeccion_pendiente; para verlo en Neo4j hay que
correr después `python -m src.proyeccion.consumidor`.
"""

import argparse
import json

from bson import json_util

from .conexion_neo4j import abrir_mongo
from .consultas.q13 import crear_cliente, dar_de_baja_cliente, modificar_cliente


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="accion", required=True)
    sub.add_parser("ver").add_argument("id_cliente")
    sub.add_parser("alta").add_argument("--json", required=True, type=json.loads)
    modificar = sub.add_parser("modificar")
    modificar.add_argument("id_cliente")
    modificar.add_argument("--json", required=True, type=json.loads)
    sub.add_parser("baja").add_argument("id_cliente")
    args = parser.parse_args()

    cliente, db = abrir_mongo()
    with cliente:
        try:
            if args.accion == "ver":
                resultado = db.clientes.find_one({"id_cliente": args.id_cliente}, {"_id": 0})
                if resultado is None:
                    raise LookupError(f"No existe el cliente {args.id_cliente}")
            elif args.accion == "alta":
                resultado = crear_cliente(db, args.json)
            elif args.accion == "modificar":
                resultado = modificar_cliente(db, args.id_cliente, args.json)
            else:
                resultado = dar_de_baja_cliente(db, args.id_cliente)
        except (ValueError, LookupError) as error:
            raise SystemExit(f"Rechazado: {error}") from None
    print(json_util.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
