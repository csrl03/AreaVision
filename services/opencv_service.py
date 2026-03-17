"""
Pipeline de procesamiento de imagen con OpenCV.

Pipeline idéntico al de la app Flutter (opencv_dart):
    BGR → Grayscale → GaussianBlur → AdaptiveThreshold → Morfología
    → FindContours → LargestContour → Área + Métricas + Overlay visual

El overlay en tiempo real colorea el contorno y dibuja el bounding box,
lo que permite al usuario ver qué está siendo detectado en cada frame.
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
)
from core.entities import ProcessingResult, MeasurementCategory
from core.exceptions import ProcessingError
from core.formulas import compute_circularity

logger = logging.getLogger(__name__)


class OpenCVService:
    """
    Procesa un frame BGR y retorna las métricas del contorno más grande
    junto con imágenes intermedias para visualización paso a paso.
    """

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
        min_area = total_area * MIN_CONTOUR_AREA_RATIO
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

            # ── 3. Umbralización adaptativa (idéntico a la app Flutter) ──────
            binary = cv2.adaptiveThreshold(
                blurred,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                ADAPTIVE_BLOCK_SIZE,
                ADAPTIVE_C,
            )

            # ── 4. Morfología — cierra huecos pequeños en el objeto ───────────
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            binary_clean = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

            # ── 5. Buscar contornos externos ──────────────────────────────────
            contours, _ = cv2.findContours(
                binary_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # ── 6. Filtrar por área mínima y máxima ───────────────────────────
            valid = [c for c in contours if min_area < cv2.contourArea(c) < max_area]

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

            # ── 7. Seleccionar el contorno más grande (igual que Flutter) ─────
            largest = max(valid, key=cv2.contourArea)
            area_px     = cv2.contourArea(largest)
            perimeter   = cv2.arcLength(largest, True)
            circularity = compute_circularity(area_px, perimeter)
            x, y, bw, bh = cv2.boundingRect(largest)
            aspect_ratio = bw / bh if bh > 0 else 0.0

            # ── 8. Generar imagen de overlay ──────────────────────────────────
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
            )

        except Exception as exc:
            logger.exception("Error en pipeline OpenCV")
            raise ProcessingError(f"Error inesperado en pipeline: {exc}") from exc
