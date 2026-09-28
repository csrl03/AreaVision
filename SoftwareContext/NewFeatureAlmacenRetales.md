# Feature: Almacén de Retales

> Sistema de gestión de retales metálicos: clasificación geométrica, decisión
> reutilización/reciclaje, asignación automática a repisas, inventario, costo
> económico, alerta de geometría punzante y exportación DXF.
>
> Basado en `SoftwareContext/ProjectContext.md`. Fecha: 2026-09-26

- **status**: `completed` — 2026-09-26
- **alcance**: extends (no rewrite) — el pipeline OpenCV, calibración, historial y
  configuración existentes se conservan sin cambios de comportamiento.
- **verificación**: 257 pruebas automatizadas en verde (`python -m pytest`).
  Base de datos real migrada a esquema v2 sin pérdida de historial.

---

## 1. Resumen

VisiSize pasa de "medir área" a "gestionar retales". El flujo final:

```
Capturar → Detectar → Área m² → Dimensiones → Forma → Regularidad
        → Espesor (manual) → Riesgo punzante
        → ¿Reutilizable?
              ├─ NO  → RECICLAJE (con motivos)
              └─ SÍ  → Buscar repisas compatibles
                        → Verificar espacio físico (packing 2D + rotación 90°)
                        → Proponer ubicación
                        → Registrar → Inventario → Valor estimado → Exportar DXF
```

## 2. Decisiones tomadas (respuestas del usuario)

| Decisión | Valor |
|---|---|
| Moneda | COP configurable — prefijo `$`, separador de miles es-EC (`85.000`) |
| Retal reutilizable sin ubicación | **Configurable** — toggle `auto_recycle_sin_ubicacion` (default `false` = queda SIN UBICACIÓN + alerta) |
| Umbrales por defecto | Los ejemplos del prompt: `area_min 0.25 m²`, `espesor_min 2 mm`, `regularidad_min 0.70` |
| Navegación | Pestañas de primer nivel → 5 en total: Cámara · Historial · **Almacén** · **Inventario** · Configuración |
| Migración | Columna `scrap_id` **nullable** en `measurements`. Las Medidas viejas quedan `NULL` (solo historial). FK con `ON DELETE SET NULL` |
| Umbral sharp | `0.55` default, configurable |
| Polígono regular | `5 <= n <= 8` vértices |
| DXF | `ezdxf` añadido a `requirements.txt` (ya instalado: 1.4.4) |

## 3. Archivos nuevos

### `core/` — dominio puro (sin I/O, sin Qt)

| Archivo | Responsabilidad |
|---|---|
| `core/geometry.py` | `ShapeType` (Enum), `Regularity` (Enum), `GeometryAnalysis` (dataclass), `analyze_contour(contour, factor_k)`. Aplica `approxPolyDP` + `minAreaRect` + circularidad + solidez + defects de convexidad. Devuelve largo_m / ancho_m / vértices / confidence. |
| `core/safety.py` | `SharpnessReport` (dataclass), `analyze_sharpness(contour)`. `sharpness_score` = f(min_angle, protrusion_depth, aspect local, defects, spikes). |
| `core/packing.py` | `fits_single(item_w, item_h, bin_w, bin_h)` con rotación 0°/90°, `try_place(rects, bin_w, bin_h, nuevo)` — guillotine / shelf-first determinista y conservador. |
| `core/scoring.py` | `compute_estimated_value(area_m2, costo_por_m2, moneda)`, `format_currency()`. |
| `core/dxf.py` | `contour_to_dxf(contour, factor_k, path, tolerance_px)`. Simplifica con `approxPolyDP` y escribe LWPOLYLINE; emite CIRCLE si detecta geometría circular limpia. |

### `services/`

| Archivo | Responsabilidad |
|---|---|
| `services/classification_service.py` | Orquesta: geometría → seguridad → espesor → decisión reutilizable/reciclaje. **Sin UI, testeable.** Devuelve `ScrapAnalysis`. |
| `services/allocation_service.py` | Filtra repisas por reglas, evalúa packing real, elige la mejor, propone rotación. Devuelve `AllocationProposal`. |
| `services/cad_service.py` | Fachada fina de `core/dxf.py` (rutas, nombres de archivo seguros, DXF de contorno o de rectángulo de repisa). |

### `data/`

| Archivo | Responsabilidad |
|---|---|
| `data/storage_repositories.py` | `StorageAreaRepository`, `ShelfRepository`, `ScrapRepository`. Mismo estilo que `MeasurementRepository` (placeholders `?`, `_row_to_entity`). |

### `ui/`

| Archivo | Responsabilidad |
|---|---|
| `ui/windows/storage_window.py` | Pestaña Almacén: árbol Estantes→Repisas + panel de reglas de la repisa seleccionada. |
| `ui/windows/inventory_window.py` | Pestaña Inventario: tabla de retales + buscador por dimensiones + detalle con "Exportar DXF". |
| `ui/windows/scrap_review_dialog.py` | Diálogo post-captura: muestra área/dimensiones/forma/regularidad/espesor/valor/ubicación/riesgo. El usuario revisa y confirma. |
| `ui/widgets/scrap_card.py` | Tarjeta de retal para la lista de inventario (réplica de `MeasurementCard`). |

### `tests/`

`test_packing.py`, `test_geometry.py`, `test_safety.py`, `test_scoring.py`,
`test_classification_service.py`, `test_allocation_service.py`,
`test_dxf.py`, `test_migration.py`, `test_regression.py`.

## 4. Archivos modificados

| Archivo | Cambio | Riesgo |
|---|---|---|
| `core/entities.py` | **Añadir** `StorageArea`, `Shelf`, `ShelfRules`, `Scrap`, `ScrapStatus`, `ScrapDestination`, `ScrapAnalysis`, `AllocationProposal` | Bajo (aditivo) |
| `core/exceptions.py` | **Añadir** `AllocationError`, `GeometryAnalysisError` | Bajo (aditivo) |
| `data/database.py` | `SCHEMA_VERSION` 1→2; 3 tablas nuevas; `ALTER TABLE measurements ADD COLUMN scrap_id` con try/except `OperationalError` | **Medio** — migración |
| `data/repositories.py` | `save()` inserta `scrap_id`; `_row_to_entity` lo lee con fallback `NULL` | **Medio** — regresión |
| `data/settings_repository.py` | 8 claves nuevas en `_DEFAULTS` + validación en `_validate()` | Bajo |
| `services/opencv_service.py` | **Añadir** campo `main_contour: Optional[np.ndarray]` a `ProcessingResult` para que geometría/seguridad/DXF no reprocesen la imagen | Bajo (aditivo) |
| `core/entities.py` | `ProcessingResult.main_contour` opcional | Bajo |
| `services/measurement_service.py` | `save_measurement()` acepta `scrap_id` | Bajo |
| `ui/app.py` | Construir los 3 servicios nuevos y pasarlos a `MainWindow` | Bajo |
| `ui/windows/main_window.py` | 2 pestañas nuevas; `_show_save_dialog` → `ScrapReviewDialog`; grupo de config "Retales" | Medio |
| `ui/theme.py` | Badge de destino reutilizable/reciclaje y chip de alerta | Bajo |
| `requirements.txt` | `ezdxf` | Bajo |
| `FUNCIONAMIENTO.md`, `README.md` | Documentar el flujo nuevo | Bajo |

## 5. Modelo de datos (SQLite v2)

```
storage_areas (1) ──< shelves (N) ──< scraps (N)
                                    ↑
                              measurements.scrap_id (NULLABLE, FK SET NULL)
```

```sql
CREATE TABLE IF NOT EXISTS storage_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shelves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_area_id INTEGER NOT NULL REFERENCES storage_areas(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    width_m REAL NOT NULL,          -- ancho  (eje X de la repisa)
    length_m REAL NOT NULL,         -- largo  (eje Y de la repisa)
    accepts_regular INTEGER NOT NULL DEFAULT 1,
    accepts_irregular INTEGER NOT NULL DEFAULT 1,
    min_width_m REAL, max_width_m REAL,
    min_length_m REAL, max_length_m REAL,
    min_area_m2 REAL, max_area_m2 REAL,
    min_thickness_mm REAL, max_thickness_mm REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scraps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    measurement_id INTEGER,                    -- referência lógica, sin FK dura
    name TEXT,
    area_m2 REAL NOT NULL,
    width_m REAL NOT NULL,
    length_m REAL NOT NULL,
    thickness_mm REAL,                         -- NULL = no capturado
    shape TEXT NOT NULL,
    regularity TEXT NOT NULL,
    shape_confidence REAL,
    regularity_score REAL,
    vertex_count INTEGER,
    shelf_id INTEGER REFERENCES shelves(id) ON DELETE SET NULL,
    storage_area_id INTEGER,                   -- desnormalizado para consulta rápida
    destination TEXT NOT NULL,                 -- REUTILIZABLE | RECICLABLE
    status TEXT NOT NULL,                      -- DISPONIBLE | RESERVADO | UTILIZADO | RECICLADO
    sharpness_score REAL,
    safety_alert INTEGER NOT NULL DEFAULT 0,
    estimated_value REAL,
    cost_per_m2 REAL,
    reasons TEXT,                              -- JSON: motivos de reciclaje/decisión
    silhouette_path TEXT,
    created_at TEXT NOT NULL
);
```

**Migración (v1 → v2)**, idempotente y no destructiva:

```python
# 1. CREATE TABLE IF NOT EXISTS × 3  (nunca falla si ya existen)
# 2. ALTER TABLE measurements ADD COLUMN scrap_id INTEGER
#    envuelto en try/except sqlite3.OperationalError → ignora "duplicate column name"
# 3. UPDATE meta SET value='2' WHERE key='schema_version'
```

Las mediciones históricas **no se tocan**: `scrap_id` queda `NULL` y `_row_to_entity`
lee con `row.keys()` para no romper con filas antiguas.

## 6. Puntos de integración

```python
# ui/app.py
from services.classification_service import ClassificationService
from services.allocation_service import AllocationService
from services.cad_service import CadService
from data.storage_repositories import StorageAreaRepository, ShelfRepository, ScrapRepository

window = MainWindow(..., classification_svc=..., allocation_svc=..., cad_svc=...,
                    storage_repo=..., shelf_repo=..., scrap_repo=...)
```

```python
# main_window.py — navegación por índice posicional
tabs.addTab(self._build_camera_tab(),    "  Cámara  ")      # 0
tabs.addTab(self._build_history_tab(),   "  Historial  ")   # 1
tabs.addTab(self._build_storage_tab(),   "  Almacén  ")     # 2  NUEVO
tabs.addTab(self._build_inventory_tab(), "  Inventario  ")  # 3  NUEVO
tabs.addTab(self._build_settings_tab(),  "  Configuración  ")# 4
```

## 7. Estrategia de clasificación geométrica

Combinación de métricas, ninguna por sí sola decide:

1. `approxPolyDP` con `ε = 0.02 × perímetro` → nº de vértices `n`
2. `cv2.minAreaRect` → **dimensiones reales** `width_m` / `length_m`
   (long_max = lado largo, short = lado corto) — corrige el sesgo de `boundingRect`
3. `solidez = área / área_hull` — distingue polígono simple de cóncavo/irregular
4. `4πA/P²` — circularidad
5. `defects = convexityDefects()` → nº de agujeros de concavidad

| Evidencia | `ShapeType` |
|---|---|
| `circ > 0.90` y `hull_area ≈ area` (error < 3%) | `CIRCULO` |
| `n == 4` y `solidez > 0.95` y `ratio_lados` cv < 0.12 | `CUADRADO` |
| `n == 4` y `solidez > 0.90` | `RECTANGULO` |
| `n == 3` y `solidez > 0.80` | `TRIANGULO` |
| `5 ≤ n ≤ 8` y `solidez > 0.85` y varianza de lados < 25% | `POLIGONO_REGULAR` |
| resto | `POLIGONO_IRREGULAR` / `OTRA` |

`Regularity = REGULAR` si `solidez ≥ 0.92 y defecto_circularidad ≤ 0.10 y n ≤ 8`;
`IRREGULAR` si `solidez < 0.75 o defects ≥ 3`; `SEMI_REGULAR` intermedio.
`regularity_score` ∈ [0,1] = media ponderada de solidez, (1−|1−circ|), defecto relativo.

**Toda clasificación devuelve un `confidence` heurístico, nunca una certeza.**

## 8. Estrategia de detección de geometría punzante

No es `if angle < X`. Es un score compuesto de 5 señales:

| Señal | Cálculo | Peso |
|---|---|---|
| `min_angle` | mín. de los ángulos internos de la polilínea simplificada | 0.30 |
| `protrusion_depth` | `1 − hull_area/area` normalizado | 0.25 |
| `spike_factor` | para cada vértice: `dist(v, prev)+dist(v,next)` vs. longitud mediana de arista | 0.20 |
| `convexity_defects` | `min(|d|, 1.0)` de `convexityDefects` normalizado | 0.15 |
| `local_aspect` | `p90(widths por arista) / min_width` — astillas y lengüetas | 0.10 |

`sharpness_score = clip(Σ wᵢ·sᵢ, 0, 1)`, donde cada `sᵢ ∈ [0,1]`.
Alerta si `score ≥ sharpness_threshold` (default 0.55, configurable).

La UI muestra explícitamente: *"No constituye una certificación de seguridad industrial."*

## 9. Estrategia de asignación física

**No** compara `área_retal ≤ área_disponible`. El filtro es:

1. `rectángulo cabe` → `w ≤ W and h ≤ L`  ó  `w ≤ L and h ≤ W` (rotación 90°)
2. **packing real**: guillotine "shelf-first" determinista —
   1. Se prueban las 2 rotaciones candidatas.
   2. Para cada rotación, se ordenan los rects ya guardados por `y` y se barre una
      estantería horizontal desde `y=0` con altura `h_nuevo`, colocando lado a lado
      mientras quepan; luego `y += h_estante`.
   3. Si no cabe en la primera pasada, se hace una 2ª pasada，允许 huecos "above"
      (greedy best-fit por `y` ascendente).
   4. Devuelve `(x, y, rotated)` en metros o `None`.

Es **conservador y determinista** (mismo inventario → misma posición), no óptimo.
La arquitectura (`PackingStrategy` como parámetro) permite sustituirlo por
MaxRects o por un optimizador real sin tocar el resto.

Ocupación reportada = `Σ área_retales` (m²) + `espacio_disponible` como
`área_total − Σ área`, claramente etiquetado como *estimación por área*, no como
espacio realmente utilizable. Cuando el packing no encuentra posición:
`"No se encontró una ubicación física compatible."`

## 10. Configuración nueva (`settings.json`)

```json
{
  "cost_per_m2_sheet": 85000.0,
  "currency_code": "COP",
  "currency_symbol": "$",
  "min_reusable_area_m2": 0.25,
  "max_reusable_area_m2": 0.0,
  "min_reusable_thickness_mm": 2.0,
  "min_regularity_score": 0.70,
  "sharpness_alert_threshold": 0.55,
  "auto_recycle_sin_ubicacion": false,
  "dxf_simplify_epsilon_ratio": 0.02
}
```

`max_reusable_area_m2 = 0.0` significa "sin máximo" (0 = ∞).
Todas editables desde la pestaña Configuración → grupo **"Retales"**.

## 11. Checklist de implementación

- [x] `core/geometry.py` — análisis geométrico + dimensiones reales
- [x] `core/safety.py` — sharpness score
- [x] `core/packing.py` — packing 2D con rotación
- [x] `core/scoring.py` — valor económico + formato COP
- [x] `core/dxf.py` — exportación DXF
- [x] `core/entities.py` — dataclasses nuevas
- [x] `data/database.py` — migración v1→v2
- [x] `data/storage_repositories.py` — 3 repositorios
- [x] `services/classification_service.py` — pipeline de decisión
- [x] `services/allocation_service.py` — asignación
- [x] `services/cad_service.py` — fachada DXF
- [x] `data/settings_repository.py` — claves nuevas
- [x] `services/opencv_service.py` — exponer `main_contour`
- [x] `services/measurement_service.py` — aceptar `scrap_id`
- [x] `ui/windows/storage_window.py` — CRUD almacén
- [x] `ui/windows/inventory_window.py` — inventario + búsqueda
- [x] `ui/windows/scrap_review_dialog.py` — revisión post-captura
- [x] `ui/widgets/scrap_card.py` — tarjeta de retal
- [x] `ui/app.py` — composition root
- [x] `ui/windows/main_window.py` — 2 pestañas + diálogo + config
- [x] `ui/theme.py` — estilos nuevos
- [x] `requirements.txt` — ezdxf
- [x] `tests/` — 9 archivos de prueba, 257 tests
- [x] Documentación (`FUNCIONAMIENTO.md`, `README.md`)

## 12. Desviaciones respecto al plan original

Tres decisiones se alejaron de lo planificado al descubrir que los datos reales
no sostenían la hipótesis inicial. Se documentan porque cambian el
comportamiento esperado:

1. **Círculo vs. polígono regular** — el plan hablaba solo de circularidad.
   Medido: un círculo digitalizado da 0.893 y un hexágono 0.824, así que el
   umbral 0.90 del plan habría clasificado *todo* círculo como polígono. Se
   añadió el **déficit de área de la simplificación** como tercera señal.

2. **Regularidad** — el plan medía simetría. Medido: un rectángulo 2:1 tiene
   CV de lados 0.25 y un 3:1 tiene 0.50, así que cualquier medida de simetría
   marcaba como irregular un corte perfectamente limpio. Se cambió a
   **suavidad del contorno** (nº de vértices tras simplificar) + profundidad
   de muesca *relativa al tamaño de la pieza*.

3. **Regularidad desconocida** — sin contorno, la regularidad salía 0.0 y
   mandaba a reciclaje piezas buenas. Se añadió `GeometryAnalysis.is_degraded`
   para que "no lo sé" no se interprete como "es irregular".

4. **Bug en el packing** — `_shelf_first_pass` no comprobaba que la pieza cupiera
   en la altura del bin y devolvía posiciones fuera de la repisa. Destapado por
   un test; corregido con una red de seguridad en `_is_free`.

5. **Copia superficial en settings** — `dict(_DEFAULTS)` compartía los
   sub-diccionarios, así que mutar la config cargada envenenaba los defaults de
   toda la app. Corregido con `copy.deepcopy`.
