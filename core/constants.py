"""
Constantes del algoritmo de visión por computador.

¡IMPORTANTE! Estos valores deben ser idénticos a los de la app Flutter (opencv_dart)
para que los resultados sean comparables entre ambas plataformas.
Modificarlos afecta TODOS los resultados existentes y rompe la compatibilidad
con calibraciones guardadas.
"""

# ─── Pipeline OpenCV ───────────────────────────────────────────────────────────
GAUSSIAN_KERNEL_SIZE: int = 5        # Tamaño del kernel de blur (debe ser impar)
GAUSSIAN_SIGMA: float = 0.0          # Sigma del blur gaussiano (0 = calculado automáticamente)
ADAPTIVE_BLOCK_SIZE: int = 11        # Vecindario de umbralización adaptativa (debe ser impar)
ADAPTIVE_C: int = 2                  # Constante sustraída a la media en umbralización

MIN_CONTOUR_AREA_RATIO: float = 0.001  # Contorno mínimo = 0.1% del área total de la imagen
MAX_CONTOUR_AREA_RATIO: float = 0.95   # Contorno máximo = 95% (evita detectar el fondo completo)
MIN_CONTOUR_AREA_PIXELS: int = 500     # Área mínima absoluta en px² (ignora piezas diminutas)
CONTOUR_SOLIDITY_THRESHOLD: float = 0.40  # Solidez mínima área/convexHull — descarta sombras y líneas

# ─── Validación de FactorK ─────────────────────────────────────────────────────
MIN_FACTOR_K: float = 1e-9     # Límite inferior — calibraciones con objetos de referencia enormes
MAX_FACTOR_K: float = 1000.0   # Límite superior — calibraciones con objetos de referencia diminutos
MIN_CALIBRATION_PIXELS: int = 1000  # El área de referencia debe tener al menos 1000 px²

# ─── Categorías de área (m²) — (min_inclusivo, max_exclusivo) ─────────────────
# Compatible con MeasurementCategory de la app Flutter
CATEGORY_THRESHOLDS: dict[str, tuple[float, float]] = {
    "A":     (0.0, 1.0),
    "B":     (1.0, 2.0),
    "C":     (2.0, 3.0),
    "D":     (3.0, 4.0),
    "error": (4.0, float("inf")),
}
CATEGORY_BOUNDARY_TOLERANCE: float = 0.05  # ±5% alrededor de un límite → advertencia de borde

# ─── Calibración ──────────────────────────────────────────────────────────────
CALIBRATION_MAX_AGE_DAYS: int = 30           # Advertencia si la calibración supera este tiempo
CALIBRATION_RESOLUTION_TOLERANCE: float = 0.10  # ±10% en resolución entre calibración y medición

# ─── Almacenamiento de imágenes ────────────────────────────────────────────────
SILHOUETTE_MAX_SIZE_PX: int = 512  # Lado máximo al guardar la silueta (redimensionar si es mayor)
SILHOUETTE_PNG_COMPRESS: int = 6   # Nivel de compresión PNG (0 = sin compresión, 9 = máximo)

# ─── Timeouts ─────────────────────────────────────────────────────────────────
PROCESSING_TIMEOUT_S: float = 5.0   # Tiempo máximo para procesar un frame
CAMERA_INIT_TIMEOUT_S: float = 10.0  # Tiempo máximo para inicializar la cámara
