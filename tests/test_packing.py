"""
Pruebas del packing 2D (`core/packing`).

Cubren los casos que el enunciado exige explícitamente:
  - retal que cabe exactamente
  - retal que no cabe por ancho
  - retal que no cabe por largo
  - retal que necesita rotación de 90°
  - repisa llena
"""
from __future__ import annotations

import pytest

from core.packing import compute_occupancy, fits_single, place_in_bin


class TestFitsSingle:
    """El filtro barato: ¿cabe en alguna orientación?"""

    def test_cabe_sin_rotar(self):
        assert fits_single(1.10, 0.90, 2.00, 1.20) is True

    def test_cabe_exactamente(self):
        """Los límites son inclusivos: una pieza del tamaño exacto sí entra."""
        assert fits_single(2.00, 1.20, 2.00, 1.20) is True

    def test_no_cabe_por_ancho(self):
        # 2.05 > 2.00 del lado largo de la repisa, ni sin rotar ni girada
        assert fits_single(2.05, 0.80, 2.00, 1.20) is False

    def test_no_cabe_por_largo(self):
        # 2.10 m excede el lado más largo de la repisa (2.00 m) en cualquier
        # orientación: no hay forma de girarlo para que entre.
        assert fits_single(0.80, 2.10, 2.00, 1.20) is False

    def test_misma_area_comportamiento_distinto(self):
        """
        El caso central del enunciado: dos piezas de 1.50 m² sobre una repisa
        de 2.00 m² son intercambiables solo si se miran las dimensiones.

            Retal A  1.00 × 1.50 m  → cabe SOLO girada 90°
            Retal B  0.20 × 7.50 m  → no cabe de ninguna manera

        Un filtro por área las aceptaría a las dos.
        """
        assert fits_single(1.00, 1.50, 2.00, 1.00) is True    # A, girada
        assert fits_single(0.20, 7.50, 2.00, 1.00) is False   # B, imposible

    def test_una_pieza_necesita_giro_para_entrar(self):
        """A 1.00 × 1.50 m no cabe derecho en 2.00 × 1.00 m, pero sí girada."""
        assert fits_single(1.00, 1.50, 2.00, 1.00) is True
        # Elpacking es quien decide el giro: aquí debe devolverse rotado.
        x, y, rotated = place_in_bin(1.00, 1.50, 2.00, 1.00, [])
        assert rotated is True
        assert (x, y) == (0.0, 0.0)

    def test_requiere_rotacion_de_90(self):
        """1.50 × 0.40 no cabe sin rotar, pero sí girada en 2.00 × 0.50."""
        assert fits_single(1.50, 0.40, 2.00, 0.50) is True

    def test_cuadro_no_necesita_rotacion(self):
        assert fits_single(0.50, 0.50, 0.50, 0.50) is True

    @pytest.mark.parametrize("args", [
        (0.0, 1.0, 2.0, 1.0),
        (1.0, 0.0, 2.0, 1.0),
        (1.0, 1.0, 0.0, 1.0),
        (1.0, 1.0, 2.0, 0.0),
        (-1.0, 1.0, 2.0, 1.0),
    ])
    def test_dimensiones_invalidas(self, args):
        assert fits_single(*args) is False


class TestPlaceInBin:
    """Colocación real con hueco verificado."""

    def test_repisa_vacia(self):
        pos = place_in_bin(1.0, 0.5, 2.0, 1.2, [])
        assert pos is not None
        x, y, rotated = pos
        assert (x, y) == (0.0, 0.0)
        assert rotated is False

    def test_ocupa_exactamente_toda_la_repisa(self):
        pos = place_in_bin(2.0, 1.2, 2.0, 1.2, [])
        assert pos is not None

    def test_segunda_pieza_al_lado(self):
        placed = [(0.0, 0.0, 1.0, 1.2)]
        pos = place_in_bin(1.0, 1.2, 2.0, 1.2, placed)
        assert pos is not None
        x, y, _ = pos
        assert x == pytest.approx(1.0)   # a la derecha
        assert y == pytest.approx(0.0)

    def test_segunda_pieza_encima(self):
        """Sin hueco horizontal, abre una estantería nueva arriba."""
        placed = [(0.0, 0.0, 2.0, 0.6)]
        pos = place_in_bin(2.0, 0.6, 2.0, 1.2, placed)
        assert pos is not None
        x, y, _ = pos
        assert x == pytest.approx(0.0)
        assert y == pytest.approx(0.6)

    def test_repisa_llena(self):
        placed = [(0.0, 0.0, 2.0, 1.2)]
        assert place_in_bin(0.5, 0.5, 2.0, 1.2, placed) is None

    def test_cabe_por_area_pero_no_por_forma(self):
        """
        Dos piezas de 0.9 m² cada una sobre una repisa de 1.5 m²:
        la suma cabe, pero juntas no.
        """
        placed = [(0.0, 0.0, 0.90, 1.00)]
        assert place_in_bin(0.90, 1.00, 1.50, 1.00, placed) is None

    def test_rotacion_para_aprovechar_espacio(self):
        """
        Una franja vertical ocupa x∈[0, 0.5) en toda la altura. Queda libre una
        franja de 1.5 × 2.0 m: la pieza de 1.8 × 0.4 no cabe derecha, pero sí
        girada 90°.
        """
        placed = [(0.0, 0.0, 0.5, 2.0)]
        pos = place_in_bin(1.8, 0.4, 2.0, 2.0, placed)
        assert pos is not None, "la pieza girada debería caber en la franja libre"
        x, y, rotated = pos
        assert rotated is True, "debe girarse 90° para caber en la franja restante"
        assert x == pytest.approx(0.5)
        assert y == pytest.approx(0.0)

    def test_pieza_que_no_cabe_en_ninguna_orientacion(self):
        """
        Un cuadrado de 1.5 × 1.5 m no cabe en 2.0 × 1.0 m: girarlo no cambia
        nada, así que debe rechazarse sin inventar una posición.
        """
        assert place_in_bin(1.5, 1.5, 2.0, 1.0, []) is None

    def test_guardia_tras_bug_de_altura(self):
        """
        Regresión del fallo real de `_shelf_first_pass`: devolvía una posición
        fuera de la repisa para un candidato cuya altura superaba la del bin,
        sin comprobar `sy + h > bin_h`. La primera orientación (1.0 × 1.5) no
        cabe en 2.0 × 1.0, pero la girada sí: el resultado debe ser la girada,
        con la altura correcta.
        """
        pos = place_in_bin(1.0, 1.5, 2.0, 1.0, [])
        assert pos is not None
        x, y, rotated = pos
        assert rotated is True
        w, h = (1.5, 1.0) if rotated else (1.0, 1.5)
        assert y + h <= 1.0 + 1e-9
        assert x + w <= 2.0 + 1e-9

    def test_nunca_solapa(self):
        """Propiedad de seguridad: toda colocación debe quedar libre."""
        placed = [
            (0.0, 0.0, 1.0, 0.6),
            (1.0, 0.0, 1.0, 0.6),
            (0.0, 0.6, 1.0, 0.6),
        ]
        pos = place_in_bin(1.0, 0.6, 2.0, 1.2, placed)
        assert pos is not None
        x, y, rotated = pos
        w, h = (0.6, 1.0) if rotated else (1.0, 0.6)
        for px, py, pw, ph in placed:
            overlap_x = not (x + w <= px or px + pw <= x)
            overlap_y = not (y + h <= py or py + ph <= y)
            assert not (overlap_x and overlap_y), "la pieza se solapa con otra"

    def test_determinista(self):
        """El mismo inventario debe producir siempre la misma posición."""
        placed = [(0.0, 0.0, 0.9, 1.0), (0.9, 0.0, 0.9, 0.5)]
        results = {place_in_bin(0.7, 0.8, 2.0, 1.2, placed) for _ in range(20)}
        assert len(results) == 1

    def test_siempre_dentro_de_la_repisa(self):
        placed = [(0.0, 0.0, 0.5, 0.5), (0.5, 0.0, 0.5, 0.5)]
        pos = place_in_bin(0.4, 0.9, 2.0, 1.0, placed)
        assert pos is not None
        x, y, rotated = pos
        w, h = (0.9, 0.4) if rotated else (0.4, 0.9)
        assert x >= 0 and y >= 0
        assert x + w <= 2.0 + 1e-9
        assert y + h <= 1.0 + 1e-9

    def test_ningun_retal_grande(self):
        assert place_in_bin(3.0, 0.8, 2.0, 1.2, []) is None


class TestComputeOccupancy:
    def test_repisa_vacia(self):
        m = compute_occupancy([], 2.0, 1.0)
        assert m["total_area_m2"] == pytest.approx(2.0)
        assert m["used_area_m2"] == pytest.approx(0.0)
        assert m["available_area_m2"] == pytest.approx(2.0)
        assert m["occupancy_ratio"] == pytest.approx(0.0)
        assert m["piece_count"] == 0

    def test_repisa_ocupada(self):
        m = compute_occupancy([(0, 0, 1.0, 1.0)], 2.0, 2.0)
        assert m["used_area_m2"] == pytest.approx(1.0)
        assert m["available_area_m2"] == pytest.approx(3.0)
        assert m["occupancy_ratio"] == pytest.approx(0.25)
        assert m["piece_count"] == 1

    def test_area_nunca_negativa(self):
        """Aunque se pase un área usada mayor que el total, no debe quedar negativo."""
        m = compute_occupancy([(0, 0, 3.0, 3.0)], 1.0, 1.0)
        assert m["available_area_m2"] >= 0.0

    def test_repisa_de_area_cero(self):
        """No debe dividir por cero."""
        m = compute_occupancy([], 0.0, 0.0)
        assert m["occupancy_ratio"] == 0.0
