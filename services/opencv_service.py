"""
Pipeline de procesamiento de imagen con OpenCV.

Pipeline:
    BGR → Grayscale → GaussianBlur → AdaptiveThreshold
    → MORPH_OPEN (elimina líneas finas/ruido)
    → MORPH_CLOSE (rellena huecos)
    → FindContours → Filtrado (área + solidez) → Contorno más grande
    → Área + Métricas + Overlay visual

La sensibilidad de detección y el área mínima en píxeles son
configurables en tiempo de ejecución mediante update_config().
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np

from core.constants import (
    GAUSSIAN_KERNEL_SIZE,
    GAUSSIAN_SIGMA,
    ADAPTIVE_BLOCK_SIZE,
    ADAPTIVE_C,
    MIN_CONTOUR_AREA_RATIO,
    MAX_CONTOUR_AREA_RATIO,
    MIN_CONTOUR_AREA_PIXELS,
    CONTOUR_SOLIDITY_THRESHOLD,
)
from core.entities import ProcessingResult, MeasurementCategory
from core.exceptions import ProcessingError
from core.formulas import compute_circularity

logger = logging.getLogger(__name__)


class OpenCVService:
    """
    Procesa un frame BGR y retorna las métricas del contorno más grande
    junto con imágenes intermedias para visualización paso a paso.

    La configuración de detección es mutable en tiempo de ejecución
    mediante update_config(), sin necesidad de reiniciar la app.
    """

    def __init__(self) -> None:
        # Configuración de detección — se puede actualizar con update_config()
        self._adaptive_c: int = ADAPTIVE_C
        self._block_size: int = ADAPTIVE_BLOCK_SIZE
        self._min_pixels: int = MIN_CONTOUR_AREA_PIXELS
        self._solidity_threshold: float = CONTOUR_SOLIDITY_THRESHOLD
        self._close_kernel_size: int = 11  # Tamaño del kernel MORPH_CLOSE; mayor = une fragmentos más separados

    def update_config(
        self,
        min_pixels: int | None = None,
        adaptive_c: int | None = None,
        block_size: int | None = None,
        solidity_threshold: float | None = None,
        close_kernel_size: int | None = None,
    ) -> None:
        """
        Actualiza la configuración de detección en caliente.

        Args:
            min_pixels:         Área mínima absoluta de contorno en píxeles cuadrados (≥ 1).
            adaptive_c:         Constante de umbralización adaptativa (mayor → menos sensible).
            block_size:         Tamaño de vecindario adaptativo (debe ser impar, ≥ 3).
            solidity_threshold: Solidez mínima área/convexHull (0–1). Descarta sombras lineales.
            close_kernel_size:  Tamaño del kernel MORPH_CLOSE (mayor → une más fragmentos).
        """
        if min_pixels is not None:
            self._min_pixels = max(1, int(min_pixels))
        if adaptive_c is not None:
            self._adaptive_c = int(adaptive_c)
        if block_size is not None:
            bs = int(block_size)
            self._block_size = bs if bs % 2 == 1 else bs + 1  # garantiza impar
        if solidity_threshold is not None:
            self._solidity_threshold = float(solidity_threshold)
        if close_kernel_size is not None:
            ck = int(close_kernel_size)
            self._close_kernel_size = ck if ck % 2 == 1 else ck + 1
        logger.debug(
            "OpenCVService config actualizada: min_px=%d adaptive_c=%d block=%d solidity=%.2f close_k=%d",
            self._min_pixels, self._adaptive_c, self._block_size,
            self._solidity_threshold, self._close_kernel_size,
        )

    def process_frame(
        self,
        frame: np.ndarray,
        draw_overlay: bool = True,
        area_m2: Optional[float] = None,
        category: Optional[MeasurementCategory] = None,
    ) -> ProcessingResult:
        """
        Ejecuta el pipeline completo sobre un frame BGR.

        Args:
            frame:        Frame BGR de OpenCV (H×W×3).
            draw_overlay: Si True, dibuja contorno verde + bounding box + área sobre la imagen.
            area_m2:      Si se provee, se muestra en el overlay junto con la categoría.
            category:     Categoría para colorear el overlay según la app Flutter.

        Returns:
            ProcessingResult con métricas e imágenes de cada etapa del pipeline.
        """
        t_start = time.perf_counter()
        h, w = frame.shape[:2]
        total_area = w * h
        # Umbral combinado: usa el mayor entre el ratio relativo y el mínimo absoluto
        min_area = max(total_area * MIN_CONTOUR_AREA_RATIO, float(self._min_pixels))
        max_area = total_area * MAX_CONTOUR_AREA_RATIO

        try:
            # ── 1. Grayscale ─────────────────────────────────────────────────
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # ── 2. Gaussian Blur ─────────────────────────────────────────────
            blurred = cv2.GaussianBlur(
                gray,
                (GAUSSIAN_KERNEL_SIZE, GAUSSIAN_KERNEL_SIZE),
                GAUSSIAN_SIGMA,
            )

            # ── 3. Umbralización adaptativa ───────────────────────────────────
            binary = cv2.adaptiveThreshold(
                blurred,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                self._block_size,
                self._adaptive_c,
            )

            # ── 4. MORPH_OPEN — elimina líneas finas, sombras y ruido puntual ─
            kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            binary_opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)

            # ── 5. MORPH_CLOSE — rellena huecos y une fragmentos del contorno ──
            # Kernel configurable: mayor tamaño = une fragmentos más separados
            ck = self._close_kernel_size
            kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ck, ck))
            binary_clean = cv2.morphologyEx(binary_opened, cv2.MORPH_CLOSE, kernel_close, iterations=2)

            # ── 6. Buscar contornos externos ──────────────────────────────────
            contours, _ = cv2.findContours(
                binary_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # ── 7. Filtrar por área (absoluta + relativa) y solidez ───────────
            def _solidity(c: np.ndarray) -> float:
                """Razón área_contorno / área_cierre_convexo (0–1)."""
                hull_area = cv2.contourArea(cv2.convexHull(c))
                return cv2.contourArea(c) / hull_area if hull_area > 0 else 0.0

            valid = [
                c for c in contours
                if min_area < cv2.contourArea(c) < max_area
                and _solidity(c) >= self._solidity_threshold
            ]

            # Imágenes intermedias para el panel de visualización
            gray_bgr   = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            binary_bgr = cv2.cvtColor(binary_clean, cv2.COLOR_GRAY2BGR)
            t_ms = (time.perf_counter() - t_start) * 1000

            if not valid:
                contours_img = frame.copy()
                cv2.putText(
                    contours_img, "Sin contorno detectado",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 80, 255), 2,
                )
                return ProcessingResult(
                    area_pixels=0.0,
                    perimeter_pixels=0.0,
                    contour_count=0,
                    circularity=0.0,
                    aspect_ratio=0.0,
                    image_width=w,
                    image_height=h,
                    bounding_box=(0, 0, 0, 0),
                    processing_time_ms=t_ms,
                    original_frame=frame.copy(),
                    grayscale_image=gray_bgr,
                    binary_image=binary_bgr,
                    contours_image=contours_img,
                    error_message="No se detectó ningún contorno válido.",
                )

            # ── 8. Seleccionar el contorno más grande ─────────────────────────
            largest = max(valid, key=cv2.contourArea)
            area_px     = cv2.contourArea(largest)
            perimeter   = cv2.arcLength(largest, True)
            circularity = compute_circularity(area_px, perimeter)
            x, y, bw, bh = cv2.boundingRect(largest)
            aspect_ratio = bw / bh if bh > 0 else 0.0

            # ── 9. Generar imagen de overlay ──────────────────────────────────
            contours_img = frame.copy()
            if draw_overlay:
                # Color del contorno según categoría (igual que la app Flutter)
                overlay_color = (0, 200, 60)
                if category is not None:
                    hex_c = category.hex_color.lstrip("#")
                    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
                    overlay_color = (b, g, r)   # OpenCV usa BGR

                # Máscara semitransparente del área detectada
                mask = np.zeros_like(frame)
                cv2.drawContours(mask, [largest], -1, overlay_color, thickness=cv2.FILLED)
                contours_img = cv2.addWeighted(contours_img, 0.65, mask, 0.35, 0)

                # Contorno exterior nítido
                cv2.drawContours(contours_img, [largest], -1, overlay_color, 2)

                # Bounding box
                cv2.rectangle(
                    contours_img, (x, y), (x + bw, y + bh), (0, 120, 255), 2
                )

                # Texto superior — área en píxeles y en m² si está disponible
                label_px = f"{area_px:.0f} px²"
                label_m2 = f"  {area_m2:.4f} m²" if area_m2 is not None else ""
                cat_label = f"  [{category.value}]" if category is not None else ""
                full_label = label_px + label_m2 + cat_label

                text_y = y - 10 if y > 30 else y + bh + 25
                cv2.putText(
                    contours_img, full_label,
                    (x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, overlay_color, 2,
                )

                # Pequeño indicador de tiempo de proceso (esquina inferior derecha)
                cv2.putText(
                    contours_img, f"{t_ms:.1f} ms",
                    (w - 100, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1,
                )

            t_ms = (time.perf_counter() - t_start) * 1000
            return ProcessingResult(
                area_pixels=area_px,
                perimeter_pixels=perimeter,
                contour_count=len(valid),
                circularity=circularity,
                aspect_ratio=aspect_ratio,
                image_width=w,
                image_height=h,
                bounding_box=(x, y, bw, bh),
                processing_time_ms=t_ms,
                original_frame=frame.copy(),
                grayscale_image=gray_bgr,
                binary_image=binary_bgr,
                contours_image=contours_img,
                # El contorno se expone para que el análisis geométrico, el de
                # seguridad y la exportación DXF trabajen sobre el MISMO contorno
                # que el usuario ve, en vez de re-segmentar la imagen.
                main_contour=largest,
            )

        except Exception as exc:
            logger.exception("Error en pipeline OpenCV")
            raise ProcessingError(f"Error inesperado en pipeline: {exc}") from exc
