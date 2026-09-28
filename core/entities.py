"""
Entidades del dominio — Clases de datos puras sin dependencias externas ni de UI.
Equivalente a las entities de la app Flutter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ShapeType(Enum):
    """
    Clasificación geométrica de la silueta de un retal.

    Es una etiqueta heurística de la forma observada en la imagen, no una
    certificación industrial de la geometría real de la pieza.
    """
    CIRCULO             = "circulo"
    CUADRADO            = "cuadrado"
    RECTANGULO          = "rectangulo"
    TRIANGULO           = "triangulo"
    POLIGONO_REGULAR    = "poligono_regular"
    POLIGONO_IRREGULAR  = "poligono_irregular"
    OTRA                = "otra"

    @property
    def label_es(self) -> str:
        return {
            ShapeType.CIRCULO:            "Círculo",
            ShapeType.CUADRADO:           "Cuadrado",
            ShapeType.RECTANGULO:         "Rectángulo",
            ShapeType.TRIANGULO:          "Triángulo",
            ShapeType.POLIGONO_REGULAR:   "Polígono regular",
            ShapeType.POLIGONO_IRREGULAR: "Polígono irregular",
            ShapeType.OTRA:               "Otra / desconocida",
        }[self]

    @property
    def is_regular_kind(self) -> bool:
        """True si la forma pertenece a la familia de contornos regulares."""
        return self in _REGULAR_SHAPES

    @property
    def is_irregular_kind(self) -> bool:
        """True si la forma pertenece a la familia de contornos irregulares."""
        return self in _IRREGULAR_SHAPES


_REGULAR_SHAPES: frozenset[ShapeType] = frozenset({
    ShapeType.CIRCULO,
    ShapeType.CUADRADO,
    ShapeType.RECTANGULO,
    ShapeType.TRIANGULO,
    ShapeType.POLIGONO_REGULAR,
})

_IRREGULAR_SHAPES: frozenset[ShapeType] = frozenset({
    ShapeType.POLIGONO_IRREGULAR,
    ShapeType.OTRA,
})


class Regularity(Enum):
    """
    Grado de regularidad del contorno.
    `SEMI_REGULAR` existe para que el usuario pueda decidir con un umbral configurable
    si una pieza intermedia se acepta o no.
    """
    REGULAR      = "regular"
    SEMI_REGULAR = "semi_regular"
    IRREGULAR    = "irregular"

    @property
    def label_es(self) -> str:
        return {
            Regularity.REGULAR:      "Regular",
            Regularity.SEMI_REGULAR: "Semi-regular",
            Regularity.IRREGULAR:    "Irregular",
        }[self]

    @classmethod
    def from_score(cls, score: float, regular_at: float = 0.92, irregular_below: float = 0.75) -> "Regularity":
        """Deriva la regularidad a partir del score continuo en [0, 1]."""
        if score >= regular_at:
            return cls.REGULAR
        if score <= irregular_below:
            return cls.IRREGULAR
        return cls.SEMI_REGULAR


class ScrapDestination(Enum):
    """Destino operativo de un retal medido."""
    REUTILIZABLE = "REUTILIZABLE"
    RECICLABLE   = "RECICLABLE"

    @property
    def label_es(self) -> str:
        return {
            ScrapDestination.REUTILIZABLE: "REUTILIZABLE",
            ScrapDestination.RECICLABLE:   "RECICLAJE",
        }[self]

    @property
    def hex_color(self) -> str:
        return {
            ScrapDestination.REUTILIZABLE: "#4caf50",
            ScrapDestination.RECICLABLE:   "#f44336",
        }[self]


class ScrapStatus(Enum):
    """Ciclo de vida de un retal dentro del inventario."""
    DISPONIBLE = "DISPONIBLE"
    RESERVADO  = "RESERVADO"
    UTILIZADO  = "UTILIZADO"
    RECICLADO  = "RECICLADO"

    @property
    def label_es(self) -> str:
        return {
            ScrapStatus.DISPONIBLE: "Disponible",
            ScrapStatus.RESERVADO:  "Reservado",
            ScrapStatus.UTILIZADO:  "Utilizado",
            ScrapStatus.RECICLADO:  "Reciclado",
        }[self]


class MeasurementCategory(Enum):
    """
    Clasificación de área medida.
    Compatible con MeasurementCategory de la app Flutter (mismos valores y rangos).
    """
    A = "A"          # < 1.0 m²  — verde
    B = "B"          # 1.0–2.0 m² — azul
    C = "C"          # 2.0–3.0 m² — ámbar
    D = "D"          # 3.0–4.0 m² — naranja
    ERROR = "error"  # ≥ 4.0 m²  — rojo

    @property
    def label_es(self) -> str:
        return {
            MeasurementCategory.A:     "A — Pequeño  (< 1 m²)",
            MeasurementCategory.B:     "B — Mediano  (1–2 m²)",
            MeasurementCategory.C:     "C — Grande   (2–3 m²)",
            MeasurementCategory.D:     "D — Muy grande (3–4 m²)",
            MeasurementCategory.ERROR: "Fuera de rango (> 4 m²)",
        }[self]

    @property
    def hex_color(self) -> str:
        return {
            MeasurementCategory.A:     "#4caf50",
            MeasurementCategory.B:     "#2196f3",
            MeasurementCategory.C:     "#ff9800",
            MeasurementCategory.D:     "#ff5722",
            MeasurementCategory.ERROR: "#f44336",
        }[self]


@dataclass
class CalibrationData:
    """
    Datos de calibración almacenados.
    El campo clave es `factor_k`: metros cuadrados por píxel en el instante de calibración.
    """
    factor_k: float                     # m²/px² al momento de calibrar
    calibration_area_pixels: float      # Área del objeto de referencia en px²
    calibration_area_real_m2: float     # Área real conocida del objeto de referencia (m²)
    calibration_image_width: int        # Resolución de la imagen usada en la calibración
    calibration_image_height: int
    calibration_distance_cm: float      # Distancia cámara-objeto durante la calibración (cm)
    calibration_date: datetime          # Fecha y hora de la calibración
    notes: Optional[str] = None

    @property
    def is_recent(self) -> bool:
        """True si la calibración tiene menos de 30 días."""
        from core.constants import CALIBRATION_MAX_AGE_DAYS
        return (datetime.now() - self.calibration_date).days < CALIBRATION_MAX_AGE_DAYS

    @property
    def age_days(self) -> int:
        return (datetime.now() - self.calibration_date).days

    def is_valid_for_resolution(self, width: int, height: int) -> bool:
        """True si la resolución actual está dentro del ±10% de la resolución de calibración."""
        from core.constants import CALIBRATION_RESOLUTION_TOLERANCE
        tol = CALIBRATION_RESOLUTION_TOLERANCE
        w_ok = abs(width - self.calibration_image_width) / max(self.calibration_image_width, 1) <= tol
        h_ok = abs(height - self.calibration_image_height) / max(self.calibration_image_height, 1) <= tol
        return w_ok and h_ok


@dataclass
class ProcessingResult:
    """Resultado del pipeline OpenCV para un frame."""
    area_pixels: float
    perimeter_pixels: float
    contour_count: int
    circularity: float
    aspect_ratio: float
    image_width: int
    image_height: int
    bounding_box: tuple[int, int, int, int]  # (x, y, w, h)
    processing_time_ms: float
    # Imágenes intermedias para visualización (numpy arrays BGR o None)
    original_frame: Optional[Any] = None
    grayscale_image: Optional[Any] = None
    binary_image: Optional[Any] = None
    contours_image: Optional[Any] = None
    # Contorno principal detectado (np.ndarray Nx1x2). Lo consume el análisis
    # geométrico/seguridad/DXF para no reprocesar la imagen. Opcional: los
    # resultados construidos a mano (tests, apps Flutter) siguen siendo válidos.
    main_contour: Optional[Any] = None
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error_message is None and self.area_pixels > 0


@dataclass
class Measurement:
    """Registro de medición persistido en la base de datos."""
    area_pixels: float
    area_m2: float
    category: MeasurementCategory
    factor_k_used: float
    distance_cm: float
    timestamp: datetime
    id: Optional[int] = None
    name: Optional[str] = None
    notes: Optional[str] = None
    silhouette_path: Optional[str] = None
    perimeter_pixels: Optional[float] = None
    circularity: Optional[float] = None
    confidence: Optional[float] = None
    is_valid: bool = True

    @property
    def area_cm2(self) -> float:
        return self.area_m2 * 10_000

    @property
    def display_name(self) -> str:
        return self.name or f"Medición {self.timestamp.strftime('%d/%m/%Y %H:%M')}"

    # scrap_id se añadió en la migración v1→v2 (nullable). Las mediciones
    # históricas quedan en None y siguen siendo válidas.
    scrap_id: Optional[int] = None


@dataclass
class GeometryAnalysis:
    """
    Resultado del análisis geométrico de un contorno.

    Contiene la etiqueta de forma, la regularidad y las **dimensiones físicas
    reales** derivadas de `cv2.minAreaRect` (no del bounding rect alineado a ejes,
    que distorsiona piezas inclinadas).

    `confidence` es un valor heurístico en [0, 1]: mide cuán respaldada está la
    etiqueta por las métricas, no la certeza de que la pieza sea realmente así.
    """
    shape: ShapeType
    regularity: Regularity
    regularity_score: float                 # [0, 1]
    confidence: float                       # [0, 1]
    width_m: float                          # lado corto (eje Y del minAreaRect, m)
    length_m: float                         # lado largo  (eje X del minAreaRect, m)
    vertex_count: int
    circularity: float
    solidity: float
    convexity_defects: int
    area_m2: float

    @property
    def dimensions_text(self) -> str:
        return f"{self.length_m:.2f} × {self.width_m:.2f} m"

    @property
    def aspect_ratio(self) -> float:
        """Relación lado_largo / lado_corto (1.0 = cuadrado perfecto)."""
        return self.length_m / self.width_m if self.width_m > 0 else 1.0

    @property
    def is_degraded(self) -> bool:
        """
        True si la forma NO se pudo analizar y solo se conoce el área.

        Sucede cuando el contorno no está disponible (p. ej. un
        `ProcessingResult` construido fuera del pipeline de OpenCV). En ese
        caso los valores por defecto NO deben interpretarse como mediciones:
        una regularidad de 0.0 significa "desconocida", no "borde rasgado".
        """
        return self.vertex_count == 0


@dataclass
class SharpnessReport:
    """
    Evaluación heurística de riesgo geométrico.

    NO certifica seguridad industrial: solo indica que la silueta observada
    presenta rasgos compatibles con una punta o borde cortante.
    """
    score: float                            # [0, 1]
    min_internal_angle_deg: float           # ángulo interno más pequeño (grados)
    protrusion_depth: float                 # 1 - area/hull_area
    spike_factor: float                     # vértices "hocudo" vs. arista mediana
    convexity_defect_ratio: float           # defecto de convexidad normalizado
    local_aspect: float                     # p90 de anchos locales / ancho mínimo
    triggered: bool

    @property
    def severity_es(self) -> str:
        if self.score >= 0.80:
            return "Alto"
        if self.score >= 0.65:
            return "Medio"
        return "Bajo"


@dataclass
class StorageArea:
    """Estante del almacén. Contenedor de primer nivel de repisas."""
    name: str
    id: Optional[int] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    @property
    def display_name(self) -> str:
        return self.name or f"Estante {self.id}"


@dataclass
class ShelfRules:
    """
    Criterios de aceptación de una repisa.

    Todos los rangos son intervalos cerrados [min, max]. `None` o 0 significa
    "sin límite en ese extremo", para que el usuario pueda abrir la repisa
    a un rango amplio sin tener que inventar un número grande.
    """
    accepts_regular: bool = True
    accepts_irregular: bool = True
    min_width_m: Optional[float] = None
    max_width_m: Optional[float] = None
    min_length_m: Optional[float] = None
    max_length_m: Optional[float] = None
    min_area_m2: Optional[float] = None
    max_area_m2: Optional[float] = None
    min_thickness_mm: Optional[float] = None
    max_thickness_mm: Optional[float] = None

    def rejects_shape_family(self, shape: ShapeType) -> bool:
        """True si la repisa NO admite la familia de forma indicada."""
        if shape.is_irregular_kind:
            return not self.accepts_irregular
        return not self.accepts_regular

    def dimension_reasons(self, width_m: float, length_m: float) -> list[str]:
        """
        Devuelve los motivos por los que las dimensiones quedan fuera de rango.

        Se evalúan **ambos lados** en las dos orientaciones, porque un retal
        puede girar 90°: una pieza de 1.0 × 1.5 m sí puede entrar en una repisa
        de 1.5 × 1.0 m y no debe rechazarse por el orden de los factores.
        """
        reasons: list[str] = []
        for label, value, lo, hi in (
            ("largo", length_m, self.min_length_m, self.max_length_m),
            ("ancho", width_m, self.min_width_m, self.max_width_m),
        ):
            if lo is not None and lo > 0 and value < lo:
                reasons.append(f"{label} {value:.2f} m menor al mínimo ({lo:.2f} m)")
            if hi is not None and hi > 0 and value > hi:
                reasons.append(f"{label} {value:.2f} m mayor al máximo ({hi:.2f} m)")
        return reasons

    def area_reasons(self, area_m2: float) -> list[str]:
        reasons: list[str] = []
        if self.min_area_m2 is not None and self.min_area_m2 > 0 and area_m2 < self.min_area_m2:
            reasons.append(f"área {area_m2:.3f} m² menor al mínimo ({self.min_area_m2:.3f} m²)")
        if self.max_area_m2 is not None and self.max_area_m2 > 0 and area_m2 > self.max_area_m2:
            reasons.append(f"área {area_m2:.3f} m² mayor al máximo ({self.max_area_m2:.3f} m²)")
        return reasons

    def thickness_reasons(self, thickness_mm: Optional[float]) -> list[str]:
        """`thickness_mm is None` significa 'no capturado' → no genera motivo de rechazo."""
        if thickness_mm is None:
            return []
        reasons: list[str] = []
        if self.min_thickness_mm is not None and self.min_thickness_mm > 0 and thickness_mm < self.min_thickness_mm:
            reasons.append(
                f"espesor {thickness_mm:.1f} mm menor al mínimo ({self.min_thickness_mm:.1f} mm)"
            )
        if self.max_thickness_mm is not None and self.max_thickness_mm > 0 and thickness_mm > self.max_thickness_mm:
            reasons.append(
                f"espesor {thickness_mm:.1f} mm mayor al máximo ({self.max_thickness_mm:.1f} mm)"
            )
        return reasons


@dataclass
class Shelf:
    """Repisa física: rectángulo de width_m × length_m con reglas de aceptación."""
    storage_area_id: int
    name: str
    width_m: float
    length_m: float
    id: Optional[int] = None
    rules: ShelfRules = field(default_factory=ShelfRules)
    created_at: Optional[datetime] = None
    # Campos calculados por los repositorios (no persistidos)
    area_m2: float = 0.0
    used_area_m2: float = 0.0
    scrap_count: int = 0
    storage_area_name: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.area_m2:
            self.area_m2 = self.width_m * self.length_m

    @property
    def available_area_m2(self) -> float:
        """
        Área no ocupada según la suma de áreas de los retales.

        NO es espacio realmente utilizable: dos retales cuya suma de áreas cabe
        pueden no caber juntos por forma. Para el espacio físico real usa
        `core.packing`.
        """
        return max(0.0, self.area_m2 - self.used_area_m2)

    @property
    def occupancy_ratio(self) -> float:
        return self.used_area_m2 / self.area_m2 if self.area_m2 > 0 else 0.0

    @property
    def display_name(self) -> str:
        return self.name or f"Repisa {self.id}"

    @property
    def location_text(self) -> str:
        area = self.storage_area_name or f"Estante {self.storage_area_id}"
        return f"{area} / {self.display_name}"


@dataclass
class Scrap:
    """Retal registrado en el inventario (reutilizable o destined a reciclaje)."""
    area_m2: float
    width_m: float
    length_m: float
    shape: ShapeType
    regularity: Regularity
    destination: ScrapDestination
    id: Optional[int] = None
    measurement_id: Optional[int] = None
    name: Optional[str] = None
    thickness_mm: Optional[float] = None
    shape_confidence: Optional[float] = None
    regularity_score: Optional[float] = None
    vertex_count: Optional[int] = None
    shelf_id: Optional[int] = None
    storage_area_id: Optional[int] = None
    status: ScrapStatus = ScrapStatus.DISPONIBLE
    sharpness_score: Optional[float] = None
    safety_alert: bool = False
    estimated_value: Optional[float] = None
    cost_per_m2: Optional[float] = None
    reasons: list[str] = field(default_factory=list)
    silhouette_path: Optional[str] = None
    created_at: Optional[datetime] = None
    # Desnormalizado para pintar la UI sin JOIN
    shelf_name: Optional[str] = None
    storage_area_name: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.name or f"Retal #{self.id:03d}" if self.id else "Retal sin nombre"

    @property
    def dimensions_text(self) -> str:
        return f"{self.length_m:.2f} × {self.width_m:.2f} m"

    @property
    def location_text(self) -> str:
        if self.shelf_id is None:
            return "Sin ubicación"
        area = self.storage_area_name or f"Estante {self.storage_area_id}"
        return f"{area} / {self.shelf_name or f'Repisa {self.shelf_id}'}"

    def fits_request(self, req_width_m: float, req_length_m: float) -> bool:
        """True si el retal cubre una pieza solicitada, evaluando ambas rotaciones."""
        if req_width_m <= 0 or req_length_m <= 0:
            return False
        return (self.width_m >= req_width_m and self.length_m >= req_length_m) or \
               (self.length_m >= req_width_m and self.width_m >= req_length_m)


@dataclass
class AllocationProposal:
    """
    Resultado de la búsqueda automática de ubicación.

    `shelf is None` con `reason` explica por qué no se encontró una ubicación
    físicamente compatible. `is_confident` es False cuando el packing no pudo
    demostrar una posición libre (estrategia conservadora).
    """
    shelf: Optional[Shelf] = None
    rotated: bool = False
    position_x_m: Optional[float] = None
    position_y_m: Optional[float] = None
    reason: str = ""
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (ubicación, motivo)
    is_confident: bool = True

    @property
    def found(self) -> bool:
        return self.shelf is not None

    @property
    def location_text(self) -> str:
        return self.shelf.location_text if self.shelf else "Sin ubicación"


@dataclass
class ScrapAnalysis:
    """
    Resultado completo del pipeline de clasificación de un retal.

    Reúne geometría, seguridad y decisión de destino. Lo consume la UI para
    mostrar el razonamiento y `services.allocation_service` para asignar.
    """
    geometry: GeometryAnalysis
    safety: SharpnessReport
    destination: ScrapDestination
    estimated_value: float
    reasons: list[str] = field(default_factory=list)
    thickness_mm: Optional[float] = None
    cost_per_m2: float = 0.0
