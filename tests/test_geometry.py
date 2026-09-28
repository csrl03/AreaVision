"""
Pruebas de la clasificación geométrica (`core/geometry`).

Verifican las etiquetas de forma, las dimensiones reales derivadas de
`minAreaRect` y el score de regularidad.
"""
from __future__ import annotations

import math

import pytest

from conftest import (
    circle_contour, jagged_contour, l_shape_contour, ngon_contour,
    notched_contour, rect_contour, star_contour, FACTOR_K,
)
from core.entities import ShapeType
from core.geometry import analyze_contour

PX_TO_M = math.sqrt(FACTOR_K)  # 0.01 m por píxel


class TestShapeClassification:
    def test_rectangulo(self):
        g = analyze_contour(rect_contour(200, 120), FACTOR_K)
        assert g.shape == ShapeType.RECTANGULO
        assert g.vertex_count == 4

    def test_cuadrado(self):
        g = analyze_contour(rect_contour(200, 200), FACTOR_K)
        assert g.shape == ShapeType.CUADRADO

    def test_cuadrado_y_rectangulo_se_distinguen_por_el_aspecto(self):
        """Un 2:1 no puede verse como cuadrado ni al revés."""
        cuadrado = analyze_contour(rect_contour(200, 200), FACTOR_K)
        rectangulo = analyze_contour(rect_contour(200, 100), FACTOR_K)
        assert cuadrado.aspect_ratio == pytest.approx(1.0, abs=0.05)
        assert rectangulo.aspect_ratio == pytest.approx(2.0, abs=0.05)

    @pytest.mark.parametrize("radius", [100, 50, 25])
    def test_circulo(self, radius):
        g = analyze_contour(circle_contour(radius), FACTOR_K)
        assert g.shape == ShapeType.CIRCULO

    def test_triangulo(self):
        g = analyze_contour(ngon_contour(3, 150), FACTOR_K)
        assert g.shape == ShapeType.TRIANGULO

    @pytest.mark.parametrize("n", [5, 6, 8])
    def test_poligono_regular(self, n):
        g = analyze_contour(ngon_contour(n, 150), FACTOR_K)
        assert g.shape == ShapeType.POLIGONO_REGULAR

    @pytest.mark.parametrize("n", [9, 10])
    def test_mas_de_8_lados_es_irregular(self, n):
        """El rango de "polígono regular" es 5..8; por encima es irregular."""
        g = analyze_contour(ngon_contour(n, 150), FACTOR_K)
        assert g.shape == ShapeType.POLIGONO_IRREGULAR

    def test_dodecagono_es_ambiguo_con_un_circulo(self):
        """
        Limitación REAL y documentada, no un caso que "debería" pasar.

        A 150 px de radio, un dodecágono regular y un círculo dan las mismas
        métricas (circularidad ≈0.886 en ambos) porque a esa resolución la
        diferencia geométrica es menor que el ruido de la pixelización. El
        sistema los etiqueta a los dos como `circulo`.

        No se puede separar con cámara monocular a esta escala. La consecuencia
        práctica es menor de lo que parece: un dodecágono y un disco se
        almacenan igual, se cortan igual y se valoran igual. Si en algún momento
        la distinción es relevante, hace falta más resolución o un sensor
        distinto, no otro ajuste de umbral.
        """
        dodecagono = analyze_contour(ngon_contour(12, 150), FACTOR_K)
        circulo = analyze_contour(circle_contour(150), FACTOR_K)
        assert dodecagono.shape == circulo.shape == ShapeType.CIRCULO

    def test_l_shape_es_irregular(self):
        assert analyze_contour(l_shape_contour(), FACTOR_K).shape.is_irregular_kind

    def test_borde_rasgado_es_irregular(self):
        assert analyze_contour(jagged_contour(), FACTOR_K).shape.is_irregular_kind

    def test_estrella_es_irregular(self):
        assert analyze_contour(star_contour(), FACTOR_K).shape.is_irregular_kind

    def test_hexagono_no_se_confunde_con_circulo(self):
        """
        Regresión del criterio de separación.

        Un hexágono regular tiene circularidad ≈0.82 y un círculo digitalizado
        ≈0.89: se solapan. El discriminante correcto es el *déficit de área*
        de la simplificación (círculo ≈0.09, hexágono ≈0.003).
        """
        hexa = analyze_contour(ngon_contour(6, 150), FACTOR_K)
        circ = analyze_contour(circle_contour(150), FACTOR_K)
        assert hexa.shape == ShapeType.POLIGONO_REGULAR
        assert circ.shape == ShapeType.CIRCULO


class TestDimensions:
    def test_dimensiones_de_un_rectangulo(self):
        g = analyze_contour(rect_contour(200, 120), FACTOR_K)
        assert g.length_m == pytest.approx(2.00, abs=0.02)
        assert g.width_m == pytest.approx(1.20, abs=0.02)

    def test_dimensiones_de_un_circulo(self):
        g = analyze_contour(circle_contour(100), FACTOR_K)
        assert g.length_m == pytest.approx(2.0, rel=0.05)
        assert g.width_m == pytest.approx(2.0, rel=0.05)

    def test_escala_lineal_con_el_factor_k(self):
        """Duplicar el FactorK multiplica el área por 2 y las dimensiones por √2."""
        c = rect_contour(200, 120)
        g1 = analyze_contour(c, FACTOR_K)
        g2 = analyze_contour(c, FACTOR_K * 2)
        assert g2.area_m2 == pytest.approx(g1.area_m2 * 2, rel=0.01)
        assert g2.length_m == pytest.approx(g1.length_m * math.sqrt(2), rel=0.01)

    def test_rectangulo_inclinado_usa_el_rectangulo_minimo_rotado(self):
        """
        El fallo documentado en `GestionErrores/`: con `boundingRect` (alineado
        a ejes) una pieza de 200×100 px girada 45° reporta aspecto ≈1.0.
        `minAreaRect` debe recuperar el aspecto real ≈2.0.
        """
        import cv2
        import numpy as np

        mask = np.zeros((600, 600), np.uint8)
        box = cv2.boxPoints(((300, 300), (200, 100), 45)).astype(np.int32)
        cv2.fillPoly(mask, [box], 255)
        from conftest import contour_from_mask
        g = analyze_contour(contour_from_mask(mask), FACTOR_K)
        assert g.aspect_ratio == pytest.approx(2.0, rel=0.15)
        assert g.length_m == pytest.approx(2.0, rel=0.10)
        assert g.width_m == pytest.approx(1.0, rel=0.15)

    def test_texto_de_dimensiones(self):
        g = analyze_contour(rect_contour(200, 120), FACTOR_K)
        assert g.dimensions_text == f"{g.length_m:.2f} × {g.width_m:.2f} m"


class TestRegularity:
    @pytest.mark.parametrize("factory,args,es_regular", [
        (rect_contour, (200, 200), True),
        (rect_contour, (200, 120), True),      # un rectángulo 5:1 sigue siendo regular
        (ngon_contour, (6, 150), True),
        (ngon_contour, (3, 150), True),
        (circle_contour, (100,), True),
        (l_shape_contour, (), False),
        (jagged_contour, (), False),
        (star_contour, (), False),
    ])
    def test_regularidad(self, factory, args, es_regular):
        g = analyze_contour(factory(*args), FACTOR_K)
        if es_regular:
            assert g.regularity_score >= 0.85, f"{g.shape} puntúa {g.regularity_score:.2f}"
        else:
            assert g.regularity_score < 0.75, f"{g.shape} puntúa {g.regularity_score:.2f}"

    def test_rectangulo_no_es_menos_regular_que_un_cuadrado(self):
        """
        Una medida de simetría (CV de lados) marcaría un 2:1 como irregular,
        porque sus lados son [L, W, L, W]. La regularidad debe medir la
        *suavidad del corte*, no la simetría.
        """
        largo = analyze_contour(rect_contour(300, 100), FACTOR_K)
        assert largo.regularity_score >= 0.85

    def test_score_en_rango_unitario(self):
        for c in (rect_contour(200, 200), circle_contour(100), jagged_contour()):
            g = analyze_contour(c, FACTOR_K)
            assert 0.0 <= g.regularity_score <= 1.0

    def test_confianza_en_rango_unitario(self):
        for c in (rect_contour(200, 120), circle_contour(100), star_contour()):
            g = analyze_contour(c, FACTOR_K)
            assert 0.0 <= g.confidence <= 1.0


class TestMetrics:
    def test_metricas_basicas(self):
        g = analyze_contour(rect_contour(200, 120), FACTOR_K)
        assert 0.0 <= g.circularity <= 1.0
        assert 0.0 <= g.solidity <= 1.0
        assert g.convexity_defects >= 0

    def test_solidez_alta_para_formas_convexas(self):
        g = analyze_contour(rect_contour(200, 120), FACTOR_K)
        assert g.solidity > 0.99

    def test_solidez_baja_para_forma_concava(self):
        g = analyze_contour(l_shape_contour(), FACTOR_K)
        assert g.solidity < 0.95

    def test_circularidad_alta_para_un_circulo(self):
        g = analyze_contour(circle_contour(100), FACTOR_K)
        assert g.circularity > 0.85


class TestEdgeCases:
    def test_contorno_none(self):
        assert analyze_contour(None, FACTOR_K) is None

    def test_factor_k_invalido(self):
        assert analyze_contour(rect_contour(200, 120), 0.0) is None
        assert analyze_contour(rect_contour(200, 120), -1.0) is None

    def test_contorno_degradado(self):
        import numpy as np
        assert analyze_contour(np.array([[[10, 10]]], np.int32), FACTOR_K) is None

    def test_contorno_de_una_linea(self):
        """
        Dos puntos no encierran área: `analyze_contour` debe devolver None.

        (Con tres puntos no colineales sí hay un triángulo con área real, y se
        analiza legítimamente; el descarte de piezas demasiado pequeñas para el
        negocio es una regla de clasificación, no del análisis geométrico.)
        """
        import cv2
        import numpy as np
        segment = np.array([[[10, 10]], [[110, 10]]], np.int32)
        assert analyze_contour(cv2.convexHull(segment), FACTOR_K) is None

    def test_contorno_de_puntos_identicos(self):
        import numpy as np
        dot = np.array([[[50, 50]], [[50, 50]]], np.int32)
        assert analyze_contour(dot, FACTOR_K) is None

    def test_tolerancia_de_simplificacion_altera_el_numero_de_vertices(self):
        """Un ε mayor debe producir siempre menos o iguales vértices."""
        c = jagged_contour()
        n_alta = analyze_contour(c, FACTOR_K, simplify_ratio=0.005).vertex_count
        n_baja = analyze_contour(c, FACTOR_K, simplify_ratio=0.08).vertex_count
        assert n_baja <= n_alta
        assert n_baja < 40   # nunca los 40 vérticos originales del dentado
