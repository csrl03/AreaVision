"""
VisiSize Python v1 — Punto de entrada
======================================
Uso:
    python main.py

Requisitos:
    pip install -r requirements.txt
"""
from __future__ import annotations

import logging
import os
import sys
import traceback


def _setup_logging() -> None:
    """Configura logging a consola y archivo con formato unificado."""
    from config import LOG_LEVEL, LOG_FILE

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
    except OSError as exc:
        # Continuar sin log de archivo si hay problema de permisos
        print(f"[AVISO] No se pudo crear el archivo de log: {exc}", file=sys.stderr)

    logging.basicConfig(level=level, format=fmt, handlers=handlers)


def _ensure_directories() -> None:
    """Crea los directorios de datos necesarios si no existen."""
    from config import DATA_DIR, IMAGES_DIR

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)


def _install_global_exception_handler() -> None:
    """
    Captura excepciones no manejadas y las registra antes de mostrar
    el diálogo de error de Qt (si la UI está activa).
    """
    logger = logging.getLogger("uncaught")

    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Excepción no capturada:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        # Mostrar diálogo de error si la app Qt está viva
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance()
            if app is not None:
                QMessageBox.critical(
                    None,
                    "Error inesperado",
                    f"Ha ocurrido un error inesperado:\n\n{exc_type.__name__}: {exc_value}\n\n"
                    "Consulte app.log para más detalles.",
                )
        except Exception:
            pass

    sys.excepthook = handle_exception


def main() -> int:
    _setup_logging()
    _ensure_directories()
    _install_global_exception_handler()

    logger = logging.getLogger("main")
    logger.info("═══ Iniciando VisiSize Python v1 ═══")

    # ── Inicializar base de datos ────────────────────────────────────────────
    try:
        from data.database import DatabaseManager

        db = DatabaseManager()
        db.initialize()
        logger.info("Base de datos lista")
    except Exception as exc:
        logger.critical("Error al inicializar la base de datos: %s", exc)
        print(f"\n[ERROR FATAL] No se pudo inicializar la base de datos: {exc}", file=sys.stderr)
        return 1

    # ── Lanzar UI ─────────────────────────────────────────────────────────────
    try:
        from ui.app import run_app

        return run_app(db)
    except ImportError as exc:
        logger.critical("Dependencia faltante: %s", exc)
        print(
            f"\n[ERROR] Dependencia no instalada: {exc}\n"
            "Ejecute:  pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        logger.exception("Error al iniciar la UI")
        print(f"\n[ERROR] No se pudo iniciar la interfaz: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
