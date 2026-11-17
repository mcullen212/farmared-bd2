"""Demo guiada de FarmaRed: tres consultas en MongoDB y dos en Neo4j.

Pasos:
    0. Reinicia farmared_demo y reconstruye el grafo (la demo se puede repetir).
    1. q07 (MongoDB, agregación): top 5 de productos vendidos.
    2. q14 + q15 (MongoDB, servicio): venta con receta, descuento FEFO y receta actualizada.
    3. q14 + q15 (MongoDB, servicio): venta rechazada por stock, sin cambios en la base.
    4. q03 (Neo4j): historial del cliente, antes y después de proyectar la venta.
    5. q10 (Neo4j): clientes atendidos en una sucursal, con farmacéutico activo o no.

Uso (con MONGODB_URI apuntando a la base farmared_demo):
    python -m src.demo                # todos los pasos, con pausa entre pasos (Enter)
    python -m src.demo --sin-pausa
    python -m src.demo --paso 2       # un solo paso (lo usa la presentación en Slidev)

Los pasos 2 a 5 dependen de los anteriores: correrlos en orden, empezando por el 0.
"""

import argparse
from datetime import date

from .carga_mongo import cargar, preparar_datos
from .conexion_neo4j import abrir_mongo, abrir_neo4j_driver
from .consultas.q03 import q03
from .consultas.q07 import q07
from .consultas.q10 import q10
from .consultas.q14 import registrar_venta
from .proyeccion.construir import construir_grafo
from .proyeccion.consumidor import procesar_pendientes

# Fecha fija para FEFO: así el lote L005 (vence el 30/11/2026) sigue vigente
# y el ejemplo da siempre el mismo resultado, se corra el día que se corra.
HOY = date(2026, 11, 16)

CLIENTE, FARMACEUTICO, SUCURSAL, RECETA, PRODUCTO = "C006", "F002", "S001", "RC004", "PRD003"
SUCURSAL_Q10 = "S002"  # F004 (inactivo) atendió ahí a C004

VENTA_OK = {
    "id_venta": "VDEMO1", "id_cliente": CLIENTE, "id_farmaceutico": FARMACEUTICO,
    "id_receta": RECETA, "fecha": HOY.isoformat(), "medio_pago": "Obra social",
    "detalle": [{"id_producto": PRODUCTO, "cantidad": 42}],
}
# PRD005 (Metformina) no tiene lotes en S001: la venta entera se tiene que rechazar.
VENTA_RECHAZADA = {
    "id_venta": "VDEMO2", "id_cliente": CLIENTE, "id_farmaceutico": FARMACEUTICO,
    "id_receta": RECETA, "fecha": HOY.isoformat(), "medio_pago": "Obra social",
    "detalle": [{"id_producto": PRODUCTO, "cantidad": 1}, {"id_producto": "PRD005", "cantidad": 1}],
}

PAUSA = True


def titulo(texto):
    print(f"\n{'=' * 70}\n{texto}\n{'=' * 70}")


def subtitulo(texto):
    print(f"\n--- {texto}")


def pausa():
    if PAUSA:
        input("\n[Enter para seguir] ")


def fmt(valor):
    if valor is None:
        return "-"
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d")
    return str(valor)


def tabla(filas, columnas):
    """Imprime una lista de dicts como tabla de texto con las columnas pedidas."""
    if not filas:
        print("(sin filas)")
        return
    celdas = [[fmt(f.get(c)) for c in columnas] for f in filas]
    anchos = [max(len(c), *(len(fila[i]) for fila in celdas)) for i, c in enumerate(columnas)]
    print("  ".join(c.ljust(a) for c, a in zip(columnas, anchos)))
    print("  ".join("-" * a for a in anchos))
    for fila in celdas:
        print("  ".join(v.ljust(a) for v, a in zip(fila, anchos)))


def mostrar_lotes(db):
    lotes = db.stock_lotes.find(
        {"id_producto": PRODUCTO, "id_sucursal": SUCURSAL}, {"_id": 0}
    ).sort("vencimiento", 1)
    tabla(list(lotes), ["id_lote", "id_producto", "vencimiento", "unidades"])


def mostrar_receta(db):
    receta = db.recetas.find_one({"id_receta": RECETA}, {"_id": 0})
    receta["dispensas"] = f"{receta['dispensas_realizadas']} de {receta['dispensas_autorizadas']}"
    tabla([receta], ["id_receta", "tipo", "dispensas", "proxima_dispensa", "estado"])


def mostrar_avisos(db):
    pendientes = db.proyeccion_pendiente.count_documents({"estado": "pendiente"})
    print(f"Avisos pendientes para Neo4j (proyeccion_pendiente): {pendientes}")


def paso0(db, driver):
    titulo("Paso 0 · Preparar: cargar MongoDB desde los CSV y construir el grafo")
    nuevos = cargar(db, preparar_datos(), reiniciar_demo=True)
    print("MongoDB:")
    for coleccion, cantidad in nuevos.items():
        print(f"  {coleccion}: {cantidad}")
    conteos = construir_grafo(db, driver, reset=True)
    print("Neo4j nodos:", ", ".join(f"{e} {n}" for e, n in conteos["nodos"].items()))
    print("Neo4j relaciones:", ", ".join(f"{e} {n}" for e, n in conteos["relaciones"].items()))


def paso1(db):
    titulo("Paso 1 · q07 (MongoDB, agregación): top 5 de productos más vendidos")
    print("Solo ventas Completada. $unwind del detalle embebido + $group + $lookup al catálogo.\n")
    filas = [{"#": i, "id_producto": r["id_producto"], "producto": r["producto"]["nombre"],
              "unidades": r["unidades_vendidas"]} for i, r in enumerate(q07(db), 1)]
    tabla(filas, ["#", "id_producto", "producto", "unidades"])


def paso2(db):
    titulo("Paso 2 · q14 + q15 (MongoDB, servicio): registrar una venta con receta")
    print(f"{CLIENTE} compra 42 x {PRODUCTO} (Amoxicilina) con {FARMACEUTICO} en {SUCURSAL}, "
          f"usando la receta {RECETA}.")
    subtitulo("ANTES · lotes de la sucursal (orden FEFO: vence antes, sale antes)")
    mostrar_lotes(db)
    subtitulo("ANTES · receta")
    mostrar_receta(db)
    mostrar_avisos(db)
    pausa()

    venta = registrar_venta(db, VENTA_OK, hoy=HOY)
    subtitulo("Venta registrada")
    tabla([venta], ["id_venta", "id_cliente", "id_receta", "fecha", "total", "estado"])
    subtitulo("Lotes que usó q15")
    tabla(venta["movimiento_stock"]["asignaciones"], ["id_producto", "id_lote", "cantidad"])
    subtitulo("DESPUÉS · lotes")
    mostrar_lotes(db)
    subtitulo("DESPUÉS · receta")
    mostrar_receta(db)
    mostrar_avisos(db)


def paso3(db):
    titulo("Paso 3 · q14 + q15 (MongoDB, servicio): venta rechazada")
    print(f"Misma venta, pero agrega PRD005 (Metformina), que no tiene lotes en {SUCURSAL}.")
    try:
        registrar_venta(db, VENTA_RECHAZADA, hoy=HOY)
        print("¡La venta no debería haberse registrado!")
    except ValueError as error:
        print(f"\nVenta rechazada: {error}")
    subtitulo("La transacción se revirtió: nada cambió")
    existe = db.ventas.count_documents({"id_venta": VENTA_RECHAZADA["id_venta"]})
    print(f"¿Existe {VENTA_RECHAZADA['id_venta']}? {'sí' if existe else 'no'}")
    mostrar_lotes(db)
    mostrar_receta(db)
    mostrar_avisos(db)


def mostrar_historial(driver):
    resultado = q03(driver, CLIENTE)
    c = resultado["cliente"]
    print(f"Cliente {c['id']}: {c['nombre']} {c['apellido']}")
    tabla(resultado["historial"], ["fecha", "evento", "id", "estado", "total", "sucursal"])


def paso4(db, driver):
    titulo("Paso 4 · q03 (Neo4j): historial del cliente")
    print("Recorre Cliente -REALIZO-> Venta -ATENDIDA_POR-> Farmacéutico -TRABAJA_EN-> Sucursal")
    print("y Cliente -TIENE_RECETA-> Receta.")
    subtitulo("Grafo todavía sin proyectar la venta nueva (consistencia eventual)")
    mostrar_historial(driver)
    pausa()
    subtitulo("Corremos el consumidor: lee proyeccion_pendiente y actualiza Neo4j")
    print(procesar_pendientes(db, driver))
    mostrar_avisos(db)
    subtitulo("Ahora la venta aparece en el grafo")
    mostrar_historial(driver)


def paso5(driver):
    titulo(f"Paso 5 · q10 (Neo4j): clientes atendidos en la sucursal {SUCURSAL_Q10}")
    print("Tres saltos: Sucursal <-TRABAJA_EN- Farmacéutico <-ATENDIDA_POR- Venta <-REALIZO- Cliente")
    print("Cuenta también las ventas de farmacéuticos inactivos: C004 compró con F004, dado de baja.\n")
    tabla(q10(driver, SUCURSAL_Q10), ["id_cliente", "nombre", "apellido", "activo"])


def main():
    global PAUSA
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-pausa", action="store_true", help="No espera Enter entre pasos")
    parser.add_argument("--paso", type=int, choices=range(6), help="Corre solo ese paso (0 a 5)")
    args = parser.parse_args()
    PAUSA = not args.sin_pausa

    cliente, db = abrir_mongo()
    if db.name != "farmared_demo":
        raise SystemExit("La demo reinicia la base: apuntá MONGODB_URI a farmared_demo.")
    with cliente, abrir_neo4j_driver() as driver:
        pasos = [lambda: paso0(db, driver), lambda: paso1(db), lambda: paso2(db),
                 lambda: paso3(db), lambda: paso4(db, driver), lambda: paso5(driver)]
        if args.paso is not None:
            try:
                pasos[args.paso]()
            except ValueError as error:
                raise SystemExit(f"\nError: {error}\nLos pasos van en orden: para reiniciar, "
                                 "corré primero el paso 0.") from None
            return
        for i, paso in enumerate(pasos):
            paso()
            if i < len(pasos) - 1:
                pausa()
    print("\nFin de la demo.")


if __name__ == "__main__":
    main()
