#!/usr/bin/env bash
# Deja lista la demo en vivo de la presentación (macOS con colima y Homebrew):
#   1. Docker (colima) con MongoDB (replica set) y Neo4j de prueba.
#   2. Entorno de Python en .venv con las dependencias del repo.
#   3. Base farmared_demo cargada y grafo construido (paso 0 de la demo).
#   4. Terminal web (ttyd) en http://localhost:7681, solo accesible desde esta compu.
# Después, en otra terminal: cd presentacion && npm run dev
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
export FARMARED_REPO="$REPO"

echo "==> Docker"
colima status >/dev/null 2>&1 || colima start

if ! docker ps --format '{{.Names}}' | grep -qx fr-mongo; then
  docker rm -f fr-mongo >/dev/null 2>&1 || true
  docker run -d --name fr-mongo -p 27117:27017 --tmpfs /data/db \
    mongo:8.0 mongod --replSet rs0 --bind_ip_all >/dev/null
fi
if ! docker ps --format '{{.Names}}' | grep -qx fr-neo4j; then
  docker rm -f fr-neo4j >/dev/null 2>&1 || true
  docker run -d --name fr-neo4j -p 7688:7687 --tmpfs /data \
    -e NEO4J_AUTH=neo4j/farmared-local neo4j:5.26 >/dev/null
fi

echo "==> Esperando a MongoDB"
until docker exec fr-mongo mongosh --quiet --eval 'db.runCommand({ping: 1}).ok' >/dev/null 2>&1; do sleep 2; done
docker exec fr-mongo mongosh --quiet --eval '
  try { rs.status() } catch (e) { rs.initiate({_id: "rs0", members: [{_id: 0, host: "localhost:27017"}]}) }' >/dev/null
until docker exec fr-mongo mongosh --quiet --eval 'quit(db.hello().isWritablePrimary ? 0 : 1)' >/dev/null 2>&1; do sleep 2; done

echo "==> Esperando a Neo4j"
until docker exec fr-neo4j cypher-shell -u neo4j -p farmared-local 'RETURN 1' >/dev/null 2>&1; do sleep 3; done

echo "==> Python"
if [ ! -x "$REPO/.venv/bin/python" ]; then
  python3 -m venv "$REPO/.venv"
fi
"$REPO/.venv/bin/pip" install -q -r "$REPO/requirements.txt"

echo "==> Cargando farmared_demo y construyendo el grafo"
(
  cd "$REPO"
  export MONGODB_URI='mongodb://localhost:27117/farmared_demo?replicaSet=rs0&directConnection=true'
  export NEO4J_URI='bolt://localhost:7688' NEO4J_USER='neo4j' NEO4J_PASSWORD='farmared-local'
  "$REPO/.venv/bin/python" -m src.demo --paso 0 --sin-pausa
)

if lsof -nP -iTCP:7681 -sTCP:LISTEN >/dev/null 2>&1; then
  echo
  echo "El puerto 7681 ya está en uso. Si es otra terminal web de la demo, cerrala con:"
  echo "  pkill ttyd"
  echo "y volvé a correr este script."
  exit 1
fi

echo
echo "==> Terminal web en http://localhost:7681 (Ctrl+C para cerrarla)"
echo "    En otra terminal: cd presentacion && npm run dev"
exec ttyd -i lo0 -p 7681 -W \
  -t fontSize=10 \
  -t 'fontFamily=Menlo, monospace' \
  -t disableLeaveAlert=true \
  -t 'theme={"background":"#0F1A18","foreground":"#D7E4DF","cursor":"#7FC8A0"}' \
  bash --rcfile "$REPO/presentacion/demo.bashrc" -i
