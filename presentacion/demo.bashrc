# Entorno de cada terminal embebida en la presentación (lo carga ttyd).
# levantar.sh exporta FARMARED_REPO antes de iniciar ttyd.

cd "$FARMARED_REPO" || exit 1
source "$FARMARED_REPO/.venv/bin/activate"

export MONGODB_URI='mongodb://localhost:27117/farmared_demo?replicaSet=rs0&directConnection=true'
export NEO4J_URI='bolt://localhost:7688'
export NEO4J_USER='neo4j'
export NEO4J_PASSWORD='farmared-local'

# demo N: corre el paso N de src/demo.py (0 reinicia la base y el grafo).
demo() {
  python -m src.demo --paso "$1"
}

export BASH_SILENCE_DEPRECATION_WARNING=1
PS1='\[\e[38;5;114m\]farmared\[\e[0m\] $ '
clear
