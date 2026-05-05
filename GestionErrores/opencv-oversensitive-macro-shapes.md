---
error-id: opencv-oversensitive-macro-shapes
status: en-progreso
fecha-inicio: 2026-05-04
fecha-resolucion:
plataforma: python / opencv
---

# OpenCV detecta sombras y detalles internos — clasificador siempre retorna "Otro"

## Descripción
OpenCV detecta contornos de sombras, texturas internas y detalles finos dentro
de las figuras en lugar de captar el contorno externo "macro" del objeto.
El clasificador geométrico recibe métricas incoherentes (circularidad y aspecto
de un fragmento de sombra, no del objeto real) y siempre retorna "Otro".

## Contexto
- **Servicio**: `services/opencv_service.py`
- **Clasificador**: `services/ai_classifier/geometry_classifier.py`
- **Configuración activa**: sensibilidad "baja" en settings.json

---

## Causas Posibles

1. **`adaptive_c` demasiado bajo y `block_size` pequeño** — La umbralización
   adaptativa con ventana pequeña y C bajo resalta variaciones locales mínimas
   (textura, sombras suaves), generando muchos contornos pequeños dentro del
   objeto. El filtro de solidez (0.40) es demasiado permisivo para descartarlos.
   Indicio: se ven muchos contornos dentro de la figura, no solo el borde externo.

2. **`MORPH_CLOSE` con kernel pequeño (5×5)** — El kernel de cierre morfológico
   no es lo suficientemente grande para unir los fragmentos del contorno exterior
   en un único contorno sólido, especialmente en objetos grandes (láminas).
   Indicio: el contorno del objeto aparece como varios arcos separados en lugar
   de un polígono cerrado.

3. **`MIN_CONTOUR_AREA_RATIO = 0.001` deja pasar fragmentos** — El 0.1% del
   área de un frame 640×480 es solo ~307 px², contornos de sombras internas
   superan fácilmente ese umbral. El clasificador toma el "más grande" de esos
   fragmentos, que puede ser una sombra interior, no el objeto completo.
   Indicio: `result.area_pixels` reporta valores pequeños aunque el objeto
   sea grande en pantalla.

4. **`aspect_ratio` en `ProcessingResult` usa bounding rect alineado** —
   `cv2.boundingRect` devuelve un rectángulo alineado con los ejes, no el
   mínimo rotado. Para objetos inclinados el aspecto aparece distorsionado
   (ej: tubo a 45° da aspecto ≈1.0 en lugar de ≈3–4), forzando la
   clasificación hacia "Otro".
   Indicio: el clasificador falla para objetos inclinados.

---

## Plan de Soluciones

| # | Solución | Causa que Ataca | Estado |
|---|----------|-----------------|--------|
| Sol-1 | Subir umbrales de sensibilidad a modo "macro" (adaptive_c alto + block_size grande + MORPH_CLOSE mayor + solidity alto) | Causas 1 + 2 + 3 | 🔄 En progreso |
| Sol-2 | Reemplazar `cv2.boundingRect` por `cv2.minAreaRect` para calcular `aspect_ratio` correcto | Causa 4 | ⏳ Pendiente |
| Sol-3 | Pre-filtrar contornos por convex hull antes de seleccionar el más grande | Causa 3 + 1 | ⏳ Pendiente |

---

## Intentos

### Sol-1 — Parámetros "macro" en sensibilidad baja + solidity alto — Estado: 🔄 En progreso

**Cambios aplicados:**
- `SENSITIVITY_PARAMS["baja"]`: `adaptive_c 14→22`, `block_size 31→51`
- `CONTOUR_SOLIDITY_THRESHOLD` default: `0.40→0.65`
- `MORPH_CLOSE` kernel: `(5,5)→(11,11)` iterations=2
- `MIN_CONTOUR_AREA_PIXELS` default: `500→2000`
- `SENSITIVITY_PARAMS` agrega nivel `"macro"` dedicado

**Instrucciones para el usuario:**
1. Reiniciar la app (`python main.py`)
2. En Configuración → Sensibilidad de detección → seleccionar **"Baja"**
3. Apuntar la cámara a una lámina o tubo y verificar si el contorno verde
   ahora rodea el objeto completo (no sus detalles internos)
4. Observar si el label IA cambia de "Otro" a "Lámina"/"Tubo"

**Resultado:**
<!-- Completar tras feedback del usuario -->

---

## Resolución Final
<!-- Solo completar cuando status = resuelto -->
