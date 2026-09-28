"""
Pruebas del servicio de clasificación (`services/classification_service`).

Verifican la decisión REUTILIZABLE / RECICLABLE, la entrada manual de espesor y
la degradación elegante cuando no hay contorno.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from conftest import (
    circle_contour, contour_from_mask, jagged_contour, l_shape_contour,
    ngon_contour, rect_contour, star_contour, FACTOR_K,
)
from core.entities import ScrapDestination
from services.classification_service import ClassificationService, ReusePolicy


@pytest.fixture
def service() -> ClassificationService:
    return ClassificationService(ReusePolicy())


def analyze(service, contour, thickness=3.0, fk=FACTOR_K):
    area = cv2.contourArea(contour) * fk
    return service.analyze(contour, fk, area, thickness)


class TestReusableDecisions:
    def test_retal_grande_y_grueso(self, service):
        a = analyze(service, rect_contour(200, 120), 3.0)
        assert a.destination == ScrapDestination.REUTILIZABLE
        assert a.reasons

    def test_retal_circular(self, service):
        a = analyze(service, circle_contour(100), 2.0)
        assert a.destination == ScrapDestination.REUTILIZABLE

    def test_espesor_no_capturado_no_bloquea(self, service):
        """El usuario puede no conocer el espesor; no debe forzar el reciclaje."""
        a = analyze(service, rect_contour(200, 120), None)
        assert a.destination == ScrapDestination.REUTILIZABLE
        assert any("no capturado" in r.lower() for r in a.reasons)

    def test_valor_estimado(self, service):
        a = analyze(service, rect_contour(200, 120), 3.0)
        assert a.estimated_value == pytest.approx(a.geometry.area_m2 * 85_000.0)


class TestRecyclableDecisions:
    def test_area_insuficiente(self, service):
        a = analyze(service, rect_contour(30, 30), 3.0)
        assert a.destination == ScrapDestination.RECICLABLE
        assert any("área" in r.lower() for r in a.reasons)

    def test_espesor_insuficiente(self, service):
        a = analyze(service, rect_contour(200, 120), 0.5)
        assert a.destination == ScrapDestination.RECICLABLE
        assert any("espesor" in r.lower() for r in a.reasons)

    def test_forma_irregular(self, service):
        a = analyze(service, jagged_contour(), 3.0)
        assert a.destination == ScrapDestination.RECICLABLE
        assert any("irregular" in r.lower() for r in a.reasons)

    def test_area_maxima_superada(self):
        service = ClassificationService(ReusePolicy(max_reusable_area_m2=0.5))
        a = analyze(service, rect_contour(200, 120), 3.0)
        assert a.destination == ScrapDestination.RECICLABLE
        assert any("máximo" in r.lower() for r in a.reasons)

    def test_se_reportan_todos_los_motivos(self, service):
        """Un retal que falla por dos reglas debe reportar ambas."""
        a = analyze(service, rect_contour(20, 20), 0.3)
        assert a.destination == ScrapDestination.RECICLABLE
        assert len(a.reasons) >= 2


class TestThresholdsAreConfigurable:
    """Ninguna regla de negocio puede estar fija en el código."""

    def test_area_minima_mas_permisiva(self):
        service = ClassificationService(ReusePolicy(min_reusable_area_m2=0.05))
        a = analyze(service, rect_contour(30, 30), 3.0)
        assert a.destination == ScrapDestination.REUTILIZABLE

    def test_area_minima_mas_exigente(self):
        service = ClassificationService(ReusePolicy(min_reusable_area_m2=5.0))
        a = analyze(service, rect_contour(200, 120), 3.0)
        assert a.destination == ScrapDestination.RECICLABLE

    def test_regularidad_minima_mas_exigente(self):
        service = ClassificationService(ReusePolicy(min_regularity_score=0.99))
        a = analyze(service, l_shape_contour(), 3.0)
        assert a.destination == ScrapDestination.RECICLABLE

    def test_espesor_minimo_a_cero(self):
        service = ClassificationService(ReusePolicy(min_reusable_thickness_mm=0.0))
        a = analyze(service, rect_contour(200, 120), 0.1)
        assert a.destination == ScrapDestination.REUTILIZABLE

    def test_umbral_de_alerta_mas_alto(self):
        service = ClassificationService(ReusePolicy(sharpness_alert_threshold=0.99))
        a = analyze(service, star_contour(5, 160, 45), 3.0)
        assert a.safety.triggered is False

    def test_costo_configurable(self):
        service = ClassificationService(ReusePolicy(cost_per_m2_sheet=10_000.0))
        a = analyze(service, rect_contour(200, 120), 3.0)
        assert a.estimated_value == pytest.approx(a.geometry.area_m2 * 10_000.0)

    def test_politica_desde_settings(self):
        policy = ReusePolicy.from_settings({
            "cost_per_m2_sheet": 42_000.0,
            "min_reusable_area_m2": 1.0,
            "min_reusable_thickness_mm": 5.0,
        })
        assert policy.cost_per_m2_sheet == 42_000.0
        assert policy.min_reusable_area_m2 == 1.0
        assert policy.min_reusable_thickness_mm == 5.0

    def test_politica_desde_settings_vacio_usa_defaults(self):
        policy = ReusePolicy.from_settings({})
        assert policy.min_reusable_area_m2 == 0.25
        assert policy.min_reusable_thickness_mm == 2.0
        assert policy.min_regularity_score == 0.70

    def test_set_policy_en_caliente(self, service):
        c = rect_contour(30, 30)
        assert analyze(service, c, 3.0).destination == ScrapDestination.RECICLABLE
        service.set_policy(ReusePolicy(min_reusable_area_m2=0.01))
        assert analyze(service, c, 3.0).destination == ScrapDestination.REUTILIZABLE


class TestDegradation:
    def test_sin_contorno_clasifica_por_area(self, service):
        """Sin `main_contour` el análisis no se rompe: usa solo el área."""
        a = service.analyze(None, FACTOR_K, 2.4, 3.0)
        assert a is not None
        assert a.destination == ScrapDestination.REUTILIZABLE
        assert a.geometry.shape.value == "otra"
        assert a.geometry.regularity_score == 0.0

    def test_sin_contorno_no_dispara_alerta_de_riesgo(self, service):
        """
        La ausencia de datos no es evidencia de riesgo: no debe inventar
        falsos positivos de seguridad.
        """
        a = service.analyze(None, FACTOR_K, 2.4, 3.0)
        assert a.safety.triggered is False
        assert a.safety.score == 0.0

    def test_area_cero_devuelve_none(self, service):
        assert service.analyze(None, FACTOR_K, 0.0, 3.0) is None

    def test_sin_contorno_sigue_clasificando_por_area(self, service):
        """
        Sin FactorK ni contorno, pero con un área ya calculada, el servicio
        degrada a clasificación por área en vez de fallar. El pipeline siempre
        entrega el área calibrada, así que perder el contorno no debe impedir
        registrar la pieza.
        """
        a = service.analyze(rect_contour(200, 120), 0.0, 2.4, 3.0)
        assert a is not None
        assert a.destination == ScrapDestination.REUTILIZABLE
        assert a.geometry.is_degraded is True


class TestResultStructure:
    def test_el_resultado_trae_todas_las_piezas(self, service):
        a = analyze(service, rect_contour(200, 120), 3.0)
        assert a.geometry is not None
        assert a.safety is not None
        assert a.destination in list(ScrapDestination)
        assert isinstance(a.reasons, list)
        assert a.thickness_mm == 3.0
        assert a.cost_per_m2 == 85_000.0

    def test_el_servicio_no_depende_de_la_ui(self):
        """
        El módulo de negocio no debe importar PyQt6.

        Se comprueba el árbol de imports real, no el texto del fuente: un
        docstring que mencione "PyQt6" no debe hacer fallar la prueba.
        """
        import ast
        import inspect
        import services.classification_service as mod

        tree = ast.parse(inspect.getsource(mod))
        importados = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                importados.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                importados.add(node.module.split(".")[0])
        assert "PyQt6" not in importados, importados
        assert "ui" not in importados, importados

    def test_sin_importar_qt_al_arrancar(self):
        """Importar el servicio no debe arrastrar la UI."""
        import subprocess
        import sys
        r = subprocess.run(
            [sys.executable, "-c",
             "import services.classification_service, sys; "
             "print('PyQt6' in sys.modules)"],
            capture_output=True, text=True,
        )
        assert r.stdout.strip() == "False", r.stdout + r.stderr
