# FarmaRed · TPO de Bases de Datos II

FarmaRed usa MongoDB para las ventas, el stock y las recetas, y Neo4j para consultar las relaciones entre clientes, ventas y sucursales.

## Estructura

- `docs/` contiene el [enunciado](docs/TPO_FarmaRed.pdf).
- `data/original/` contiene los nueve CSV de la cátedra.
- `data/extra/` los registros adicionales se guardan por separado.
- `src/` contiene la carga de datos y el acceso a MongoDB.
- `tests/` las pruebas.

## Preparar el entorno

En GitHub, abrí **Code → Codespaces → Create codespace** en la rama que tenga esta
configuración. Codespaces inicia MongoDB y Neo4j y abre la terminal del proyecto
cuando MongoDB es primario del replica set y Neo4j responde a Cypher.

En local, con Docker iniciado, ejecutá desde la raíz del repositorio:

```sh
docker compose up -d --wait
docker compose exec workspace bash
```

En Codespaces, usá la terminal que abre el entorno. Los comandos de Python
de las secciones siguientes se ejecutan dentro de `workspace` o desde esa
terminal.

Compose configura `MONGODB_URI` para la base `farmared` del replica set `rs0`
y `NEO4J_URI`, `NEO4J_USER` y `NEO4J_PASSWORD` para conectarse a Neo4j. Los
datos persisten en volúmenes al detener el entorno.

Para probar una transacción real desde la máquina que ejecuta Docker Compose,
ejecutá lo siguiente. La prueba confirma una escritura y la elimina al terminar.

```sh
docker compose exec -T mongo mongosh 'mongodb://mongo:27017/farmared?replicaSet=rs0' --quiet --file /dev/stdin <<'JS'
const collection = 'infra_smoke_' + new ObjectId().toHexString();
const session = db.getMongo().startSession();
try {
  db.createCollection(collection);
  session.withTransaction(() => {
    session.getDatabase('farmared').getCollection(collection).insertOne({_id: 'committed'});
  });
  if (!db.getCollection(collection).findOne({_id: 'committed'})) {
    throw new Error('No se confirmó la escritura de la transacción');
  }
  print('Transacción confirmada');
} finally {
  session.endSession();
  db.getCollection(collection).drop();
}
JS
```

## Cargar MongoDB y construir el grafo de Neo4j

Desde la terminal del contenedor de trabajo o del Codespace:

```sh
python -m venv /tmp/farmared-venv
source /tmp/farmared-venv/bin/activate
python -m pip install -r requirements.txt
python -m src.carga_mongo
python -m src.proyeccion.construir
```

Volvé a activar el entorno virtual al abrir otra terminal. Si se recrea el
contenedor, volvé a crear el entorno virtual e instalar las dependencias.
El último comando proyecta clientes, ventas, recetas, farmacéuticos y
sucursales desde MongoDB a Neo4j.

El loader valida los CSV originales y los extras disponibles antes de escribir.
Crea los índices e inserta en una transacción los IDs que aún no existen. Una
segunda ejecución conserva las ventas y los saldos que cambiaron en operación.
El stock del CSV es el saldo inicial. Las ventas completadas se importan con
`movimiento_stock.estado = "historico"` y su sucursal se toma del farmacéutico
del CSV.

### Reiniciar y verificar la base de demostración

Usá `farmared_demo` para verificar la carga desde cero. Desde la terminal del
contenedor de trabajo o del Codespace, con el entorno virtual activo:

```sh
MONGODB_URI='mongodb://mongo:27017/farmared_demo?replicaSet=rs0' \
  python -m src.carga_mongo --reiniciar-demo
MONGODB_URI='mongodb://mongo:27017/farmared_demo?replicaSet=rs0' \
  python -m src.carga_mongo
```

El primer comando reemplaza los datos importados y vacía la cola de proyección
de `farmared_demo`. Deberías ver 18 clientes, 15 sucursales, 17 farmacéuticos,
15 proveedores, 23 productos, 19 recetas, 28 lotes y 26 ventas. Los 32 ítems
quedan dentro de `ventas.detalle`. El segundo comando debe mostrar `0 nuevos`
en cada colección. Para consultar esos datos en Neo4j, seguí las instrucciones de la sección Neo4j.

## Ejecutar las consultas

Corré estos comandos desde `workspace` o Codespaces, con el entorno virtual
activo y la carga inicial completada.

### MongoDB

```sh
python -m src.consultas_mongo q01
python -m src.consultas_mongo q02
python -m src.consultas_mongo q05 --hoy 2026-11-12
python -m src.consultas_mongo q06 --hoy 2026-11-12
python -m src.consultas_mongo q07
python -m src.consultas_mongo q08
python -m src.consultas_mongo q09
python -m src.consultas_mongo q11 --hoy 2026-11-12
python -m src.consultas_mongo q12 --hoy 2026-11-12
```

La salida usa JSON extendido de MongoDB. En q05, q06, q11 y q12, `--hoy`
fija la fecha de referencia. Si omitís el argumento, se usa el día de negocio
en Buenos Aires. La carga instala la vista de q11.

Para consultar los datos de demostración, indicá la base en el comando:

```sh
MONGODB_URI='mongodb://mongo:27017/farmared_demo?replicaSet=rs0' \
  python -m src.consultas_mongo q01
```

### Neo4j

```sh
python -m src.consultas_neo4j q03 C001
python -m src.consultas_neo4j q04
python -m src.consultas_neo4j q10 S002
```

En q03, el argumento es el ID del cliente. En q10, es el ID de la sucursal.
Si querés consultar el grafo con datos de demostración, reconstruí la
proyección después de cargar `farmared_demo`. El comando borra el grafo
actual antes de reconstruirlo:

```sh
MONGODB_URI='mongodb://mongo:27017/farmared_demo?replicaSet=rs0' \
  python -m src.proyeccion.construir --reset
```

Para volver al grafo de `farmared`, ejecutá
`python -m src.proyeccion.construir --reset` con la configuración de Compose.

Desde la terminal que ejecuta Docker Compose, podés inspeccionar el grafo
con Cypher:

```sh
docker compose exec -T neo4j cypher-shell -u neo4j -p farmared-local \
  'MATCH (n) RETURN n LIMIT 10;'
```

### q13 · ABM de clientes y actualización del grafo

```sh
python -m src.abm_clientes ver C001
python -m src.abm_clientes alta --json '{"nombre": "Ana", "apellido": "Gil", "dni": "40111222", "obra_social": "OSDE", "nro_afiliado": "OS-1"}'
```

Reemplazá `ID_DEL_ALTA` por el `id_cliente` devuelto por el alta:

```sh
id_cliente='ID_DEL_ALTA'
python -m src.abm_clientes modificar "$id_cliente" --json '{"telefono": "11-5555-0000"}'
python -m src.abm_clientes baja "$id_cliente"
python -m src.proyeccion.consumidor
```

Un alta con un DNI existente se rechaza gracias al índice único de
`clientes.dni`. Cada alta, modificación o baja deja un evento en
`proyeccion_pendiente` dentro de la misma transacción. El consumidor relee el
estado actual de MongoDB, actualiza Neo4j con `MERGE` y marca el evento como
procesado. Si Neo4j no responde, el evento queda pendiente para la próxima
corrida.

Para q14, P3 registra la venta con
`registrar_evento(db, "q14.venta", [{"entidad": "venta", "id": ...}, {"entidad": "receta", "id": ...}], session=session)`
de `src/proyeccion/eventos.py`, dentro de su transacción.

### Acceso para q14 y q15

Instanciá `RepositorioMongo(db)` y abrí una sesión con `repo.iniciar_sesion()`.
Dentro de `session.with_transaction(...)`, pasá `session=session` a las
operaciones de las colecciones y a `repo.lotes_fefo` y
`repo.decrementar_lote`. Los servicios controlan el commit y el abort.

Para probar stock insuficiente con los CSV iniciales, usá la sucursal `S001`
y el farmacéutico `F001` con una unidad de `PRD001` seguida de una unidad
de `PRD101`. Ambos son de venta libre. El primero tiene el lote `L001`
en esa sucursal y el segundo tiene un lote en `S101`. Con el cliente activo `C001`
y fecha de prueba 2026-11-11, el caso permite verificar que el saldo de
`L001` se conserva al abortar.

### Tests

Con las dependencias de `requirements.txt` instaladas, los tests unitarios de
P1 se pueden ejecutar sin levantar MongoDB ni Neo4j.

```sh
python -m pytest tests/test_consultas_p1.py tests/test_carga_p1.py
```

Los tests de integración necesitan MongoDB y Neo4j levantados. Reinician
`farmared_demo` y el grafo, así que después hay que reconstruir el grafo de la
base habitual con `construir --reset`.

```sh
python -m pytest tests
```
