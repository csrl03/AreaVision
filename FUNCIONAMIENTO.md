# VisiSize — Cómo funciona el programa

## ¿Qué hace el programa?

**VisiSize** es una aplicación de escritorio que mide el **área real** (en m²) de objetos físicos usando la imagen de una cámara. El usuario apunta la cámara al objeto, el programa lo detecta automáticamente, calcula su área y la clasifica en una categoría.

Sobre esa base, VisiSize gestiona un **almacén de retales metálicos**: clasifica la geometría de cada pieza, decide si se reutiliza o se recicla, le asigna automáticamente una repisa, valora el material y exporta planos CAD.

> **Alcance del dominio**: láminas metálicas planas. El sistema **no** intenta detectar si un objeto es metálico —una cámara monocular no puede hacerlo de forma fiable—; simplemente el dominio de aplicación está definido así.
> **Alcance de la medición**: objetos planos vistos desde arriba. No se resuelven objetos volumétricos, tubos ni tuberías.

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
   (sensibilidad ajustable: Alta / Media / Baja)
       │
       ▼
4. Morfología (apertura) → elimina líneas finas, sombras y ruido
   MORPH_OPEN            puntual antes de detectar contornos
       │
       ▼
5. Morfología (cierre)   → rellena pequeños huecos dentro del objeto
   MORPH_CLOSE
       │
       ▼
6. Detección de          → encuentra los bordes del objeto
   contornos externos
       │
       ▼
7. Filtrado              → descarta contornos por tres criterios:
                           • Área mínima relativa (% del frame)
                           • Área mínima absoluta en px² (configurable)
                           • Solidez < 0.40 (descarta sombras/líneas irregulares)
                           • Área máxima (descarta el fondo completo)
       │
       ▼
8. Selección del         → el objeto principal = el contorno de mayor área
   contorno más grande
       │
       ▼
9. Cálculo de métricas   → área en píxeles, perímetro, circularidad,
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

La aplicación tiene cinco pestañas principales:

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

### Pestaña "Almacén" (versión 2)
- Árbol de **Estantes → Repisas**, con alta, edición y baja de ambos.
- Panel de la repisa seleccionada: dimensiones, capacidad, ocupación y espacio
  libre por área, y la lista de retales que contiene.
- Editor de **reglas de aceptación** por repisa.
- Exportación del plano DXF de la repisa (en metros).

### Pestaña "Inventario" (versión 2)
- Listado de todos los retales con destino, valor y alerta de riesgo.
- Filtro por destino (reutilizable / reciclaje) y búsqueda por nombre.
- Ficha completa de cada retal, con cambio de estado y exportación DXF
  (desde la silueta real o desde el rectángulo de sus dimensiones).
- **Buscador de reutilización**: se introducen las dimensiones de la pieza que
  se quiere fabricar y el sistema lista los retales que la cubren.
- Resumen: total de retales, m² por destino, valor acumulado, alertas y
  retales sin ubicación.

### Pestaña "Configuración"
- Selección de fuente de cámara (webcam por índice o URL de IP).
- Gestión de calibración: ver calibración actual, crear nueva o eliminarla.
- Ajuste de tema visual (oscuro / claro).
- **Detección de contornos** (persistente entre sesiones):
  - *Área mínima (px²)*: contornos con menos píxeles son ignorados completamente. Útil para descartar piezas muy pequeñas o partículas de ruido.
  - *Sensibilidad*: Alta / Media / Baja. Controla la agresividad del umbral adaptativo. "Baja" descarta sombras y bordes de pared que no son objetos sólidos.
- **Rangos de categorías (m²)**: el usuario define el límite superior de cada categoría A, B, C, D. Las clasificaciones se aplican inmediatamente sin reiniciar. Los valores persisten en `data/settings.json`.
- **Gestión de retales (versión 2)**: costo por m², símbolo de moneda, área
  mínima y máxima reutilizables, espesor mínimo, regularidad mínima, umbral de
  alerta de riesgo, tolerancia de simplificación del DXF y la política para los
  retales que no encuentran ubicación.

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
Abre el diálogo "Revisar retal" (sección 10)
        │
        ▼
Usuario confirma → retal + medición guardados en SQLite + imagen PNG
```

---

## 10. Gestión de retales (añadido en la versión 2)

A partir de aquí, todo lo anterior sigue igual. Lo que sigue se apoya en el
mismo pipeline y el mismo FactorK; no lo sustituye.

### 10.1 Flujo completo

```
Capturar
   ↓  pipeline OpenCV (sin cambios)
Detectar objeto
   ↓  área calibrada en m²
Calcular área
   ↓  minAreaRect → dimensiones reales
Clasificar geometría
   ↓  core/geometry.py
Determinar regularidad
   ↓  solidez + suavidad + muesca
Evaluar espesor            ← entrada MANUAL del usuario
   ↓
Evaluar riesgo punzante    ← core/safety.py
   ↓
Evaluar reutilización      ← services/classification_service.py
        ├── NO  → RECICLABLE (+ lista de motivos)
        └── SÍ  → Buscar ubicaciones compatibles
                     ↓  reglas de cada repisa
                  Comprobar espacio físico
                     ↓  core/packing.py (packing 2D + rotación 90°)
                  Asignar repisa
   ↓
Registrar → Inventario → Valor estimado → Exportar DXF
```

### 10.2 Dimensiones reales, no solo el área

El área por sí sola no basta. `core/geometry.py` calcula además el
**rectángulo mínimo rotado** (`cv2.minAreaRect`), que da el largo y el ancho
reales de la pieza.

> Por qué no `cv2.boundingRect`: devuelve el rectángulo alineado a los ejes. Una
> pieza de 1.20 × 0.40 m girada 45° reportaría aspecto ≈1.0 en lugar de ≈3.0, y
> toda la clasificación se desviaría. Es el fallo documentado en
> `GestionErrores/opencv-oversensitive-macro-shapes.md` (Sol-2).

### 10.3 Clasificación geométrica

Ninguna métrica decide sola. Se combinan cinco evidencias:

| Evidencia | Para qué sirve |
|---|---|
| `approxPolyDP` con ε = 2 % del perímetro | Nº de vértices de la polilínea simplificada |
| `cv2.minAreaRect` | Dimensiones reales |
| solidez = área / área del hull | Separa polígonos simples de formas cóncavas |
| circularidad = 4πA/P² | Distingue disco de polígono |
| déficit de área de la simplificación | **Separa círculo de hexágono** (ver abajo) |

| Resultado | Etiqueta |
|---|---|
| circular ≥ 0.84 + hull limpio + déficit ≥ 0.05 | `circulo` |
| 4 vértices, sólido, aspecto ≈ 1 | `cuadrado` |
| 4 vértices, sólido ≥ 0.90 | `rectangulo` |
| 3 vértices, sólido ≥ 0.80 | `triangulo` |
| 5–8 vértices, sólido, lados parecidos | `poligono_regular` |
| resto | `poligono_irregular` / `otra` |

**El detalle del círculo.** Un círculo digitalizado de 100 px tiene circularidad
0.893 (la escalera de píxeles infla el perímetro) y un hexágono regular del mismo
radio tiene 0.824. Los rangos se solapan, así que la circularidad sola no basta.
El discriminante fiable es el **déficit de área**: un polígono regular se puede
representar con exactamente sus n vértices, así que `approxPolyDP` lo reproduce
sin perder nada (déficit ≈ 0.003), mientras que un círculo no tiene un número
finito de vértices y cualquier polilínea inscrita queda dentro (déficit ≈ 0.094).
La diferencia es de un orden de magnitud.

Cada clasificación devuelve un `confidence` heurístico. **No es una certeza**: es
cuán respaldada está la etiqueta por las métricas.

### 10.4 Regularidad

La regularidad responde a *"¿esto es un corte limpio de máquina o un borde
rasgado?"*, **no** a *"¿es simétrico?"*.

> Por qué: un rectángulo tiene lados `[L, W, L, W]`, así que su coeficiente de
> variación de lados es `|L−W|/(L+W)` — 0.25 para un 2:1 y 0.50 para un 3:1.
> Cualquier medida de simetría marcaría como irregular un rectángulo
> perfectamente limpio, y en un almacén de recortes eso es un falso negativo
> constante.

```
regularidad = 0.40·solidez + 0.35·suavidez + 0.25·(1 − muesca)
```

La **suavidez** usa el número de vértices como proxy: `approxPolyDP` colapsa un
corte limpio en 3–8 vértices, pero necesita 17–40 para seguir el dentado de una
rotura de chapa. La **muesca** usa la profundidad del defecto de convexidad
*relativa al tamaño de la pieza*, no el número de defectos: un círculo
digitalizado produce 2–3 defectos de 1 px que no deben penalizarlo.

`REGULAR` ≥ 0.92 · `IRREGULAR` ≤ 0.75 · `SEMI_REGULAR` en medio.

### 10.5 Detección de geometrías potencialmente punzantes

> ⚠ **Esto NO certifica seguridad industrial.** Solo genera una alerta de riesgo
> potencial a partir de la silueta observada. La ausencia de alerta no significa
> que la pieza sea segura.

Un umbral único del tipo `if ángulo < 30°: peligro` produce demasiados falsos
positivos: una lámina rectangular vista en perspectiva puede reportar 30–40° de
error sin tener ninguna punta, y un triángulo normal tiene un vértice a 60°.

Por eso el `sharpness_score` combina **cinco señales normalizadas**:

| Señal | Peso | Qué detecta |
|---|---|---|
| Ángulo interno mínimo | 0.30 | Vértices agudos |
| Profundidad de protrusión (`1 − hull/area`) | 0.25 | Puntas sobresaliendo del cuerpo |
| Factor de espina | 0.20 | Salientes estrechas y lengüetas |
| Defecto de convexidad | 0.15 | Muescas profundas |
| Relación de aspecto local (p90/min) | 0.10 | Astillas y dientes finos |

El resultado se compara con un **umbral configurable** (por defecto 0.55):

```
cuadrado 0.11   rectángulo 0.08   círculo 0.28   triángulo 0.23
L-shape  0.52   muesca 0.59 ⚠      estrella 0.65 ⚠    sierra 0.70 ⚠
```

### 10.6 Almacén: estantes y repisas

El usuario define la estructura; el sistema nunca la presupone.

```
Almacén
├── Estante 1
│   ├── Repisa 1   2.00 × 1.20 m   [reglas de aceptación]
│   └── Repisa 2
└── Estante 2
    └── Repisa 1
```

Cada repisa tiene dimensiones y reglas configurables: admite formas regulares
y/o irregulares, y rangos de ancho, largo, área y espesor. **Dejar un límite en 0
significa "sin límite"** en ese extremo.

### 10.7 Asignación: por qué no basta el área

Este es el punto donde un sistema ingenuo falla:

```
Repisa = 2.00 × 1.00 m
Retal A = 1.00 × 1.50 m   (1.50 m²)
Retal B = 0.20 × 7.50 m   (1.50 m²)
```

Ambos tienen menos área que la repisa, pero **ninguno de los dos cabe**. Un
filtro por área aceptaría los dos. Por eso `core/packing.py` exige una posición
real libre.

**Algoritmo employed — "shelf-first" determinista:**

1. Filtro barato: ¿cabe en alguna de las dos orientaciones?
2. Reglas de la repisa (forma, dimensiones, área, espesor).
3. Barrido de estanterías horizontales: se agrupan los rectángulos ya colocados
   por su Y, y se busca la primera estantería con hueco.
4. Si no cabe, segunda pasada "best-fit" sobre todos los bordes X/Y.
5. Entre repisas válidas gana la que deja **más** área libre (agrupa piezas
   parecidas en vez de dispersarlas).

Garantías del algoritmo:

- **Determinista** — el mismo inventario produce siempre la misma posición.
- **Conservador** — si devuelve «no cabe», es que de verdad no halló hueco.
- **Sin solapamientos** — cada pieza se ancla en un hueco verificado libre.
- **Sustituible** — la UI nunca lo llama directamente; todo pasa por
  `AllocationService`, de modo que reemplazarlo por MaxRects o por un
  optimizador real solo requiere tocar `core/packing.py`.

> **No es un bin packing óptimo.** Resolverlo es NP-difícil. Esta heurística es
> conservadora y documentada, y su arquitectura permite mejorarla.

Cuando no encuentra hueco, el sistema lo dice explícitamente:
`No se encontró una ubicación física compatible.` + el detalle de por qué se
descartó cada repisa.

### 10.8 Reutilizable vs. reciclaje

Un retal va a **RECICLAJE** si:

- el área es menor al mínimo reutilizable;
- el área es mayor al máximo reutilizable (si está configurado);
- el espesor es menor al mínimo;
- la regularidad es menor al mínimo;
- o, si el usuario lo activó, no cabe en ninguna repisa.

La interfaz siempre muestra **por qué**:

```
Destino: RECICLAJE
Motivos:
· Espesor inferior al mínimo (0.5 < 2.0 mm).
· Forma demasiado irregular (regularidad 0.39 < 0.70).
```

**Todos los umbrales son configurables** desde Configuración → Gestión de
retales. No hay ningún valor de negocio escrito en el código.

> Si la regularidad es *desconocida* (no se pudo analizar el contorno), el retal
> **no** se manda a reciclaje: «no lo sé» no es «es irregular».

### 10.9 Espesor

Una cámara monocular **no puede medir el espesor**. En esta versión es **entrada
manual** en el diálogo de revisión.

La arquitectura ya está preparada para sustituirlo:

```
Entrada manual ──→  espesor_mm
                        │
                        ▼
             (futuro) sensor / visión
```

`espesor_mm` es un campo `NULL`-able en la base de datos y un parámetro
independiente del pipeline, así que cambiar la fuente no toca nada más.

### 10.10 Valor económico

```
valor_estimado = area_m2 × costo_por_m2_lamina
```

Con `costo_por_m2_lamina = 85.000` y un retal de 1.40 m² → `$ 119.000`.

> **No se asume ningún precio para el reciclaje.** Si el negocio necesita
> valorar el chatarra, se añade `precio_reciclaje` como campo independiente,
> nunca como un factor oculto sobre el mismo número.

### 10.11 Exportación DXF

```
Contorno OpenCV
     ↓  approxPolyDP (ε configurable = % del perímetro)
Polilínea de pocos vértices
     ↓  escala px → mm
Geometría en milímetros
     ↓
DXF
```

- Si la geometría se reconoce como un disco limpio, escribe un **CIRCLE**
  nativo; en caso contrario, una **LWPOLYLINE** cerrada.
- El criterio es **exactamente el mismo** que usa la clasificación, para que lo
  que se ve en pantalla como «Círculo» sea lo que se abre en AutoCAD.
- Se exportan a **milímetros**; los planos de repisa, a **metros**.
- Los nombres de archivo se generan del id y del timestamp, **nunca** del texto
  del usuario (defensa contra path traversal).

> **Por qué DXF y no DWG:** DWG es un formato binario propietario y no hay
> librería Python fiable y libre para escribirlo. DXF es el estándar de
> intercambio que leen AutoCAD, BricsCAD, LibreCAD, QCAD y Fusion.

> **Por qué la simplificación es obligatoria:** una máscara de 1280×720 produce
> miles de puntos. Volcarlos tal cual genera un archivo de varios MB que tarda
> segundos en abrir, reproduce cada artefacto de la segmentación como si fuera
> geometría real y es inútil como plano de corte.

### 10.12 Inventario y búsqueda de reutilización

Cada retal reutilizable guarda: dimensiones, área, espesor, forma, regularidad,
confianza, vértices, ubicación, fecha, silueta, `sharpness_score`, estado y
valor estimado.

El buscador responde a la pregunta operativa:

> *Necesito fabricar una pieza de 1.10 × 0.80 m, ¿qué retales tengo?*

Filtra por ancho, largo, área, espesor y forma, evaluando **ambas rotaciones**:
un retal de 1.00 × 0.40 m sirve para pedir 0.50 × 0.90 m girado.

---

## 11. Archivos y carpetas clave

```
AreaCamPython_v1/
├── config.py              ← Configuración global (cámara, rutas, tema)
├── main.py                ← Punto de entrada de la aplicación
├── pytest.ini             ← Configuración de las pruebas
├── app.log                ← Log de actividad (se crea al ejecutar)
├── core/
│   ├── formulas.py        ← Cálculos matemáticos (FactorK, área, categorías)
│   ├── entities.py        ← Estructuras de datos (Medición, Calibración, Retal, Repisa)
│   ├── constants.py       ← Parámetros del pipeline y límites de categoría
│   ├── geometry.py        ← Clasificación geométrica y dimensiones reales
│   ├── safety.py          ← Detección de geometrías punzantes
│   ├── packing.py         ← Packing 2D con rotación de 90°
│   ├── scoring.py         ← Valoración económica
│   └── dxf.py             ← Generación de planos DXF
├── services/
│   ├── calibration_service.py     ← Lógica de calibración y corrección
│   ├── measurement_service.py     ← Orquesta el procesamiento de cada frame
│   ├── camera_service.py          ← Conexión con webcam o cámara IP
│   ├── opencv_service.py          ← Pipeline de procesamiento de imagen
│   ├── classification_service.py  ← Reutilización vs. reciclaje
│   ├── allocation_service.py      ← Asignación automática de repisa
│   └── cad_service.py             ← Fachada de exportación DXF
├── data/
│   ├── database.py          ← Esquema SQLite y migraciones
│   ├── repositories.py      ← CRUD de mediciones e imágenes
│   ├── storage_repositories.py ← CRUD de estantes, repisas y retales
│   ├── settings_repository.py  ← Preferencias del usuario
│   ├── calibration.json     ← Calibración activa (JSON)
│   ├── settings.json        ← Configuración del usuario
│   ├── measurements.db      ← Historial, almacén e inventario (SQLite)
│   ├── images/              ← Siluetas PNG
│   └── dxf/                 ← Planos DXF exportados
├── tests/                   ← Suite de pruebas (pytest)
└── ui/
    ├── windows/             ← Ventanas, pestañas y diálogos
    └── widgets/             ← Componentes reutilizables
```
