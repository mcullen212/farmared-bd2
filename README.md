# FarmaRed · TPO de Bases de Datos II

FarmaRed usa MongoDB para las ventas, el stock y las recetas, y Neo4j para consultar las relaciones entre clientes, ventas y sucursales.

## Estructura

- `docs/` contiene el [enunciado](docs/TPO_FarmaRed.pdf).
- `data/original/` contiene los nueve CSV de la cátedra. Los registros adicionales se pueden guardar por separado en `data/extra/` al preparar la carga.
- `src/` contiene la carga de datos y el acceso a MongoDB.
- `tests/` queda reservada para las pruebas.

## Entorno de desarrollo

En GitHub, abrí **Code → Codespaces → Create codespace** en la rama que tenga esta
configuración. Codespaces inicia MongoDB y Neo4j y abre la terminal del proyecto
cuando MongoDB es primario del replica set y Neo4j responde a Cypher.

Desde una máquina con Docker Compose, ejecutá estos comandos en la raíz del repositorio.

```sh
docker compose up -d --wait
```

Dentro del contenedor de trabajo, usá `MONGODB_URI` para conectarte a la base
`farmared` y `NEO4J_URI`, `NEO4J_USER` y `NEO4J_PASSWORD` para conectarte al
grafo. Las conexiones usan la red interna de Docker y las credenciales son de
desarrollo. Los datos persisten en volúmenes al detener el entorno.

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

## Carga inicial de MongoDB

Si estás en la terminal de tu Mac, ejecutá estos comandos desde la raíz del
repositorio después de iniciar Docker Compose. La instalación y la carga se
ejecutan dentro de `workspace`, donde Compose ya configuró `MONGODB_URI`.
Estos comandos cargan la base habitual `farmared`.

```sh
docker compose exec workspace python -m venv /tmp/farmared-venv
docker compose exec workspace /tmp/farmared-venv/bin/python -m pip install -r requirements.txt
docker compose exec workspace /tmp/farmared-venv/bin/python -m src.carga_mongo
```

Desde la terminal del Codespace, o si ya entraste con
`docker compose exec workspace bash`, ejecutá estos comandos:

```sh
python -m venv /tmp/farmared-venv
/tmp/farmared-venv/bin/python -m pip install -r requirements.txt
/tmp/farmared-venv/bin/python -m src.carga_mongo
```

El entorno virtual mantiene PyMongo separado del Python del sistema. Podés
ignorar el aviso de actualización de pip. Si se recrea el contenedor, volvé
a crear el entorno virtual e instalar las dependencias.

El loader valida los CSV originales y los extras disponibles antes de escribir.
Crea los índices e inserta en una transacción los IDs que aún no existen. Una
segunda ejecución conserva las ventas y los saldos que cambiaron en operación.
El stock del CSV es el saldo inicial. Las ventas completadas se importan con
`movimiento_stock.estado = "historico"` y su sucursal se toma del farmacéutico
del CSV.

### Reiniciar y verificar la base de demostración

Usá `farmared_demo` para ver la carga desde cero y conservar los datos de
`farmared`. Desde la raíz del repo en la terminal de tu Mac, ejecutá:

```sh
docker compose exec -e 'MONGODB_URI=mongodb://mongo:27017/farmared_demo?replicaSet=rs0' workspace /tmp/farmared-venv/bin/python -m src.carga_mongo --reiniciar-demo
docker compose exec -e 'MONGODB_URI=mongodb://mongo:27017/farmared_demo?replicaSet=rs0' workspace /tmp/farmared-venv/bin/python -m src.carga_mongo
```

Desde la terminal del Codespace o del contenedor de trabajo, ejecutá:

```sh
MONGODB_URI='mongodb://mongo:27017/farmared_demo?replicaSet=rs0' \
  /tmp/farmared-venv/bin/python -m src.carga_mongo --reiniciar-demo
MONGODB_URI='mongodb://mongo:27017/farmared_demo?replicaSet=rs0' \
  /tmp/farmared-venv/bin/python -m src.carga_mongo
```

El primer comando reemplaza los datos importados y vacía la cola de proyección
de `farmared_demo`. Deberías ver 18 clientes, 15 sucursales, 17 farmacéuticos,
15 proveedores, 23 productos, 19 recetas, 28 lotes y 26 ventas. Los 32 ítems
quedan dentro de `ventas.detalle`. El segundo comando debe mostrar `0 nuevos`
en cada colección. Si se usa Neo4j con esos datos, hay que reconstruir el grafo
después del reinicio.

### Ejecutar las consultas de MongoDB

Con `farmared_demo` cargada, desde la terminal de tu Mac:

```sh
docker compose exec -e 'MONGODB_URI=mongodb://mongo:27017/farmared_demo?replicaSet=rs0' workspace /tmp/farmared-venv/bin/python -m src.consultas_mongo q01
```

En Codespaces o dentro de `workspace`:

```sh
MONGODB_URI='mongodb://mongo:27017/farmared_demo?replicaSet=rs0' \
  /tmp/farmared-venv/bin/python -m src.consultas_mongo q01
```

Reemplazá `q01` por cualquiera de las ocho consultas de P1. La salida usa
JSON extendido de MongoDB. Para reproducir los ejemplos de q05, q11 y q12,
agregá `--hoy 2026-11-12` después del nombre de la consulta. Sin ese argumento
se usa el día de negocio en Buenos Aires. La carga instala la vista de q11.
Si cargaste los datos con una versión anterior, repetí la carga para crearla.

Las [decisiones y ejemplos de P1](docs/DECISIONES_CONSULTAS_P1.md) incluyen
los resultados de referencia para los CSV del repositorio.

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
