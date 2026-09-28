# VisiSize Python v1

**Aplicación de escritorio** que mide el **área real (en m²)** de objetos físicos usando la imagen de una cámara (webcam USB o cámara IP/RTSP). Detecta el objeto automáticamente mediante visión por computador (OpenCV), aplica un factor de calibración píxel→metro y clasifica el resultado en categorías A/B/C/D con código de colores.

Sobre esa base, **gestiona un almacén de retales metálicos**: clasifica la geometría de cada pieza, decide si se reutiliza o se recicla, le asigna automáticamente una repisa, valora el material y exporta planos CAD en DXF.

> Para una explicación detallada del funcionamiento interno (pipeline de imagen, modelo de calibración, clasificación geométrica, almacenamiento de datos, etc.) consulta [FUNCIONAMIENTO.md](FUNCIONAMIENTO.md).

## ¿Cómo funciona en resumen?

1. **Detección** — Cada fotograma pasa por un pipeline OpenCV: escala de grises → desenfoque gaussiano → umbralización adaptativa → apertura morfológica (elimina sombras y líneas) → cierre morfológico → detección de contornos. Los contornos se filtran por área mínima absoluta (en px²), ratio relativo al frame y solidez mínima. El contorno más grande restante se toma como el objeto a medir.
2. **Calibración** — Antes de medir, el usuario fotografía un objeto de área conocida (p. ej. una hoja A4) y dibuja un rectángulo sobre él. El sistema calcula el **FactorK** (m²/px²) que relaciona píxeles con metros cuadrados reales.
3. **Corrección de distancia** — Si la cámara cambia de altura respecto a la calibración, el FactorK se corrige automáticamente con `FactorK × (d_cal / d_actual)²`.
4. **Clasificación** — El área resultante se categoriza (A, B, C, D, fuera de rango) según rangos configurables por el usuario desde la pestaña Configuración. Los cambios se aplican en caliente y persisten entre sesiones.
5. **Persistencia** — Cada medición se guarda en una base de datos SQLite local junto con la silueta PNG del objeto. La configuración de detección y categorías se guarda en `data/settings.json`.

### Gestión de retales (versión 2)

6. **Geometría** — Del contorno se obtiene el **rectángulo mínimo rotado**, que da el largo y el ancho reales de la pieza, y se clasifica la forma (círculo, cuadrado, rectángulo, triángulo, polígono regular/irregular) combinando cinco evidencias geométricas. No basta el área: dos piezas del mismo tamaño pueden ocupar la repisa de forma muy distinta.
7. **Riesgo punzante** — Un `sharpness_score` compuesto por cinco señales (ángulo mínimo, protuberancia, espinas, defecto de convexidad y aspecto local) avisa de geometrías potencialmente cortantes. **No es una certificación de seguridad industrial.**
8. **Reutilización vs. reciclaje** — Se decide con umbrales configurables (área, espesor, regularidad) y **siempre se muestra el motivo**.
9. **Asignación automática** — Se busca la repisa que cumpla sus reglas y **que tenga hueco físico real**, con packing 2D y rotación de 90°. Un retal que solo "cabe por área" pero no por dimensiones se rechaza.
10. **Inventario y valor** — Los retales reutilizables se inventarían con su valor estimado (`área × costo por m²`) y se puede buscar si alguno sirve para fabricar una pieza pedida.
11. **Exportación DXF** — El contorno real, simplificado geométricamente y escalado a milímetros, se exporta como plano CAD.

Aplicación de escritorio para medir áreas de superficies planas (láminas, paneles, tubos)
usando visión por computador (OpenCV) en tiempo real con cámara.

## Requisitos

- Python 3.11 o superior
- Webcam USB o cámara IP accesible desde la red local

## Instalación

```bash
# 1. Clonar / copiar el proyecto
cd AreaCamPython_v1

# 2. Crear entorno virtual (recomendado)
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

# 3. Instalar dependencias
pip install -r requirements.txt
```

## Ejecución

```bash
python main.py
```

## Uso básico

### Primera vez — Calibrar la app

1. Coloca un objeto de **área conocida** frente a la cámara (ej: hoja A4 = 0.0623 m²).
2. Ve a la pestaña **Configuración** → botón **Nueva calibración**.
3. Captura el frame, dibuja un rectángulo sobre el objeto de referencia.
4. Ingresa el área real del objeto y la distancia cámara-objeto en centímetros.
5. Guarda la calibración.

### Medir un objeto

1. Ve a la pestaña **Cámara**.
2. Ingresa la distancia actual entre la cámara y el objeto (en cm).
3. Apunta la cámara al objeto — verás el contorno detectado en verde en tiempo real.
4. Presiona **Capturar** cuando el contorno sea correcto.
5. Asigna un nombre y guarda la medición.

### Ver historial

- La pestaña **Historial** muestra todas las mediciones guardadas.
- Busca por nombre o filtra por categoría.
- Haz doble clic en una medición para ver su detalle completo.

## Categorías de área

| Categoría | Rango       | Color   |
|-----------|-------------|---------|
| A         | < 1.0 m²    | Verde   |
| B         | 1.0 – 2.0 m²| Azul    |
| C         | 2.0 – 3.0 m²| Ámbar   |
| D         | 3.0 – 4.0 m²| Naranja |
| Error     | > 4.0 m²    | Rojo    |

## Fórmula de calibración

```
factorK_base = área_real_m² / área_píxeles
factorK_correcto = factorK_base × (d_calibración / d_medición)²
área_m² = área_píxeles × factorK_correcto
```

La corrección cuadrática compensa que el objeto ocupa menos píxeles cuando
está más lejos de la cámara.

## Estructura del proyecto

```
AreaCamPython_v1/
├── main.py              # Entry point
├── config.py            # Configuración editable
├── requirements.txt
├── pytest.ini           # Configuración de pruebas
├── core/                # Dominio puro: entidades, fórmulas, geometría,
│                        # seguridad, packing, valoración y DXF
├── services/            # Lógica: cámara, OpenCV, calibración, medición,
│   │                    # clasificación, asignación y CAD
│   └── ai_classifier/   # Stub para clasificador IA futuro (YOLOv8)
├── data/                # Persistencia: SQLite + imágenes + DXF en disco
├── tests/               # Suite de pruebas (pytest)
└── ui/                  # Interfaz PyQt6 (5 pestañas)
    ├── windows/
    └── widgets/
```

## Pruebas

```bash
python -m pytest              # toda la suite
python -m pytest -v           # con detalle
python -m pytest tests/test_packing.py
```

La suite cubre el packing 2D, la clasificación geométrica, el detector de
riesgo, la valoración económica, los servicios de clasificación y asignación,
la exportación DXF, la migración del esquema SQLite y una batería de **pruebas
de regresión** de la funcionalidad original (calibración, FactorK, categorías,
pipeline OpenCV, imágenes, historial y configuración).

## Alcance y limitaciones

Este documento describe lo que el sistema hace y lo que **no** hace. Las
limitaciones son reales, no son artefactos de diseño pendientes:

| Área | Estado | Nota |
|---|---|---|
| Detección de "metal" | **No implementada** | Una cámara monocular no puede determinarlo. El dominio de la app está definido como lámina metálica; no se simula. |
| Espesor | **Entrada manual** | No hay sensor. La arquitectura ya admite sustituir la fuente sin tocar nada más. |
| Clasificación de forma | **Heurística** | Umbrales ajustados sobre figuras sintéticas. La confianza indica cuánto respalda la etiqueta, no una certeza. |
| Riesgo punzante | **Alerta, no certificación** | Solo analiza la silueta 2D. No cubre riesgo real de corte. |
| Packing | **Heurística determinista** | No es un bin packing óptimo (NP-difícil). Conservadora y sustituible. |
| Dodecágono vs. círculo | **Ambiguo** | A la resolución de trabajo, un polígono de 12 lados y un círculo dan las mismas métricas. No se pueden separar. |
| Inclinación de la pieza | **Distorsiona** | El FactorK asume cámara cenital. Una pieza muy inclinada da medidas incorrectas. |
| Conversión a mm | **Asume FactorK vigente** | El DXF se escala con el FactorK del momento de la medición. |
| DWG | **No implementado** | DWG es propietario; no hay librería libre fiable. El formato estándar es DXF. |
| Detección de textura superficial | **No implementada** | Un retal de 2 mm y otro de 0,5 mm se ven iguales. Por eso el espesor es manual. |

## Notas sobre el clasificador IA (Feature Futura)

El módulo `services/ai_classifier/` contiene la interfaz lista para conectar
un modelo YOLOv8 entrenado con clases personalizadas (Lámina, Tubo, Panel, etc.).
Actualmente retorna `None` (sin clasificación). Para activarlo, entrenar el modelo
y seguir las instrucciones en `services/ai_classifier/yolo_classifier.py`.
