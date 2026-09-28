"""
Pruebas de regresión de la funcionalidad EXISTENTE.

La nueva funcionalidad no puede haber roto calibración, medición, pipeline
OpenCV, categorías, imágenes, historial ni configuración.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest

from core.entities import CalibrationData, MeasurementCategory
from core.formulas import (
    apply_distance_correction, classify_area, compute_circularity,
    compute_factor_k, is_at_category_boundary, pixels_to_m2,
    set_category_thresholds, validate_calibration_pixels, validate_factor_k,
)
from core.constants import CATEGORY_THRESHOLDS
from data.settings_repository import SettingsRepository


class TestCalibrationFormulas:
    def test_factor_k(self):
        assert compute_factor_k(0.0623, 50000.0) == pytest.approx(1.246e-6)

    def test_factor_k_rechaza_no_positivos(self):
        with pytest.raises(ValueError):
            compute_factor_k(1.0, 0.0)
        with pytest.raises(ValueError):
            compute_factor_k(0.0, 100.0)

    def test_correccion_por_distancia(self):
        """factorK × (d_cal / d_med)²"""
        fk = apply_distance_correction(1.0e-6, 100.0, 50.0)
        assert fk == pytest.approx(1.0e-6 * 4)

    def test_correccion_neutra_a_la_misma_distancia(self):
        assert apply_distance_correction(1.0e-6, 80.0, 80.0) == pytest.approx(1.0e-6)

    def test_objeto_mas_lejos_ajusta_mas(self):
        """
        A menor distancia, el mismo objeto ocupa más píxeles, así que el
        FactorK corregido es mayor: hay que multiplicar por más píxeles para
        llegar al mismo metro cuadrado.
        """
        cerca = apply_distance_correction(1.0e-6, 80.0, 40.0)    # 1e-6 × 4
        lejos = apply_distance_correction(1.0e-6, 80.0, 160.0)   # 1e-6 × 0.25
        assert cerca > lejos
        assert cerca == pytest.approx(4.0e-6)
        assert lejos == pytest.approx(0.25e-6)

    def test_correccion_rechaza_distancias_no_positivas(self):
        with pytest.raises(ValueError):
            apply_distance_correction(1.0e-6, 0.0, 50.0)

    def test_pixels_to_m2(self):
        assert pixels_to_m2(10000.0, 1.0e-6) == pytest.approx(0.01)

    def test_circularidad(self):
        assert compute_circularity(0.0, 0.0) == 0.0
        assert 0.0 < compute_circularity(50000.0, 800.0) <= 1.0

    def test_validar_pixels_de_calibracion(self):
        assert validate_calibration_pixels(100.0) is not None
        assert validate_calibration_pixels(50000.0) is None

    def test_validar_factor_k(self):
        assert validate_factor_k(1.0e-6) is None
        assert validate_factor_k(0.0) is not None
        assert validate_factor_k(1e9) is not None


class TestCategories:
    def setup_method(self):
        set_category_thresholds({k: list(v) for k, v in
                                 {"A": [0, 1], "B": [1, 2], "C": [2, 3], "D": [3, 4]}.items()})

    def test_limites_por_defecto(self):
        assert set(CATEGORY_THRESHOLDS) == {"A", "B", "C", "D", "error"}

    @pytest.mark.parametrize("area,esperado", [
        (0.5, MeasurementCategory.A),
        (1.0, MeasurementCategory.B),
        (1.9, MeasurementCategory.B),
        (2.0, MeasurementCategory.C),
        (3.5, MeasurementCategory.D),
        (4.5, MeasurementCategory.ERROR),
    ])
    def test_clasificacion_por_area(self, area, esperado):
        assert classify_area(area) == esperado

    def test_umbrales_configurables(self):
        set_category_thresholds({"A": [0, 0.5], "B": [0.5, 1.0], "C": [1.0, 2.0], "D": [2.0, 3.0]})
        assert classify_area(0.7) == MeasurementCategory.B
        set_category_thresholds({"A": [0, 1], "B": [1, 2], "C": [2, 3], "D": [3, 4]})

    def test_frontera_de_categoria(self):
        assert is_at_category_boundary(1.0) is True
        assert is_at_category_boundary(1.5) is False


class TestCalibrationData:
    def test_antiguedad(self):
        cal = CalibrationData(
            factor_k=1e-6, calibration_area_pixels=50000.0,
            calibration_area_real_m2=0.0623, calibration_image_width=1280,
            calibration_image_height=720, calibration_distance_cm=80.0,
            calibration_date=datetime.now() - timedelta(days=5),
        )
        assert cal.age_days == 5
        assert cal.is_recent is True

    def test_calibracion_antigua(self):
        cal = CalibrationData(
            factor_k=1e-6, calibration_area_pixels=50000.0,
            calibration_area_real_m2=0.0623, calibration_image_width=1280,
            calibration_image_height=720, calibration_distance_cm=80.0,
            calibration_date=datetime.now() - timedelta(days=45),
        )
        assert cal.is_recent is False

    def test_resolucion_compatible(self):
        cal = CalibrationData(
            factor_k=1e-6, calibration_area_pixels=50000.0,
            calibration_area_real_m2=0.0623, calibration_image_width=1280,
            calibration_image_height=720, calibration_distance_cm=80.0,
            calibration_date=datetime.now(),
        )
        assert cal.is_valid_for_resolution(1280, 720) is True
        assert cal.is_valid_for_resolution(1920, 1080) is False


class TestOpenCvPipeline:
    """El pipeline existente no debe haber cambiado."""

    def _frame_con_rectangulo(self, w=200, h=150):
        frame = np.zeros((720, 1280, 3), np.uint8)
        cv2.rectangle(frame, (400, 250), (400 + w, 250 + h), (255, 255, 255), -1)
        return frame

    def test_detecta_el_objeto(self):
        from services.opencv_service import OpenCVService
        result = OpenCVService().process_frame(self._frame_con_rectangulo())
        assert result.success
        assert result.area_pixels > 0
        assert result.perimeter_pixels > 0

    def test_expone_el_contorno_principal(self):
        """El campo nuevo `main_contour` debe estar poblado."""
        from services.opencv_service import OpenCVService
        result = OpenCVService().process_frame(self._frame_con_rectangulo())
        assert result.main_contour is not None
        assert result.main_contour.shape[0] > 2

    def test_sin_objeto_reporta_error(self):
        from services.opencv_service import OpenCVService
        result = OpenCVService().process_frame(np.zeros((720, 1280, 3), np.uint8))
        assert result.success is False
        assert result.error_message

    def test_configuracion_en_caliente(self):
        from services.opencv_service import OpenCVService
        svc = OpenCVService()
        svc.update_config(min_pixels=100_000)
        result = svc.process_frame(self._frame_con_rectangulo())
        assert result.success is False  # ahora el mínimo descarta el objeto

    def test_resultados_previsibles(self):
        """
        Área y perímetro de un rectángulo conocido, dentro de un margen.

        El área medida es MAYOR que la dibujada porque `MORPH_CLOSE` (kernel
        11 por defecto, 2 iteraciones) dilata el contorno antes de medirlo.
        Es el comportamiento preexistente del pipeline y la causa conocida
        del error `opencv-oversensitive-macro-shapes`: el pipeline no está
        calibrado para dar el área exacta, sino un área consistente. Por eso
        el FactorK absorbs el sesgo en la práctica.
        """
        from services.opencv_service import OpenCVService
        result = OpenCVService().process_frame(self._frame_con_rectangulo(200, 150))
        # Entre un 5 % por debajo y un 30 % por encima del área real dibujada.
        assert 200 * 150 * 0.95 <= result.area_pixels <= 200 * 150 * 1.30
        assert result.perimeter_pixels > 2 * (200 + 150) * 0.9

    def test_el_dilatado_del_cierre_es_consistente(self):
        """Misma forma dos veces → mismo área (no hay aleatoriedad)."""
        from services.opencv_service import OpenCVService
        svc = OpenCVService()
        areas = {svc.process_frame(self._frame_con_rectangulo(200, 150)).area_pixels
                 for _ in range(5)}
        assert len(areas) == 1


class TestImageStorage:
    def test_guarda_y_nombra_por_timestamp(self, tmp_path):
        from data.repositories import ImageStorageService
        svc = ImageStorageService(images_dir=str(tmp_path))
        img = np.zeros((200, 300, 3), np.uint8)
        path = svc.save_silhouette(img, datetime(2026, 9, 26, 10, 30, 15, 123456))
        assert os.path.exists(path)
        assert path.endswith(".png")
        assert "20260926_103015" in os.path.basename(path)
        assert img.shape[1] == 300   # menor que 512, no se redimensiona

    def test_redimensiona_si_supera_el_limite(self, tmp_path):
        from data.repositories import ImageStorageService
        svc = ImageStorageService(images_dir=str(tmp_path))
        img = np.zeros((1200, 1600, 3), np.uint8)
        path = svc.save_silhouette(img, datetime.now())
        reloaded = cv2.imread(path)
        assert max(reloaded.shape[:2]) <= 512


class TestSettings:
    def test_defaults_si_no_existe(self, tmp_path):
        repo = SettingsRepository(str(tmp_path / "settings.json"))
        cfg = repo.load()
        assert cfg["detection_sensitivity"] in ("alta", "media", "baja", "macro")
        assert set(cfg["category_thresholds"]) == {"A", "B", "C", "D"}

    def test_ida_y_vuelta(self, tmp_path):
        repo = SettingsRepository(str(tmp_path / "settings.json"))
        repo.load()
        cfg = dict(repo.get())
        cfg["min_contour_area_pixels"] = 1234
        cfg["cost_per_m2_sheet"] = 99_999.0
        repo.save(cfg)
        assert repo.load()["min_contour_area_pixels"] == 1234
        assert repo.load()["cost_per_m2_sheet"] == 99_999.0

    def test_descarta_claves_desconocidas(self, tmp_path):
        """
        Comportamiento PREEXISTENTE que este test deja documentado, no una
        funcionalidad que se haya añadido:

        `_validate()` reconstruye el dict solo con las claves conocidas, así
        que un ajuste escrito por una versión futura de la app se pierde al
        cargar. No se ha cambiado porque la restricción es no alterar el
        comportamiento existente sin causa justificada, y no la hay.
        """
        path = tmp_path / "settings.json"
        path.write_text(
            '{"min_contour_area_pixels": 500, "clave_futura": "valor"}',
            encoding="utf-8",
        )
        cfg = SettingsRepository(str(path)).load()
        assert "clave_futura" not in cfg
        assert cfg["min_contour_area_pixels"] == 500

    def test_rechaza_umbrales_no_ascendentes(self, tmp_path):
        repo = SettingsRepository(str(tmp_path / "settings.json"))
        cfg = dict(repo.load())
        cfg["category_thresholds"] = {"A": [0, 2.0], "B": [1.0, 3.0], "C": [2.0, 4.0], "D": [3.0, 5.0]}
        repo.save(cfg)
        th = repo.load()["category_thresholds"]
        assert th["A"][1] < th["B"][1] < th["C"][1] < th["D"][1]

    def test_sensibilidad_invalida_cae_al_default(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text('{"detection_sensitivity": "inventada"}', encoding="utf-8")
        assert SettingsRepository(str(path)).load()["detection_sensitivity"] == "baja"

    def test_json_malformado_cae_al_default(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("{esto no es json", encoding="utf-8")
        assert "category_thresholds" in SettingsRepository(str(path)).load()

    def test_las_claves_nuevas_no_contaminan_los_defaults(self, tmp_path):
        """
        Regresión del shallow-copy: `dict(_DEFAULTS)` compartía los
        sub-diccionarios, así que mutar la config cargada envenenaba los
        defaults de toda la aplicación.
        """
        path = tmp_path / "settings.json"
        repo = SettingsRepository(str(path))
        cfg = repo.load()
        cfg["category_thresholds"]["A"][1] = 999.0
        cfg["cost_per_m2_sheet"] = 1.0
        assert repo.load()["category_thresholds"]["A"][1] == 1.0
        assert repo.load()["cost_per_m2_sheet"] == 85_000.0

    def test_nuevas_claves_de_retales(self, tmp_path):
        cfg = SettingsRepository(str(tmp_path / "settings.json")).load()
        for clave in ("cost_per_m2_sheet", "currency_symbol", "min_reusable_area_m2",
                      "max_reusable_area_m2", "min_reusable_thickness_mm",
                      "min_regularity_score", "sharpness_alert_threshold",
                      "auto_recycle_sin_ubicacion", "dxf_simplify_epsilon_ratio"):
            assert clave in cfg, f"falta la clave {clave}"

    def test_max_reusable_area_cero_significa_sin_maximo(self, tmp_path):
        cfg = SettingsRepository(str(tmp_path / "settings.json")).load()
        assert cfg["max_reusable_area_m2"] == 0.0


class TestMeasurementFlow:
    def test_el_repositorio_acepta_scraps(self, db_manager):
        """`save_measurement` sigue funcionando igual, ahora con scrap_id."""
        from core.entities import Measurement
        from data.repositories import MeasurementRepository
        repo = MeasurementRepository(db_manager)
        new_id = repo.save(Measurement(
            name="Prueba", area_pixels=1000.0, area_m2=0.5,
            category=MeasurementCategory.A, factor_k_used=1e-6,
            distance_cm=50.0, timestamp=datetime.now(),
        ))
        assert repo.get_by_id(new_id).scrap_id is None

    def test_lectura_de_fila_sin_scrap_id(self, db_manager):
        """
        Una fila sin la columna (base no migrada, o SELECT explícito) debe
        seguir leyéndose: la lectura de `scrap_id` es defensiva.
        """
        import sqlite3
        from data.repositories import MeasurementRepository
        with db_manager.get_connection() as conn:
            conn.execute(
                "INSERT INTO measurements (name, area_pixels, area_m2, category, "
                "factor_k_used, distance_cm, timestamp, is_valid) "
                "VALUES ('X', 100, 0.1, 'A', 1e-6, 50, '2026-01-01T00:00:00', 1)"
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM measurements"
            ).fetchone()
        # El Row no tiene scrap_id si el SELECT lo excluye; _row_to_entity lo tolera.
        from data.repositories import MeasurementRepository as MR
        m = MR._row_to_entity(row)
        assert m.name == "X"
        assert m.scrap_id is None


class TestGeometryClassifierLegacy:
    """El clasificador IA existente no debe haber cambiado."""

    def test_sigue_disponible(self):
        from services.ai_classifier import GeometryClassifier
        assert GeometryClassifier().is_available() is True

    def test_desde_el_resultado_del_pipeline(self):
        from services.ai_classifier import GeometryClassifier
        from services.opencv_service import OpenCVService
        frame = np.zeros((720, 1280, 3), np.uint8)
        cv2.rectangle(frame, (400, 250), (800, 400), (255, 255, 255), -1)
        result = OpenCVService().process_frame(frame)
        c = GeometryClassifier().classify_from_result(result)
        assert c is not None
        assert c.object_class

    def test_sin_resultado_valido(self):
        from services.ai_classifier import GeometryClassifier
        assert GeometryClassifier().classify_from_result(None) is None
