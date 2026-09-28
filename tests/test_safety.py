"""
Pruebas del detector de geometrías punzantes (`core/safety`).

Recuerden: esto NO certifica seguridad industrial. Lo que se verifica es que el
score separa bordes limpios de bordes con puntas, y que no dispara ante ruido
de segmentación.
"""
from __future__ import annotations

import pytest

from conftest import (
    circle_contour, jagged_contour, l_shape_contour, notched_contour,
    ngon_contour, rect_contour, star_contour,
)
from core.safety import analyze_sharpness

UMBRAL = 0.55


class TestCleanShapes:
    """Las formas de corte limpio no deben generar alerta."""

    @pytest.mark.parametrize("factory,args", [
        (rect_contour, (200, 200)),
        (rect_contour, (200, 120)),
        (rect_contour, (300, 100)),
        (circle_contour, (100,)),
        (ngon_contour, (3, 150)),
        (ngon_contour, (6, 150)),
    ])
    def test_sin_alerta(self, factory, args):
        r = analyze_sharpness(factory(*args), threshold=UMBRAL)
        assert r is not None
        assert not r.triggered, f"score {r.score:.2f} disparó la alerta sin motivo"
        assert r.score < UMBRAL

    def test_rectangulo_tiene_angulos_rectos(self):
        r = analyze_sharpness(rect_contour(200, 120))
        assert r.min_internal_angle_deg == pytest.approx(90.0, abs=1.0)

    def test_circulo_no_tiene_angulos_agudos(self):
        r = analyze_sharpness(circle_contour(100))
        assert r.min_internal_angle_deg > 120.0


class TestSharpShapes:
    """Las geometrías con puntas o bordes rotos deben generar alerta."""

    @pytest.mark.parametrize("factory,args,nombre", [
        (star_contour, (5, 160, 45), "estrella de 5 puntas"),
        (jagged_contour, (), "borde rasgado"),
        (notched_contour, (), "rectángulo con muesca profunda"),
    ])
    def test_dispara_alerta(self, factory, args, nombre):
        r = analyze_sharpness(factory(*args), threshold=UMBRAL)
        assert r.triggered, f"{nombre} no disparó la alerta (score {r.score:.2f})"

    def test_angulo_agudo_de_la_estrella(self):
        r = analyze_sharpness(star_contour(5, 160, 45))
        assert r.min_internal_angle_deg < 50.0

    def test_protrusion_alta_en_la_estrella(self):
        r = analyze_sharpness(star_contour(5, 160, 45))
        assert r.protrusion_depth > 0.4

    def test_angulo_agudo_de_la_muesca(self):
        r = analyze_sharpness(notched_contour())
        assert r.min_internal_angle_deg < 40.0

    def test_score_ordenado_por_riesgo(self):
        """
        El score debe ordenar las formas de más a menos arriesgadas, sin importar
        qué señal domine en cada una.
        """
        limpio = analyze_sharpness(rect_contour(200, 120)).score
        lshape = analyze_sharpness(l_shape_contour()).score
        muesca = analyze_sharpness(notched_contour()).score
        estrella = analyze_sharpness(star_contour(5, 160, 45)).score
        sierra = analyze_sharpness(jagged_contour()).score

        assert limpio < muesca
        assert limpio < estrella
        assert lshape < sierra


class TestThreshold:
    def test_umbral_configurable(self):
        """Subir el umbral debe desactivar alertas que antes se disparaban."""
        c = star_contour(5, 160, 45)
        assert analyze_sharpness(c, threshold=0.55).triggered is True
        assert analyze_sharpness(c, threshold=0.99).triggered is False

    def test_umbral_cero_dispara_siempre(self):
        r = analyze_sharpness(rect_contour(200, 120), threshold=0.0)
        assert r.triggered is True

    def test_umbral_uno_no_dispara_nunca(self):
        r = analyze_sharpness(star_contour(5, 160, 45), threshold=1.0)
        assert r.triggered is False


class TestRobustness:
    def test_contorno_none(self):
        assert analyze_sharpness(None) is None

    def test_contorno_sin_area(self):
        import cv2
        import numpy as np
        assert analyze_sharpness(np.array([[[5, 5]]], np.int32)) is None

    @pytest.mark.parametrize("factory,args", [
        (rect_contour, (200, 200)),
        (circle_contour, (100,)),
        (star_contour, (5, 160, 45)),
        (jagged_contour, ()),
    ])
    def test_score_en_rango_unitario(self, factory, args):
        r = analyze_sharpness(factory(*args))
        assert 0.0 <= r.score <= 1.0

    @pytest.mark.parametrize("factory,args", [
        (rect_contour, (200, 200)),
        (circle_contour, (100,)),
        (star_contour, (5, 160, 45)),
    ])
    def test_determinista(self, factory, args):
        c = factory(*args)
        scores = {analyze_sharpness(c).score for _ in range(10)}
        assert len(scores) == 1

    def test_escala_invariante(self):
        """
        UnCuadrado debe puntuar igual aunque se analice a distinta resolución:
        todas las señales son longitudes normalizadas, no absolutas.
        """
        pequeno = analyze_sharpness(rect_contour(60, 60)).score
        grande = analyze_sharpness(rect_contour(400, 400)).score
        assert pequeno == pytest.approx(grande, abs=0.05)

    def test_estrella_pequena_tambien_se_detecta(self):
        """Una punta no deja de ser punta por estar a menor resolución."""
        r = analyze_sharpness(star_contour(5, 60, 18))
        assert r.score > 0.4
