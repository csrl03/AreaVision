# VisiSize (AreaCamPython_v1) — Contexto del Proyecto

> Generado por análisis automático del repositorio. Fuente de verdad para features nuevas.
> Última auditoría: 2026-09-26

---

## 1. Identidad del proyecto

| Campo | Valor |
|---|---|
| Nombre | VisiSize (paquete/directorio `AreaCamPython_v1`) |
| Tipo | Aplicación de escritorio (monolito modular) |
| Lenguaje | Python 3.11.5 |
| Entry point | `main.py` → `ui.app.run_app(db)` |
| Idioma de UI y comentarios | Español |
| Documentación funcional | `FUNCIONAMIENTO.md`, `README.md`, `docs/implementation-plan.md` |
| Tracking de errores | `GestionErrores/*.md` (frontmatter YAML: error-id, status, fechas) |

---

## 2. Stack tecnológico

Dependencias (`requirements.txt`, todas con versión fijada):

| Librería | Versión | Rol |
|---|---|---|
| `opencv-python` | 4.9.0.80 | Pipeline de visión por computador |
| `PyQt6` | 6.7.1 | UI de escritorio |
| `ultralytics` | 8.2.0 | Stub YOLOv8 (inactivo) |
| `Pillow` | 10.3.0 | Guardado de PNG |
| `numpy` | 1.26.4 | Arrays numéricos |
| `ezdxf` | 1.4.4 | **Añadido 2026-09-26** — exportación CAD DXF |
| `pytest` | 8.4.2 | **Añadido 2026-09-26** — suite de pruebas (dev) |

Sin ORM: SQLite vía `sqlite3` de la stdlib. Sin gestor de dependencias: `requirements.txt` plano.

---

## 3. Arquitectura por capas

Monolito modular con 4 capas de dependencia estrictamente descendente:

```
ui/          (PyQt6)          → depende de services/, data/, core/
services/    (lógica)         → depende de core/, data/
data/        (persistencia)   → depende de core/
core/        (dominio puro)   → NO depende de nada del proyecto
```

- **Regla de oro de `core/`**: sin I/O, sin efectos secundarios, sin UI, sin framework.
  Solo `dataclass`, `Enum`, `math`. Verificado en `core/formulas.py` (funciones puras).
- **Inyección de dependencias manual**: los servicios reciben colaboradores por constructor
  (ver `MeasurementService.__init__`, `MainWindow.__init__`). No hay contenedor DI.
- **Grafo de dependencias construido en `ui/app.py:run_app()`**, único lugar donde se
  instancian y conectan los servicios.

### Árbol de archivos actual

```
config.py                     ← constantes globales (cámara, rutas, tema, ventana)
main.py                       ← entry point: logging, dirs, DB init, run_app
core/
  __init__.py
  constants.py                ← parámetros numéricos del pipeline y categorías
  entities.py                 ← MeasurementCategory, CalibrationData, ProcessingResult, Measurement
  exceptions.py               ← jerarquía VisiSizeError → CameraError, ProcessingError, …
  formulas.py                 ← factorK, corrección distancia, classify_area, circularidad
data/
  database.py                 ← DatabaseManager (schema + conexión + PRAGMAs)
  repositories.py             ← MeasurementRepository (CRUD), ImageStorageService
  settings_repository.py      ← settings.json con _validate() defensivo
  calibration.json            ← calibración activa
  settings.json               ← preferencias persistidas
  images/                     ← PNG de siluetas
services/
  camera_service.py           ← webcam (índice) + IP (RTSP/HTTP)
  opencv_service.py           ← pipeline: gray→blur→adaptiveThr→morph→contours→métricas
  calibration_service.py      ← cálculo FactorK, corrección, persistencia JSON
  measurement_service.py      ← orquesta process() y save_measurement()
  ai_classifier/              ← ObjectClassifier (ABC), GeometryClassifier (OpenCV), YOLO stub
ui/
  app.py                      ← run_app(): composition root
  theme.py                    ← ThemeManager + QSS dark/light completos
  windows/main_window.py      ← QMainWindow con QTabWidget
  windows/calibration_window.py
  windows/measurement_detail_window.py
  widgets/camera_feed_widget.py  ← CameraThread (QThread) + CameraFeedWidget (QLabel)
  widgets/measurement_card.py    ← tarjeta para el historial
  widgets/area_selector_widget.py
```

---

## 4. Convenciones de código

| Aspecto | Convención |
|---|---|
| Nombres de archivo | `snake_case.py` |
| Clases / funciones / variables | `PascalCase` / `snake_case` |
| Constantes de módulo | `UPPER_SNAKE_CASE` |
| Métodos privados UI | prefijo `_` +Verbo (`_on_click`, `_build_ui`, `_reload_history`) |
| Docstrings | Español, con sección `Args:` / `Returns:` / `Raises:` en inglés (Google-ish) |
| Type hints | Obligatorios; `from __future__ import annotations` en todos los módulos |
| Union | `X | None` (PEP 604), nunca `Optional` en firma nueva |
| SQL | Placeholders `?` exclusivamente (nunca f-strings) |
| Entidades | `@dataclass` en `core/entities.py` |
| Errores | Siempre una subclase de `VisiSizeError` en `core/exceptions.py` |
| Logs | `logger = logging.getLogger(__name__)` a nivel de módulo |

### Anti-patrones observados (no replicar)

- `settings_repository._validate()` hace `dict(_DEFAULTS)` como *shallow* copy y luego
  muta sub-diccionarios compartidos. Corregido a `copy.deepcopy` el 2026-09-26.
- `settings_repository._validate()` **descarta** las claves que no conoce: reconstruye
  el dict de salida solo con las claves del esquema. Un ajuste escrito por una versión
  futura de la app se pierde al cargar. **No se cambió** (no hay causa técnica que lo
  justifique), pero está documentado en `tests/test_regression.py`.
  → **Al añadir una clave hay que tocar `_DEFAULTS` Y `_validate`**, o no se persiste.

---

## 5. UI / UX y theming

- **Navegación**: un único `QTabWidget` en `MainWindow._build_ui()`. Las pestañas se
  registran con `tabs.addTab(...)` y se indexan por posición en `_on_tab_changed()`.
  **Añadir una pestaña = añadir un `addTab` y extender el `elif` de `_on_tab_changed`.**
- **Tema**: dos QSS completos en `ui/theme.py` (`DARK_QSS`, `LIGHT_QSS`).
  Paleta oscura: fondo `#1a1a2e`, panel `#16213e`, acentos `#0f3460`, primario `#e94560`.
  Paleta clara: fondo `#f4f6f9`, panel `#ffffff`, acentos `#dce3ec`, primario `#1565c0`.
  Colores de categoría (`CATEGORY_COLORS`): A `#4caf50`, B `#2196f3`, C `#ff9800`,
  D `#ff5722`, error `#f44336`.
- **Estilos por objectName**: `btn_capture`, `btn_calibrate`, `btn_danger`, `btn_secondary`,
  `label_area`, `label_cat`, `label_status`, `label_title`.
- **Layouts**: `QHBoxLayout` raíz con feed (stretch 3) + panel de control de `setFixedWidth(260)`.
  La pestaña de Configuración usa `QScrollArea` + `QWidget` interno (patrón a replicar
  para pestañas largas).
- **Concurrencia**: el hilo de cámara (`CameraThread`) emite señales; la UI solo pinta.
  Patrón: `QThread` + `pyqtSignal` + throttling por contador (`_CLASSIFY_EVERY = 10`).

---

## 6. Servicios y acceso a datos

- **Repositorio por tabla**: `MeasurementRepository` encapsula todo SQL.
  Convención: `get_all` / `get_by_id` / `save` / `delete` / `delete_all` / `search_by_name` /
  `filter_by_*`, y un `_row_to_entity(row)` estático al final.
- **Conexión**: `DatabaseManager.get_connection()` es un context manager que aplica
  `row_factory`, `foreign_keys=ON`, `journal_mode=WAL`. Se usa siempre como `with self._db.get_connection() as conn:`
  y `conn.commit()` explícito.
- **Migraciones**: no hay framework. `SCHEMA_VERSION` en `data/database.py` + tabla `meta`
  + `INSERT OR IGNORE INTO meta`. **El patrón de migración es `CREATE TABLE IF NOT EXISTS` +
  `ALTER TABLE ADD COLUMN` con try/except sobre `sqlite3.OperationalError`.**
- **Configuración**: JSON, no SQLite. `SettingsRepository` con `_DEFAULTS` y `_validate()`
  que **reemplaza silenciosamente** valores inválidos por el default y loguea un warning.

---

## 7. Testing

- **Estado previo a 2026-09-26**: sin pruebas. `docs/implementation-plan.md` registra
  explícitamente "Pruebas manuales únicamente | Proyecto universitario local".
- **A partir de 2026-09-26**: `pytest` 8.4.2 disponible; suite en `tests/`.
  Convenciones a seguir: `pytest`, clases `Test*`, Arrange/Act/Assert, sin fixtures
 Settings compartidas, BD temporal por test con `:memory:` o `tmp_path`.

---

## 8. Puntos de integración para features nuevas

1. **`ui/app.py:run_app()`** → registrar el servicio nuevo antes de construir `MainWindow`.
2. **`MainWindow.__init__`** → añadir el parámetro con keyword y asignarlo a `self._svc`.
3. **`MainWindow._build_ui()`** → añadir la pestaña con `tabs.addTab(self._build_x_tab(), "  X  ")`.
4. **`MainWindow._on_tab_changed(index)`** → extender el `elif` para refrescar al cambiar de pestaña.
5. **`data/database.py`** → `CREATE TABLE IF NOT EXISTS` + bump de `SCHEMA_VERSION`.
6. **`data/settings_repository.py`** → nueva clave en `_DEFAULTS` **y** en `_validate()`.
7. **`core/entities.py`** → dataclass de dominio, sin dependencias.

---

## 9. Riesgos técnicos conocidos

| Riesgo | Detalle | Mitigación aplicada en features nuevas |
|---|---|---|
| OpenCV sobre-sensible | `GestionErrores/opencv-oversensitive-macro-shapes.md` (status `en-progreso`) | No re-tocar umbrales del pipeline; usar `minAreaRect` en vez de `boundingRect` para dimensiones reales |
| `aspect_ratio` de `ProcessingResult` | Usa `cv2.boundingRect` (ejes alineados) → distorsiona objetos inclinados | Calcular largo/ancho reales con `cv2.minAreaRect` en el módulo de geometría |
| Compatibilidad Flutter | `core/constants.py` avisa que los valores deben ser idénticos a `opencv_dart` | No cambiar constantes existentes; añadir nuevas con prefijo propio |
| Calibración monotonous | Sin `factor_k` válido, `area_m2` es `None` y el flujo se detiene | Todo lo nuevo debe degradar con elegancia cuando `area_m2 is None` |
| FactorK por distancia | Asume cámara cenital; un objeto inclinado a la cámara distorsiona | Documentar como limitación; no "corregir" sin sensor |
| Sin厚度 automático | La cámara monocular no mide espesor | Entrada manual con `espesor_mm` nullable, arquitectura lista para sensor |
