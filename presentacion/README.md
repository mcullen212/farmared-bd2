# Presentación de FarmaRed (Slidev)

18 slides con la demo en vivo: las slides 10, 12, 13, 14 y 15 tienen una terminal real embebida que corre las consultas contra MongoDB y Neo4j.

Respaldo sin terminal (mismas slides, con las salidas reales como capturas): https://claude.ai/artifact/7SpMfoKGTKg7xazRB6w2fM

## Requisitos (macOS, una sola vez)

```sh
brew install node ttyd colima docker
cd presentacion && npm install
```

## Antes de presentar

Dos terminales, desde la raíz del repo:

```sh
# Terminal 1: Docker + bases + datos de la demo + terminal web (dejarla abierta)
presentacion/levantar.sh

# Terminal 2: la presentación (abre el navegador en http://localhost:3030)
cd presentacion && npm run dev
```

`levantar.sh` deja la base `farmared_demo` recién cargada y el grafo construido. No toca la base `farmared`.

## Durante la demo

| Slide | Escribir en la terminal | Qué pasa |
|---|---|---|
| 10 · q07 | `demo 1` | Top 5 de productos |
| 12 · venta | `demo 2` y Enter | Antes y después de lotes, receta y avisos |
| 13 · rechazo | `demo 3` | Venta rechazada, nada cambia |
| 14 · q03 | `demo 4` y Enter | Historial sin la venta, corre el consumidor, aparece la venta |
| 15 · q10 | `demo 5` | Clientes de S002, incluido el del farmacéutico inactivo |

- **Hacé clic en la terminal antes de escribir.** Para pasar de slide, hacé clic fuera de la terminal (por ejemplo, en el título) y usá las flechas: mientras la terminal tiene el foco, las teclas van a ella.
- **Los pasos van en orden** (2 antes que 3 y 4). Si algo sale mal o querés repetir la demo, escribí `demo 0`: reinicia la base y el grafo en unos segundos.
- Presionando `p` en Slidev se abre la vista de presentador con las notas de cada slide.

## Si algo falla

- **"La terminal no está levantada"** en la slide: `levantar.sh` no está corriendo. Correlo y recargá la página.
- **"No me pude conectar a Neo4j"**: Neo4j todavía está arrancando; esperá unos segundos.
- **Nada funciona**: usar la presentación de respaldo del link de arriba y, si hace falta, mostrar la demo en una terminal común con `python -m src.demo` (ver `docs/DEMO.md`).
