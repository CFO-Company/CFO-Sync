from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.models import AppConfig, ResourceConfig
from cfo_sync.core.pipeline import SyncPipeline
from cfo_sync.core.runtime_paths import app_config_path, ensure_runtime_layout
from cfo_sync.core.sheets_exporter import GoogleSheetsExporter
from cfo_sync.platforms.omie.credentials import build_omie_platform_config


PERIOD_CHOICES = (
    "rolling_months",
    "yesterday",
    "year_current",
    "year_previous",
    "custom",
)


def _add_months(base_month: date, delta: int) -> date:
    month_index = (base_month.year * 12 + (base_month.month - 1)) + delta
    target_year = month_index // 12
    target_month = month_index % 12 + 1
    return date(target_year, target_month, 1)


def _resolve_period(
    period: str,
    months: int,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str]:
    today = date.today()

    if period == "rolling_months":
        if months < 1:
            raise ValueError("Parametro --months deve ser maior ou igual a 1.")
        current_month_start = today.replace(day=1)
        start = _add_months(current_month_start, -(months - 1))
        end = today
        return start.isoformat(), end.isoformat()

    if period == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday.isoformat(), yesterday.isoformat()

    if period == "year_current":
        return date(today.year, 1, 1).isoformat(), today.isoformat()

    if period == "year_previous":
        previous_year = today.year - 1
        return date(previous_year, 1, 1).isoformat(), date(previous_year, 12, 31).isoformat()

    if period == "custom":
        if not start_date or not end_date:
            raise ValueError("Para --period custom, informe --start-date e --end-date.")
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start > end:
            raise ValueError("Data inicial maior que data final.")
        return start.isoformat(), end.isoformat()

    raise ValueError(f"Periodo invalido: {period}")


def _resolve_omie_credentials_override(config: AppConfig, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None

    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (config.credentials_dir / candidate).resolve()


def _with_overridden_omie_platform(config: AppConfig, omie_credentials_path: Path) -> AppConfig:
    omie_platform = build_omie_platform_config(
        omie_credentials_path,
        key="omie_2026",
        label="OMIE 2026",
    )
    if omie_platform is None:
        raise ValueError(
            "Nao foi possivel carregar Omie com arquivo alternativo: "
            f"{omie_credentials_path}"
        )

    platforms = [
        platform
        for platform in config.platforms
        if platform.key not in {"omie", "omie_2026"}
    ]
    platforms.append(omie_platform)

    return AppConfig(
        database_path=config.database_path,
        credentials_dir=config.credentials_dir,
        google_sheets=config.google_sheets,
        yampi=config.yampi,
        meta_ads=config.meta_ads,
        google_ads=config.google_ads,
        platforms=platforms,
    )


def _resolve_log_dir(raw_log_dir: str) -> Path:
    candidate = Path(raw_log_dir)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


def _build_logger(platform: str, log_dir: Path) -> tuple[logging.Logger, Path, str]:
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = log_dir / f"{platform}_{date.today().isoformat()}.log"

    logger = logging.getLogger(f"cfo_sync.automation.{platform}.{run_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

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
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(run_filter)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(run_filter)

    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger, log_path, run_id


def _resolve_sheet_target(resource: ResourceConfig, client: str) -> tuple[str, str, str] | None:
    target_tab = GoogleSheetsExporter._resolve_client_tab(resource=resource, client=client)
    if target_tab is None:
        return None

    spreadsheet_id = target_tab.spreadsheet_id or resource.spreadsheet_id
    tab_name = str(target_tab.tab_name or "")
    gid = str(target_tab.gid)
    return spreadsheet_id, gid, tab_name


def _is_not_found_error(error: Exception) -> bool:
    text = str(error).casefold()
    tokens = (
        "nao encontrado",
        "não encontrado",
        "not found",
        "gid",
        "aba",
        "cliente",
        "plataforma",
    )
    return any(token in text for token in tokens)


def _run(args: argparse.Namespace) -> int:
    ensure_runtime_layout()

    log_dir = _resolve_log_dir(args.log_dir)
    logger, log_path, run_id = _build_logger(platform=args.platform, log_dir=log_dir)
    logger.info(
        "RUN_START platform=%s host=%s pid=%s python=%s log=%s",
        args.platform,
        socket.gethostname(),
        os.getpid(),
        sys.version.split()[0],
        str(log_path),
    )

    run_start = perf_counter()

    config = load_app_config(app_config_path())
    omie_credentials_override = _resolve_omie_credentials_override(
        config=config,
        raw_path=args.omie_credentials_file,
    )
    if omie_credentials_override is not None:
        config = _with_overridden_omie_platform(config, omie_credentials_override)
        logger.info("OMIE_OVERRIDE credentials=%s", str(omie_credentials_override))

    period_start, period_end = _resolve_period(
        period=args.period,
        months=args.months,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    logger.info(
        "PERIODO platform=%s start=%s end=%s",
        args.platform,
        period_start,
        period_end,
    )

    platform = next((item for item in config.platforms if item.key == args.platform), None)
    if platform is None:
        message = f"Plataforma '{args.platform}' nao configurada no app_config."
        if args.allow_missing_platform:
            logger.warning("SKIP NAO_ENCONTRADO motivo=%s", message)
            logger.info("RUN_END status=ok run=%s", run_id)
            return 0
        raise ValueError(message)

    pipeline = SyncPipeline(
        config=config,
        omie_credentials_path=omie_credentials_override,
    )
    if args.platform not in pipeline.connectors:
        message = f"Conector '{args.platform}' nao disponivel nesta instalacao."
        if args.allow_missing_platform:
            logger.warning("SKIP NAO_ENCONTRADO motivo=%s", message)
            logger.info("RUN_END status=ok run=%s", run_id)
            return 0
        raise ValueError(message)

    logger.info(
        "PLATAFORMA key=%s label=%s clientes=%s recursos=%s",
        platform.key,
        platform.label,
        len(platform.clients),
        len(platform.resources),
    )

    total_exported = 0
    failed_tasks = 0
    total_tasks = 0

    for client in platform.clients:
        for resource in platform.resources:
            total_tasks += 1
            task_start = perf_counter()

            try:
                target = _resolve_sheet_target(resource=resource, client=client)
            except Exception as error:  # noqa: BLE001
                target = None
                logger.error(
                    "PLANILHA_ERRO platform=%s recurso=%s cliente=%s erro=%s",
                    args.platform,
                    resource.name,
                    client,
                    error,
                )

            if target is None:
                logger.warning(
                    "PLANILHA_NAO_ENCONTRADA platform=%s recurso=%s cliente=%s",
                    args.platform,
                    resource.name,
                    client,
                )
            else:
                spreadsheet_id, gid, tab_name = target
                logger.info(
                    "PLANILHA platform=%s recurso=%s cliente=%s spreadsheet_id=%s gid=%s tab=%s",
                    args.platform,
                    resource.name,
                    client,
                    spreadsheet_id,
                    gid,
                    tab_name,
                )

            logger.info(
                "TASK_START platform=%s recurso=%s cliente=%s",
                args.platform,
                resource.name,
                client,
            )

            try:
                exported = pipeline.export_to_sheets(
                    platform_key=args.platform,
                    client=client,
                    start_date=period_start,
                    end_date=period_end,
                    resource_names=[resource.name],
                )
            except Exception as error:  # noqa: BLE001
                elapsed = perf_counter() - task_start
                failed_tasks += 1
                error_kind = "NAO_ENCONTRADO" if _is_not_found_error(error) else "ERRO"
                logger.error(
                    "%s platform=%s recurso=%s cliente=%s tempo=%.2fs msg=%s",
                    error_kind,
                    args.platform,
                    resource.name,
                    client,
                    elapsed,
                    error,
                )
                logger.exception("TRACEBACK platform=%s recurso=%s cliente=%s", args.platform, resource.name, client)

                if elapsed >= args.slow_task_seconds:
                    logger.warning(
                        "LENTIDAO platform=%s recurso=%s cliente=%s tempo=%.2fs limite=%.2fs",
                        args.platform,
                        resource.name,
                        client,
                        elapsed,
                        args.slow_task_seconds,
                    )

                if args.fail_fast:
                    run_elapsed = perf_counter() - run_start
                    logger.error("FAIL_FAST acionado apos %.2fs", run_elapsed)
                    logger.info("RUN_END status=error run=%s", run_id)
                    return 1
                continue

            elapsed = perf_counter() - task_start
            total_exported += exported
            speed = exported / elapsed if elapsed > 0 else float(exported)
            logger.info(
                "TASK_OK platform=%s recurso=%s cliente=%s linhas=%s tempo=%.2fs linhas_por_seg=%.4f",
                args.platform,
                resource.name,
                client,
                exported,
                elapsed,
                speed,
            )

            if elapsed >= args.slow_task_seconds:
                logger.warning(
                    "LENTIDAO platform=%s recurso=%s cliente=%s tempo=%.2fs limite=%.2fs",
                    args.platform,
                    resource.name,
                    client,
                    elapsed,
                    args.slow_task_seconds,
                )

    run_elapsed = perf_counter() - run_start
    logger.info(
        "RESUMO platform=%s tarefas=%s falhas=%s linhas_exportadas=%s tempo_total=%.2fs",
        args.platform,
        total_tasks,
        failed_tasks,
        total_exported,
        run_elapsed,
    )

    if run_elapsed >= args.slow_run_seconds:
        logger.warning(
            "LENTIDAO_RUN platform=%s tempo_total=%.2fs limite=%.2fs",
            args.platform,
            run_elapsed,
            args.slow_run_seconds,
        )

    logger.info("RUN_END status=%s run=%s", "error" if failed_tasks else "ok", run_id)
    return 1 if failed_tasks else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa exportacao automatica por plataforma para uso no Task Scheduler.",
    )
    parser.add_argument(
        "--platform",
        required=True,
        help="Ex.: omie_2025, omie_2026, yampi, mercado_livre, meta_ads",
    )
    parser.add_argument("--period", required=True, choices=PERIOD_CHOICES)
    parser.add_argument(
        "--months",
        type=int,
        default=3,
        help="Quantidade de meses para --period rolling_months.",
    )
    parser.add_argument("--start-date", help="Formato YYYY-MM-DD (apenas para custom).")
    parser.add_argument("--end-date", help="Formato YYYY-MM-DD (apenas para custom).")
    parser.add_argument(
        "--omie-credentials-file",
        help=(
            "Arquivo alternativo para Omie 2026 (absoluto ou relativo a secrets/), "
            "ex.: omie_credentials_override.json"
        ),
    )
    parser.add_argument(
        "--allow-missing-platform",
        action="store_true",
        help="Nao falha se plataforma/conector nao estiver disponivel.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Interrompe na primeira falha de cliente/recurso.",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/automation",
        help="Diretorio de logs (padrao: logs/automation).",
    )
    parser.add_argument(
        "--slow-task-seconds",
        type=float,
        default=120.0,
        help="Limite de lentidao por tarefa cliente/recurso (segundos).",
    )
    parser.add_argument(
        "--slow-run-seconds",
        type=float,
        default=1800.0,
        help="Limite de lentidao da execucao completa (segundos).",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return _run(args)
    except Exception as error:  # noqa: BLE001
        print(f"FALHA FATAL: {error}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
