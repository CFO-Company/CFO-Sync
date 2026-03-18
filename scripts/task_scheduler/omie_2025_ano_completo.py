from __future__ import annotations

import argparse
import logging
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.pipeline import SyncPipeline
from cfo_sync.core.runtime_paths import app_config_path, ensure_runtime_layout

PLATFORM_KEY = "omie_2025"
RESOURCE_NAME = "financeiro"
TARGET_YEAR = 2025


def _build_logger(log_dir: Path) -> tuple[logging.Logger, Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{PLATFORM_KEY}_{date.today().isoformat()}.log"
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    logger = logging.getLogger(f"cfo_sync.automation.{PLATFORM_KEY}.{run_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | run=%(run_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    class RunIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.run_id = run_id
            return True

    run_filter = RunIdFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(run_filter)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(run_filter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger, log_path


def _resolve_period() -> tuple[str, str]:
    start = date(TARGET_YEAR, 1, 1)
    end = date(TARGET_YEAR, 12, 31)
    return start.isoformat(), end.isoformat()


def _run(log_dir: Path) -> int:
    ensure_runtime_layout()
    logger, log_path = _build_logger(log_dir=log_dir)
    start_date, end_date = _resolve_period()

    run_start = perf_counter()
    logger.info(
        "RUN_START platform=%s python=%s log=%s periodo=%s..%s",
        PLATFORM_KEY,
        sys.version.split()[0],
        str(log_path),
        start_date,
        end_date,
    )

    config = load_app_config(app_config_path())
    platform = next((item for item in config.platforms if item.key == PLATFORM_KEY), None)
    if platform is None:
        raise ValueError(f"Plataforma '{PLATFORM_KEY}' nao configurada no app_config.")

    resource = next((item for item in platform.resources if item.name == RESOURCE_NAME), None)
    if resource is None:
        resources = sorted(item.name for item in platform.resources)
        raise ValueError(
            f"Recurso '{RESOURCE_NAME}' nao encontrado na plataforma {PLATFORM_KEY}. "
            f"Recursos atuais: {resources}"
        )

    logger.info(
        "PLATAFORMA key=%s label=%s clientes=%s recursos=%s",
        platform.key,
        platform.label,
        len(platform.clients),
        len(platform.resources),
    )

    pipeline = SyncPipeline(config=config)
    if PLATFORM_KEY not in pipeline.connectors:
        raise ValueError(f"Conector '{PLATFORM_KEY}' nao disponivel nesta instalacao.")

    total_tasks = 0
    failed_tasks = 0
    total_exported = 0

    for client in platform.clients:
        target = resource.client_tabs.get(client)
        if target is None:
            failed_tasks += 1
            logger.error(
                "PLANILHA_NAO_ENCONTRADA platform=%s recurso=%s cliente=%s",
                PLATFORM_KEY,
                RESOURCE_NAME,
                client,
            )
            continue

        spreadsheet_id = target.spreadsheet_id or resource.spreadsheet_id
        logger.info(
            "PLANILHA platform=%s recurso=%s cliente=%s spreadsheet_id=%s gid=%s tab=%s",
            PLATFORM_KEY,
            RESOURCE_NAME,
            client,
            spreadsheet_id,
            target.gid,
            target.tab_name,
        )

        total_tasks += 1
        task_start = perf_counter()
        logger.info(
            "TASK_START platform=%s cliente=%s recurso=%s",
            PLATFORM_KEY,
            client,
            RESOURCE_NAME,
        )
        try:
            exported = pipeline.export_to_sheets(
                platform_key=PLATFORM_KEY,
                client=client,
                start_date=start_date,
                end_date=end_date,
                resource_names=[RESOURCE_NAME],
            )
            elapsed = perf_counter() - task_start
            total_exported += exported
            logger.info(
                "TASK_OK platform=%s cliente=%s recurso=%s linhas=%s tempo=%.2fs",
                PLATFORM_KEY,
                client,
                RESOURCE_NAME,
                exported,
                elapsed,
            )
        except Exception as error:  # noqa: BLE001
            elapsed = perf_counter() - task_start
            failed_tasks += 1
            logger.error(
                "TASK_ERRO platform=%s cliente=%s recurso=%s tempo=%.2fs msg=%s",
                PLATFORM_KEY,
                client,
                RESOURCE_NAME,
                elapsed,
                error,
            )
            logger.error("TRACEBACK\n%s", traceback.format_exc())

    run_elapsed = perf_counter() - run_start
    logger.info(
        "RUN_END platform=%s status=%s tarefas=%s falhas=%s linhas=%s tempo_total=%.2fs",
        PLATFORM_KEY,
        "error" if failed_tasks else "ok",
        total_tasks,
        failed_tasks,
        total_exported,
        run_elapsed,
    )
    return 1 if failed_tasks else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Runner da Omie 2025 para ano completo (01/01/2025 a 31/12/2025).",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/automation",
        help="Diretorio de logs (padrao: logs/automation).",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    log_dir = Path(args.log_dir)
    if not log_dir.is_absolute():
        log_dir = (PROJECT_ROOT / log_dir).resolve()

    try:
        return _run(log_dir=log_dir)
    except Exception as error:  # noqa: BLE001
        print(f"FALHA FATAL: {error}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
