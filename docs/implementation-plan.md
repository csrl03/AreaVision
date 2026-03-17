# Plan de Implementación — VisiSize Python (AreaCamPython_v1)

**Fecha:** 2026-03-14  
**Estado:** ✅ IMPLEMENTACIÓN COMPLETA  
**Última actualización:** 2026-03-14

---

## Decisiones de Stack y Arquitectura

| Decisión | Opción Elegida | Notas |
|----------|---------------|-------|
| Lenguaje | Python 3.11+ | Compatibilidad con PyQt6 y Ultralytics YOLO |
| Plataforma | Escritorio (Windows/Linux) | App de ventana nativa |
| UI Framework | PyQt6 | Dark/light toggle; controles nativos modernos |
| CV Principal | OpenCV (cv2) | Grayscale → blur → threshold → contornos, idéntico a la app Flutter |
| CV Avanzado / IA | YOLOv8 (ultralytics) — segmentación de instancias | Integrado como stub ahora; se activa con el clasificador real en el futuro |
| Persistencia | SQLite (sqlite3 stdlib) | Registros estructurados; sin ORM externo |
| Imágenes | Disco local — `data/images/` | Rutas almacenadas en DB; no BLOBs |
| Calibración | Rectángulo interactivo en tiempo real + corrección por distancia | Ver fórmula abajo |
| Cámara | Webcam (índice 0,1,2...) + Cámara IP (RTSP/HTTP) opcional | Configurable desde Settings |
| Tema visual | Oscuro + Claro (toggle en Settings) | Consistente con la app Flutter |
| Idioma UI | Español | — |
| Tests | Pruebas manuales únicamente | Proyecto universitario local |
| Servidor remoto | Ninguno — 100% autónomo | El backend Flask queda excluido |
| Arquitectura código | Modular simple | `core/`, `services/`, `data/`, `ui/` |
| Seguridad | Básica (proyecto local universitario) | Validación de entradas, sin credenciales hardcodeadas, sin llamadas remotas |

---

## Fórmula Central de Calibración con Corrección por Distancia

$$\text{factorK}_{medición} = \text{factorK}_{base} \times \left(\frac{d_{calibración}}{d_{medición}}\right)^2$$

$$\text{área}_{m^2} = \text{área}_{píxeles} \times \text{factorK}_{medición}$$

- **factorK_base**: calculado durante calibración interactiva (`área_real_m² / área_píxeles`)
- **d_calibración**: distancia (cm) al momento de calibrar — ingresada por el usuario
- **d_medición**: distancia (cm) al momento de medir — ingresada por el usuario antes de cada captura
- **El área escala con el cuadrado de la distancia** (ley de proyección en perspectiva)

---

## Estructura de Carpetas

```
AreaCamPython_v1/
├── main.py                          # Entry point
├── requirements.txt                 # Dependencias con versiones fijadas
├── config.py                        # Constantes configurables globales
├── .env.example                     # Variables de entorno (futura expansión)
├── .gitignore
├── README.md
│
├── core/                            # Capa de dominio — sin dependencias externas
│   ├── __init__.py
│   ├── constants.py                 # Parámetros OpenCV, umbrales de categorías, etc.
│   ├── entities.py                  # Dataclasses: CalibrationData, Measurement, ProcessingResult
│   ├── formulas.py                  # Funciones puras: factorK, corrección distancia, categoría
│   └── exceptions.py                # Jerarquía de errores tipados
│
├── services/                        # Lógica de aplicación
│   ├── __init__.py
│   ├── camera_service.py            # Webcam + IP camera (OpenCV VideoCapture)
│   ├── opencv_service.py            # Pipeline: grayscale→blur→threshold→contornos→área
│   ├── calibration_service.py       # FactorK con corrección por distancia; persistencia JSON
│   ├── measurement_service.py       # Orquestación: procesar frame → área → categoría → guardar
│   └── ai_classifier/               # Módulo IA (stub ahora, YOLOv8 real en el futuro)
│       ├── __init__.py
│       ├── classifier_interface.py  # ABC: método classify(frame) → ObjectClass | None
│       └── yolo_classifier.py       # Placeholder: retorna None; estructura lista para YOLOv8
│
├── data/                            # Capa de datos
│   ├── __init__.py
│   ├── database.py                  # Inicialización SQLite, migraciones, conexión
│   ├── repositories.py              # CRUD: MeasurementRepository, CalibrationRepository
│   └── images/                      # PNGs de siluetas (generado en runtime, gitignoreado)
│
├── ui/                              # Capa de presentación — PyQt6
│   ├── __init__.py
│   ├── app.py                       # QApplication, carga de tema
│   ├── theme.py                     # Estilos QSS dark/light; colores por categoría
│   ├── windows/
│   │   ├── __init__.py
│   │   ├── main_window.py           # Ventana principal con tabs: Cámara / Historial / Settings
│   │   ├── calibration_window.py    # Asistente de calibración (captura → rectángulo → área conocida)
│   │   └── measurement_detail_window.py  # Detalle de medición guardada
│   └── widgets/
│       ├── __init__.py
│       ├── camera_feed_widget.py    # QLabel con feed en tiempo real + overlay OpenCV
│       ├── area_selector_widget.py  # Widget de dibujo de rectángulo sobre imagen congelada
│       └── measurement_card.py      # Tarjeta en la lista de historial
│
└── docs/
    └── implementation-plan.md       # Este archivo
```

---

## Fases de Implementación

| Fase | Nombre | Entregables Clave | Depende De |
|------|--------|-------------------|------------|
| **0** ✅ | Setup del Proyecto | Scaffold completo, requirements.txt, config, README, .gitignore | — |
| **1** ✅ | Capa Core | Entidades (dataclasses), fórmulas puras, constantes, excepciones | 0 |
| **2** ✅ | Capa Data | SQLite schema + CRUD, image storage, calibración JSON | 1 |
| **3** ✅ | Servicios | CameraService, OpenCVService (tiempo real), CalibrationService, MeasurementService, AI stub | 1, 2 |
| **4** ✅ | UI PyQt6 | MainWindow + tabs, feed en tiempo real con overlay, ventana calibración, historial con lista, settings | 3 |
| **5** ✅ | Integración y Polish | Conexión completa de capas, manejo de errores, logging, validación inputs, UX final | 1–4 |

---

## Detalle por Fase

### Fase 0 — Setup del Proyecto
- `requirements.txt` con versiones fijadas (opencv-python, PyQt6, ultralytics, pillow)
- `config.py` con todas las constantes editables
- `README.md` con instrucciones de instalación y ejecución
- `.gitignore` (excluye `data/images/`, `data/*.db`, `__pycache__/`, `.env`)
- Verificación: `python main.py` arranca sin errores

### Fase 1 — Capa Core (sin frameworks, sin I/O)
- `CalibrationData`: factorK, d_calibración, resolución, fecha, notas
- `Measurement`: id, nombre, área_m2, área_cm2, píxeles, factorK_usado, categoría, timestamp, ruta_imagen, distancia_cm, confianza
- `ProcessingResult`: área_píxeles, perímetro, circularidad, contornos, imágenes intermedias
- `MeasurementCategory`: A(<1m²)/B(1-2)/C(2-3)/D(3-4)/error(>4) — igual que la app Flutter
- Fórmulas puras: `compute_factor_k()`, `apply_distance_correction()`, `pixels_to_m2()`, `classify_area()`
- Verificación: ejecutar las fórmulas directamente en Python REPL

### Fase 2 — Capa Data
- SQLite con tabla `measurements` (esquema compatible con entities.py)
- `CalibrationRepository`: guarda/carga JSON local (`data/calibration.json`)
- `MeasurementRepository`: insert, get_all, get_by_id, delete, search_by_name, filter_by_category
- `ImageStorageService`: guarda PNG en `data/images/<timestamp>.png`, retorna ruta relativa
- Verificación: insertar y recuperar un registro de prueba

### Fase 3 — Servicios
- `CameraService`: detecta webcams disponibles; soporta índice entero o URL RTSP/HTTP; genera frames BGR como numpy arrays
- `OpenCVService.process_frame()`: Pipeline idéntico al Flutter — grayscale→GaussianBlur→adaptiveThreshold→findContours→largest contour→área; dibuja overlay en tiempo real (contorno verde, bounding box, área en texto)
- `CalibrationService`: calibración interactiva (captura frame → usuario dibuja rectángulo → ingresa área real + distancia → calcula factorK); corrección por distancia con la fórmula cuadrática
- `MeasurementService`: orquesta proceso → calibración → cálculo → categoría → guardar
- `AIClassifier` stub: `classify(frame) → None` (placeholder); interface lista para YOLOv8 real
- Verificación: `OpenCVService` muestra ventana con overlay en tiempo real

### Fase 4 — UI PyQt6
- **MainWindow**: 3 tabs — Cámara, Historial, Configuración
- **Tab Cámara**: feed en tiempo real con overlay de contorno + área + categoría en esquina; botón Capturar; botón Calibrar; selector de distancia actual (spinbox cm); botón toggle detección ON/OFF
- **Tab Historial**: lista de mediciones con miniatura, nombre, área, categoría, fecha; búsqueda por nombre; filtro por categoría; doble-click abre detalle; botón eliminar
- **Tab Configuración**: selector de cámara (webcam/IP); campo URL cámara IP; toggle dark/light; campo nombre de medición defecto; sección estado calibración (factorK, fecha, distancia de calibración)
- **CalibrationWindow**: asistente paso a paso — captura frame → `AreaSelectorWidget` → input área real + distancia → preview factorK → guardar
- **MeasurementDetailWindow**: imagen silueta grande + todos los metadatos
- Verificación: navegar todas las pantallas sin crashes

### Fase 5 — Integración y Polish
- Logging con `logging` stdlib (nivel INFO en consola, archivo `app.log`)
- Validación de todos los inputs del usuario (distancia > 0, área conocida > 0, nombre no vacío)
- Manejo global de excepciones no capturadas (QApplication.setExceptHook)
- Estados de carga/error en UI (spinner, mensajes de error descriptivos en español)
- Iconos y colores de categoría consistentes con la app Flutter (verde/azul/ámbar/naranja/rojo)
- README final con instrucciones completas

---

## Dependencias (requirements.txt previsto)

```
opencv-python==4.9.0.80
PyQt6==6.7.1
ultralytics==8.2.0
Pillow==10.3.0
numpy==1.26.4
```

---

## Consideraciones de Seguridad (proyecto local universitario)

- No hay credenciales ni tokens — no aplica almacenamiento seguro
- URLs de cámara IP validadas con regex antes de pasarlas a `cv2.VideoCapture`
- Nombres de archivo de imágenes generados con timestamp (no basados en input del usuario) → previene path traversal
- Queries SQLite con placeholders `?` — previene inyección SQL
- Sin llamadas de red excepto al stream de cámara IP (configurable por el usuario)

---

## Estado de las Fases

| Fase | Estado |
|------|--------|
| 0 — Setup | ⬜ Pendiente |
| 1 — Core | ⬜ Pendiente |
| 2 — Data | ⬜ Pendiente |
| 3 — Servicios | ⬜ Pendiente |
| 4 — UI | ⬜ Pendiente |
| 5 — Integración | ⬜ Pendiente |
