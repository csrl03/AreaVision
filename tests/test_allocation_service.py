"""
Pruebas del servicio de asignación (`services/allocation_service`).

Cubren los casos de negocio: repisa compatible, varias compatibles, ninguna
compatible, repisa llena, y la política de "sin ubicación".
"""
from __future__ import annotations

from datetime import datetime

import pytest

from conftest import make_scrap
from core.entities import (
    Regularity, Scrap, ScrapDestination, Shelf, ShelfRules, ShapeType,
)
from services.allocation_service import AllocationService


@pytest.fixture
def allocator(warehouse):
    """Depende de `warehouse` para garantizar que existen estantes y repisas."""
    from services.allocation_service import AllocationService
    _, shelf_repo, scrap_repo = warehouse["repos"]
    return AllocationService(shelf_repo, scrap_repo)


def shelves_of(warehouse):
    return warehouse["repos"][1].get_all()


class TestBasicAssignment:
    def test_asigna_a_la_repisa_compatible(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 2.0, 1.2, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found
        assert p.shelf is not None
        assert "Estante 1" in p.location_text

    def test_no_asigna_a_un_retal_reciclable(self, warehouse, allocator):
        s = make_scrap(ShapeType.POLIGONO_IRREGULAR, 2.0, 1.2,
                       destination=ScrapDestination.RECICLABLE)
        p = allocator.propose(s, shelves_of(warehouse))
        assert not p.found
        assert "reciclaje" in p.reason.lower()

    def test_sin_repisas_registradas(self, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.0, 0.8)
        p = allocator.propose(s, [])
        assert not p.found
        assert "repisas" in p.reason.lower()

    def test_ignora_piezas_que_no_caben(self, warehouse, allocator):
        """Un retal más largo que el lado mayor de todas las repisas."""
        s = make_scrap(ShapeType.RECTANGULO, 3.0, 0.5, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert not p.found
        assert p.rejected


class TestShelfRules:
    def test_respeta_forma_regular(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.5, 0.8, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found
        assert p.shelf.rules.accepts_regular

    def test_respeta_forma_irregular(self, warehouse, allocator):
        s = make_scrap(ShapeType.POLIGONO_IRREGULAR, 1.2, 1.0, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found
        assert p.shelf.rules.accepts_irregular
        assert not p.shelf.rules.accepts_regular

    def test_respeta_rango_de_dimensiones(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.9, 1.1, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found

    def test_rechaza_por_ancho_minimo(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.0, 0.2, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert not p.found
        assert any("menor al mínimo" in why for _, why in p.rejected)

    def test_rechaza_por_espesor(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.2, 0.9, thickness_mm=0.1)
        p = allocator.propose(s, shelves_of(warehouse))
        assert not p.found
        assert any("espesor" in why for _, why in p.rejected)

    def test_rechaza_por_area(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.0, 0.9, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        # 0.9 m² supera el máximo de 0.5 m² de la repisa pequeña; las otras
        # dos no fijan área, así que debe encontrar una.
        assert p.found

    def test_espesor_no_capturado_no_rechaza(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.2, 0.9, thickness_mm=None)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found


class TestMultipleCandidates:
    def test_elige_la_que_mas_espacio_libre_tiene(self, warehouse, allocator):
        """Con varias repisas válidas gana la que menos espacio pierde."""
        s = make_scrap(ShapeType.RECTANGULO, 1.0, 0.6, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found
        # 0.5×0.5 es demasiado pequeña, luego gana una de 2.0×1.2 o 1.5×1.0
        assert p.shelf.area_m2 == pytest.approx(2.4)

    def test_registra_las_repisas_descartadas(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.0, 0.6, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found
        assert len(p.rejected) >= 1
        for ubicacion, motivo in p.rejected:
            assert ubicacion and motivo

    def test_preferencia_por_mayor_capacidad(self, warehouse, allocator):
        """Entre dos repisas válidas, la de mayor capacidad debe ganar."""
        _, shelf_repo, _ = warehouse["repos"]
        grande = Shelf(storage_area_id=warehouse["area_regular"],
                       name="Grande", width_m=4.0, length_m=4.0)
        shelf_repo.save(grande)
        s = make_scrap(ShapeType.RECTANGULO, 0.8, 0.6, thickness_mm=3.0)
        p = allocator.propose(s, shelf_repo.get_all())
        assert p.shelf.id == grande.id


class TestPhysicalSpace:
    def test_repisa_llena_no_acepta_una_pieza_mas(self, warehouse, allocator):
        """La repisa 2.00×1.20 se llena con un retal de 2.00×1.20."""
        _, shelf_repo, scrap_repo = warehouse["repos"]
        shelf_id = warehouse["regular"]

        # Registrar un retal que ocupa la repisa entera
        grande = make_scrap(ShapeType.RECTANGULO, 2.0, 1.2, thickness_mm=3.0,
                            created_at=datetime.now())
        grande.shelf_id = shelf_id
        grande.storage_area_id = warehouse["area_regular"]
        scrap_repo.save(grande)

        # El siguiente debe buscar otra repisa o no encontrar ninguna
        s = make_scrap(ShapeType.RECTANGULO, 2.0, 1.2, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        if p.found:
            assert p.shelf.id != shelf_id

    def test_dos_piezas_pequenas_caben_juntas(self, warehouse, allocator):
        _, shelf_repo, scrap_repo = warehouse["repos"]
        shelf_id = warehouse["regular"]
        p1 = make_scrap(ShapeType.RECTANGULO, 1.0, 1.0, thickness_mm=3.0,
                        created_at=datetime.now())
        p1.shelf_id = shelf_id
        p1.storage_area_id = warehouse["area_regular"]
        scrap_repo.save(p1)

        s = make_scrap(ShapeType.RECTANGULO, 1.0, 1.0, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found
        assert p.shelf.id == shelf_id
        assert p.position_x_m == pytest.approx(1.0)

    def test_devuelve_posicion_dentro_de_la_repisa(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.1, 0.9, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found
        assert p.position_x_m >= 0
        assert p.position_y_m >= 0
        w, h = (s.width_m, s.length_m)
        if p.rotated:
            w, h = h, w
        assert p.position_x_m + w <= p.shelf.width_m + 1e-9
        assert p.position_y_m + h <= p.shelf.length_m + 1e-9


class TestNoLocationPolicy:
    """
    Un retal reutilizable que no cabe puede quedar sin ubicación o reciclarse,
    según lo que haya configurado el usuario. Por defecto NO se recicla:
    es material valioso.
    """

    def _gigante(self):
        return make_scrap(ShapeType.RECTANGULO, 4.0, 1.5, thickness_mm=3.0)

    def test_por_defecto_queda_reutilizable_sin_ubicacion(self, warehouse, allocator):
        s = self._gigante()
        p = allocator.propose(s, shelves_of(warehouse))
        assert not p.found
        assert allocator.destination_for(s, p) == ScrapDestination.REUTILIZABLE

    def test_con_auto_recycle_activado_pasa_a_reciclaje(self, warehouse, allocator):
        allocator.set_auto_recycle(True)
        s = self._gigante()
        p = allocator.propose(s, shelves_of(warehouse))
        assert not p.found
        assert allocator.destination_for(s, p) == ScrapDestination.RECICLABLE

    def test_con_ubicacion_siempre_queda_reutilizable(self, warehouse, allocator):
        allocator.set_auto_recycle(True)
        s = make_scrap(ShapeType.RECTANGULO, 1.0, 0.8, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.found
        assert allocator.destination_for(s, p) == ScrapDestination.REUTILIZABLE

    def test_el_motivo_explica_las_causas(self, warehouse, allocator):
        s = self._gigante()
        p = allocator.propose(s, shelves_of(warehouse))
        assert "No se encontró" in p.reason
        assert p.rejected

    def test_append_no_location_reason(self, warehouse, allocator):
        s = self._gigante()
        p = allocator.propose(s, shelves_of(warehouse))
        reasons = allocator.append_no_location_reason(s, p)
        assert len(reasons) > len(s.reasons)
        assert p.reason in reasons[-1]

    def test_confianza_cuando_no_encuentra(self, warehouse, allocator):
        """Sin hueco demostrado, `is_confident` debe ser False."""
        s = self._gigante()
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.is_confident is False

    def test_confianza_cuando_encuentra(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.0, 0.8, thickness_mm=3.0)
        p = allocator.propose(s, shelves_of(warehouse))
        assert p.is_confident is True


class TestDegradation:
    def test_sin_repositorio_devuelve_propuesta_vacia(self):
        allocator = AllocationService()
        s = make_scrap(ShapeType.RECTANGULO, 1.0, 0.8)
        p = allocator.propose(s, None)
        assert not p.found
        assert "repositorio" in p.reason.lower()

    def test_determinista(self, warehouse, allocator):
        s = make_scrap(ShapeType.RECTANGULO, 1.1, 0.9, thickness_mm=3.0)
        shelves = shelves_of(warehouse)
        results = {allocator.propose(s, shelves).shelf.id for _ in range(15)}
        assert len(results) == 1
