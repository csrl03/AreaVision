"""
Pruebas de la valoración económica (`core/scoring`).
"""
from __future__ import annotations

import pytest

from core.scoring import compute_estimated_value, format_currency


class TestEstimatedValue:
    def test_ejemplo_del_enunciado(self):
        """Área 1.40 m² × 85.000 COP/m² = 119.000 COP."""
        assert compute_estimated_value(1.40, 85_000.0) == pytest.approx(119_000.0)

    def test_es_lineal_con_el_area(self):
        v1 = compute_estimated_value(1.0, 50_000.0)
        v2 = compute_estimated_value(2.0, 50_000.0)
        assert v2 == pytest.approx(v1 * 2)

    def test_es_lineal_con_el_costo(self):
        v1 = compute_estimated_value(1.0, 50_000.0)
        v2 = compute_estimated_value(1.0, 100_000.0)
        assert v2 == pytest.approx(v1 * 2)

    @pytest.mark.parametrize("area,cost,esperado", [
        (0.0, 85_000.0, 0.0),      # área nula
        (-1.0, 85_000.0, 0.0),     # área negativa
        (1.5, 0.0, 0.0),           # costo no configurado
        (1.5, -100.0, 0.0),        # costo negativo
    ])
    def test_casos_no_validos_devuelven_cero(self, area, cost, esperado):
        assert compute_estimated_value(area, cost) == esperado

    def test_area_muy_pequena(self):
        assert compute_estimated_value(0.001, 85_000.0) == pytest.approx(85.0)


class TestFormatCurrency:
    def test_formato_es_ec(self):
        """Separador de miles es-EC: 119000 → '119.000'."""
        assert format_currency(119_000.0) == "$ 119.000"

    def test_ejemplo_del_enunciado(self):
        assert format_currency(compute_estimated_value(1.40, 85_000.0)) == "$ 119.000"

    def test_simbolo_personalizado(self):
        assert format_currency(119_000.0, symbol="COP ") == "COP  119.000"

    def test_sin_costo_configurado(self):
        assert format_currency(0.0) == "Sin costo configurado"
        assert format_currency(None) == "Sin costo configurado"

    def test_decimales_redondeados(self):
        assert format_currency(1234.56) == "$ 1.235"

    def test_valores_grandes(self):
        assert format_currency(12_345_678.0) == "$ 12.345.678"

    def test_cero_y_negativo(self):
        assert format_currency(0.0) == "Sin costo configurado"
        assert format_currency(-5.0) == "Sin costo configurado"
