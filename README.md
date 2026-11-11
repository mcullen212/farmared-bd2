# FarmaRed · TPO de Bases de Datos II

FarmaRed usa MongoDB para las ventas, el stock y las recetas, y Neo4j para consultar las relaciones entre clientes, ventas y sucursales.

## Estructura

- `docs/` contiene el [enunciado](docs/TPO_FarmaRed.pdf).
- `data/original/` contiene los nueve CSV de la cátedra. Los registros adicionales se pueden guardar por separado en `data/extra/` al preparar la carga.
- `src/` queda reservada para la implementación.
- `tests/` queda reservada para las pruebas.

## Entorno de desarrollo

En GitHub, abrí **Code → Codespaces → Create codespace** en la rama que tenga esta
configuración. Codespaces inicia MongoDB y Neo4j y abre la terminal del proyecto
cuando MongoDB es primario del replica set y Neo4j responde a Cypher.

Desde una máquina con Docker Compose, ejecutá estos comandos en la raíz del repositorio.

```sh
docker compose up -d --wait
docker compose exec workspace bash
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

La carga de los CSV y las consultas se incorporarán en las siguientes etapas.
La carga se ejecutará desde la terminal del proyecto con las conexiones del entorno.
