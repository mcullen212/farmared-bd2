**Trabajo Práctico Obligatorio**

**Sistema de Gestión de Red de Farmacias**
FarmaRed usa MongoDB para las ventas, el stock y las recetas, y Neo4j para consultar las relaciones entre clientes, ventas y sucursales.

**INSTITUTO TECNOLÓGICO DE BUENOS AIRES**

**72.41 \- Base de Datos II 2026c2**

Grupo 7

Integrantes del grupo:

| 64660 | Jonathan Lucas Blankleder           |
| :---- | :---------------------------------- |
| 62560 | Martina Schvartz Tallone            |
| 63065 | Magdalena Itziar Cullen De Erquiaga |


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
El nombre `mongo` se resuelve dentro de la red de Compose. Si estás en la
terminal de tu Mac, entrá a `workspace` antes de ejecutar los módulos de Python.

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

Volvé a activar el entorno con `source /tmp/farmared-venv/bin/activate` al
abrir otra terminal dentro del contenedor. Si Python indica que falta
`pytest`, ejecutá `python -m pip install -r requirements.txt` con el entorno activo.
Si se recrea el contenedor, volvé a crear el entorno virtual e instalar las
dependencias.
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

Indicá el código de la consulta. Las consultas temporales admiten la opción
`--hoy` con una fecha `AAAA-MM-DD`.

```text
python -m src.consultas_mongo <consulta>
python -m src.consultas_mongo <consulta_temporal> --hoy <AAAA-MM-DD>
```

Ejemplos

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

```text
python -m src.consultas_neo4j q03 <id_cliente>
python -m src.consultas_neo4j q04
python -m src.consultas_neo4j q10 <id_sucursal>
```

Ejemplos

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

### Servicios de escritura en una base de prueba

Desde `workspace` o Codespaces, con el entorno virtual activo, creá una base
para los ejemplos de Q13 a Q15. Ejecutá los comandos siguientes en esa misma
terminal para conservar `MONGODB_URI`.

```sh
export MONGODB_URI="mongodb://mongo:27017/farmared_servicios_demo_$(date +%s)?replicaSet=rs0"
python -m src.carga_mongo
```

#### Q13 · ABM de clientes

```text
# Alta de cliente
python -m src.abm_clientes alta --json '{
  "nombre": "<nombre>",
  "apellido": "<apellido>",
  "dni": "<dni>",
  "obra_social": "<obra_social>",
  "nro_afiliado": "<numero_de_afiliado>"
}'

# Modificación de contacto y cobertura
python -m src.abm_clientes modificar <id_cliente> --json '{
  "telefono": "<telefono>",
  "obra_social": "<obra_social>",
  "nro_afiliado": "<numero_de_afiliado>"
}'

# Baja lógica del cliente
python -m src.abm_clientes baja <id_cliente>

# Consulta de un cliente por ID
python -m src.abm_clientes ver <id_cliente>
```

En el alta son obligatorios `nombre`, `apellido` y `dni`. Incluí
`nro_afiliado` cuando corresponda a la cobertura. En la modificación,
enviá solo los campos que quieras cambiar.

**Ejemplo.** El último comando repite el alta para verificar el rechazo por DNI duplicado.

El alta devuelve el ID del cliente. Con los CSV actuales, el ejemplo devuelve
`C111`. Si recibís otro ID, usalo para la modificación y la baja.

```sh
# Alta de cliente
datos='{"nombre":"Ana","apellido":"Gil","dni":"40111222","obra_social":"OSDE","nro_afiliado":"OS-1"}'
python -m src.abm_clientes alta --json "$datos"

# Modificación de contacto y cobertura
id_cliente=C111
python -m src.abm_clientes modificar "$id_cliente" \
  --json '{"telefono":"11-5555-0000","obra_social":"Sin cobertura"}'

# Baja lógica del cliente
python -m src.abm_clientes baja "$id_cliente"

# Rechazo de un alta por DNI duplicado
python -m src.abm_clientes alta --json "$datos"
```

El último comando devuelve `Rechazado: Ya existe un cliente con DNI 40111222`
gracias al índice único de `clientes.dni`. Cada alta, modificación o baja deja un evento en
`proyeccion_pendiente` dentro de la misma transacción. El consumidor relee el
estado actual de MongoDB, actualiza Neo4j con `MERGE` y marca el evento como
procesado. Si Neo4j no responde, el evento queda pendiente para la próxima
corrida.

#### Q14 y Q15 · Registro de venta y descuento de stock

```text
# Q14 · Registro de venta
python -m src.consultas.q14 --json '{
  "id_venta": "<id_venta>",
  "id_cliente": "<id_cliente>",
  "id_farmaceutico": "<id_farmaceutico>",
  "id_receta": "<id_receta>",
  "fecha": "<AAAA-MM-DD>",
  "medio_pago": "<medio_pago>",
  "detalle": [{"id_producto": "<id_producto>", "cantidad": 1}]
}' [--hoy <AAAA-MM-DD>]

# Q15 · Descuento de stock por ID de venta
python -m src.consultas.q15 <id_venta> [--hoy <AAAA-MM-DD>]
```

En Q14 podés omitir `id_venta` y `fecha`. Incluí `id_receta` si la venta
requiere receta. Reemplazá `1` por la cantidad entera de cada ítem y agregá
otros ítems a `detalle` según la venta. Los corchetes alrededor de
`--hoy` indican que esa opción es facultativa.

**Ejemplo.** Registrar una venta libre y volver a invocar el descuento sobre ella.

En la base de prueba recién cargada, ejecutá estos comandos una vez con
un ID de venta nuevo. La fecha explícita permite reproducir el ejemplo con
los vencimientos de los CSV. Si omitís `--hoy`, se usa el día de negocio.

```sh
# Q14 · Registro de una venta libre
python -m src.consultas.q14 --hoy 2026-11-12 --json '{
  "id_venta":"VDEMO14","id_cliente":"C001","id_farmaceutico":"F001",
  "medio_pago":"Efectivo","fecha":"2026-11-12",
  "detalle":[{"id_producto":"PRD001","cantidad":1}]
}'

# Q15 · Reintento del descuento para la misma venta
python -m src.consultas.q15 VDEMO14 --hoy 2026-11-12
```

Q14 llama a Q15 dentro de la misma transacción. Si falta stock, MongoDB
revierte la venta y los decrementos parciales. Si hay una receta, se
actualiza después del descuento y se confirma junto con la venta, el stock
y el evento de proyección. La segunda orden devuelve las asignaciones
guardadas por Q14 sin volver a descontar unidades.

Para probar el rechazo por stock insuficiente, pedí también una unidad de
`PRD101`. Tiene stock en `S101`, mientras que el farmacéutico `F001` atiende en
`S001`. El comando se rechaza y el saldo del lote `L001` conserva las 119
unidades que quedaron después de la venta anterior.

```sh
# Q14 · Rechazo de una venta por stock insuficiente
python -m src.consultas.q14 --hoy 2026-11-12 --json '{
  "id_venta":"VDEMO14R","id_cliente":"C001","id_farmaceutico":"F001",
  "medio_pago":"Efectivo","fecha":"2026-11-12",
  "detalle":[{"id_producto":"PRD001","cantidad":1},{"id_producto":"PRD101","cantidad":1}]
}'
```

## Pruebas

### Pruebas unitarias de carga CSV, stock y consultas MongoDB

Con las dependencias de `requirements.txt` instaladas, estas pruebas pueden
ejecutarse sin levantar los motores.

```sh
python -m pytest tests/test_carga_csv_y_stock.py tests/test_consultas_mongo_unitarias.py
```

### Pruebas de los servicios Q13, Q14 y Q15

Ejecutalas dentro de `workspace` o Codespaces con MongoDB levantado y el
entorno virtual activo. Cada prueba crea y elimina su propia base temporal.
La opción `-s` muestra las tablas Markdown de Q14 y Q15 con los estados antes
y después del éxito, el rechazo y, en Q15, el reintento.

```text
python -m pytest -q -s <ruta_de_prueba> [-k '<filtro>']
```

Ejemplo para ejecutar los tres servicios

```sh
python -m pytest -q -s tests/test_q13.py tests/test_q14.py tests/test_q15.py
```

### Suite completa de pruebas

Desde la terminal donde usás Docker Compose, iniciá la instancia descartable
de Neo4j para pruebas. Desde `workspace` o Codespaces, ejecutá la suite con
el entorno virtual activo:

```sh
# Terminal con Docker Compose
docker compose --profile test up -d --wait neo4j-test

# Terminal de workspace o Codespaces
NEO4J_TEST_URI=bolt://neo4j-test:7687 python -m pytest tests -rs
```

Las integraciones crean una base temporal de MongoDB por caso. Las pruebas
de grafo requieren una instancia vacía de Neo4j dedicada a la suite y limpian
sus nodos después de cada caso. Si usás otra instancia descartable, configurá
`NEO4J_TEST_URI`, `NEO4J_TEST_USER` y `NEO4J_TEST_PASSWORD` según corresponda.
Revisá los motivos de omisión que muestra `-rs`.
