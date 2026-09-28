"""
Pruebas de la exportación DXF (`core.dxf` y `services.cad_service`).
"""
from __future__ import annotations

import math
import os

import numpy as np
import pytest

from conftest import (
    circle_contour, contour_from_mask, jagged_contour, rect_contour, FACTOR_K,
)
from core.dxf import build_shelf_dxf, contour_to_dxf, summarize_contour
from core.entities import Scrap, ScrapDestination, Shelf, ShapeType
from services.cad_service import CadExportError, CadService

ezdxf = pytest.importorskip("ezdxf", reason="ezdxf no instalado")
MM_PER_PX = math.sqrt(FACTOR_K) * 1000.0  # 10 mm por px


def entities_of(path: str):
    doc = ezdxf.readfile(path)
    return list(doc.modelspace())


class TestContourToDxf:
    def test_rectangulo_es_una_polilinea(self, tmp_path):
        out = str(tmp_path / "rect.dxf")
        contour_to_dxf(rect_contour(200, 120), FACTOR_K, out)
        ents = entities_of(out)
        assert len(ents) == 1
        assert ents[0].dxftype() == "LWPOLYLINE"
        assert len(ents[0].get_points()) == 4

    def test_circulo_es_una_entidad_circulo(self, tmp_path):
        out = str(tmp_path / "circ.dxf")
        contour_to_dxf(circle_contour(100), FACTOR_K, out)
        ents = entities_of(out)
        assert len(ents) == 1
        assert ents[0].dxftype() == "CIRCLE"
        # radio = 100 px → 1000 mm
        assert ents[0].dxf.radius == pytest.approx(1000.0, rel=0.05)

    def test_hexagono_no_se_exporta_como_circulo(self, tmp_path):
        """La misma regla que usa la clasificación, para no contradecirla."""
        from conftest import ngon_contour
        out = str(tmp_path / "hex.dxf")
        contour_to_dxf(ngon_contour(6, 150), FACTOR_K, out)
        assert entities_of(out)[0].dxftype() == "LWPOLYLINE"

    def test_escalado_px_a_mm(self, tmp_path):
        """200 px × 10 mm/px = 2000 mm de lado."""
        out = str(tmp_path / "scale.dxf")
        contour_to_dxf(rect_contour(200, 120), FACTOR_K, out)
        pts = entities_of(out)[0].get_points()
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        assert max(xs) - min(xs) == pytest.approx(2000.0, rel=0.02)
        assert max(ys) - min(ys) == pytest.approx(1200.0, rel=0.02)

    def test_polilinea_cerrada(self, tmp_path):
        out = str(tmp_path / "closed.dxf")
        contour_to_dxf(rect_contour(200, 120), FACTOR_K, out)
        assert entities_of(out)[0].closed is True

    def test_simplificacion_acota_los_vertices(self, tmp_path):
        """
        El requisito clave: una máscara ruidosa no puede volcar miles de puntos.

        El dentado tiene 40 vértices; el DXF debe tener muchos menos.
        """
        out = str(tmp_path / "jagged.dxf")
        contour_to_dxf(jagged_contour(), FACTOR_K, out)
        pts = entities_of(out)[0].get_points()
        assert 3 <= len(pts) <= 20
        assert len(pts) < 40

    def test_tolerancia_mayor_fewer_vertices(self, tmp_path):
        c = jagged_contour()
        alta = str(tmp_path / "a.dxf")
        baja = str(tmp_path / "b.dxf")
        contour_to_dxf(c, FACTOR_K, alta, simplify_ratio=0.005)
        contour_to_dxf(c, FACTOR_K, baja, simplify_ratio=0.08)
        n_alta = len(entities_of(alta)[0].get_points())
        n_baja = len(entities_of(baja)[0].get_points())
        assert n_baja < n_alta

    def test_archivo_legible_y_pequeno(self, tmp_path):
        out = str(tmp_path / "size.dxf")
        contour_to_dxf(jagged_contour(), FACTOR_K, out)
        assert os.path.getsize(out) < 200_000

    def test_capa_personalizada(self, tmp_path):
        out = str(tmp_path / "layer.dxf")
        contour_to_dxf(rect_contour(200, 120), FACTOR_K, out, layer="RETAL_007")
        assert entities_of(out)[0].dxf.layer == "RETAL_007"

    def test_contorno_none(self, tmp_path):
        with pytest.raises(ValueError):
            contour_to_dxf(None, FACTOR_K, str(tmp_path / "x.dxf"))

    def test_factor_k_invalido(self, tmp_path):
        with pytest.raises(ValueError):
            contour_to_dxf(rect_contour(200, 120), 0.0, str(tmp_path / "x.dxf"))

    def test_contorno_sin_area(self, tmp_path):
        c = np.array([[[10, 10]], [[20, 20]]], np.int32)
        with pytest.raises(ValueError):
            contour_to_dxf(c, FACTOR_K, str(tmp_path / "x.dxf"))

    def test_crea_el_directorio(self, tmp_path):
        out = str(tmp_path / "sub" / "dir" / "x.dxf")
        contour_to_dxf(rect_contour(200, 120), FACTOR_K, out)
        assert os.path.exists(out)


class TestShelfDxf:
    def test_rectangulo_de_la_repisa(self, tmp_path):
        out = str(tmp_path / "shelf.dxf")
        build_shelf_dxf(2.0, 1.2, out)
        pts = entities_of(out)[0].get_points()
        assert len(pts) == 4
        # Las coordenadas van en metros, no en milímetros.
        assert max(p[0] for p in pts) == pytest.approx(2.0)
        assert max(p[1] for p in pts) == pytest.approx(1.2)

    @pytest.mark.parametrize("w,l", [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)])
    def test_dimensiones_invalidas(self, tmp_path, w, l):
        with pytest.raises(ValueError):
            build_shelf_dxf(w, l, str(tmp_path / "x.dxf"))


class TestSummarize:
    def test_metricas_en_metros(self):
        s = summarize_contour(rect_contour(200, 120), FACTOR_K)
        assert s["area_m2"] == pytest.approx(200 * 120 * FACTOR_K, rel=0.02)
        assert s["length_m"] == pytest.approx(2.0, rel=0.02)
        assert s["width_m"] == pytest.approx(1.2, rel=0.02)
        assert s["perimeter_mm"] == pytest.approx(2 * (2000 + 1200), rel=0.02)

    def test_contorno_none(self):
        assert summarize_contour(None, FACTOR_K) == {}


class TestCadService:
    @pytest.fixture
    def service(self, tmp_path):
        return CadService(output_dir=str(tmp_path / "dxf"))

    def _scrap(self, **kwargs):
        base = dict(
            area_m2=2.4, width_m=1.2, length_m=2.0,
            shape=ShapeType.RECTANGULO,
            regularity=__import__("core.entities", fromlist=["Regularity"]).Regularity.REGULAR,
            destination=ScrapDestination.REUTILIZABLE,
        )
        base.update(kwargs)
        return Scrap(**base)

    def test_exporta_contorno(self, service):
        out = service.export_contour(rect_contour(200, 120), FACTOR_K, self._scrap())
        assert os.path.exists(out)
        assert out.endswith(".dxf")
        assert entities_of(out)

    def test_nombre_seguro_sin_texto_del_usuario(self, service):
        """
        El nombre NUNCA puede derivarse del texto del usuario: un retal llamado
        "../../../evil" no debe poder escribir fuera del directorio de salida.
        """
        malicioso = self._scrap(name="../../../../windows/system32/evil")
        out = service.export_contour(rect_contour(200, 120), FACTOR_K, malicioso)
        servicio_dir = os.path.abspath(service.output_dir)
        assert os.path.abspath(out).startswith(servicio_dir)

    def test_nombres_no_colisionan(self, service):
        """Dos exportaciones del mismo retal en el mismo segundo no se pisan."""
        s = self._scrap(id=1)
        a = service.export_contour(rect_contour(200, 120), FACTOR_K, s)
        b = service.export_contour(rect_contour(200, 120), FACTOR_K, s)
        assert a != b

    def test_exporta_rectangulo_de_respaldo(self, service):
        out = service.export_scrap_rectangle(self._scrap())
        assert os.path.exists(out)
        pts = entities_of(out)[0].get_points()
        # En metros: 2.00 × 1.20
        assert max(p[0] for p in pts) == pytest.approx(2.0)
        assert max(p[1] for p in pts) == pytest.approx(1.2)

    def test_exporta_repisa(self, service):
        s = Shelf(storage_area_id=1, name="Repisa 1", width_m=2.0, length_m=1.2)
        out = service.export_shelf(s)
        assert os.path.exists(out)
        assert "Repisa" in os.path.basename(out) or "repisa" in os.path.basename(out).lower()

    def test_sin_contorno_da_error_tipado(self, service):
        with pytest.raises(CadExportError):
            service.export_contour(None, FACTOR_K, self._scrap())

    def test_sin_silueta_da_error_claro(self, service):
        with pytest.raises(CadExportError, match="silueta"):
            service.export_from_silhouette(None, FACTOR_K, self._scrap())

    def test_silueta_inexistente(self, service):
        with pytest.raises(CadExportError):
            service.export_from_silhouette("/no/existe.png", FACTOR_K, self._scrap())

    def test_rectangulo_sin_dimensiones(self, service):
        with pytest.raises(CadExportError):
            service.export_scrap_rectangle(self._scrap(length_m=0.0))

    def test_reconstruye_contorno_desde_silueta(self, service, tmp_path):
        """El contour se recupera del PNG guardado, que es lo que ve el usuario."""
        import cv2
        mask = np.zeros((400, 400), np.uint8)
        cv2.rectangle(mask, (50, 50), (250, 170), 255, -1)
        png = str(tmp_path / "sil.png")
        cv2.imwrite(png, mask)

        out = service.export_from_silhouette(png, FACTOR_K, self._scrap())
        assert os.path.exists(out)
        pts = entities_of(out)[0].get_points()
        xs = [p[0] for p in pts]
        assert max(xs) - min(xs) == pytest.approx(2000.0, rel=0.05)

    def test_set_simplify_ratio(self, service):
        service.set_simplify_ratio(0.05)
        a = service.export_contour(jagged_contour(), FACTOR_K, self._scrap(), "a.dxf")
        service.set_simplify_ratio(0.005)
        b = service.export_contour(jagged_contour(), FACTOR_K, self._scrap(), "b.dxf")
        n_a = len(entities_of(a)[0].get_points())
        n_b = len(entities_of(b)[0].get_points())
        assert n_b >= n_a

    def test_ratio_invalido_se_ignora(self, service):
        original = service._simplify_ratio
        service.set_simplify_ratio(0.0)
        service.set_simplify_ratio(-1.0)
        service.set_simplify_ratio(5.0)
        assert service._simplify_ratio == original
