# VisiSize — Cómo funciona el programa

## ¿Qué hace el programa?

**VisiSize** es una aplicación de escritorio que mide el **área real** (en m²) de objetos físicos usando la imagen de una cámara. El usuario apunta la cámara al objeto, el programa lo detecta automáticamente, calcula su área y la clasifica en una categoría.

---

## 1. Modelo de detección de área y forma (pipeline de imagen)

El corazón del programa es una cadena de procesamiento de imagen que funciona en tiempo real sobre cada fotograma de la cámara:

```
Frame de cámara
       │
       ▼
1. Escala de grises      → elimina el color, solo luminosidad
       │
       ▼
2. Desenfoque gaussiano  → suaviza el ruido de la imagen
       │
       ▼
3. Umbralización         → convierte la imagen a blanco/negro
   adaptativa            (el objeto queda blanco, el fondo negro)
       │
       ▼
4. Morfología (cierre)   → rellena pequeños huecos dentro del objeto
       │
       ▼
5. Detección de          → encuentra los bordes del objeto
   contornos externos
       │
       ▼
6. Filtrado              → descarta contornos demasiado pequeños o
                           demasiado grandes (ruido o fondo completo)
       │
       ▼
7. Selección del         → el objeto principal = el contorno de mayor área
   contorno más grande
       │
       ▼
8. Cálculo de métricas   → área en píxeles, perímetro, circularidad,
                           relación de aspecto (ancho/alto)
```

### ¿Qué se calcula sobre la forma?

| Métrica | Descripción |
|---|---|
| **Área (px²)** | Número de píxeles que cubre el objeto |
| **Perímetro (px)** | Longitud del borde del objeto en píxeles |
| **Circularidad** | Qué tan redondo es el objeto (1.0 = círculo perfecto) |
| **Relación de aspecto** | Ancho dividido entre alto del bounding box |

### De píxeles a metros cuadrados

La fórmula central es:

```
Área real (m²) = Área (px²) × FactorK
```

Donde **FactorK** (m²/px²) es el puente entre el mundo de píxeles y el mundo real. Este factor se obtiene en la **calibración** (ver sección 2).

---

## 2. Calibración — el puente entre píxeles y el mundo real

La calibración es obligatoria antes de poder medir. Sin ella, el programa detecta el objeto pero no puede expresar su área en metros cuadrados.

### ¿Para qué sirve?

La misma cámara a distancias diferentes produce tamaños de objeto diferentes en píxeles. La calibración establece la relación entre píxeles y metros para una configuración específica de cámara y distancia.

### ¿Cómo se realiza? (3 pasos guiados)

**Paso 1 — Capturar imagen de referencia**
Coloca un objeto de **área real conocida** frente a la cámara (ejemplos típicos: una hoja A4 = 0.0623 m², una baldosa 30×30 cm = 0.09 m²). El programa congela un fotograma.

**Paso 2 — Seleccionar el objeto en la imagen**
El usuario dibuja un rectángulo alrededor del objeto de referencia con el ratón. El programa mide el área de ese rectángulo en píxeles.

**Paso 3 — Introducir datos reales**
El usuario escribe el área real del objeto (m²) y la distancia actual cámara-objeto (cm). El programa calcula:

```
FactorK = Área real (m²) / Área en píxeles (px²)
```

### Corrección por distancia

Si durante la medición el objeto está a una distancia diferente a la de calibración, el programa ajusta el FactorK automáticamente:

```
FactorK corregido = FactorK base × (distancia_calibración / distancia_medición)²
```

Esto compensa la perspectiva: un objeto más lejos aparece más pequeño en píxeles, pero su área real no cambia.

### ¿Dónde se guarda?

La calibración se guarda en `data/calibration.json` con estos campos:

```json
{
  "factor_k": 0.000123,
  "calibration_area_pixels": 48500.0,
  "calibration_area_real_m2": 0.0623,
  "calibration_image_width": 1280,
  "calibration_image_height": 720,
  "calibration_distance_cm": 80.0,
  "calibration_date": "2026-03-17T10:30:00",
  "notes": "Hoja A4, luz natural"
}
```

El programa avisa si la calibración tiene más de **30 días** o si la resolución de cámara actual difiere más del **±10%** de la resolución usada en la calibración.

---

## 3. Categorías de área

El resultado de cada medición se clasifica automáticamente según rangos de área:

| Categoría | Rango | Color |
|---|---|---|
| **A — Pequeño** | < 1.0 m² | Verde |
| **B — Mediano** | 1.0 – 2.0 m² | Azul |
| **C — Grande** | 2.0 – 3.0 m² | Ámbar |
| **D — Muy grande** | 3.0 – 4.0 m² | Naranja |
| **Error / Fuera de rango** | > 4.0 m² | Rojo |

Si el área cae dentro del ±5% de un límite de categoría, el programa muestra una advertencia indicando que un pequeño error podría cambiar la clasificación.

---

## 4. Selección de cámara

El programa soporta dos tipos de fuente de imagen:

### Webcam local
- Se detectan automáticamente los índices disponibles (0, 1, 2…).
- El índice 0 suele ser la cámara integrada del equipo.
- Se pueden configurar resolución y FPS (por defecto 1280×720 a 30 fps).

### Cámara IP / RTSP
- Se introduce la URL directamente en la configuración.
- Formatos soportados:
  - `rtsp://192.168.1.10:554/stream`
  - `http://192.168.1.10:8080/video`
- El programa valida que la URL tenga el formato correcto antes de conectar.

---

## 5. Almacenamiento de datos

### Base de datos — `data/measurements.db` (SQLite)

Cada medición guardada queda registrada con los siguientes campos:

| Campo | Descripción |
|---|---|
| `id` | Identificador único (autogenerado) |
| `name` | Nombre opcional del registro |
| `area_pixels` | Área del objeto en píxeles cuadrados |
| `area_m2` | Área real calculada en metros cuadrados |
| `category` | Categoría asignada (A/B/C/D/error) |
| `factor_k_used` | FactorK aplicado en esa medición |
| `distance_cm` | Distancia cámara-objeto al momento de medir |
| `timestamp` | Fecha y hora exactas de la medición |
| `notes` | Notas libres del usuario |
| `silhouette_path` | Ruta a la imagen guardada (si aplica) |
| `perimeter_pixels` | Perímetro del objeto en píxeles |
| `circularity` | Índice de circularidad del objeto |
| `confidence` | Confianza del clasificador IA (reservado) |
| `is_valid` | Indica si la medición está activa o fue marcada como inválida |

### Imágenes — `data/images/`

Al guardar una medición, se puede almacenar la silueta del objeto como imagen PNG. Las imágenes se redimensionan a un máximo de **512 px** por lado para ahorrar espacio.

### Log de actividad — `app.log`

Toda la actividad del programa (errores, calibraciones, mediciones) queda registrada en este archivo de texto en la raíz del proyecto.

---

## 6. Interfaz de usuario

La aplicación tiene tres pestañas principales:

### Pestaña "Cámara"
- Visualización en tiempo real del feed de cámara con el contorno detectado dibujado sobre el objeto.
- Panel lateral con:
  - Botones de inicio/detención de cámara.
  - Control de **distancia cámara-objeto** (ajusta el FactorK en tiempo real).
  - Botón de captura para guardar una medición.
  - Resultado del último frame: área, categoría, circularidad.

### Pestaña "Historial"
- Listado de todas las mediciones guardadas.
- Acceso a los detalles de cada medición y su imagen de silueta.
- Opción de eliminar registros individuales o borrar todo el historial.

### Pestaña "Configuración"
- Selección de fuente de cámara (webcam por índice o URL de IP).
- Gestión de calibración: ver calibración actual, crear nueva o eliminarla.
- Ajuste de tema visual (oscuro / claro).

---

## 7. Clasificador IA (YOLO) — en desarrollo

El programa incluye la infraestructura para un clasificador basado en **YOLOv8** (visión por computadora con inteligencia artificial) que identificará el **tipo de objeto** detectado (lámina, tubo, panel, placa, etc.).

Actualmente este módulo está en modo **placeholder**: el esqueleto está implementado pero inactivo hasta que el modelo entrenado esté disponible. Cuando esté listo, se activará sin cambios en el resto del sistema.

---

## 8. Flujo completo de una medición

```
Usuario inicia cámara
        │
        ▼
Pipeline detecta objeto en cada frame → muestra overlay en tiempo real
        │
        ▼
Usuario ajusta distancia cámara-objeto en el panel lateral
        │
        ▼
Usuario presiona "Capturar"
        │
        ▼
Sistema aplica FactorK (con corrección de distancia) → calcula área m²
        │
        ▼
Asigna categoría A/B/C/D → muestra resultado con color
        │
        ▼
Usuario confirma → registro guardado en SQLite + imagen PNG opcional
```

---

## 9. Archivos y carpetas clave

```
AreaCamPython_v1/
├── config.py              ← Configuración global (cámara, rutas, tema)
├── main.py                ← Punto de entrada de la aplicación
├── app.log                ← Log de actividad (se crea al ejecutar)
├── core/
│   ├── formulas.py        ← Cálculos matemáticos (FactorK, área, categorías)
│   ├── entities.py        ← Estructuras de datos (Medición, Calibración)
│   └── constants.py       ← Parámetros del pipeline y límites de categoría
├── services/
│   ├── calibration_service.py  ← Lógica de calibración y corrección
│   ├── measurement_service.py  ← Orquesta el procesamiento de cada frame
│   ├── camera_service.py       ← Conexión con webcam o cámara IP
│   └── opencv_service.py       ← Pipeline de procesamiento de imagen
├── data/
│   ├── calibration.json   ← Calibración activa (JSON)
│   ├── measurements.db    ← Historial de mediciones (SQLite)
│   └── images/            ← Siluetas PNG guardadas
└── ui/
    ├── windows/           ← Ventanas principales y diálogos
    └── widgets/           ← Componentes reutilizables (feed, selector de área)
```
