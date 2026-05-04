from __future__ import annotations

import calendar
import json
import os
import queue
import subprocess
import sys
import threading
import ctypes
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

PROJECT_DIR = Path(__file__).resolve().parent
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cfo_sync.core.models import (
    AppConfig,
    GoogleAdsConfig,
    GoogleSheetsConfig,
    MetaAdsConfig,
    PlatformConfig,
    ResourceConfig,
    TikTokAdsConfig,
    TikTokShopConfig,
    YampiConfig,
)
from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.pipeline import SyncPipeline
from cfo_sync.core.remote_api import RemoteApiError, RemoteCFOClient
from cfo_sync.core.runtime_paths import (
    available_sound_dirs,
    app_config_path,
    custom_sounds_dir,
    data_dir,
    desktop_settings_path,
    ensure_runtime_layout,
    secrets_dir,
    update_config_path,
)
from cfo_sync.core.updater import check_for_updates, download_and_launch_update, get_releases_page_url
from cfo_sync.platforms.mercado_livre.transaction_details import (
    DEFAULT_SHEET_ID,
    DEFAULT_SPREADSHEET_ID,
    sync_transaction_detail_map,
)
from cfo_sync.platforms.ui_registry import build_platform_ui_registry
from cfo_sync.platforms.yampi.credentials import YampiCredentialsStore
from cfo_sync.version import __version__


ALL_SUB_CLIENTS = "Todos"
NO_NOTIFICATION_SOUND = "Sem som"
SERVER_URL_KEY = "server_url"
SERVER_TOKEN_KEY = "server_token"
DESKTOP_SETTINGS_PATH = desktop_settings_path()
SOUNDS_DIR = custom_sounds_dir()
UPDATE_APP_DEFAULT_LABEL = "Atualizar app"

COLOR_BG = "#0B0D10"
COLOR_SURFACE = "#14181D"
COLOR_SURFACE_ALT = "#1B2026"
COLOR_BORDER = "#2A313A"
COLOR_TEXT = "#F5F7FA"
COLOR_MUTED = "#AAB4C0"
COLOR_ACCENT = "#E7EBF0"
COLOR_ACCENT_HOVER = "#D8E0EA"
COLOR_ACCENT_ACTIVE = "#C9D3DE"
COLOR_BUTTON_ALT = "#28303A"
COLOR_BUTTON_ALT_HOVER = "#313A46"
COLOR_BUTTON_ALT_ACTIVE = "#394452"
COLOR_BUTTON_DISABLED = "#171B20"
COLOR_DANGER = "#FF6868"
COLOR_HEADER = "#10151B"
COLOR_HEADER_BORDER = "#2D353F"
COLOR_SCROLLBAR_THUMB = "#333C47"
COLOR_SCROLLBAR_THUMB_HOVER = "#44505E"

PT_BR_MONTH_NAMES = (
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
PT_BR_WEEKDAY_ABBR = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")

@dataclass(frozen=True)
class PlatformChoice:
    label: str
    platform_key: str
    resource_name: str


CLIENT_REGISTRATION_SCHEMAS: dict[str, list[dict[str, object]]] = {
    "yampi": [
        {
            "name": "alias",
            "label": "Alias",
            "required": True,
            "help": "Nome do subcliente/loja que aparecera na selecao de Pedidos.",
        },
        {
            "name": "user_token",
            "label": "User token",
            "required": True,
            "secret": True,
            "help": "Token da API da conta Yampi.",
        },
        {
            "name": "user_secret_key",
            "label": "User secret key",
            "required": True,
            "secret": True,
            "help": "Secret key da API da conta Yampi.",
        },
        {
            "name": "sku_gid",
            "label": "GID da aba SKU (opcional)",
            "required": False,
            "resource_gid": "sku",
            "help": "sheetId da aba SKU para este cliente (nao e o ID da planilha).",
        },
    ],
    "mercado_livre": [
        {"name": "client_id", "label": "Client ID", "required": True, "help": "ID do app Mercado Livre."},
        {
            "name": "client_secret",
            "label": "Client secret",
            "required": True,
            "secret": True,
            "help": "Secret do app Mercado Livre.",
        },
        {
            "name": "access_token",
            "label": "Access token",
            "required": True,
            "secret": True,
            "help": "Token de acesso atual.",
        },
        {
            "name": "refresh_token",
            "label": "Refresh token",
            "required": True,
            "secret": True,
            "help": "Token de renovacao.",
        },
        {
            "name": "account_alias",
            "label": "Alias/Filial",
            "required": False,
            "help": "Alias da conta dentro do cliente selecionado.",
        },
        {"name": "user_id", "label": "User ID (opcional)", "required": False, "help": "ID do vendedor."},
    ],
    "meta_ads": [
        {
            "name": "business_manager_name",
            "label": "Business manager",
            "required": True,
            "help": "Nome do BM da conta.",
        },
        {
            "name": "ad_account_name",
            "label": "Conta de anuncio",
            "required": True,
            "help": "Nome da conta de anuncio.",
        },
        {"name": "account_id", "label": "Account ID", "required": True, "help": "ID numerico da conta."},
        {
            "name": "cost_center",
            "label": "Centro de custo (opcional)",
            "required": False,
            "help": "Centro de custo interno.",
        },
    ],
    "google_ads": [
        {
            "name": "account_name",
            "label": "Nome da conta",
            "required": True,
            "help": "Nome da conta Google Ads.",
        },
        {
            "name": "customer_id",
            "label": "Customer ID",
            "required": True,
            "help": "ID da conta (aceita com ou sem pontuacao).",
        },
        {
            "name": "cost_center",
            "label": "Centro de custo (opcional)",
            "required": False,
            "help": "Centro de custo interno.",
        },
        {"name": "manager_account_name", "label": "MCC (opcional)", "required": False, "help": "Nome do MCC."},
    ],
    "tiktok_ads": [
        {
            "name": "account_name",
            "label": "Nome da conta",
            "required": True,
            "help": "Nome da conta TikTok Ads.",
        },
        {"name": "advertiser_id", "label": "Advertiser ID", "required": True, "help": "ID numerico da conta."},
        {
            "name": "cost_center",
            "label": "Centro de custo (opcional)",
            "required": False,
            "help": "Centro de custo interno.",
        },
        {
            "name": "business_center_name",
            "label": "Business center (opcional)",
            "required": False,
            "help": "Nome do business center.",
        },
        {
            "name": "access_token",
            "label": "Access token (opcional)",
            "required": False,
            "secret": True,
            "help": "Token especifico da conta (opcional).",
        },
    ],
    "tiktok_shop": [
        {
            "name": "account_name",
            "label": "Nome da conta",
            "required": True,
            "help": "Nome da conta/loja TikTok Shop.",
        },
        {
            "name": "shop_cipher",
            "label": "Shop cipher",
            "required": True,
            "help": "Identificador cifrado da loja (shop_cipher).",
        },
        {
            "name": "shop_id",
            "label": "Shop ID (opcional)",
            "required": False,
            "help": "ID numerico da loja, quando disponivel.",
        },
        {
            "name": "access_token",
            "label": "Access token (opcional)",
            "required": False,
            "secret": True,
            "help": "Token especifico da loja (opcional).",
        },
    ],
    "__omie__": [
        {
            "name": "alias",
            "label": "Alias",
            "required": True,
            "help": "Nome da filial/alias para o cliente (tambem usado como app_name).",
        },
        {"name": "app_key", "label": "App key", "required": True, "secret": True, "help": "App key da Omie."},
        {
            "name": "app_secret",
            "label": "App secret",
            "required": True,
            "secret": True,
            "help": "App secret da Omie.",
        },
        {
            "name": "include_accounts_payable",
            "label": "Incluir contas a pagar",
            "required": True,
            "kind": "bool",
            "default": "Sim",
            "help": "Ativa coleta de contas a pagar para este alias.",
        },
        {
            "name": "include_accounts_receivable",
            "label": "Incluir contas a receber",
            "required": True,
            "kind": "bool",
            "default": "Sim",
            "help": "Ativa coleta de contas a receber para este alias.",
        },
    ],
}

CLIENT_REGISTRATION_MODE_OPTIONS: list[tuple[str, str]] = [
    ("Nova filial/alias (cliente existente)", "existing_client"),
    ("Novo cliente (cadastro completo)", "new_client"),
]

GENERATOR_SCHEMAS: dict[str, list[dict[str, object]]] = {
    "mercado_livre": [
        {
            "name": "account_alias",
            "label": "Alias/Filial",
            "required": True,
            "help": "Nome da filial/alias que identifica a conta autorizada.",
        }
    ]
}


def _empty_app_config() -> AppConfig:
    return AppConfig(
        database_path=data_dir() / "cfo_sync.db",
        credentials_dir=secrets_dir(),
        google_sheets=GoogleSheetsConfig(credentials_file="google_service_account.json"),
        yampi=YampiConfig(credentials_file="yampi_credentials.json"),
        meta_ads=MetaAdsConfig(credentials_file="meta_ads_credentials.json"),
        google_ads=GoogleAdsConfig(credentials_file="google_ads_credentials.json"),
        tiktok_ads=TikTokAdsConfig(credentials_file="tiktok_ads_credentials.json"),
        tiktok_shop=TikTokShopConfig(credentials_file="tiktok_shop_credentials.json"),
        platforms=[],
    )


class CFODesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"CFO Sync v{__version__}")
        self.root.geometry("1240x760")
        self.root.minsize(1120, 680)
        self.root.resizable(True, True)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.busy = False

        ensure_runtime_layout()
        self.config = _empty_app_config()
        self.pipeline: SyncPipeline | None = None
        self.platform_ui_registry = build_platform_ui_registry(self.config)
        self.platform_choices: list[PlatformChoice] = []
        self.choice_by_label: dict[str, PlatformChoice] = {}
        self.estoque_platform_choices: list[PlatformChoice] = []
        self.estoque_choice_by_label: dict[str, PlatformChoice] = {}
        self.remote_client: RemoteCFOClient | None = None
        self.remote_catalog_sub_clients: dict[tuple[str, str], list[str]] = {}
        self.yampi_estoque_credentials_store: YampiCredentialsStore | None = None

        self.platform_var = tk.StringVar()
        self.client_var = tk.StringVar()
        self.estoque_platform_var = tk.StringVar()
        self.estoque_client_var = tk.StringVar()
        self.sub_client_options: list[str] = []
        self.estoque_sub_client_options: list[str] = []
        self.sub_client_summary_var = tk.StringVar(value=ALL_SUB_CLIENTS)
        self.estoque_sub_client_summary_var = tk.StringVar(value=ALL_SUB_CLIENTS)
        self.start_date_var = tk.StringVar()
        self.end_date_var = tk.StringVar()
        self.update_mercado_livre_categories_var = tk.BooleanVar(value=False)
        self.estoque_start_date_var = tk.StringVar()
        self.estoque_end_date_var = tk.StringVar()
        self.sku_order_number_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto")
        self.update_notice_var = tk.StringVar(value="")
        self.sku_preview_rows: list[dict[str, object]] = []
        self.notification_sound_var = tk.StringVar(value=NO_NOTIFICATION_SOUND)
        self.notification_sound_options: list[str] = [NO_NOTIFICATION_SOUND]
        self.server_url_var = tk.StringVar(value="")
        self.server_token_var = tk.StringVar(value="")
        self.server_status_var = tk.StringVar(value="Servidor desconectado")
        self.server_secret_path_var = tk.StringVar(value="")
        self.server_secret_modified_var = tk.StringVar(value="-")
        self.server_secret_size_var = tk.StringVar(value="-")
        self.server_secret_files: list[dict[str, object]] = []
        self.server_secret_loaded_path = ""
        self.client_registration_mode_var = tk.StringVar()
        self.client_registration_platform_var = tk.StringVar()
        self.client_registration_client_var = tk.StringVar()
        self.client_registration_client_name_var = tk.StringVar()
        self.client_registration_gid_var = tk.StringVar()
        self.client_registration_mode_map: dict[str, str] = {}
        self.client_registration_platform_map: dict[str, str] = {}
        self.client_registration_clients: list[str] = []
        self.client_registration_field_specs: list[dict[str, object]] = []
        self.client_registration_field_vars: dict[str, tk.Variable] = {}
        self.client_registration_dynamic_entries: list[ttk.Entry] = []
        self.client_registration_dynamic_combos: list[ttk.Combobox] = []
        self.client_registration_fields_canvas: tk.Canvas | None = None
        self.client_registration_fields_window_id: int | None = None
        self.btn_use_local_secrets: ttk.Button | None = None
        self.update_notice_label: ttk.Label | None = None
        self.generator_mode_var = tk.StringVar()
        self.generator_platform_var = tk.StringVar()
        self.generator_client_var = tk.StringVar()
        self.generator_client_name_var = tk.StringVar()
        self.generator_gid_var = tk.StringVar()
        self.generator_link_var = tk.StringVar()
        self.generator_mode_map: dict[str, str] = {}
        self.generator_platform_map: dict[str, str] = {}
        self.generator_clients: list[str] = []
        self.generator_field_specs: list[dict[str, object]] = []
        self.generator_field_vars: dict[str, tk.Variable] = {}
        self.generator_dynamic_entries: list[ttk.Entry] = []
        self.generator_dynamic_combos: list[ttk.Combobox] = []
        self._date_picker_window: tk.Toplevel | None = None
        self._date_picker_month_label_var = tk.StringVar()
        self._date_picker_hint_var = tk.StringVar()
        self._date_picker_grid_frame: ttk.Frame | None = None
        self._date_picker_month = date.today().replace(day=1)
        self._date_picker_selection_start: date | None = None
        self._date_picker_selection_end: date | None = None
        self._date_picker_target = "pedidos"

        self._bootstrap_runtime_mode()
        self._refresh_estoque_credentials_store()

        self.style = ttk.Style(self.root)
        self._apply_theme()
        self._build_ui()
        self.root.after(50, self._apply_native_titlebar_color)
        self._bind_events()
        self._set_default_dates_current_month()
        self._set_default_estoque_dates_current_month()
        self._load_initial_values()
        self.root.after(1200, self._check_updates_notice_async)
        self._poll_logs()

    def _bootstrap_runtime_mode(self) -> None:
        saved_url = self._saved_server_url()
        saved_token = self._saved_server_token()
        self.server_url_var.set(saved_url)
        self.server_token_var.set(saved_token)
        if not saved_url or not saved_token:
            self.status_var.set("Conecte ao servidor na aba Configuracoes")
            return
        try:
            client = RemoteCFOClient(saved_url, saved_token)
            catalog = client.fetch_catalog()
            self._activate_remote_catalog(client, catalog)
            self.status_var.set("Conectado ao servidor")
        except Exception as error:  # noqa: BLE001
            self.server_status_var.set("Falha ao conectar no servidor")
            self.status_var.set("Conecte ao servidor na aba Configuracoes")
            self.log(f"Aviso: conexao inicial com servidor falhou ({error}).")

    def _activate_remote_catalog(self, client: RemoteCFOClient, catalog: dict[str, object]) -> None:
        config, sub_clients_map = self._build_app_config_from_catalog(catalog)
        self.remote_client = client
        self.remote_catalog_sub_clients = sub_clients_map
        self.config = config
        self.pipeline = None
        self.platform_ui_registry = build_platform_ui_registry(self.config)
        self.platform_choices = self._build_platform_choices()
        self.choice_by_label = {choice.label: choice for choice in self.platform_choices}
        self.estoque_platform_choices = self._build_estoque_platform_choices()
        self.estoque_choice_by_label = {choice.label: choice for choice in self.estoque_platform_choices}
        self._refresh_estoque_credentials_store()
        self.server_status_var.set(f"Conectado: {client.base_url}")

    def _refresh_estoque_credentials_store(self) -> None:
        self.yampi_estoque_credentials_store = None
        credentials_path = self.config.credentials_dir / "yampi_estoque.json"
        if not credentials_path.exists():
            return
        try:
            self.yampi_estoque_credentials_store = YampiCredentialsStore.from_file(credentials_path)
        except Exception as error:  # noqa: BLE001
            self.log(f"Aviso: nao foi possivel carregar yampi_estoque.json ({error}).")

    def _build_app_config_from_catalog(
        self,
        catalog: dict[str, object],
    ) -> tuple[AppConfig, dict[tuple[str, str], list[str]]]:
        raw_platforms = catalog.get("platforms")
        if not isinstance(raw_platforms, list):
            raise ValueError("Catalogo remoto invalido: campo 'platforms' ausente.")

        platforms: list[PlatformConfig] = []
        sub_clients_map: dict[tuple[str, str], list[str]] = {}

        for raw_platform in raw_platforms:
            if not isinstance(raw_platform, dict):
                continue
            platform_key = str(raw_platform.get("key") or "").strip()
            platform_label = str(raw_platform.get("label") or platform_key).strip()
            if not platform_key:
                continue

            resources_data = raw_platform.get("resources")
            if not isinstance(resources_data, list):
                continue
            resources: list[ResourceConfig] = []
            for raw_resource in resources_data:
                if not isinstance(raw_resource, dict):
                    continue
                resource_name = str(raw_resource.get("name") or "").strip()
                if not resource_name:
                    continue
                endpoint = str(raw_resource.get("endpoint") or "").strip()
                field_map_raw = raw_resource.get("field_map")
                field_map: dict[str, str] = {}
                if isinstance(field_map_raw, dict):
                    field_map = {
                        str(key): str(value)
                        for key, value in field_map_raw.items()
                    }
                resources.append(
                    ResourceConfig(
                        name=resource_name,
                        endpoint=endpoint,
                        spreadsheet_url="",
                        spreadsheet_id="",
                        field_map=field_map,
                        client_tabs={},
                    )
                )

            clients_data = raw_platform.get("clients")
            clients: list[str] = []
            if isinstance(clients_data, list):
                for raw_client in clients_data:
                    if not isinstance(raw_client, dict):
                        continue
                    client_name = str(raw_client.get("name") or "").strip()
                    if not client_name:
                        continue
                    clients.append(client_name)
                    raw_sub_clients = raw_client.get("sub_clients")
                    if isinstance(raw_sub_clients, list):
                        sub_clients = [str(item).strip() for item in raw_sub_clients if str(item).strip()]
                        sub_clients_map[(platform_key, client_name)] = sub_clients

            platforms.append(
                PlatformConfig(
                    key=platform_key,
                    label=platform_label,
                    clients=clients,
                    resources=resources,
                )
            )

        return (
            AppConfig(
                database_path=data_dir() / "cfo_sync.db",
                credentials_dir=secrets_dir(),
                google_sheets=GoogleSheetsConfig(credentials_file="google_service_account.json"),
                yampi=YampiConfig(credentials_file="yampi_credentials.json"),
                meta_ads=MetaAdsConfig(credentials_file="meta_ads_credentials.json"),
                google_ads=GoogleAdsConfig(credentials_file="google_ads_credentials.json"),
                tiktok_ads=TikTokAdsConfig(credentials_file="tiktok_ads_credentials.json"),
                tiktok_shop=TikTokShopConfig(credentials_file="tiktok_shop_credentials.json"),
                platforms=platforms,
            ),
            sub_clients_map,
        )

    def _saved_server_url(self) -> str:
        settings = self._load_desktop_settings()
        value = settings.get(SERVER_URL_KEY)
        if not isinstance(value, str):
            return ""
        return value.strip()

    def _saved_server_token(self) -> str:
        settings = self._load_desktop_settings()
        value = settings.get(SERVER_TOKEN_KEY)
        if not isinstance(value, str):
            return ""
        return value.strip()

    def _persist_server_connection(self, server_url: str, server_token: str) -> None:
        settings = self._load_desktop_settings()
        settings[SERVER_URL_KEY] = server_url.strip()
        settings[SERVER_TOKEN_KEY] = server_token.strip()
        self._save_desktop_settings(settings)

    def _clear_server_connection(self) -> None:
        settings = self._load_desktop_settings()
        settings.pop(SERVER_URL_KEY, None)
        settings.pop(SERVER_TOKEN_KEY, None)
        self._save_desktop_settings(settings)

    def _apply_theme(self) -> None:
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(bg=COLOR_BG)

        self.style.configure("Dark.TFrame", background=COLOR_BG)
        self.style.configure("Card.TFrame", background=COLOR_SURFACE)
        self.style.configure(
            "Dark.TNotebook",
            background=COLOR_BG,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
            relief="flat",
            focuscolor=COLOR_BG,
            lightcolor=COLOR_BG,
            darkcolor=COLOR_BG,
            bordercolor=COLOR_BG,
        )
        self.style.configure(
            "Dark.TNotebook.Tab",
            background=COLOR_SURFACE_ALT,
            foreground=COLOR_MUTED,
            padding=(16, 9),
            font=("Segoe UI Semibold", 9),
            borderwidth=0,
            relief="flat",
            focuscolor=COLOR_SURFACE_ALT,
            lightcolor=COLOR_SURFACE_ALT,
            darkcolor=COLOR_SURFACE_ALT,
            bordercolor=COLOR_SURFACE_ALT,
        )
        self.style.map(
            "Dark.TNotebook.Tab",
            background=[("selected", COLOR_SURFACE), ("active", COLOR_BUTTON_ALT_HOVER)],
            foreground=[("selected", COLOR_TEXT), ("!selected", COLOR_MUTED)],
            padding=[("selected", (16, 9)), ("!selected", (16, 9))],
            focuscolor=[("selected", COLOR_SURFACE), ("!selected", COLOR_SURFACE_ALT)],
            lightcolor=[("selected", COLOR_SURFACE), ("!selected", COLOR_SURFACE_ALT)],
            darkcolor=[("selected", COLOR_SURFACE), ("!selected", COLOR_SURFACE_ALT)],
            bordercolor=[("selected", COLOR_SURFACE), ("!selected", COLOR_SURFACE_ALT)],
            expand=[("selected", (0, 0, 0, 0)), ("!selected", (0, 0, 0, 0))],
        )

        self.style.configure(
            "Title.TLabel",
            background=COLOR_BG,
            foreground=COLOR_TEXT,
            font=("Segoe UI Semibold", 22),
        )
        self.style.configure(
            "Subtitle.TLabel",
            background=COLOR_BG,
            foreground=COLOR_MUTED,
            font=("Segoe UI", 10),
        )
        self.style.configure(
            "CardTitle.TLabel",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT,
            font=("Segoe UI Semibold", 11),
        )
        self.style.configure(
            "Field.TLabel",
            background=COLOR_SURFACE,
            foreground=COLOR_MUTED,
            font=("Segoe UI", 10),
        )
        self.style.configure(
            "Status.TLabel",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT,
            font=("Segoe UI Semibold", 10),
        )
        self.style.configure(
            "HeaderStatusTitle.TLabel",
            background=COLOR_BG,
            foreground=COLOR_MUTED,
            font=("Segoe UI", 9),
        )
        self.style.configure(
            "HeaderStatusValue.TLabel",
            background=COLOR_BG,
            foreground=COLOR_TEXT,
            font=("Segoe UI Semibold", 10),
        )
        self.style.configure(
            "UpdateNotice.TLabel",
            background=COLOR_SURFACE,
            foreground="#F7C66A",
            font=("Segoe UI Semibold", 9),
        )
        self.style.configure(
            "FieldValue.TLabel",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT,
            font=("Segoe UI Semibold", 9),
        )
        self.style.configure(
            "Modern.Vertical.TScrollbar",
            background=COLOR_SCROLLBAR_THUMB,
            troughcolor=COLOR_SURFACE_ALT,
            bordercolor=COLOR_SURFACE_ALT,
            lightcolor=COLOR_SCROLLBAR_THUMB,
            darkcolor=COLOR_SCROLLBAR_THUMB,
            arrowcolor=COLOR_TEXT,
            gripcount=0,
            arrowsize=11,
            relief="flat",
            width=12,
        )
        self.style.map(
            "Modern.Vertical.TScrollbar",
            background=[("active", COLOR_SCROLLBAR_THUMB_HOVER), ("pressed", COLOR_SCROLLBAR_THUMB_HOVER)],
            lightcolor=[("active", COLOR_SCROLLBAR_THUMB_HOVER), ("pressed", COLOR_SCROLLBAR_THUMB_HOVER)],
            darkcolor=[("active", COLOR_SCROLLBAR_THUMB_HOVER), ("pressed", COLOR_SCROLLBAR_THUMB_HOVER)],
            arrowcolor=[("disabled", COLOR_MUTED), ("!disabled", COLOR_TEXT)],
        )
        self.style.configure(
            "Dark.Treeview",
            background=COLOR_SURFACE_ALT,
            foreground=COLOR_TEXT,
            fieldbackground=COLOR_SURFACE_ALT,
            bordercolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
            darkcolor=COLOR_BORDER,
            rowheight=28,
            relief="flat",
        )
        self.style.map(
            "Dark.Treeview",
            background=[("selected", COLOR_BUTTON_ALT_HOVER)],
            foreground=[("selected", COLOR_TEXT)],
        )
        self.style.configure(
            "Dark.Treeview.Heading",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
            darkcolor=COLOR_BORDER,
            font=("Segoe UI Semibold", 9),
            relief="flat",
        )
        self.style.map(
            "Dark.Treeview.Heading",
            background=[("active", COLOR_BUTTON_ALT_HOVER)],
            foreground=[("active", COLOR_TEXT)],
        )

        self.style.configure(
            "Dark.TEntry",
            fieldbackground=COLOR_SURFACE_ALT,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
            darkcolor=COLOR_BORDER,
            padding=(8, 7),
        )
        self.style.map(
            "Dark.TEntry",
            bordercolor=[("focus", COLOR_ACCENT), ("!focus", COLOR_BORDER)],
            lightcolor=[("focus", COLOR_ACCENT), ("!focus", COLOR_BORDER)],
            darkcolor=[("focus", COLOR_ACCENT), ("!focus", COLOR_BORDER)],
        )

        self.style.configure(
            "Dark.TCombobox",
            fieldbackground=COLOR_SURFACE_ALT,
            background=COLOR_SURFACE_ALT,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
            darkcolor=COLOR_BORDER,
            arrowcolor=COLOR_TEXT,
            padding=(8, 7),
        )
        self.style.map(
            "Dark.TCombobox",
            fieldbackground=[
                ("readonly", COLOR_SURFACE_ALT),
                ("disabled", COLOR_SURFACE_ALT),
            ],
            background=[("readonly", COLOR_SURFACE_ALT)],
            foreground=[("readonly", COLOR_TEXT), ("disabled", COLOR_MUTED)],
            bordercolor=[("focus", COLOR_ACCENT), ("!focus", COLOR_BORDER)],
            lightcolor=[("focus", COLOR_ACCENT), ("!focus", COLOR_BORDER)],
            darkcolor=[("focus", COLOR_ACCENT), ("!focus", COLOR_BORDER)],
            arrowcolor=[("disabled", COLOR_MUTED), ("!disabled", COLOR_TEXT)],
            selectbackground=[("readonly", COLOR_SURFACE_ALT)],
            selectforeground=[("readonly", COLOR_TEXT)],
        )

        self.style.configure(
            "Secondary.TButton",
            background=COLOR_BUTTON_ALT,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BUTTON_ALT,
            lightcolor=COLOR_BUTTON_ALT,
            darkcolor=COLOR_BUTTON_ALT,
            padding=(14, 9),
            font=("Segoe UI Semibold", 9),
        )
        self.style.map(
            "Secondary.TButton",
            background=[
                ("active", COLOR_BUTTON_ALT_HOVER),
                ("pressed", COLOR_BUTTON_ALT_ACTIVE),
                ("disabled", COLOR_SURFACE_ALT),
            ],
            bordercolor=[
                ("active", COLOR_BUTTON_ALT_HOVER),
                ("pressed", COLOR_BUTTON_ALT_ACTIVE),
                ("disabled", COLOR_SURFACE_ALT),
            ],
            foreground=[("disabled", COLOR_MUTED)],
        )
        self.style.configure(
            "Sku.TButton",
            background=COLOR_BUTTON_ALT,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BUTTON_ALT,
            lightcolor=COLOR_BUTTON_ALT,
            darkcolor=COLOR_BUTTON_ALT,
            padding=(14, 9),
            font=("Segoe UI Semibold", 9),
        )
        self.style.map(
            "Sku.TButton",
            background=[
                ("active", COLOR_BUTTON_ALT_HOVER),
                ("pressed", COLOR_BUTTON_ALT_ACTIVE),
                ("disabled", COLOR_BUTTON_DISABLED),
            ],
            bordercolor=[
                ("active", COLOR_BUTTON_ALT_HOVER),
                ("pressed", COLOR_BUTTON_ALT_ACTIVE),
                ("disabled", COLOR_BUTTON_DISABLED),
            ],
            foreground=[("disabled", "#5F6975"), ("!disabled", COLOR_TEXT)],
            lightcolor=[("disabled", COLOR_BUTTON_DISABLED)],
            darkcolor=[("disabled", COLOR_BUTTON_DISABLED)],
        )

        self.style.configure(
            "Primary.TButton",
            background=COLOR_ACCENT,
            foreground=COLOR_BG,
            bordercolor=COLOR_ACCENT,
            lightcolor=COLOR_ACCENT,
            darkcolor=COLOR_ACCENT,
            padding=(16, 9),
            font=("Segoe UI Semibold", 9),
        )
        self.style.map(
            "Primary.TButton",
            background=[
                ("active", COLOR_ACCENT_HOVER),
                ("pressed", COLOR_ACCENT_ACTIVE),
                ("disabled", COLOR_SURFACE_ALT),
            ],
            bordercolor=[
                ("active", COLOR_ACCENT_HOVER),
                ("pressed", COLOR_ACCENT_ACTIVE),
                ("disabled", COLOR_SURFACE_ALT),
            ],
            foreground=[("disabled", COLOR_MUTED)],
        )

        self.style.configure(
            "Dark.TCheckbutton",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT,
            focuscolor=COLOR_SURFACE,
            padding=(0, 2),
            font=("Segoe UI", 9),
        )
        self.style.map(
            "Dark.TCheckbutton",
            background=[("active", COLOR_SURFACE), ("disabled", COLOR_SURFACE)],
            foreground=[("disabled", COLOR_MUTED), ("!disabled", COLOR_TEXT)],
            indicatorcolor=[
                ("selected", COLOR_ACCENT),
                ("!selected", COLOR_SURFACE_ALT),
                ("disabled", COLOR_BUTTON_DISABLED),
            ],
            bordercolor=[("focus", COLOR_ACCENT), ("!focus", COLOR_BORDER)],
        )

    def _build_platform_choices(self) -> list[PlatformChoice]:
        choices: list[PlatformChoice] = []
        hidden_resources = {"sku", "estoque"}
        for platform in self.config.platforms:
            if not self._clients_for_platform(platform.key):
                continue
            platform_behavior = self.platform_ui_registry.get(platform.key)
            for resource in platform.resources:
                resource_name = resource.name.strip().lower()
                if resource_name in hidden_resources:
                    # SKU e Estoque possuem abas dedicadas.
                    continue
                if platform_behavior and platform_behavior.uses_dedicated_resource_tab(resource.name):
                    # Recursos dedicados usam aba propria e exportacao especifica.
                    continue
                label = self._platform_resource_label(platform.key, platform.label, resource.name)
                choices.append(
                    PlatformChoice(label=label, platform_key=platform.key, resource_name=resource.name)
                )
        return choices

    def _build_estoque_platform_choices(self) -> list[PlatformChoice]:
        choices: list[PlatformChoice] = []
        for platform in self.config.platforms:
            for resource in platform.resources:
                if resource.name.strip().lower() != "estoque":
                    continue
                label = self._platform_resource_label(platform.key, platform.label, resource.name)
                choices.append(
                    PlatformChoice(label=label, platform_key=platform.key, resource_name=resource.name)
                )
        return choices

    def _clients_for_platform(self, platform_key: str) -> list[str]:
        platform = next((item for item in self.config.platforms if item.key == platform_key), None)
        configured_clients = list(platform.clients) if platform is not None else []

        behavior = self.platform_ui_registry.get(platform_key)
        if behavior is None:
            return configured_clients
        return behavior.companies(configured_clients)

    @staticmethod
    def _platform_resource_label(platform_key: str, platform_label: str, resource_name: str) -> str:
        key = platform_key.lower()
        resource = resource_name.lower()
        if key.startswith("omie"):
            return platform_label
        if key == "yampi" and resource == "financeiro":
            return "Yampi Financeiro"
        if key == "yampi" and resource == "estoque":
            return "Yampi Estoque"
        if key == "mercado_livre":
            return "Mercado Livre"
        if key == "tiktok_ads":
            return "TikTok ADS"
        if key == "tiktok_shop":
            return "TikTok Shop"
        if key == "meta_ads":
            return "Meta ADS"
        if key == "google_ads":
            return "Google ADS"
        return f"{platform_label} - {resource_name.title()}"

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, style="Dark.TFrame", padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(frame, style="Dark.TFrame")
        header.pack(fill=tk.X, pady=(0, 12))
        header.columnconfigure(0, weight=1)

        header_left = ttk.Frame(header, style="Dark.TFrame")
        header_left.grid(row=0, column=0, sticky=tk.W)

        header_right = ttk.Frame(header, style="Dark.TFrame")
        header_right.grid(row=0, column=1, sticky=tk.E)

        ttk.Label(header_left, text="Painel de Sincronização", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header_left,
            text=f"Versao {__version__} | Selecione plataforma, cliente e filial/alias para coletar e exportar.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        ttk.Label(header_right, text="Status", style="HeaderStatusTitle.TLabel").pack(anchor=tk.E)
        ttk.Label(header_right, textvariable=self.status_var, style="HeaderStatusValue.TLabel").pack(
            anchor=tk.E,
            pady=(2, 0),
        )

        body = ttk.Frame(frame, style="Dark.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        # Prioriza mais largura para a area de configuracao/preview (SKU).
        body.columnconfigure(0, weight=7)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(body, style="Dark.TFrame")
        left_panel.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 10))

        right_panel = ttk.Frame(body, style="Dark.TFrame")
        right_panel.grid(row=0, column=1, sticky=tk.NSEW)
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)

        self.tabs = ttk.Notebook(left_panel, style="Dark.TNotebook", takefocus=False)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        config_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=16)
        self.pedidos_tab = config_tab
        self.estoque_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=16)
        self.clients_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=16)
        self.generator_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=16)
        self.sku_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=16)
        self.settings_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=16)
        self.settings_tab.columnconfigure(1, weight=1)
        self.server_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=16)
        self.server_tab.columnconfigure(0, weight=1)
        self.server_tab.rowconfigure(0, weight=1)

        self.tabs.add(config_tab, text="Pedidos")
        self.tabs.add(self.estoque_tab, text="Estoque")
        self.tabs.add(self.clients_tab, text="Clientes")
        self.tabs.add(self.generator_tab, text="Gerador")
        self.tabs.add(self.sku_tab, text="SKU")
        self.tabs.add(self.settings_tab, text="Configurações")
        self.tabs.add(self.server_tab, text="Server")

        ttk.Label(config_tab, text="Pedidos", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 12)
        )

        compact_padx = (0, 8)
        compact_pady = 4
        field_width = 27

        ttk.Label(config_tab, text="Plataforma", style="Field.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.platform_combo = ttk.Combobox(
            config_tab,
            textvariable=self.platform_var,
            state="readonly",
            values=[choice.label for choice in self.platform_choices],
            style="Dark.TCombobox",
            width=field_width,
        )
        self.platform_combo.grid(row=1, column=1, sticky=tk.EW, pady=compact_pady)

        ttk.Label(config_tab, text="Cliente", style="Field.TLabel").grid(
            row=2, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.client_combo = ttk.Combobox(
            config_tab,
            textvariable=self.client_var,
            state="readonly",
            style="Dark.TCombobox",
            width=field_width,
        )
        self.client_combo.grid(row=2, column=1, sticky=tk.EW, pady=compact_pady)

        ttk.Label(config_tab, text="Filiais / Alias", style="Field.TLabel").grid(
            row=3, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        sub_client_panel = ttk.Frame(config_tab, style="Card.TFrame")
        sub_client_panel.grid(row=3, column=1, sticky=tk.NSEW, pady=compact_pady)
        sub_client_panel.columnconfigure(0, weight=1)
        sub_client_panel.rowconfigure(1, weight=1)

        ttk.Label(sub_client_panel, textvariable=self.sub_client_summary_var, style="FieldValue.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, compact_pady)
        )

        sub_client_actions = ttk.Frame(sub_client_panel, style="Card.TFrame")
        sub_client_actions.grid(row=0, column=1, sticky=tk.E, pady=(0, compact_pady))

        self.btn_select_all_sub_clients = ttk.Button(
            sub_client_actions,
            text="Todos",
            style="Secondary.TButton",
            command=self._select_all_sub_clients,
        )
        self.btn_select_all_sub_clients.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_clear_sub_clients = ttk.Button(
            sub_client_actions,
            text="Limpar",
            style="Secondary.TButton",
            command=self._clear_sub_clients,
        )
        self.btn_clear_sub_clients.pack(side=tk.LEFT)

        sub_client_list_frame = ttk.Frame(sub_client_panel, style="Card.TFrame")
        sub_client_list_frame.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW)
        sub_client_list_frame.columnconfigure(0, weight=1)
        sub_client_list_frame.rowconfigure(0, weight=1)

        self.sub_client_listbox = tk.Listbox(
            sub_client_list_frame,
            selectmode=tk.MULTIPLE,
            exportselection=False,
            height=9,
            bg=COLOR_SURFACE_ALT,
            fg=COLOR_TEXT,
            selectbackground=COLOR_BUTTON_ALT_HOVER,
            selectforeground=COLOR_TEXT,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_ACCENT,
            relief=tk.FLAT,
            borderwidth=0,
            activestyle="none",
            font=("Segoe UI", 10),
        )
        self.sub_client_listbox.grid(row=0, column=0, sticky=tk.EW)

        sub_client_scroll = ttk.Scrollbar(
            sub_client_list_frame,
            orient=tk.VERTICAL,
            style="Modern.Vertical.TScrollbar",
            command=self.sub_client_listbox.yview,
        )
        sub_client_scroll.grid(row=0, column=1, sticky=tk.NS, padx=(5, 0))
        self.sub_client_listbox.configure(yscrollcommand=sub_client_scroll.set)

        ttk.Label(config_tab, text="Data inicial", style="Field.TLabel").grid(
            row=4, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        date_controls = ttk.Frame(config_tab, style="Card.TFrame")
        date_controls.grid(row=4, column=1, rowspan=2, sticky=tk.EW, pady=compact_pady)
        date_controls.columnconfigure(0, weight=1)
        date_controls.columnconfigure(1, weight=0)

        self.start_entry = ttk.Entry(
            date_controls,
            textvariable=self.start_date_var,
            width=18,
            style="Dark.TEntry",
        )
        self.start_entry.grid(row=0, column=0, sticky=tk.EW, pady=(0, compact_pady))

        ttk.Label(config_tab, text="Data final", style="Field.TLabel").grid(
            row=5, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.end_entry = ttk.Entry(
            date_controls,
            textvariable=self.end_date_var,
            width=18,
            style="Dark.TEntry",
        )
        self.end_entry.grid(row=1, column=0, sticky=tk.EW)

        period_actions = ttk.Frame(date_controls, style="Card.TFrame")
        period_actions.grid(row=0, column=1, rowspan=2, sticky=tk.NE, padx=(8, 0))

        self.btn_pick_period = ttk.Button(
            period_actions,
            text="Selecionar no calendario",
            style="Secondary.TButton",
            command=self._open_date_range_picker,
        )
        self.btn_pick_period.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, compact_pady))

        period_btn = ttk.Button(
            period_actions,
            text="Mês atual",
            style="Secondary.TButton",
            command=self._set_default_dates_current_month,
        )
        period_btn.grid(row=1, column=0, sticky=tk.EW, padx=(0, 5))

        previous_month_btn = ttk.Button(
            period_actions,
            text="Mês anterior",
            style="Secondary.TButton",
            command=self._set_previous_month_period_based_on_today,
        )
        previous_month_btn.grid(row=1, column=1, sticky=tk.EW)

        period_actions.columnconfigure(0, weight=1)
        period_actions.columnconfigure(1, weight=1)

        config_tab.rowconfigure(3, weight=1)
        config_tab.columnconfigure(1, weight=1)

        ttk.Label(self.estoque_tab, text="Estoque", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 12)
        )

        ttk.Label(self.estoque_tab, text="Plataforma", style="Field.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.estoque_platform_combo = ttk.Combobox(
            self.estoque_tab,
            textvariable=self.estoque_platform_var,
            state="readonly",
            values=[choice.label for choice in self.estoque_platform_choices],
            style="Dark.TCombobox",
            width=field_width,
        )
        self.estoque_platform_combo.grid(row=1, column=1, sticky=tk.EW, pady=compact_pady)

        ttk.Label(self.estoque_tab, text="Cliente", style="Field.TLabel").grid(
            row=2, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.estoque_client_combo = ttk.Combobox(
            self.estoque_tab,
            textvariable=self.estoque_client_var,
            state="readonly",
            style="Dark.TCombobox",
            width=field_width,
        )
        self.estoque_client_combo.grid(row=2, column=1, sticky=tk.EW, pady=compact_pady)

        ttk.Label(self.estoque_tab, text="Filiais / Alias", style="Field.TLabel").grid(
            row=3, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        estoque_sub_client_panel = ttk.Frame(self.estoque_tab, style="Card.TFrame")
        estoque_sub_client_panel.grid(row=3, column=1, sticky=tk.NSEW, pady=compact_pady)
        estoque_sub_client_panel.columnconfigure(0, weight=1)
        estoque_sub_client_panel.rowconfigure(1, weight=1)

        ttk.Label(
            estoque_sub_client_panel,
            textvariable=self.estoque_sub_client_summary_var,
            style="FieldValue.TLabel",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, compact_pady))

        estoque_sub_client_actions = ttk.Frame(estoque_sub_client_panel, style="Card.TFrame")
        estoque_sub_client_actions.grid(row=0, column=1, sticky=tk.E, pady=(0, compact_pady))

        self.btn_estoque_select_all_sub_clients = ttk.Button(
            estoque_sub_client_actions,
            text="Todos",
            style="Secondary.TButton",
            command=self._select_all_estoque_sub_clients,
        )
        self.btn_estoque_select_all_sub_clients.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_estoque_clear_sub_clients = ttk.Button(
            estoque_sub_client_actions,
            text="Limpar",
            style="Secondary.TButton",
            command=self._clear_estoque_sub_clients,
        )
        self.btn_estoque_clear_sub_clients.pack(side=tk.LEFT)

        estoque_sub_client_list_frame = ttk.Frame(estoque_sub_client_panel, style="Card.TFrame")
        estoque_sub_client_list_frame.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW)
        estoque_sub_client_list_frame.columnconfigure(0, weight=1)
        estoque_sub_client_list_frame.rowconfigure(0, weight=1)

        self.estoque_sub_client_listbox = tk.Listbox(
            estoque_sub_client_list_frame,
            selectmode=tk.MULTIPLE,
            exportselection=False,
            height=9,
            bg=COLOR_SURFACE_ALT,
            fg=COLOR_TEXT,
            selectbackground=COLOR_BUTTON_ALT_HOVER,
            selectforeground=COLOR_TEXT,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_ACCENT,
            relief=tk.FLAT,
            borderwidth=0,
            activestyle="none",
            font=("Segoe UI", 10),
        )
        self.estoque_sub_client_listbox.grid(row=0, column=0, sticky=tk.EW)

        estoque_sub_client_scroll = ttk.Scrollbar(
            estoque_sub_client_list_frame,
            orient=tk.VERTICAL,
            style="Modern.Vertical.TScrollbar",
            command=self.estoque_sub_client_listbox.yview,
        )
        estoque_sub_client_scroll.grid(row=0, column=1, sticky=tk.NS, padx=(5, 0))
        self.estoque_sub_client_listbox.configure(yscrollcommand=estoque_sub_client_scroll.set)

        ttk.Label(self.estoque_tab, text="Data inicial", style="Field.TLabel").grid(
            row=4, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        estoque_date_controls = ttk.Frame(self.estoque_tab, style="Card.TFrame")
        estoque_date_controls.grid(row=4, column=1, rowspan=2, sticky=tk.EW, pady=compact_pady)
        estoque_date_controls.columnconfigure(0, weight=1)
        estoque_date_controls.columnconfigure(1, weight=0)

        self.estoque_start_entry = ttk.Entry(
            estoque_date_controls,
            textvariable=self.estoque_start_date_var,
            width=18,
            style="Dark.TEntry",
        )
        self.estoque_start_entry.grid(row=0, column=0, sticky=tk.EW, pady=(0, compact_pady))

        ttk.Label(self.estoque_tab, text="Data final", style="Field.TLabel").grid(
            row=5, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.estoque_end_entry = ttk.Entry(
            estoque_date_controls,
            textvariable=self.estoque_end_date_var,
            width=18,
            style="Dark.TEntry",
        )
        self.estoque_end_entry.grid(row=1, column=0, sticky=tk.EW)

        estoque_period_actions = ttk.Frame(estoque_date_controls, style="Card.TFrame")
        estoque_period_actions.grid(row=0, column=1, rowspan=2, sticky=tk.NE, padx=(8, 0))

        self.btn_estoque_pick_period = ttk.Button(
            estoque_period_actions,
            text="Selecionar no calendario",
            style="Secondary.TButton",
            command=self._open_estoque_date_range_picker,
        )
        self.btn_estoque_pick_period.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, compact_pady))

        estoque_period_btn = ttk.Button(
            estoque_period_actions,
            text="Mês atual",
            style="Secondary.TButton",
            command=self._set_default_estoque_dates_current_month,
        )
        estoque_period_btn.grid(row=1, column=0, sticky=tk.EW, padx=(0, 5))

        estoque_previous_month_btn = ttk.Button(
            estoque_period_actions,
            text="Mês anterior",
            style="Secondary.TButton",
            command=self._set_previous_estoque_month_period_based_on_today,
        )
        estoque_previous_month_btn.grid(row=1, column=1, sticky=tk.EW)

        estoque_period_actions.columnconfigure(0, weight=1)
        estoque_period_actions.columnconfigure(1, weight=1)

        self.estoque_tab.rowconfigure(3, weight=1)
        self.estoque_tab.columnconfigure(1, weight=1)

        ttk.Label(self.clients_tab, text="Clientes", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 12)
        )
        ttk.Label(
            self.clients_tab,
            text=(
                "Escolha o tipo de cadastro, selecione a plataforma e preencha os campos. "
                "Use o GID da aba (sheetId)."
            ),
            style="Field.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        selectors_row = ttk.Frame(self.clients_tab, style="Card.TFrame")
        selectors_row.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=compact_pady)
        selectors_row.columnconfigure(1, weight=1)
        selectors_row.columnconfigure(3, weight=1)

        ttk.Label(selectors_row, text="Tipo de cadastro", style="Field.TLabel").grid(
            row=0, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.client_registration_mode_combo = ttk.Combobox(
            selectors_row,
            textvariable=self.client_registration_mode_var,
            state="readonly",
            style="Dark.TCombobox",
            width=field_width,
        )
        self.client_registration_mode_combo.grid(
            row=0,
            column=1,
            columnspan=3,
            sticky=tk.EW,
            pady=compact_pady,
        )

        ttk.Label(selectors_row, text="Plataforma", style="Field.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.client_registration_platform_combo = ttk.Combobox(
            selectors_row,
            textvariable=self.client_registration_platform_var,
            state="readonly",
            style="Dark.TCombobox",
            width=field_width,
        )
        self.client_registration_platform_combo.grid(
            row=1,
            column=1,
            sticky=tk.EW,
            pady=compact_pady,
            padx=(0, 12),
        )

        self.client_registration_client_label = ttk.Label(
            selectors_row,
            text="Cliente",
            style="Field.TLabel",
        )
        self.client_registration_client_label.grid(
            row=1,
            column=2,
            sticky=tk.W,
            padx=compact_padx,
            pady=compact_pady,
        )
        self.client_registration_client_combo = ttk.Combobox(
            selectors_row,
            textvariable=self.client_registration_client_var,
            state="readonly",
            style="Dark.TCombobox",
            width=field_width,
        )
        self.client_registration_client_combo.grid(
            row=1,
            column=3,
            sticky=tk.EW,
            pady=compact_pady,
        )
        self.client_registration_client_entry = ttk.Entry(
            selectors_row,
            textvariable=self.client_registration_client_name_var,
            style="Dark.TEntry",
            width=field_width,
        )
        self.client_registration_client_entry.grid(
            row=1,
            column=3,
            sticky=tk.EW,
            pady=compact_pady,
        )
        self.client_registration_client_entry.grid_remove()

        ttk.Label(self.clients_tab, text="GID da aba do cliente", style="Field.TLabel").grid(
            row=3, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.client_registration_gid_entry = ttk.Entry(
            self.clients_tab,
            textvariable=self.client_registration_gid_var,
            style="Dark.TEntry",
            width=field_width,
        )
        self.client_registration_gid_entry.grid(row=3, column=1, sticky=tk.EW, pady=compact_pady)

        ttk.Label(self.clients_tab, text="Credenciais", style="Field.TLabel").grid(
            row=4, column=0, sticky=tk.NW, padx=compact_padx, pady=compact_pady
        )
        client_registration_fields_container = ttk.Frame(self.clients_tab, style="Card.TFrame")
        client_registration_fields_container.grid(
            row=4,
            column=1,
            sticky=tk.NSEW,
            pady=compact_pady,
        )
        client_registration_fields_container.columnconfigure(0, weight=1)
        client_registration_fields_container.rowconfigure(0, weight=1)

        self.client_registration_fields_canvas = tk.Canvas(
            client_registration_fields_container,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_ACCENT,
            relief=tk.FLAT,
            borderwidth=0,
        )
        self.client_registration_fields_canvas.grid(row=0, column=0, sticky=tk.NSEW)

        client_registration_fields_scroll = ttk.Scrollbar(
            client_registration_fields_container,
            orient=tk.VERTICAL,
            style="Modern.Vertical.TScrollbar",
            command=self.client_registration_fields_canvas.yview,
        )
        client_registration_fields_scroll.grid(row=0, column=1, sticky=tk.NS, padx=(5, 0))
        self.client_registration_fields_canvas.configure(yscrollcommand=client_registration_fields_scroll.set)

        self.client_registration_fields_frame = ttk.Frame(self.client_registration_fields_canvas, style="Card.TFrame")
        self.client_registration_fields_window_id = self.client_registration_fields_canvas.create_window(
            (0, 0),
            window=self.client_registration_fields_frame,
            anchor=tk.NW,
        )
        self.client_registration_fields_frame.columnconfigure(1, weight=1)
        self.client_registration_fields_frame.bind(
            "<Configure>",
            lambda _event: self._sync_client_registration_fields_scrollregion(),
        )
        self.client_registration_fields_canvas.bind(
            "<Configure>",
            lambda event: self._sync_client_registration_fields_width(event.width),
        )

        clients_actions = ttk.Frame(self.clients_tab, style="Card.TFrame")
        clients_actions.grid(row=5, column=1, sticky=tk.E, pady=(6, 0))

        self.btn_register_client = ttk.Button(
            clients_actions,
            text="Registrar cliente",
            style="Secondary.TButton",
            command=self.register_client,
        )
        self.btn_register_client.pack(side=tk.RIGHT)

        self.btn_refresh_catalog = ttk.Button(
            clients_actions,
            text="Atualizar catalogo",
            style="Secondary.TButton",
            command=self.refresh_remote_catalog,
        )
        self.btn_refresh_catalog.pack(side=tk.RIGHT, padx=(0, 8))

        self.clients_tab.columnconfigure(1, weight=1)
        self.clients_tab.rowconfigure(4, weight=1)

        ttk.Label(self.generator_tab, text="Gerador", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 12)
        )
        ttk.Label(
            self.generator_tab,
            text=(
                "Gere links de autorizacao por plataforma. "
                "O callback registra o cliente automaticamente no servidor."
            ),
            style="Field.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        generator_selectors = ttk.Frame(self.generator_tab, style="Card.TFrame")
        generator_selectors.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=compact_pady)
        generator_selectors.columnconfigure(1, weight=1)
        generator_selectors.columnconfigure(3, weight=1)

        ttk.Label(generator_selectors, text="Tipo de cadastro", style="Field.TLabel").grid(
            row=0, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.generator_mode_combo = ttk.Combobox(
            generator_selectors,
            textvariable=self.generator_mode_var,
            state="readonly",
            style="Dark.TCombobox",
            width=field_width,
        )
        self.generator_mode_combo.grid(
            row=0,
            column=1,
            columnspan=3,
            sticky=tk.EW,
            pady=compact_pady,
        )

        ttk.Label(generator_selectors, text="Plataforma", style="Field.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.generator_platform_combo = ttk.Combobox(
            generator_selectors,
            textvariable=self.generator_platform_var,
            state="readonly",
            style="Dark.TCombobox",
            width=field_width,
        )
        self.generator_platform_combo.grid(
            row=1,
            column=1,
            sticky=tk.EW,
            pady=compact_pady,
            padx=(0, 12),
        )

        self.generator_client_label = ttk.Label(
            generator_selectors,
            text="Cliente",
            style="Field.TLabel",
        )
        self.generator_client_label.grid(
            row=1,
            column=2,
            sticky=tk.W,
            padx=compact_padx,
            pady=compact_pady,
        )
        self.generator_client_combo = ttk.Combobox(
            generator_selectors,
            textvariable=self.generator_client_var,
            state="readonly",
            style="Dark.TCombobox",
            width=field_width,
        )
        self.generator_client_combo.grid(
            row=1,
            column=3,
            sticky=tk.EW,
            pady=compact_pady,
        )
        self.generator_client_entry = ttk.Entry(
            generator_selectors,
            textvariable=self.generator_client_name_var,
            style="Dark.TEntry",
            width=field_width,
        )
        self.generator_client_entry.grid(
            row=1,
            column=3,
            sticky=tk.EW,
            pady=compact_pady,
        )
        self.generator_client_entry.grid_remove()

        ttk.Label(self.generator_tab, text="GID da aba do cliente", style="Field.TLabel").grid(
            row=3, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.generator_gid_entry = ttk.Entry(
            self.generator_tab,
            textvariable=self.generator_gid_var,
            style="Dark.TEntry",
            width=field_width,
        )
        self.generator_gid_entry.grid(row=3, column=1, sticky=tk.EW, pady=compact_pady)

        ttk.Label(self.generator_tab, text="Parametros da plataforma", style="Field.TLabel").grid(
            row=4, column=0, sticky=tk.NW, padx=compact_padx, pady=compact_pady
        )
        self.generator_fields_frame = ttk.Frame(self.generator_tab, style="Card.TFrame")
        self.generator_fields_frame.grid(row=4, column=1, sticky=tk.NSEW, pady=compact_pady)
        self.generator_fields_frame.columnconfigure(1, weight=1)

        ttk.Label(self.generator_tab, text="Link gerado", style="Field.TLabel").grid(
            row=5, column=0, sticky=tk.W, padx=compact_padx, pady=compact_pady
        )
        self.generator_link_entry = ttk.Entry(
            self.generator_tab,
            textvariable=self.generator_link_var,
            style="Dark.TEntry",
            state="readonly",
        )
        self.generator_link_entry.grid(row=5, column=1, sticky=tk.EW, pady=compact_pady)

        generator_actions = ttk.Frame(self.generator_tab, style="Card.TFrame")
        generator_actions.grid(row=6, column=1, sticky=tk.E, pady=(6, 0))

        self.btn_generate_link = ttk.Button(
            generator_actions,
            text="Gerar link",
            style="Primary.TButton",
            command=self.generate_platform_link,
        )
        self.btn_generate_link.pack(side=tk.RIGHT)

        self.btn_open_generated_link = ttk.Button(
            generator_actions,
            text="Abrir link",
            style="Secondary.TButton",
            command=self.open_generated_link,
        )
        self.btn_open_generated_link.pack(side=tk.RIGHT, padx=(0, 8))

        self.btn_copy_generated_link = ttk.Button(
            generator_actions,
            text="Copiar link",
            style="Secondary.TButton",
            command=self.copy_generated_link,
        )
        self.btn_copy_generated_link.pack(side=tk.RIGHT, padx=(0, 8))

        self.generator_tab.columnconfigure(1, weight=1)
        self.generator_tab.rowconfigure(4, weight=1)

        self.sku_tab.rowconfigure(3, weight=1)
        self.sku_tab.columnconfigure(0, weight=1)

        ttk.Label(self.sku_tab, text="SKU", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 8)
        )
        ttk.Label(
            self.sku_tab,
            text="Pesquise pelo numero do pedido para visualizar os itens SKU antes de exportar.",
            style="Field.TLabel",
        ).grid(row=1, column=0, sticky=tk.W, pady=(0, 10))

        sku_search_row = ttk.Frame(self.sku_tab, style="Card.TFrame")
        sku_search_row.grid(row=2, column=0, sticky=tk.EW, pady=(0, 10))
        sku_search_row.columnconfigure(1, weight=1)

        ttk.Label(sku_search_row, text="Numero do Pedido", style="Field.TLabel").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 10), pady=6
        )
        self.sku_order_entry = ttk.Entry(
            sku_search_row,
            textvariable=self.sku_order_number_var,
            width=28,
            style="Dark.TEntry",
        )
        self.sku_order_entry.grid(row=0, column=1, sticky=tk.EW, pady=6)

        self.btn_search_sku = ttk.Button(
            sku_search_row,
            text="Buscar SKU",
            style="Secondary.TButton",
            command=self.search_sku,
        )
        self.btn_search_sku.grid(row=0, column=2, sticky=tk.E, padx=(10, 0), pady=6)

        sku_table_frame = ttk.Frame(self.sku_tab, style="Card.TFrame")
        sku_table_frame.grid(row=3, column=0, sticky=tk.NSEW)
        sku_table_frame.columnconfigure(0, weight=1)
        sku_table_frame.rowconfigure(0, weight=1)

        sku_columns = ("number", "created_at", "sku_id", "item_sku", "quantity", "price_cost")
        self.sku_tree = ttk.Treeview(
            sku_table_frame,
            columns=sku_columns,
            show="headings",
            style="Dark.Treeview",
        )
        self.sku_tree.heading("number", text="NUMBER", anchor=tk.CENTER)
        self.sku_tree.heading("created_at", text="CREATED_AT", anchor=tk.CENTER)
        self.sku_tree.heading("sku_id", text="SKU_ID", anchor=tk.CENTER)
        self.sku_tree.heading("item_sku", text="ITEM_SKU", anchor=tk.CENTER)
        self.sku_tree.heading("quantity", text="QUANTITY", anchor=tk.CENTER)
        self.sku_tree.heading("price_cost", text="PRICE_COST", anchor=tk.CENTER)
        self.sku_tree.column("number", anchor=tk.CENTER, stretch=False)
        self.sku_tree.column("created_at", anchor=tk.CENTER, stretch=False)
        self.sku_tree.column("sku_id", anchor=tk.CENTER, stretch=False)
        self.sku_tree.column("item_sku", anchor=tk.CENTER, stretch=False)
        self.sku_tree.column("quantity", anchor=tk.CENTER, stretch=False)
        self.sku_tree.column("price_cost", anchor=tk.CENTER, stretch=False)
        self.sku_tree.grid(row=0, column=0, sticky=tk.NSEW)

        sku_scroll = ttk.Scrollbar(
            sku_table_frame,
            orient=tk.VERTICAL,
            style="Modern.Vertical.TScrollbar",
            command=self.sku_tree.yview,
        )
        sku_scroll.grid(row=0, column=1, sticky=tk.NS, padx=(6, 0))
        self.sku_tree.configure(yscrollcommand=sku_scroll.set)
        self.sku_tree.bind("<Configure>", lambda event: self._resize_sku_columns(event.width))

        ttk.Label(self.settings_tab, text="Configurações", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 12)
        )

        ttk.Label(self.settings_tab, text="Som de notificação", style="Field.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 10), pady=6
        )
        sound_actions = ttk.Frame(self.settings_tab, style="Card.TFrame")
        sound_actions.grid(row=1, column=1, sticky=tk.EW, pady=6)
        sound_actions.columnconfigure(0, weight=1)

        self.notification_sound_combo = ttk.Combobox(
            sound_actions,
            textvariable=self.notification_sound_var,
            state="readonly",
            values=self.notification_sound_options,
            style="Dark.TCombobox",
            width=30,
        )
        self.notification_sound_combo.grid(row=0, column=0, sticky=tk.EW)

        self.btn_refresh_sounds = ttk.Button(
            sound_actions,
            text="Atualizar sons",
            style="Secondary.TButton",
            command=self._refresh_notification_sounds,
        )
        self.btn_refresh_sounds.grid(row=0, column=1, sticky=tk.E, padx=(8, 0))

        ttk.Label(
            self.settings_tab,
            text="Adicione arquivos .mp3 na pasta sounds para novos sons.",
            style="Field.TLabel",
        ).grid(row=2, column=1, sticky=tk.W, pady=(0, 10))

        ttk.Label(self.settings_tab, text="URL da API servidor", style="Field.TLabel").grid(
            row=3, column=0, sticky=tk.W, padx=(0, 10), pady=6
        )
        server_url_row = ttk.Frame(self.settings_tab, style="Card.TFrame")
        server_url_row.grid(row=3, column=1, sticky=tk.EW, pady=6)
        server_url_row.columnconfigure(0, weight=1)
        self.server_url_entry = ttk.Entry(
            server_url_row,
            textvariable=self.server_url_var,
            style="Dark.TEntry",
            width=42,
        )
        self.server_url_entry.grid(row=0, column=0, sticky=tk.EW)

        ttk.Label(self.settings_tab, text="Token Bearer", style="Field.TLabel").grid(
            row=4, column=0, sticky=tk.W, padx=(0, 10), pady=6
        )
        server_token_row = ttk.Frame(self.settings_tab, style="Card.TFrame")
        server_token_row.grid(row=4, column=1, sticky=tk.EW, pady=6)
        server_token_row.columnconfigure(0, weight=1)
        self.server_token_entry = ttk.Entry(
            server_token_row,
            textvariable=self.server_token_var,
            style="Dark.TEntry",
            show="*",
            width=42,
        )
        self.server_token_entry.grid(row=0, column=0, sticky=tk.EW)

        server_actions = ttk.Frame(self.settings_tab, style="Card.TFrame")
        server_actions.grid(row=5, column=1, sticky=tk.EW, pady=(4, 10))
        server_actions.columnconfigure(0, weight=1)
        server_actions.columnconfigure(1, weight=1)
        server_actions.columnconfigure(2, weight=0)
        self.btn_connect_server = ttk.Button(
            server_actions,
            text="Conectar servidor",
            style="Secondary.TButton",
            command=self.connect_server,
        )
        self.btn_connect_server.grid(row=0, column=0, sticky=tk.EW, padx=(0, 6))
        self.btn_disconnect_server = ttk.Button(
            server_actions,
            text="Desconectar servidor",
            style="Secondary.TButton",
            command=self.disconnect_server,
        )
        self.btn_disconnect_server.grid(row=0, column=1, sticky=tk.EW, padx=(0, 6))
        self.btn_use_local_secrets = ttk.Button(
            server_actions,
            text="Usar fallback local (secrets)",
            style="Secondary.TButton",
            command=self.activate_local_mode,
        )
        self._refresh_local_fallback_visibility()

        ttk.Label(
            self.settings_tab,
            textvariable=self.server_status_var,
            style="Field.TLabel",
        ).grid(row=6, column=1, sticky=tk.W, pady=(0, 8))

        secrets_panel = ttk.Frame(self.server_tab, style="Card.TFrame")
        secrets_panel.grid(row=0, column=0, sticky=tk.NSEW)
        secrets_panel.columnconfigure(1, weight=1)
        secrets_panel.rowconfigure(1, weight=1)

        secrets_header = ttk.Frame(secrets_panel, style="Card.TFrame")
        secrets_header.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))
        secrets_header.columnconfigure(0, weight=1)
        ttk.Label(
            secrets_header,
            text="Secrets do servidor",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky=tk.W)
        self.btn_refresh_server_secrets = ttk.Button(
            secrets_header,
            text="Atualizar lista",
            style="Secondary.TButton",
            command=self.refresh_server_secret_files,
        )
        self.btn_refresh_server_secrets.grid(row=0, column=1, sticky=tk.E, padx=(8, 0))

        secrets_list_frame = ttk.Frame(secrets_panel, style="Card.TFrame")
        secrets_list_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=(0, 10))
        secrets_list_frame.rowconfigure(0, weight=1)
        secrets_list_frame.columnconfigure(0, weight=1)
        self.server_secrets_tree = ttk.Treeview(
            secrets_list_frame,
            columns=("modified",),
            show="tree headings",
            height=9,
            style="Dark.Treeview",
            selectmode="browse",
        )
        self.server_secrets_tree.heading("#0", text="Arquivo")
        self.server_secrets_tree.heading("modified", text="Editado em")
        self.server_secrets_tree.column("#0", width=260, minwidth=180, stretch=True)
        self.server_secrets_tree.column("modified", width=150, minwidth=130, stretch=False)
        self.server_secrets_tree.grid(row=0, column=0, sticky=tk.NSEW)
        secrets_list_scroll = ttk.Scrollbar(
            secrets_list_frame,
            orient=tk.VERTICAL,
            command=self.server_secrets_tree.yview,
            style="Modern.Vertical.TScrollbar",
        )
        secrets_list_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.server_secrets_tree.configure(yscrollcommand=secrets_list_scroll.set)

        secrets_editor_frame = ttk.Frame(secrets_panel, style="Card.TFrame")
        secrets_editor_frame.grid(row=1, column=1, sticky=tk.NSEW)
        secrets_editor_frame.rowconfigure(2, weight=1)
        secrets_editor_frame.columnconfigure(0, weight=1)

        secrets_meta = ttk.Frame(secrets_editor_frame, style="Card.TFrame")
        secrets_meta.grid(row=0, column=0, sticky=tk.EW, pady=(0, 6))
        secrets_meta.columnconfigure(1, weight=1)
        ttk.Label(secrets_meta, text="Arquivo", style="Field.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            secrets_meta,
            textvariable=self.server_secret_path_var,
            style="FieldValue.TLabel",
        ).grid(row=0, column=1, sticky=tk.W, padx=(8, 0))
        ttk.Label(secrets_meta, text="Ultima edicao", style="Field.TLabel").grid(
            row=1,
            column=0,
            sticky=tk.W,
            pady=(4, 0),
        )
        ttk.Label(
            secrets_meta,
            textvariable=self.server_secret_modified_var,
            style="FieldValue.TLabel",
        ).grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=(4, 0))
        ttk.Label(secrets_meta, text="Tamanho", style="Field.TLabel").grid(
            row=2,
            column=0,
            sticky=tk.W,
            pady=(4, 0),
        )
        ttk.Label(
            secrets_meta,
            textvariable=self.server_secret_size_var,
            style="FieldValue.TLabel",
        ).grid(row=2, column=1, sticky=tk.W, padx=(8, 0), pady=(4, 0))

        self.server_secret_editor = tk.Text(
            secrets_editor_frame,
            height=12,
            bg=COLOR_SURFACE_ALT,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            selectbackground=COLOR_BUTTON_ALT_HOVER,
            selectforeground=COLOR_TEXT,
            relief=tk.FLAT,
            padx=10,
            pady=10,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_ACCENT,
            borderwidth=0,
            font=("Consolas", 10),
            undo=True,
            wrap=tk.NONE,
        )
        self.server_secret_editor.grid(row=2, column=0, sticky=tk.NSEW)

        secrets_editor_actions = ttk.Frame(secrets_editor_frame, style="Card.TFrame")
        secrets_editor_actions.grid(row=3, column=0, sticky=tk.EW, pady=(8, 0))
        secrets_editor_actions.columnconfigure(0, weight=1)
        secrets_editor_actions.columnconfigure(1, weight=1)
        self.btn_load_server_secret = ttk.Button(
            secrets_editor_actions,
            text="Carregar JSON",
            style="Secondary.TButton",
            command=self.load_selected_server_secret,
        )
        self.btn_load_server_secret.grid(row=0, column=0, sticky=tk.EW, padx=(0, 6))
        self.btn_save_server_secret = ttk.Button(
            secrets_editor_actions,
            text="Salvar no servidor",
            style="Primary.TButton",
            command=self.save_selected_server_secret,
        )
        self.btn_save_server_secret.grid(row=0, column=1, sticky=tk.EW)

        app_actions = ttk.Frame(self.settings_tab, style="Card.TFrame")
        app_actions.grid(row=8, column=1, sticky=tk.EW, pady=(8, 0))
        app_actions.columnconfigure(0, weight=1)
        app_actions.columnconfigure(1, weight=1)

        self.btn_update_app = ttk.Button(
            app_actions,
            text=UPDATE_APP_DEFAULT_LABEL,
            style="Secondary.TButton",
            command=self.update_app,
        )
        self.btn_update_app.grid(row=0, column=0, sticky=tk.EW, padx=(0, 6))

        self.btn_open_changelog = ttk.Button(
            app_actions,
            text="Ver changelog",
            style="Secondary.TButton",
            command=self.open_changelog,
        )
        self.btn_open_changelog.grid(row=0, column=1, sticky=tk.EW)
        self.update_notice_label = ttk.Label(
            app_actions,
            textvariable=self.update_notice_var,
            style="UpdateNotice.TLabel",
        )
        self.update_notice_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))
        self.update_notice_label.grid_remove()

        actions_card = ttk.Frame(right_panel, style="Card.TFrame", padding=16)
        actions_card.grid(row=0, column=0, sticky=tk.EW, pady=(0, 10))
        ttk.Label(actions_card, text="Ações", style="CardTitle.TLabel").pack(anchor=tk.W, pady=(0, 10))

        buttons = ttk.Frame(actions_card, style="Card.TFrame")
        buttons.pack(fill=tk.X)

        self.btn_collect = ttk.Button(
            buttons,
            text="Coletar no banco",
            style="Secondary.TButton",
            command=self.collect_data,
        )
        self.btn_collect.pack(fill=tk.X, pady=(0, 8))

        self.btn_export = ttk.Button(
            buttons,
            text="Exportar Pedidos",
            style="Secondary.TButton",
            command=self.export_data,
        )
        self.btn_export.pack(fill=tk.X, pady=(0, 8))

        self.btn_export_sku = ttk.Button(
            buttons,
            text="Exportar Estoque",
            style="Sku.TButton",
            command=self.export_data,
            cursor="no",
        )
        self.btn_export_sku.pack(fill=tk.X)

        self.mercado_livre_categories_card = ttk.Frame(actions_card, style="Card.TFrame")
        self.update_mercado_livre_categories_check = ttk.Checkbutton(
            self.mercado_livre_categories_card,
            text="Atualizar categorias",
            variable=self.update_mercado_livre_categories_var,
            style="Dark.TCheckbutton",
        )
        self.update_mercado_livre_categories_check.pack(anchor=tk.W)
        self.mercado_livre_categories_card.pack_forget()
        self._sync_mercado_livre_categories_checkbox()

        log_card = ttk.Frame(right_panel, style="Card.TFrame", padding=16)
        log_card.grid(row=1, column=0, sticky=tk.NSEW)

        log_header = ttk.Frame(log_card, style="Card.TFrame")
        log_header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(log_header, text="Log", style="CardTitle.TLabel").pack(side=tk.LEFT, anchor=tk.W)
        self.btn_clear_log = ttk.Button(
            log_header,
            text="Limpar log",
            style="Secondary.TButton",
            command=self.clear_log,
        )
        self.btn_clear_log.pack(side=tk.RIGHT)

        self.log_box = tk.Text(
            log_card,
            height=16,
            state=tk.DISABLED,
            bg=COLOR_SURFACE_ALT,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            selectbackground=COLOR_BUTTON_ALT_HOVER,
            selectforeground=COLOR_TEXT,
            relief=tk.FLAT,
            padx=10,
            pady=10,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_ACCENT,
            borderwidth=0,
            font=("Consolas", 10),
        )
        self.log_box.pack(fill=tk.BOTH, expand=True)
        self.root.after(0, self._resize_sku_columns)

    def _resize_sku_columns(self, width: int | None = None) -> None:
        if not hasattr(self, "sku_tree"):
            return

        total_width = width if width is not None else self.sku_tree.winfo_width()
        if total_width <= 10:
            return

        available = max(total_width - 4, 200)
        ratios = [
            ("number", 0.11),
            ("created_at", 0.25),
            ("sku_id", 0.14),
            ("item_sku", 0.30),
            ("quantity", 0.10),
            ("price_cost", 0.10),
        ]

        used = 0
        for column_name, ratio in ratios[:-1]:
            col_width = int(available * ratio)
            self.sku_tree.column(column_name, width=col_width, anchor=tk.CENTER)
            used += col_width

        # Ajusta a ultima coluna com a sobra para ocupar 100% da largura visivel.
        last_column = ratios[-1][0]
        self.sku_tree.column(last_column, width=max(20, available - used), anchor=tk.CENTER)

    def _bind_events(self) -> None:
        self.platform_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_platform_change())
        self.client_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_client_change())
        self.estoque_platform_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_estoque_platform_change())
        self.estoque_client_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_estoque_client_change())
        self.client_registration_mode_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_client_registration_mode_change(),
        )
        self.client_registration_platform_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_client_registration_platform_change(),
        )
        self.client_registration_client_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._update_register_client_button_state(),
        )
        self.client_registration_client_entry.bind(
            "<KeyRelease>",
            lambda _event: self._update_register_client_button_state(),
        )
        self.generator_mode_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_generator_mode_change(),
        )
        self.generator_platform_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_generator_platform_change(),
        )
        self.generator_client_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._update_generate_link_button_state(),
        )
        self.generator_client_entry.bind(
            "<KeyRelease>",
            lambda _event: self._update_generate_link_button_state(),
        )
        self.generator_gid_entry.bind(
            "<KeyRelease>",
            lambda _event: self._update_generate_link_button_state(),
        )
        self.sub_client_listbox.bind(
            "<<ListboxSelect>>",
            lambda _event: self._update_sub_client_summary(),
        )
        self.estoque_sub_client_listbox.bind(
            "<<ListboxSelect>>",
            lambda _event: self._update_estoque_sub_client_summary(),
        )
        self.notification_sound_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_notification_sound_change(),
        )
        self.server_secrets_tree.bind(
            "<<TreeviewSelect>>",
            lambda _event: self._on_server_secret_selection_change(),
        )
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self._on_tab_changed())
        self.sku_order_entry.bind("<Return>", lambda _event: self.search_sku())

    def _period_vars_for_target(self, target: str) -> tuple[tk.StringVar, tk.StringVar]:
        if target == "estoque":
            return self.estoque_start_date_var, self.estoque_end_date_var
        return self.start_date_var, self.end_date_var

    def _open_date_range_picker(self) -> None:
        self._open_date_range_picker_for_target("pedidos")

    def _open_estoque_date_range_picker(self) -> None:
        self._open_date_range_picker_for_target("estoque")

    def _open_date_range_picker_for_target(self, target: str) -> None:
        self._date_picker_target = target
        target_start_var, target_end_var = self._period_vars_for_target(target)
        try:
            start = self._parse_ui_date(target_start_var.get().strip())
            end = self._parse_ui_date(target_end_var.get().strip())
        except ValueError:
            today = date.today()
            start = today.replace(day=1)
            end = today

        if start > end:
            start, end = end, start

        self._date_picker_selection_start = start
        self._date_picker_selection_end = end
        self._date_picker_month = start.replace(day=1)

        if self._date_picker_window is not None and self._date_picker_window.winfo_exists():
            self._refresh_date_picker_grid()
            self._date_picker_window.deiconify()
            self._date_picker_window.lift()
            self._date_picker_window.focus_force()
            self._center_date_picker_window()
            return

        popup = tk.Toplevel(self.root)
        self._date_picker_window = popup
        popup.title("Selecionar periodo")
        popup.resizable(True, False)
        popup.transient(self.root)
        popup.configure(bg=COLOR_SURFACE)
        popup.protocol("WM_DELETE_WINDOW", self._close_date_range_picker)
        popup.grab_set()
        popup.bind("<Escape>", lambda _event: self._close_date_range_picker())
        popup.bind("<Return>", lambda _event: self._apply_date_range_picker_selection())
        popup.bind("<MouseWheel>", self._on_date_picker_mouse_wheel)
        popup.bind("<Button-4>", lambda _event: self._change_date_picker_month(-1))
        popup.bind("<Button-5>", lambda _event: self._change_date_picker_month(1))

        container = ttk.Frame(popup, style="Card.TFrame", padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container, style="Card.TFrame")
        header.pack(fill=tk.X)

        ttk.Button(
            header,
            text="<",
            style="Secondary.TButton",
            command=lambda: self._change_date_picker_month(-1),
            width=3,
        ).pack(side=tk.LEFT)

        ttk.Label(
            header,
            textvariable=self._date_picker_month_label_var,
            style="CardTitle.TLabel",
            anchor=tk.CENTER,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        ttk.Button(
            header,
            text=">",
            style="Secondary.TButton",
            command=lambda: self._change_date_picker_month(1),
            width=3,
        ).pack(side=tk.RIGHT)

        content = ttk.Frame(container, style="Card.TFrame")
        content.pack(fill=tk.BOTH, expand=True, pady=(10, 8))
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=1)
        content.columnconfigure(2, weight=1)
        content.rowconfigure(0, weight=1)

        calendar_panel = ttk.Frame(content, style="Card.TFrame")
        calendar_panel.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 10))

        quick_actions_col_1 = ttk.Frame(content, style="Card.TFrame")
        quick_actions_col_1.grid(row=0, column=1, sticky=tk.NSEW, padx=(0, 6))
        quick_actions_col_2 = ttk.Frame(content, style="Card.TFrame")
        quick_actions_col_2.grid(row=0, column=2, sticky=tk.NSEW)

        quick_buttons = [
            ("Hoje", "today"),
            ("Ontem", "yesterday"),
            ("7 dias", "last7"),
            ("30 dias", "last30"),
            ("Mês atual", "current_month"),
            ("Mês anterior", "previous_month"),
            ("Ano atual", "current_year"),
            ("Ano anterior", "previous_year"),
        ]
        for index, (label, preset) in enumerate(quick_buttons):
            target_column = quick_actions_col_1 if index % 2 == 0 else quick_actions_col_2
            row_index = index // 2
            ttk.Button(
                target_column,
                text=label,
                style="Secondary.TButton",
                command=lambda selected_preset=preset: self._date_picker_apply_preset(selected_preset),
            ).grid(row=row_index, column=0, sticky=tk.EW, pady=(0 if row_index == 0 else 6, 0))

        quick_actions_col_1.columnconfigure(0, weight=1)
        quick_actions_col_2.columnconfigure(0, weight=1)

        self._date_picker_grid_frame = ttk.Frame(calendar_panel, style="Card.TFrame")
        self._date_picker_grid_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            textvariable=self._date_picker_hint_var,
            style="Field.TLabel",
        ).pack(fill=tk.X)

        actions = ttk.Frame(container, style="Card.TFrame")
        actions.pack(fill=tk.X, pady=(10, 0))
        actions.columnconfigure(0, weight=1)

        ttk.Button(
            actions,
            text="Cancelar",
            style="Secondary.TButton",
            command=self._close_date_range_picker,
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(
            actions,
            text="Limpar",
            style="Secondary.TButton",
            command=self._clear_date_picker_selection,
        ).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(
            actions,
            text="Aplicar periodo",
            style="Primary.TButton",
            command=self._apply_date_range_picker_selection,
        ).grid(row=0, column=3)

        self._refresh_date_picker_grid()
        self._center_date_picker_window()

    def _center_date_picker_window(self) -> None:
        if self._date_picker_window is None or not self._date_picker_window.winfo_exists():
            return
        self._date_picker_window.update_idletasks()
        popup_width = self._date_picker_window.winfo_width()
        popup_height = self._date_picker_window.winfo_height()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        x = root_x + max((root_width - popup_width) // 2, 0)
        y = root_y + max((root_height - popup_height) // 2, 0)
        self._date_picker_window.geometry(f"+{x}+{y}")

    def _close_date_range_picker(self) -> None:
        if self._date_picker_window is None:
            return
        try:
            self._date_picker_window.grab_release()
        except tk.TclError:
            pass
        self._date_picker_window.destroy()
        self._date_picker_window = None
        self._date_picker_grid_frame = None

    def _change_date_picker_month(self, offset: int) -> None:
        month_index = self._date_picker_month.month + offset
        year = self._date_picker_month.year + (month_index - 1) // 12
        month = (month_index - 1) % 12 + 1
        self._date_picker_month = date(year, month, 1)
        self._refresh_date_picker_grid()

    def _on_date_picker_mouse_wheel(self, event: tk.Event) -> str:
        delta = getattr(event, "delta", 0)
        if delta > 0:
            self._change_date_picker_month(-1)
        elif delta < 0:
            self._change_date_picker_month(1)
        return "break"

    def _date_picker_apply_preset(self, preset: str) -> None:
        today = date.today()
        if preset == "today":
            start = today
            end = today
        elif preset == "yesterday":
            start = today - timedelta(days=1)
            end = start
        elif preset == "last7":
            start = today - timedelta(days=6)
            end = today
        elif preset == "last30":
            start = today - timedelta(days=29)
            end = today
        elif preset == "current_month":
            start = today.replace(day=1)
            end = today
        elif preset == "previous_month":
            first_day_current_month = today.replace(day=1)
            end = first_day_current_month - timedelta(days=1)
            start = end.replace(day=1)
        elif preset == "current_year":
            start = date(today.year, 1, 1)
            end = today
        elif preset == "previous_year":
            previous_year = today.year - 1
            start = date(previous_year, 1, 1)
            end = date(previous_year, 12, 31)
        else:
            return

        self._date_picker_selection_start = start
        self._date_picker_selection_end = end
        self._date_picker_month = start.replace(day=1)
        self._refresh_date_picker_grid()

    def _clear_date_picker_selection(self) -> None:
        self._date_picker_selection_start = None
        self._date_picker_selection_end = None
        self._refresh_date_picker_grid()

    def _apply_date_range_picker_selection(self) -> None:
        start = self._date_picker_selection_start
        end = self._date_picker_selection_end
        if start is None and end is None:
            messagebox.showwarning("Periodo", "Selecione ao menos uma data no calendario.")
            return

        if start is None and end is not None:
            start = end
        if end is None and start is not None:
            end = start

        if start is None or end is None:
            messagebox.showwarning("Periodo", "Nao foi possivel determinar o periodo selecionado.")
            return

        self._set_period_dates_for_target(self._date_picker_target, start, end)
        self._close_date_range_picker()

    def _refresh_date_picker_grid(self) -> None:
        if self._date_picker_window is None or self._date_picker_grid_frame is None:
            return

        year = self._date_picker_month.year
        month = self._date_picker_month.month
        month_name = PT_BR_MONTH_NAMES[month - 1]
        self._date_picker_month_label_var.set(f"{month_name} {year}")

        for child in self._date_picker_grid_frame.winfo_children():
            child.destroy()

        for index, weekday_name in enumerate(PT_BR_WEEKDAY_ABBR):
            label = tk.Label(
                self._date_picker_grid_frame,
                text=weekday_name,
                bg=COLOR_SURFACE,
                fg=COLOR_MUTED,
                font=("Segoe UI Semibold", 9),
                width=4,
            )
            label.grid(row=0, column=index, padx=1, pady=(0, 4))

        month_grid = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
        today = date.today()
        start = self._date_picker_selection_start
        end = self._date_picker_selection_end
        has_range = start is not None and end is not None
        if has_range and start > end:
            start, end = end, start

        for row_index, week in enumerate(month_grid, start=1):
            for col_index, day in enumerate(week):
                in_current_month = day.month == month
                is_endpoint = has_range and day in (start, end)
                in_range = has_range and start is not None and end is not None and start <= day <= end

                button_bg = COLOR_SURFACE_ALT if in_current_month else COLOR_SURFACE
                button_fg = COLOR_TEXT if in_current_month else COLOR_MUTED
                if in_range:
                    button_bg = COLOR_BUTTON_ALT_HOVER
                if is_endpoint:
                    button_bg = COLOR_ACCENT
                    button_fg = COLOR_BG

                border_color = COLOR_ACCENT if day == today else COLOR_BORDER

                btn = tk.Button(
                    self._date_picker_grid_frame,
                    text=str(day.day),
                    command=lambda selected_day=day: self._on_date_picker_day_click(selected_day),
                    bg=button_bg,
                    fg=button_fg,
                    activebackground=COLOR_BUTTON_ALT_HOVER,
                    activeforeground=COLOR_TEXT,
                    disabledforeground=COLOR_MUTED,
                    relief=tk.FLAT,
                    borderwidth=0,
                    highlightthickness=1,
                    highlightbackground=border_color,
                    highlightcolor=border_color,
                    width=4,
                    pady=6,
                    cursor="hand2",
                    font=("Segoe UI", 9),
                )
                btn.grid(row=row_index, column=col_index, padx=1, pady=1)

        self._update_date_picker_hint()

    def _on_date_picker_day_click(self, selected_day: date) -> None:
        if selected_day.month != self._date_picker_month.month or selected_day.year != self._date_picker_month.year:
            self._date_picker_month = selected_day.replace(day=1)

        start = self._date_picker_selection_start
        end = self._date_picker_selection_end

        if start is None or end is not None:
            self._date_picker_selection_start = selected_day
            self._date_picker_selection_end = None
            self._refresh_date_picker_grid()
            return

        if selected_day < start:
            self._date_picker_selection_start = selected_day
            self._date_picker_selection_end = start
        else:
            self._date_picker_selection_end = selected_day
        self._refresh_date_picker_grid()

    def _update_date_picker_hint(self) -> None:
        start = self._date_picker_selection_start
        end = self._date_picker_selection_end

        if start is None:
            self._date_picker_hint_var.set(
                "Clique na data inicial e depois na data final. Enter aplica, Esc cancela."
            )
            return

        if end is None:
            start_text = start.strftime("%d/%m/%Y")
            self._date_picker_hint_var.set(
                f"Data inicial: {start_text}. Agora selecione a data final. Enter aplica."
            )
            return

        if end < start:
            start, end = end, start
        start_text = start.strftime("%d/%m/%Y")
        end_text = end.strftime("%d/%m/%Y")
        total_days = (end - start).days + 1
        self._date_picker_hint_var.set(
            f"Periodo selecionado: {start_text} a {end_text} ({total_days} dia(s)). Enter aplica."
        )

    def _set_period_dates(self, start: date, end: date) -> None:
        self._set_period_dates_for_target("pedidos", start, end)

    def _set_estoque_period_dates(self, start: date, end: date) -> None:
        self._set_period_dates_for_target("estoque", start, end)

    def _set_period_dates_for_target(self, target: str, start: date, end: date) -> None:
        if start > end:
            start, end = end, start

        target_start_var, target_end_var = self._period_vars_for_target(target)
        target_start_var.set(start.strftime("%d/%m/%Y"))
        target_end_var.set(end.strftime("%d/%m/%Y"))

        if (
            self._date_picker_window is not None
            and self._date_picker_window.winfo_exists()
            and self._date_picker_target == target
        ):
            self._date_picker_selection_start = start
            self._date_picker_selection_end = end
            self._date_picker_month = start.replace(day=1)
            self._refresh_date_picker_grid()

    def _load_initial_values(self) -> None:
        self._refresh_client_registration_modes()
        self._refresh_client_registration_platforms()
        self._refresh_generator_modes()
        self._refresh_generator_platforms()
        self._refresh_estoque_platform_options()
        if not self.platform_choices:
            if self.config.platforms:
                self.status_var.set("Sem clientes para Pedidos")
                self.log(
                    "Catalogo carregado sem clientes disponiveis para a aba Pedidos. "
                    "Use a aba Clientes para novo cadastro."
                )
            else:
                self.status_var.set("Sem plataformas configuradas")
                self.log("Nenhuma plataforma/remoto carregado. Conecte o servidor na aba Configuracoes.")
            self._update_register_client_button_state()
            self._update_generate_link_button_state()
            return

        first = self.platform_choices[0]
        self.platform_var.set(first.label)
        self.on_platform_change()
        self._refresh_notification_sounds(preserve_current=False)
        self._update_export_sku_button_state()
        self._update_register_client_button_state()
        self._update_generate_link_button_state()

    def _ensure_sounds_directory(self) -> None:
        try:
            SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.log(f"Aviso: nao foi possivel preparar a pasta de sons ({error}).")

    def _load_desktop_settings(self) -> dict[str, object]:
        if not DESKTOP_SETTINGS_PATH.exists():
            return {}

        try:
            raw = DESKTOP_SETTINGS_PATH.read_text(encoding="utf-8")
            loaded = json.loads(raw)
        except (OSError, json.JSONDecodeError) as error:
            self.log(f"Aviso: nao foi possivel ler desktop_settings.json ({error}).")
            return {}

        if not isinstance(loaded, dict):
            self.log("Aviso: desktop_settings.json invalido. Recriando configuracao padrao.")
            return {}
        return loaded

    def _save_desktop_settings(self, settings: dict[str, object]) -> None:
        try:
            DESKTOP_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(settings, indent=2, sort_keys=True)
            DESKTOP_SETTINGS_PATH.write_text(payload, encoding="utf-8")
        except OSError as error:
            self.log(f"Aviso: nao foi possivel salvar desktop_settings.json ({error}).")

    def _saved_notification_sound(self) -> str:
        settings = self._load_desktop_settings()
        value = settings.get("notification_sound")
        if not isinstance(value, str):
            return NO_NOTIFICATION_SOUND
        cleaned = value.strip()
        return cleaned if cleaned else NO_NOTIFICATION_SOUND

    def _persist_notification_sound(self, sound_name: str) -> None:
        settings = self._load_desktop_settings()
        settings["notification_sound"] = "" if sound_name == NO_NOTIFICATION_SOUND else sound_name
        self._save_desktop_settings(settings)

    def _refresh_notification_sounds(self, preserve_current: bool = True) -> None:
        self._ensure_sounds_directory()

        current_choice = self.notification_sound_var.get().strip()
        available_names: set[str] = set()
        for sound_dir in available_sound_dirs():
            if not sound_dir.exists():
                continue
            for path in sound_dir.glob("*.mp3"):
                if path.is_file():
                    available_names.add(path.name)
        available = sorted(available_names)
        options = [NO_NOTIFICATION_SOUND, *available]
        self.notification_sound_options = options
        self.notification_sound_combo.configure(values=options)

        if preserve_current and current_choice in options:
            selected = current_choice
        else:
            selected = self._saved_notification_sound()
            if selected not in options:
                selected = NO_NOTIFICATION_SOUND

        self.notification_sound_var.set(selected)
        self._persist_notification_sound(selected)

    def _on_notification_sound_change(self) -> None:
        selected = self.notification_sound_var.get().strip()
        if selected not in self.notification_sound_options:
            selected = NO_NOTIFICATION_SOUND
            self.notification_sound_var.set(selected)

        self._persist_notification_sound(selected)
        if selected == NO_NOTIFICATION_SOUND:
            self.log("Som de notificacao desativado.")
        else:
            self.log(f"Som de notificacao selecionado: {selected}")

    @staticmethod
    def _mci_error_message(error_code: int) -> str:
        if sys.platform != "win32":
            return f"codigo={error_code}"

        buffer = ctypes.create_unicode_buffer(256)
        result = ctypes.windll.winmm.mciGetErrorStringW(error_code, buffer, len(buffer))
        if result:
            return buffer.value
        return f"codigo={error_code}"

    def _play_notification_sound(self) -> None:
        selected = self.notification_sound_var.get().strip()
        if not selected or selected == NO_NOTIFICATION_SOUND:
            return

        sound_path = self._resolve_sound_file(selected)
        if sound_path is None:
            self.log(f"Aviso: som selecionado nao encontrado ({selected}).")
            return
        if sys.platform != "win32":
            self.log("Aviso: reproducao de mp3 no launcher esta disponivel apenas no Windows.")
            return

        try:
            alias = "cfo_sync_notify"
            ctypes.windll.winmm.mciSendStringW(f"close {alias}", None, 0, 0)

            open_error = ctypes.windll.winmm.mciSendStringW(
                f'open "{sound_path}" type mpegvideo alias {alias}',
                None,
                0,
                0,
            )
            if open_error:
                self.log(
                    "Aviso: nao foi possivel abrir som de notificacao "
                    f"({self._mci_error_message(open_error)})."
                )
                return

            play_error = ctypes.windll.winmm.mciSendStringW(f"play {alias} from 0", None, 0, 0)
            if play_error:
                self.log(
                    "Aviso: nao foi possivel reproduzir som de notificacao "
                    f"({self._mci_error_message(play_error)})."
                )
        except Exception as error:  # noqa: BLE001
            self.log(f"Aviso: erro ao reproduzir som de notificacao ({error}).")

    @staticmethod
    def _resolve_sound_file(sound_name: str) -> Path | None:
        for sound_dir in available_sound_dirs():
            candidate = (sound_dir / sound_name).resolve()
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _flashwindowinfo_struct():
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("hwnd", ctypes.c_void_p),
                ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint),
                ("dwTimeout", ctypes.c_uint),
            ]

        return FLASHWINFO

    def _get_main_window_handle(self) -> int:
        if sys.platform != "win32":
            return 0
        try:
            user32 = ctypes.windll.user32
            hwnd = int(self.root.winfo_id())
            GA_ROOT = 2
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT))
            if root_hwnd:
                return root_hwnd
            parent_hwnd = int(user32.GetParent(hwnd))
            if parent_hwnd:
                return parent_hwnd
            return hwnd
        except Exception:
            return 0

    def _legacy_flash_taskbar_toggle(
        self,
        hwnd: int,
        remaining_toggles: int,
        interval_ms: int = 350,
    ) -> None:
        if sys.platform != "win32" or not hwnd or remaining_toggles <= 0:
            return
        try:
            ctypes.windll.user32.FlashWindow(hwnd, True)
        except Exception:
            return
        self.root.after(
            max(100, int(interval_ms)),
            lambda: self._legacy_flash_taskbar_toggle(
                hwnd=hwnd,
                remaining_toggles=remaining_toggles - 1,
                interval_ms=interval_ms,
            ),
        )

    def _stop_taskbar_flash(self) -> None:
        if sys.platform != "win32":
            return
        try:
            FLASHWINFO = self._flashwindowinfo_struct()
            FLASHW_STOP = 0x00000000
            hwnd = self._get_main_window_handle()
            if not hwnd:
                return
            stop_info = FLASHWINFO(
                cbSize=ctypes.sizeof(FLASHWINFO),
                hwnd=hwnd,
                dwFlags=FLASHW_STOP,
                uCount=0,
                dwTimeout=0,
            )
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(stop_info))
        except Exception:
            return

    def _flash_taskbar_icon(self, duration_ms: int = 4000) -> None:
        if sys.platform != "win32":
            return

        try:
            FLASHWINFO = self._flashwindowinfo_struct()
            FLASHW_TRAY = 0x00000002
            FLASHW_TIMERNOFG = 0x0000000C
            hwnd = self._get_main_window_handle()
            if not hwnd:
                self.log("Aviso: HWND principal nao encontrado para piscar taskbar.")
                return

            flash_info = FLASHWINFO(
                cbSize=ctypes.sizeof(FLASHWINFO),
                hwnd=hwnd,
                dwFlags=FLASHW_TRAY | FLASHW_TIMERNOFG,
                uCount=0,
                dwTimeout=0,
            )
            started = bool(ctypes.windll.user32.FlashWindowEx(ctypes.byref(flash_info)))
            if not started:
                self.log("Aviso: FlashWindowEx nao iniciou; aplicando fallback de flash.")
            self._legacy_flash_taskbar_toggle(hwnd=hwnd, remaining_toggles=8, interval_ms=350)
            self.root.after(max(800, int(duration_ms)), self._stop_taskbar_flash)
        except Exception as error:  # noqa: BLE001
            self.log(f"Aviso: nao foi possivel piscar icone na barra de tarefas ({error}).")

    def _notify_export_completion(self) -> None:
        self.root.after(0, self._play_notification_sound)
        self.root.after(0, self._flash_taskbar_icon)

    def log(self, message: str) -> None:
        self.log_queue.put(message)

    def clear_log(self) -> None:
        while True:
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break

        self.log_box.configure(state=tk.NORMAL)
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _poll_logs(self) -> None:
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_box.configure(state=tk.NORMAL)
                self.log_box.insert(tk.END, f"{msg}\n")
                self.log_box.see(tk.END)
                self.log_box.configure(state=tk.DISABLED)
        except queue.Empty:
            pass

        self.root.after(120, self._poll_logs)

    def _apply_native_titlebar_color(self) -> None:
        if sys.platform != "win32":
            return

        try:
            hwnd = self.root.winfo_id()
            dwmapi = ctypes.windll.dwmapi

            dark_mode = ctypes.c_int(1)
            caption_color = ctypes.c_int(self._hex_to_colorref(COLOR_HEADER))
            text_color = ctypes.c_int(self._hex_to_colorref(COLOR_TEXT))

            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36

            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(dark_mode),
                ctypes.sizeof(dark_mode),
            )
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_CAPTION_COLOR,
                ctypes.byref(caption_color),
                ctypes.sizeof(caption_color),
            )
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_TEXT_COLOR,
                ctypes.byref(text_color),
                ctypes.sizeof(text_color),
            )
        except Exception:
            # Em sistemas sem suporte, mantem a barra nativa padrao.
            return

    @staticmethod
    def _hex_to_colorref(hex_color: str) -> int:
        color = hex_color.strip().lstrip("#")
        if len(color) != 6:
            return 0
        red = int(color[0:2], 16)
        green = int(color[2:4], 16)
        blue = int(color[4:6], 16)
        return (blue << 16) | (green << 8) | red

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if busy:
            self.btn_collect.configure(state=tk.DISABLED)
            self.btn_export.configure(state=tk.DISABLED)
            self.btn_export_sku.configure(state=tk.DISABLED, cursor="no")
            self.btn_update_app.configure(state=tk.DISABLED)
            self.btn_open_changelog.configure(state=tk.DISABLED)
            self.btn_connect_server.configure(state=tk.DISABLED)
            self.btn_disconnect_server.configure(state=tk.DISABLED)
            if self.btn_use_local_secrets is not None:
                self.btn_use_local_secrets.configure(state=tk.DISABLED)
            self.server_url_entry.configure(state=tk.DISABLED)
            self.server_token_entry.configure(state=tk.DISABLED)
            self.btn_select_all_sub_clients.configure(state=tk.DISABLED)
            self.btn_clear_sub_clients.configure(state=tk.DISABLED)
            self.sub_client_listbox.configure(state=tk.DISABLED)
            self.btn_estoque_select_all_sub_clients.configure(state=tk.DISABLED)
            self.btn_estoque_clear_sub_clients.configure(state=tk.DISABLED)
            self.estoque_sub_client_listbox.configure(state=tk.DISABLED)
            self.notification_sound_combo.configure(state=tk.DISABLED)
            self.btn_refresh_sounds.configure(state=tk.DISABLED)
            self.btn_refresh_server_secrets.configure(state=tk.DISABLED)
            self.btn_load_server_secret.configure(state=tk.DISABLED)
            self.btn_save_server_secret.configure(state=tk.DISABLED)
            self.server_secret_editor.configure(state=tk.DISABLED)
            self.btn_search_sku.configure(state=tk.DISABLED)
            self.sku_order_entry.configure(state=tk.DISABLED)
            self.btn_pick_period.configure(state=tk.DISABLED)
            self.update_mercado_livre_categories_check.configure(state=tk.DISABLED)
            self.btn_estoque_pick_period.configure(state=tk.DISABLED)
            self.client_registration_mode_combo.configure(state=tk.DISABLED)
            self.client_registration_platform_combo.configure(state=tk.DISABLED)
            self.client_registration_client_combo.configure(state=tk.DISABLED)
            self.client_registration_client_entry.configure(state=tk.DISABLED)
            self.client_registration_gid_entry.configure(state=tk.DISABLED)
            self.btn_register_client.configure(state=tk.DISABLED, cursor="no")
            self.btn_refresh_catalog.configure(state=tk.DISABLED)
            for entry in self.client_registration_dynamic_entries:
                entry.configure(state=tk.DISABLED)
            for combo in self.client_registration_dynamic_combos:
                combo.configure(state=tk.DISABLED)
            self.generator_mode_combo.configure(state=tk.DISABLED)
            self.generator_platform_combo.configure(state=tk.DISABLED)
            self.generator_client_combo.configure(state=tk.DISABLED)
            self.generator_client_entry.configure(state=tk.DISABLED)
            self.generator_gid_entry.configure(state=tk.DISABLED)
            self.btn_generate_link.configure(state=tk.DISABLED, cursor="no")
            self.btn_open_generated_link.configure(state=tk.DISABLED, cursor="no")
            self.btn_copy_generated_link.configure(state=tk.DISABLED, cursor="no")
            for entry in self.generator_dynamic_entries:
                entry.configure(state=tk.DISABLED)
            for combo in self.generator_dynamic_combos:
                combo.configure(state=tk.DISABLED)
            return

        self.btn_collect.configure(state=tk.NORMAL)
        self._update_export_sku_button_state()
        self.btn_update_app.configure(state=tk.NORMAL)
        self.btn_open_changelog.configure(state=tk.NORMAL)
        self.btn_connect_server.configure(state=tk.NORMAL)
        self.btn_disconnect_server.configure(state=tk.NORMAL)
        self._refresh_local_fallback_visibility()
        if self.btn_use_local_secrets is not None:
            local_state = tk.NORMAL if self._has_local_secrets_files() else tk.DISABLED
            self.btn_use_local_secrets.configure(state=local_state)
        self.server_url_entry.configure(state=tk.NORMAL)
        self.server_token_entry.configure(state=tk.NORMAL)

        has_sub_clients = bool(self.sub_client_options)
        controls_state = tk.NORMAL if has_sub_clients else tk.DISABLED
        has_estoque_sub_clients = bool(self.estoque_sub_client_options)
        estoque_controls_state = tk.NORMAL if has_estoque_sub_clients else tk.DISABLED
        self.btn_select_all_sub_clients.configure(state=controls_state)
        self.btn_clear_sub_clients.configure(state=controls_state)
        self.sub_client_listbox.configure(state=controls_state)
        self.btn_estoque_select_all_sub_clients.configure(state=estoque_controls_state)
        self.btn_estoque_clear_sub_clients.configure(state=estoque_controls_state)
        self.estoque_sub_client_listbox.configure(state=estoque_controls_state)
        self.notification_sound_combo.configure(state="readonly")
        self.btn_refresh_sounds.configure(state=tk.NORMAL)
        self._sync_server_secret_controls()
        sku_state = tk.NORMAL if self._platform_supports_sku_workflow() else tk.DISABLED
        self.btn_search_sku.configure(state=sku_state)
        self.sku_order_entry.configure(state=sku_state)
        self.btn_pick_period.configure(state=tk.NORMAL)
        self._sync_mercado_livre_categories_checkbox()
        self.btn_estoque_pick_period.configure(state=tk.NORMAL)
        self._sync_client_registration_input_states()
        self._sync_generator_input_states()

    def _run_task(self, action_name: str, target) -> None:
        if self.busy:
            return

        def runner() -> None:
            self._set_busy(True)
            self.status_var.set(f"Executando: {action_name}")
            try:
                target()
                self.status_var.set("Concluido")
            except Exception as error:  # noqa: BLE001
                self.status_var.set("Erro")
                self.log(f"ERRO: {error}")
                self.root.after(0, lambda: messagebox.showerror("Erro", str(error)))
            finally:
                self._set_busy(False)

        threading.Thread(target=runner, daemon=True).start()

    def _on_tab_changed(self) -> None:
        if self.busy:
            return
        self._refresh_local_fallback_visibility()
        self._update_export_sku_button_state()
        self._update_register_client_button_state()
        self._update_generate_link_button_state()

    def _platform_supports_sku_workflow(self) -> bool:
        choice = self.choice_by_label.get(self.platform_var.get())
        if choice is None:
            return False
        behavior = self.platform_ui_registry.get(choice.platform_key)
        return behavior is not None and behavior.supports_sku_workflow

    def _is_sku_tab_active(self) -> bool:
        selected_tab_id = self.tabs.select()
        return selected_tab_id == str(self.sku_tab)

    def _is_pedidos_tab_active(self) -> bool:
        selected_tab_id = self.tabs.select()
        return selected_tab_id == str(self.pedidos_tab)

    def _is_estoque_tab_active(self) -> bool:
        selected_tab_id = self.tabs.select()
        return selected_tab_id == str(self.estoque_tab)

    def _update_export_sku_button_state(self) -> None:
        can_export_pedidos = self._is_pedidos_tab_active()
        can_export_estoque = self._is_estoque_tab_active()

        self.btn_export.configure(
            state=tk.NORMAL if can_export_pedidos else tk.DISABLED,
            style="Secondary.TButton" if can_export_pedidos else "Sku.TButton",
            cursor="hand2" if can_export_pedidos else "no",
        )
        self.btn_export_sku.configure(
            state=tk.NORMAL if can_export_estoque else tk.DISABLED,
            cursor="hand2" if can_export_estoque else "no",
        )

    def _sync_client_registration_fields_scrollregion(self) -> None:
        if self.client_registration_fields_canvas is None:
            return
        bbox = self.client_registration_fields_canvas.bbox("all")
        self.client_registration_fields_canvas.configure(
            scrollregion=bbox if bbox is not None else (0, 0, 0, 0)
        )

    def _sync_client_registration_fields_width(self, width: int | None = None) -> None:
        if self.client_registration_fields_canvas is None or self.client_registration_fields_window_id is None:
            return
        target_width = width if width is not None else self.client_registration_fields_canvas.winfo_width()
        if target_width <= 0:
            return
        self.client_registration_fields_canvas.itemconfigure(
            self.client_registration_fields_window_id,
            width=target_width,
        )

    def _sync_client_registration_input_states(self) -> None:
        if self.busy:
            return
        registration_enabled = self.remote_client is not None
        registration_mode_state = (
            "readonly"
            if registration_enabled and self.client_registration_mode_map
            else tk.DISABLED
        )
        self.client_registration_mode_combo.configure(state=registration_mode_state)
        registration_platform_state = (
            "readonly"
            if registration_enabled and self.client_registration_platform_map
            else tk.DISABLED
        )
        self.client_registration_platform_combo.configure(state=registration_platform_state)

        mode = self._client_registration_mode()
        if mode == "new_client":
            self.client_registration_client_combo.configure(state=tk.DISABLED)
            self.client_registration_client_entry.configure(
                state=tk.NORMAL if registration_enabled else tk.DISABLED
            )
        else:
            registration_client_state = (
                "readonly"
                if registration_enabled and bool(self.client_registration_clients)
                else tk.DISABLED
            )
            self.client_registration_client_combo.configure(state=registration_client_state)
            self.client_registration_client_entry.configure(state=tk.DISABLED)

        registration_entry_state = tk.NORMAL if registration_enabled else tk.DISABLED
        self.client_registration_gid_entry.configure(state=registration_entry_state)
        for entry in self.client_registration_dynamic_entries:
            entry.configure(state=registration_entry_state)
        for combo in self.client_registration_dynamic_combos:
            combo.configure(state="readonly" if registration_enabled else tk.DISABLED)
        self.btn_refresh_catalog.configure(
            state=tk.NORMAL if registration_enabled else tk.DISABLED
        )

    def _update_register_client_button_state(self) -> None:
        has_platform = bool(
            self.client_registration_platform_map.get(
                self.client_registration_platform_var.get().strip(),
                "",
            )
        )
        mode = self._client_registration_mode()
        if mode == "new_client":
            has_client = bool(self.client_registration_client_name_var.get().strip())
        else:
            has_client = bool(self.client_registration_client_var.get().strip())
        can_register = has_platform and has_client and self.remote_client is not None and not self.busy
        self.btn_register_client.configure(
            state=tk.NORMAL if can_register else tk.DISABLED,
            cursor="hand2" if can_register else "no",
        )

    def _client_registration_mode(self) -> str:
        mode_label = self.client_registration_mode_var.get().strip()
        mode = self.client_registration_mode_map.get(mode_label, "").strip()
        return mode or "existing_client"

    def _sync_generator_input_states(self) -> None:
        if self.busy:
            return
        enabled = self.remote_client is not None
        mode_state = "readonly" if enabled and self.generator_mode_map else tk.DISABLED
        platform_state = "readonly" if enabled and self.generator_platform_map else tk.DISABLED
        self.generator_mode_combo.configure(state=mode_state)
        self.generator_platform_combo.configure(state=platform_state)

        mode = self._generator_mode()
        if mode == "new_client":
            self.generator_client_combo.configure(state=tk.DISABLED)
            self.generator_client_entry.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        else:
            client_state = "readonly" if enabled and bool(self.generator_clients) else tk.DISABLED
            self.generator_client_combo.configure(state=client_state)
            self.generator_client_entry.configure(state=tk.DISABLED)

        entry_state = tk.NORMAL if enabled else tk.DISABLED
        self.generator_gid_entry.configure(state=entry_state)
        for entry in self.generator_dynamic_entries:
            entry.configure(state=entry_state)
        for combo in self.generator_dynamic_combos:
            combo.configure(state="readonly" if enabled else tk.DISABLED)

        self._update_generate_link_button_state()

    def _update_generate_link_button_state(self) -> None:
        has_platform = bool(
            self.generator_platform_map.get(
                self.generator_platform_var.get().strip(),
                "",
            )
        )
        mode = self._generator_mode()
        if mode == "new_client":
            has_client = bool(self.generator_client_name_var.get().strip())
        else:
            has_client = bool(self.generator_client_var.get().strip())
        has_gid = bool("".join(ch for ch in self.generator_gid_var.get().strip() if ch.isdigit()))
        can_generate = (
            has_platform
            and has_client
            and has_gid
            and self._generator_required_fields_filled()
            and self.remote_client is not None
            and not self.busy
        )
        self.btn_generate_link.configure(
            state=tk.NORMAL if can_generate else tk.DISABLED,
            cursor="hand2" if can_generate else "no",
        )

        has_link = bool(self.generator_link_var.get().strip()) and not self.busy
        self.btn_open_generated_link.configure(
            state=tk.NORMAL if has_link else tk.DISABLED,
            cursor="hand2" if has_link else "no",
        )
        self.btn_copy_generated_link.configure(
            state=tk.NORMAL if has_link else tk.DISABLED,
            cursor="hand2" if has_link else "no",
        )

    def _generator_mode(self) -> str:
        mode_label = self.generator_mode_var.get().strip()
        mode = self.generator_mode_map.get(mode_label, "").strip()
        return mode or "existing_client"

    def _generator_required_fields_filled(self) -> bool:
        for field in self.generator_field_specs:
            if not bool(field.get("required")):
                continue
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            kind = str(field.get("kind") or "text").strip().lower()
            if kind == "bool":
                continue
            raw = self.generator_field_vars.get(name)
            if raw is None:
                return False
            if not str(raw.get() or "").strip():
                return False
        return True

    def _get_current_choice(self) -> PlatformChoice:
        choice = self.choice_by_label.get(self.platform_var.get())
        if choice is None:
            raise ValueError("Selecione uma plataforma valida.")
        return choice

    def _resolve_resource_for_choice(self, choice: PlatformChoice) -> ResourceConfig:
        platform = next((item for item in self.config.platforms if item.key == choice.platform_key), None)
        if platform is None:
            raise ValueError(f"Plataforma nao encontrada: {choice.platform_key}")

        resource = next((item for item in platform.resources if item.name == choice.resource_name), None)
        if resource is None:
            raise ValueError(f"Recurso nao encontrado: {choice.platform_key}/{choice.resource_name}")
        return resource

    def _resolve_resource_by_name(self, platform_key: str, resource_name: str) -> ResourceConfig:
        platform = next((item for item in self.config.platforms if item.key == platform_key), None)
        if platform is None:
            raise ValueError(f"Plataforma nao encontrada: {platform_key}")

        resource = next((item for item in platform.resources if item.name == resource_name), None)
        if resource is None:
            raise ValueError(f"Recurso nao encontrado: {platform_key}/{resource_name}")
        return resource

    def _render_sku_preview(self) -> None:
        self.sku_tree.delete(*self.sku_tree.get_children())
        for row in self.sku_preview_rows:
            self.sku_tree.insert(
                "",
                tk.END,
                values=(
                    row.get("number", ""),
                    row.get("created_at", ""),
                    row.get("sku_id", ""),
                    row.get("item_sku", ""),
                    row.get("quantity", 0),
                    f"{float(row.get('price_cost', 0.0)):.2f}",
                ),
            )

    def _clear_sku_preview(self) -> None:
        self.sku_preview_rows = []
        self._render_sku_preview()

    def search_sku(self) -> None:
        def task() -> None:
            choice = self._get_current_choice()
            behavior = self.platform_ui_registry.get(choice.platform_key)
            if behavior is None or not behavior.supports_sku_workflow:
                raise ValueError(f"Busca SKU nao disponivel para plataforma: {choice.platform_key}")

            client = self.client_var.get().strip()
            if not client:
                raise ValueError("Selecione um cliente.")

            order_number = self.sku_order_number_var.get().strip()
            if not order_number:
                raise ValueError("Informe o numero do pedido para buscar SKU.")

            selected_alias_names = self._selected_sub_clients()
            rows, found_aliases = behavior.search_sku_rows(
                company_name=client,
                order_number=order_number,
                selected_sub_clients=selected_alias_names,
            )
            if not rows:
                self.root.after(0, self._clear_sku_preview)
                raise ValueError(f"Pedido {order_number} nao encontrado nos aliases selecionados.")

            self.sku_preview_rows = rows
            self.root.after(0, self._render_sku_preview)
            self.log(
                f"SKU encontrado: pedido={order_number} | linhas={len(self.sku_preview_rows)} | "
                f"aliases={', '.join(found_aliases)}"
            )

        self._run_task("Buscar SKU", task)

    def _current_selection(self) -> tuple[PlatformChoice, str, list[str] | None, str, str]:
        if self._is_estoque_tab_active():
            choice = self.estoque_choice_by_label.get(self.estoque_platform_var.get())
            client = self.estoque_client_var.get().strip()
            sub_clients = self._selected_estoque_sub_clients()
            start_date_raw = self.estoque_start_date_var.get().strip()
            end_date_raw = self.estoque_end_date_var.get().strip()
        else:
            choice = self.choice_by_label.get(self.platform_var.get())
            client = self.client_var.get().strip()
            sub_clients = self._selected_sub_clients()
            start_date_raw = self.start_date_var.get().strip()
            end_date_raw = self.end_date_var.get().strip()

        if choice is None:
            raise ValueError("Selecione uma plataforma valida.")

        if not client:
            raise ValueError("Selecione um cliente.")

        start_date_obj = self._parse_ui_date(start_date_raw)
        end_date_obj = self._parse_ui_date(end_date_raw)
        start_date_obj, end_date_obj = self._normalize_monthly_period(choice, start_date_obj, end_date_obj)

        start_date = start_date_obj.isoformat()
        end_date = end_date_obj.isoformat()

        if start_date > end_date:
            raise ValueError("Data inicial nao pode ser maior que data final.")

        return choice, client, sub_clients, start_date, end_date

    @staticmethod
    def _parse_ui_date(raw_value: str) -> date:
        value = raw_value.strip()
        if not value:
            raise ValueError("Preencha as datas no formato DD/MM/AAAA.")

        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

        raise ValueError("Data invalida. Use o formato DD/MM/AAAA (ex.: 27/02/2026).")

    def _normalize_monthly_period(
        self,
        choice: PlatformChoice,
        start_date: date,
        end_date: date,
    ) -> tuple[date, date]:
        behavior = self.platform_ui_registry.get(choice.platform_key)
        if behavior is None:
            return start_date, end_date
        return behavior.normalize_period(
            resource_name=choice.resource_name,
            start_date=start_date,
            end_date=end_date,
            today=date.today(),
        )

    def on_platform_change(self) -> None:
        choice = self.choice_by_label[self.platform_var.get()]
        clients = self._clients_for_platform(choice.platform_key)
        self.client_combo.configure(values=clients)
        self._clear_sku_preview()
        self._sync_mercado_livre_categories_checkbox()
        if clients:
            self.client_var.set(clients[0])
            self.on_client_change()
        else:
            self.client_var.set("")
            self._set_sub_client_options([])
            self.log("Nenhum cliente configurado para esta plataforma.")
        self._update_export_sku_button_state()
        if not self.busy:
            sku_state = tk.NORMAL if self._platform_supports_sku_workflow() else tk.DISABLED
            self.btn_search_sku.configure(state=sku_state)
            self.sku_order_entry.configure(state=sku_state)

    def _sync_mercado_livre_categories_checkbox(self) -> None:
        if not hasattr(self, "mercado_livre_categories_card"):
            return

        choice = self.choice_by_label.get(self.platform_var.get())
        visible = choice is not None and choice.platform_key == "mercado_livre"
        if visible:
            self.mercado_livre_categories_card.pack(fill=tk.X, pady=(12, 0))
            self.update_mercado_livre_categories_check.configure(
                state=tk.DISABLED if self.busy else tk.NORMAL
            )
            return

        self.update_mercado_livre_categories_var.set(False)
        self.mercado_livre_categories_card.pack_forget()

    def on_client_change(self) -> None:
        choice = self.choice_by_label[self.platform_var.get()]
        client = self.client_var.get().strip()
        options: list[str] = []
        self._clear_sku_preview()

        try:
            if self.remote_client is not None:
                options.extend(self.remote_catalog_sub_clients.get((choice.platform_key, client), []))
            else:
                behavior = self.platform_ui_registry.get(choice.platform_key)
                if behavior is not None:
                    options.extend(behavior.sub_client_names(client))
        except Exception as error:  # noqa: BLE001
            self.log(f"Aviso ao carregar filiais/aliases: {error}")

        self._set_sub_client_options(options)
        if options:
            self.log(f"Filiais/Aliases carregadas para {client}: {', '.join(options)}")
        else:
            self.log(f"Nenhuma filial/alias cadastrada para {client}.")
        self._update_export_sku_button_state()

    def _clients_for_estoque_choice(self, choice: PlatformChoice) -> list[str]:
        if choice.platform_key == "yampi" and self.yampi_estoque_credentials_store is not None:
            return self.yampi_estoque_credentials_store.companies()

        resource = self._resolve_resource_for_choice(choice)
        configured_clients = list(resource.client_tabs.keys())
        if configured_clients:
            return sorted(configured_clients)
        return self._clients_for_platform(choice.platform_key)

    def _refresh_estoque_platform_options(self) -> None:
        self.estoque_platform_choices = self._build_estoque_platform_choices()
        self.estoque_choice_by_label = {
            choice.label: choice for choice in self.estoque_platform_choices
        }
        labels = [choice.label for choice in self.estoque_platform_choices]
        self.estoque_platform_combo.configure(values=labels)

        current = self.estoque_platform_var.get().strip()
        if current in self.estoque_choice_by_label:
            self.estoque_platform_var.set(current)
            self.on_estoque_platform_change()
            return

        if labels:
            self.estoque_platform_var.set(labels[0])
            self.on_estoque_platform_change()
            return

        self.estoque_platform_var.set("")
        self.estoque_client_var.set("")
        self.estoque_client_combo.configure(values=[])
        self._set_estoque_sub_client_options([])

    def on_estoque_platform_change(self) -> None:
        choice = self.estoque_choice_by_label.get(self.estoque_platform_var.get().strip())
        if choice is None:
            self.estoque_client_combo.configure(values=[])
            self.estoque_client_var.set("")
            self._set_estoque_sub_client_options([])
            return

        clients = self._clients_for_estoque_choice(choice)
        self.estoque_client_combo.configure(values=clients)
        if clients:
            self.estoque_client_var.set(clients[0])
            self.on_estoque_client_change()
        else:
            self.estoque_client_var.set("")
            self._set_estoque_sub_client_options([])
            self.log("Nenhum cliente configurado para esta plataforma (Estoque).")

    def on_estoque_client_change(self) -> None:
        choice = self.estoque_choice_by_label.get(self.estoque_platform_var.get().strip())
        if choice is None:
            self._set_estoque_sub_client_options([])
            return

        client = self.estoque_client_var.get().strip()
        options: list[str] = []

        def extend_fallback_options() -> None:
            if self.remote_client is not None:
                options.extend(self.remote_catalog_sub_clients.get((choice.platform_key, client), []))
                return
            behavior = self.platform_ui_registry.get(choice.platform_key)
            if behavior is not None:
                options.extend(behavior.sub_client_names(client))

        try:
            if choice.platform_key == "yampi":
                if self.yampi_estoque_credentials_store is not None:
                    options.extend(self.yampi_estoque_credentials_store.alias_names_for_company(client))
                else:
                    extend_fallback_options()
            else:
                extend_fallback_options()
        except Exception as error:  # noqa: BLE001
            self.log(f"Aviso ao carregar filiais/aliases de estoque: {error}")
            if choice.platform_key == "yampi" and not options:
                try:
                    extend_fallback_options()
                except Exception:
                    pass

        self._set_estoque_sub_client_options(options)
        if options:
            self.log(f"Filiais/Aliases de estoque para {client}: {', '.join(options)}")
        else:
            self.log(f"Nenhuma filial/alias de estoque cadastrada para {client}.")

    def _set_sub_client_options(self, options: list[str]) -> None:
        self.sub_client_options = options
        # Permite atualizar os itens mesmo quando o listbox estava desabilitado
        # pelo cliente anterior sem aliases.
        self.sub_client_listbox.configure(state=tk.NORMAL)
        self.sub_client_listbox.delete(0, tk.END)
        for option in options:
            self.sub_client_listbox.insert(tk.END, option)

        if not options:
            self.sub_client_listbox.configure(state=tk.DISABLED)
            self.btn_select_all_sub_clients.configure(state=tk.DISABLED)
            self.btn_clear_sub_clients.configure(state=tk.DISABLED)
            self.sub_client_summary_var.set(ALL_SUB_CLIENTS)
            return

        if not self.busy:
            self.sub_client_listbox.configure(state=tk.NORMAL)
            self.btn_select_all_sub_clients.configure(state=tk.NORMAL)
            self.btn_clear_sub_clients.configure(state=tk.NORMAL)

        self._select_all_sub_clients()

    def _select_all_sub_clients(self) -> None:
        if not self.sub_client_options:
            self.sub_client_summary_var.set(ALL_SUB_CLIENTS)
            return

        self.sub_client_listbox.selection_set(0, tk.END)
        self._update_sub_client_summary()

    def _clear_sub_clients(self) -> None:
        self.sub_client_listbox.selection_clear(0, tk.END)
        self._update_sub_client_summary()

    def _selected_sub_clients(self) -> list[str] | None:
        if not self.sub_client_options:
            return None

        selected_indexes = list(self.sub_client_listbox.curselection())
        if not selected_indexes:
            raise ValueError("Selecione ao menos uma filial/alias ou clique em Todos.")

        if len(selected_indexes) == len(self.sub_client_options):
            return None

        return [self.sub_client_options[index] for index in selected_indexes]

    def _update_sub_client_summary(self) -> None:
        if not self.sub_client_options:
            self.sub_client_summary_var.set(ALL_SUB_CLIENTS)
            return

        selected_indexes = list(self.sub_client_listbox.curselection())
        selected_count = len(selected_indexes)
        total = len(self.sub_client_options)

        if total == 1:
            if selected_count == 0:
                self.sub_client_summary_var.set("Nenhuma selecionada")
                return
            self.sub_client_summary_var.set(self.sub_client_options[0])
            return

        if selected_count == 0:
            self.sub_client_summary_var.set("Nenhuma selecionada")
            return

        if selected_count == total:
            self.sub_client_summary_var.set(ALL_SUB_CLIENTS)
            return

        selected_names = [self.sub_client_options[index] for index in selected_indexes]
        if selected_count <= 3:
            self.sub_client_summary_var.set(", ".join(selected_names))
            return

        self.sub_client_summary_var.set(f"{selected_count} selecionadas")

    def _set_estoque_sub_client_options(self, options: list[str]) -> None:
        self.estoque_sub_client_options = options
        self.estoque_sub_client_listbox.configure(state=tk.NORMAL)
        self.estoque_sub_client_listbox.delete(0, tk.END)
        for option in options:
            self.estoque_sub_client_listbox.insert(tk.END, option)

        if not options:
            self.estoque_sub_client_listbox.configure(state=tk.DISABLED)
            self.btn_estoque_select_all_sub_clients.configure(state=tk.DISABLED)
            self.btn_estoque_clear_sub_clients.configure(state=tk.DISABLED)
            self.estoque_sub_client_summary_var.set(ALL_SUB_CLIENTS)
            return

        if not self.busy:
            self.estoque_sub_client_listbox.configure(state=tk.NORMAL)
            self.btn_estoque_select_all_sub_clients.configure(state=tk.NORMAL)
            self.btn_estoque_clear_sub_clients.configure(state=tk.NORMAL)

        self._select_all_estoque_sub_clients()

    def _select_all_estoque_sub_clients(self) -> None:
        if not self.estoque_sub_client_options:
            self.estoque_sub_client_summary_var.set(ALL_SUB_CLIENTS)
            return
        self.estoque_sub_client_listbox.selection_set(0, tk.END)
        self._update_estoque_sub_client_summary()

    def _clear_estoque_sub_clients(self) -> None:
        self.estoque_sub_client_listbox.selection_clear(0, tk.END)
        self._update_estoque_sub_client_summary()

    def _selected_estoque_sub_clients(self) -> list[str] | None:
        if not self.estoque_sub_client_options:
            return None

        selected_indexes = list(self.estoque_sub_client_listbox.curselection())
        if not selected_indexes:
            raise ValueError("Selecione ao menos uma filial/alias ou clique em Todos (Estoque).")

        if len(selected_indexes) == len(self.estoque_sub_client_options):
            return None

        return [self.estoque_sub_client_options[index] for index in selected_indexes]

    def _update_estoque_sub_client_summary(self) -> None:
        if not self.estoque_sub_client_options:
            self.estoque_sub_client_summary_var.set(ALL_SUB_CLIENTS)
            return

        selected_indexes = list(self.estoque_sub_client_listbox.curselection())
        selected_count = len(selected_indexes)
        total = len(self.estoque_sub_client_options)

        if total == 1:
            if selected_count == 0:
                self.estoque_sub_client_summary_var.set("Nenhuma selecionada")
                return
            self.estoque_sub_client_summary_var.set(self.estoque_sub_client_options[0])
            return

        if selected_count == 0:
            self.estoque_sub_client_summary_var.set("Nenhuma selecionada")
            return

        if selected_count == total:
            self.estoque_sub_client_summary_var.set(ALL_SUB_CLIENTS)
            return

        selected_names = [self.estoque_sub_client_options[index] for index in selected_indexes]
        if selected_count <= 3:
            self.estoque_sub_client_summary_var.set(", ".join(selected_names))
            return

        self.estoque_sub_client_summary_var.set(f"{selected_count} selecionadas")

    def _refresh_client_registration_modes(self) -> None:
        labels = [label for label, _mode in CLIENT_REGISTRATION_MODE_OPTIONS]
        mapping = {label: mode for label, mode in CLIENT_REGISTRATION_MODE_OPTIONS}
        current_label = self.client_registration_mode_var.get().strip()

        self.client_registration_mode_map = mapping
        self.client_registration_mode_combo.configure(values=labels)

        if current_label in mapping:
            self.client_registration_mode_var.set(current_label)
        elif labels:
            self.client_registration_mode_var.set(labels[0])
        else:
            self.client_registration_mode_var.set("")

    def _on_client_registration_mode_change(self) -> None:
        mode = self._client_registration_mode()
        if mode == "new_client":
            self.client_registration_client_label.configure(text="Novo cliente")
            self.client_registration_client_combo.grid_remove()
            self.client_registration_client_entry.grid()
        else:
            self.client_registration_client_label.configure(text="Cliente")
            self.client_registration_client_entry.grid_remove()
            self.client_registration_client_combo.grid()
        self._sync_client_registration_input_states()
        self._update_register_client_button_state()

    def _refresh_generator_modes(self) -> None:
        labels = [label for label, _mode in CLIENT_REGISTRATION_MODE_OPTIONS]
        mapping = {label: mode for label, mode in CLIENT_REGISTRATION_MODE_OPTIONS}
        current_label = self.generator_mode_var.get().strip()

        self.generator_mode_map = mapping
        self.generator_mode_combo.configure(values=labels)

        if current_label in mapping:
            self.generator_mode_var.set(current_label)
        elif labels:
            self.generator_mode_var.set(labels[0])
        else:
            self.generator_mode_var.set("")

    def _on_generator_mode_change(self) -> None:
        self.generator_link_var.set("")
        mode = self._generator_mode()
        if mode == "new_client":
            self.generator_client_label.configure(text="Novo cliente")
            self.generator_client_combo.grid_remove()
            self.generator_client_entry.grid()
        else:
            self.generator_client_label.configure(text="Cliente")
            self.generator_client_entry.grid_remove()
            self.generator_client_combo.grid()
        self._sync_generator_input_states()
        self._update_generate_link_button_state()

    def _refresh_generator_platforms(self) -> None:
        available_platforms = [
            platform
            for platform in self.config.platforms
            if platform.key in GENERATOR_SCHEMAS
        ]

        options: list[str] = []
        mapping: dict[str, str] = {}
        repeated_labels: set[str] = set()

        for platform in available_platforms:
            label = str(platform.label or platform.key).strip() or platform.key
            if label in mapping:
                repeated_labels.add(label)
                continue
            mapping[label] = platform.key
            options.append(label)

        if repeated_labels:
            options = []
            mapping = {}
            for platform in available_platforms:
                base_label = str(platform.label or platform.key).strip() or platform.key
                label = base_label if base_label not in repeated_labels else f"{base_label} ({platform.key})"
                mapping[label] = platform.key
                options.append(label)

        current_label = self.generator_platform_var.get().strip()
        self.generator_platform_map = mapping
        self.generator_platform_combo.configure(values=options)

        if not options:
            self.generator_platform_var.set("")
            self.generator_clients = []
            self.generator_client_var.set("")
            self.generator_client_name_var.set("")
            self.generator_client_combo.configure(values=[])
            self.generator_field_specs = []
            self.generator_field_vars = {}
            self._render_generator_fields([])
            self._sync_generator_input_states()
            self._update_generate_link_button_state()
            return

        if current_label in mapping:
            self.generator_platform_var.set(current_label)
        else:
            self.generator_platform_var.set(options[0])
        self._on_generator_platform_change()
        self._on_generator_mode_change()
        self._sync_generator_input_states()

    def _on_generator_platform_change(self) -> None:
        self.generator_link_var.set("")
        platform_key = self.generator_platform_map.get(
            self.generator_platform_var.get().strip(),
            "",
        )
        self._refresh_generator_clients(platform_key)
        schema = self._generator_schema_for_platform(platform_key)
        self.generator_field_specs = schema
        self._render_generator_fields(schema)
        self._sync_generator_input_states()
        self._update_generate_link_button_state()

    def _refresh_generator_clients(self, platform_key: str) -> None:
        clients = self._clients_for_platform(platform_key) if platform_key else []
        self.generator_clients = list(clients)
        self.generator_client_combo.configure(values=self.generator_clients)
        current_client = self.generator_client_var.get().strip()
        if current_client in self.generator_clients:
            self.generator_client_var.set(current_client)
            return
        if self.generator_clients:
            self.generator_client_var.set(self.generator_clients[0])
            return
        self.generator_client_var.set("")

    @staticmethod
    def _generator_schema_for_platform(platform_key: str) -> list[dict[str, object]]:
        return list(GENERATOR_SCHEMAS.get(platform_key, []))

    def _render_generator_fields(self, schema: list[dict[str, object]]) -> None:
        for child in self.generator_fields_frame.winfo_children():
            child.destroy()
        self.generator_dynamic_entries = []
        self.generator_dynamic_combos = []
        self.generator_field_vars = {}

        if not schema:
            ttk.Label(
                self.generator_fields_frame,
                text="Plataforma sem parametros adicionais.",
                style="Field.TLabel",
            ).grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=2)
            return

        for index, field in enumerate(schema):
            row = index * 2
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            label = str(field.get("label") or name).strip()
            kind = str(field.get("kind") or "text").strip().lower()
            default_value = str(field.get("default") or "").strip()
            required = bool(field.get("required"))
            help_text = str(field.get("help") or "").strip()

            ttk.Label(
                self.generator_fields_frame,
                text=f"{label} *" if required else label,
                style="Field.TLabel",
            ).grid(row=row, column=0, sticky=tk.W, padx=(0, 8), pady=2)

            if kind == "bool":
                var = tk.StringVar(value=default_value or "Nao")
                combo = ttk.Combobox(
                    self.generator_fields_frame,
                    textvariable=var,
                    values=["Sim", "Nao"],
                    state="readonly",
                    style="Dark.TCombobox",
                    width=22,
                )
                combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self.generator_dynamic_combos.append(combo)
                self.generator_field_vars[name] = var
                var.trace_add("write", lambda *_: self._update_generate_link_button_state())
                if help_text:
                    ttk.Label(
                        self.generator_fields_frame,
                        text=help_text,
                        style="Field.TLabel",
                        wraplength=420,
                        justify=tk.LEFT,
                    ).grid(row=row + 1, column=1, sticky=tk.W, pady=(0, 2))
                continue

            var = tk.StringVar(value=default_value)
            show_char = "*" if bool(field.get("secret")) else ""
            entry = ttk.Entry(
                self.generator_fields_frame,
                textvariable=var,
                style="Dark.TEntry",
                show=show_char,
            )
            entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
            self.generator_dynamic_entries.append(entry)
            self.generator_field_vars[name] = var
            var.trace_add("write", lambda *_: self._update_generate_link_button_state())
            if help_text:
                ttk.Label(
                    self.generator_fields_frame,
                    text=help_text,
                    style="Field.TLabel",
                    wraplength=420,
                    justify=tk.LEFT,
                ).grid(row=row + 1, column=1, sticky=tk.W, pady=(0, 2))

        self.generator_fields_frame.columnconfigure(0, minsize=180, weight=0)
        self.generator_fields_frame.columnconfigure(1, weight=1)

    def _collect_generator_payload(self) -> dict[str, object]:
        platform_label = self.generator_platform_var.get().strip()
        platform_key = self.generator_platform_map.get(platform_label, "").strip()
        if not platform_key:
            raise ValueError("Selecione uma plataforma na aba Gerador.")

        mode = self._generator_mode()
        if mode == "new_client":
            client_name = self.generator_client_name_var.get().strip()
            if not client_name:
                raise ValueError("Informe o nome do novo cliente para gerar o link.")
        else:
            client_name = self.generator_client_var.get().strip()
            if not client_name:
                raise ValueError("Selecione um cliente existente para gerar o link.")

        gid = "".join(ch for ch in self.generator_gid_var.get().strip() if ch.isdigit())
        if not gid:
            raise ValueError("Informe o GID da aba do cliente (sheetId) com numeros validos.")

        credentials: dict[str, object] = {}
        for field in self.generator_field_specs:
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            raw_value = self.generator_field_vars.get(name)
            if raw_value is None:
                continue

            kind = str(field.get("kind") or "text").strip().lower()
            required = bool(field.get("required"))
            if kind == "bool":
                credentials[name] = self._parse_yes_no(raw_value.get())
                continue

            value = str(raw_value.get() or "").strip()
            if required and not value:
                raise ValueError(f"Campo obrigatorio ausente: {name}")
            if value:
                credentials[name] = value

        return {
            "platform_key": platform_key,
            "registration_mode": mode,
            "client_name": client_name,
            "gid": gid,
            "credentials": credentials,
        }

    def generate_platform_link(self) -> None:
        def task() -> None:
            if self.remote_client is None:
                raise ValueError("Conecte o servidor para usar o gerador.")

            payload = self._collect_generator_payload()
            try:
                result = self.remote_client.generate_generator_link(payload)
            except RemoteApiError as error:
                message = str(error)
                if "HTTP 404" in message and "Rota nao encontrada" in message:
                    raise ValueError(
                        "Servidor conectado sem suporte ao Gerador "
                        "(/v1/generators/link). Atualize/reinicie o servidor para a versao com Gerador."
                    ) from error
                raise
            authorization_url = str(result.get("authorization_url") or "").strip()
            if not authorization_url:
                raise ValueError("Resposta invalida do servidor: authorization_url ausente.")

            expires_at = str(result.get("expires_at") or "").strip()
            client_name = str(result.get("client_name") or payload.get("client_name") or "").strip()
            platform_key = str(result.get("platform_key") or payload.get("platform_key") or "").strip()
            self.log(
                "Link gerado: "
                f"plataforma={platform_key} | cliente={client_name} | expira={expires_at or '-'}"
            )
            self.root.after(0, lambda: self._set_generated_link(authorization_url))

        self._run_task("Gerar link", task)

    def _set_generated_link(self, url: str) -> None:
        self.generator_link_var.set(str(url or "").strip())
        self._update_generate_link_button_state()

    def open_generated_link(self) -> None:
        link = self.generator_link_var.get().strip()
        if not link:
            messagebox.showwarning("Gerador", "Nenhum link gerado para abrir.")
            return
        try:
            self._open_path(link)
            self.log("Link de autorizacao aberto no navegador.")
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Gerador", f"Nao foi possivel abrir o link.\n\n{error}")

    def copy_generated_link(self) -> None:
        link = self.generator_link_var.get().strip()
        if not link:
            messagebox.showwarning("Gerador", "Nenhum link gerado para copiar.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(link)
        self.root.update()
        self.log("Link de autorizacao copiado para a area de transferencia.")

    def _refresh_client_registration_platforms(self) -> None:
        available_platforms = [
            platform
            for platform in self.config.platforms
            if platform.key.startswith("omie") or platform.key in CLIENT_REGISTRATION_SCHEMAS
        ]

        options: list[str] = []
        mapping: dict[str, str] = {}
        repeated_labels: set[str] = set()

        for platform in available_platforms:
            label = str(platform.label or platform.key).strip() or platform.key
            if label in mapping:
                repeated_labels.add(label)
                continue
            mapping[label] = platform.key
            options.append(label)

        if repeated_labels:
            options = []
            mapping = {}
            for platform in available_platforms:
                base_label = str(platform.label or platform.key).strip() or platform.key
                label = base_label if base_label not in repeated_labels else f"{base_label} ({platform.key})"
                mapping[label] = platform.key
                options.append(label)

        current_label = self.client_registration_platform_var.get().strip()
        self.client_registration_platform_map = mapping
        self.client_registration_platform_combo.configure(values=options)

        if not options:
            self.client_registration_platform_var.set("")
            self.client_registration_clients = []
            self.client_registration_client_var.set("")
            self.client_registration_client_combo.configure(values=[])
            self.client_registration_field_specs = []
            self.client_registration_field_vars = {}
            self._render_client_registration_fields([])
            self._sync_client_registration_input_states()
            self._update_register_client_button_state()
            return

        if current_label in mapping:
            self.client_registration_platform_var.set(current_label)
        else:
            self.client_registration_platform_var.set(options[0])
        self._on_client_registration_platform_change()
        self._on_client_registration_mode_change()
        self._sync_client_registration_input_states()

    def _on_client_registration_platform_change(self) -> None:
        platform_key = self.client_registration_platform_map.get(
            self.client_registration_platform_var.get().strip(),
            "",
        )
        self._refresh_client_registration_clients(platform_key)
        schema = self._client_registration_schema_for_platform(platform_key)
        self.client_registration_field_specs = schema
        self._render_client_registration_fields(schema)
        self._sync_client_registration_input_states()
        self._update_register_client_button_state()

    def _refresh_client_registration_clients(self, platform_key: str) -> None:
        clients = self._clients_for_platform(platform_key) if platform_key else []
        self.client_registration_clients = list(clients)
        self.client_registration_client_combo.configure(values=self.client_registration_clients)
        current_client = self.client_registration_client_var.get().strip()
        if current_client in self.client_registration_clients:
            self.client_registration_client_var.set(current_client)
            return
        if self.client_registration_clients:
            self.client_registration_client_var.set(self.client_registration_clients[0])
            return
        self.client_registration_client_var.set("")

    @staticmethod
    def _client_registration_schema_for_platform(platform_key: str) -> list[dict[str, object]]:
        if platform_key.startswith("omie"):
            return list(CLIENT_REGISTRATION_SCHEMAS["__omie__"])
        return list(CLIENT_REGISTRATION_SCHEMAS.get(platform_key, []))

    def _render_client_registration_fields(self, schema: list[dict[str, object]]) -> None:
        for child in self.client_registration_fields_frame.winfo_children():
            child.destroy()
        self.client_registration_dynamic_entries = []
        self.client_registration_dynamic_combos = []
        self.client_registration_field_vars = {}

        if not schema:
            ttk.Label(
                self.client_registration_fields_frame,
                text="Plataforma sem campos extras obrigatorios.",
                style="Field.TLabel",
            ).grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=2)
            self._sync_client_registration_fields_scrollregion()
            self._sync_client_registration_fields_width()
            return

        for index, field in enumerate(schema):
            row = index * 2
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            label = str(field.get("label") or name).strip()
            kind = str(field.get("kind") or "text").strip().lower()
            default_value = str(field.get("default") or "").strip()
            required = bool(field.get("required"))
            help_text = str(field.get("help") or "").strip()

            ttk.Label(
                self.client_registration_fields_frame,
                text=f"{label} *" if required else label,
                style="Field.TLabel",
            ).grid(row=row, column=0, sticky=tk.W, padx=(0, 8), pady=2)

            if kind == "bool":
                var = tk.StringVar(value=default_value or "Nao")
                combo = ttk.Combobox(
                    self.client_registration_fields_frame,
                    textvariable=var,
                    values=["Sim", "Nao"],
                    state="readonly",
                    style="Dark.TCombobox",
                    width=22,
                )
                combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self.client_registration_dynamic_combos.append(combo)
                self.client_registration_field_vars[name] = var
                if help_text:
                    ttk.Label(
                        self.client_registration_fields_frame,
                        text=help_text,
                        style="Field.TLabel",
                        wraplength=420,
                        justify=tk.LEFT,
                    ).grid(row=row + 1, column=1, sticky=tk.W, pady=(0, 2))
                continue

            var = tk.StringVar(value=default_value)
            show_char = "*" if bool(field.get("secret")) else ""
            entry = ttk.Entry(
                self.client_registration_fields_frame,
                textvariable=var,
                style="Dark.TEntry",
                show=show_char,
            )
            entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
            self.client_registration_dynamic_entries.append(entry)
            self.client_registration_field_vars[name] = var
            if help_text:
                ttk.Label(
                    self.client_registration_fields_frame,
                    text=help_text,
                    style="Field.TLabel",
                    wraplength=420,
                    justify=tk.LEFT,
                ).grid(row=row + 1, column=1, sticky=tk.W, pady=(0, 2))

        self.client_registration_fields_frame.columnconfigure(0, minsize=180, weight=0)
        self.client_registration_fields_frame.columnconfigure(1, weight=1)
        self._sync_client_registration_fields_scrollregion()
        self._sync_client_registration_fields_width()

    def _collect_client_registration_payload(self) -> dict[str, object]:
        platform_label = self.client_registration_platform_var.get().strip()
        platform_key = self.client_registration_platform_map.get(platform_label, "").strip()
        if not platform_key:
            raise ValueError("Selecione uma plataforma na aba Clientes.")

        registration_mode = self._client_registration_mode()
        if registration_mode == "new_client":
            client_name = self.client_registration_client_name_var.get().strip()
            if not client_name:
                raise ValueError("Informe o nome do novo cliente.")
        else:
            client_name = self.client_registration_client_var.get().strip()
            if not client_name:
                raise ValueError("Selecione um cliente existente para cadastrar a nova conta/credencial.")

        gid = "".join(ch for ch in self.client_registration_gid_var.get().strip() if ch.isdigit())
        if not gid:
            raise ValueError("Informe o GID da aba do cliente (sheetId) com numeros validos.")

        credentials: dict[str, object] = {}
        resource_gids: dict[str, str] = {}

        for field in self.client_registration_field_specs:
            name = str(field.get("name") or "").strip()
            if not name:
                continue

            raw_value = self.client_registration_field_vars.get(name)
            if raw_value is None:
                continue

            kind = str(field.get("kind") or "text").strip().lower()
            required = bool(field.get("required"))
            resource_gid_for = str(field.get("resource_gid") or "").strip()

            if kind == "bool":
                parsed_bool = self._parse_yes_no(raw_value.get())
                credentials[name] = parsed_bool
                continue

            value = str(raw_value.get() or "").strip()
            if required and not value:
                raise ValueError(f"Campo obrigatorio ausente: {name}")
            if not value:
                continue

            if resource_gid_for:
                cleaned_gid = "".join(ch for ch in value if ch.isdigit())
                if not cleaned_gid:
                    raise ValueError(
                        f"GID de aba invalido para recurso '{resource_gid_for}'."
                    )
                resource_gids[resource_gid_for] = cleaned_gid
                continue

            credentials[name] = value

        if platform_key.startswith("omie"):
            alias_value = str(credentials.get("alias") or "").strip()
            if not alias_value:
                raise ValueError("Campo obrigatorio ausente: alias")
            credentials["app_name"] = alias_value

        payload: dict[str, object] = {
            "registration_mode": registration_mode,
            "platform_key": platform_key,
            "client_name": client_name,
            "gid": gid,
            "credentials": credentials,
        }
        if resource_gids:
            payload["resource_gids"] = resource_gids
        return payload

    @staticmethod
    def _parse_yes_no(value: object) -> bool:
        normalized = str(value or "").strip().casefold()
        return normalized in {"sim", "true", "1", "yes", "y"}

    def register_client(self) -> None:
        def task() -> None:
            payload = self._collect_client_registration_payload()
            registration_mode = str(payload.get("registration_mode") or "").strip() or "existing_client"
            platform_key = str(payload.get("platform_key") or "").strip()
            client_name = str(payload.get("client_name") or "").strip()

            if self.remote_client is None:
                raise ValueError("Conecte o servidor na aba Configuracoes para cadastrar clientes.")

            result = self.remote_client.register_client(payload)
            updated_resources_raw = result.get("updated_resources")
            updated_resources: list[str] = []
            if isinstance(updated_resources_raw, list):
                updated_resources = [str(item).strip() for item in updated_resources_raw if str(item).strip()]
            resources_label = ", ".join(updated_resources) if updated_resources else "-"
            mode_label = (
                "novo_cliente" if registration_mode == "new_client" else "filial_alias"
            )
            self.log(
                "Cliente cadastrado: "
                f"tipo={mode_label} | plataforma={platform_key} | cliente={client_name} "
                f"| recursos={resources_label}"
            )

            catalog = self.remote_client.fetch_catalog()
            self._apply_remote_connection_in_ui_thread(self.remote_client, catalog)

            self.root.after(0, self._reset_client_registration_form)
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Clientes",
                    (
                        f"Cadastro salvo no servidor para cliente '{client_name}' "
                        f"em '{platform_key}'."
                    ),
                ),
            )

        self._run_task("Cadastro de cliente", task)

    def refresh_remote_catalog(self) -> None:
        def task() -> None:
            if self.remote_client is None:
                raise ValueError("Conecte o servidor na aba Configuracoes para atualizar o catalogo.")
            catalog = self.remote_client.fetch_catalog()
            self._apply_remote_connection_in_ui_thread(self.remote_client, catalog)
            self.log("Catalogo remoto atualizado a partir do servidor.")

        self._run_task("Atualizar catalogo", task)

    def refresh_server_secret_files(self) -> None:
        def task() -> None:
            if self.remote_client is None:
                raise ValueError("Conecte o servidor na aba Configuracoes e acesse a aba Server para visualizar secrets.")
            payload = self.remote_client.list_secret_files()
            files_raw = payload.get("files")
            files = files_raw if isinstance(files_raw, list) else []
            self._apply_server_secret_files_in_ui_thread(files)
            self.log(f"Lista de secrets atualizada: {len(files)} arquivo(s) JSON.")

        self._run_task("Atualizar secrets", task)

    def load_selected_server_secret(self) -> None:
        def task() -> None:
            if self.remote_client is None:
                raise ValueError("Conecte o servidor na aba Configuracoes e acesse a aba Server para visualizar secrets.")
            path = self._selected_server_secret_path()
            if not path:
                raise ValueError("Selecione um arquivo JSON de secrets.")
            payload = self.remote_client.read_secret_file(path)
            self._apply_server_secret_file_in_ui_thread(payload)
            self.log(f"Secret carregado: {path}")

        self._run_task("Carregar secret", task)

    def save_selected_server_secret(self) -> None:
        def task() -> None:
            if self.remote_client is None:
                raise ValueError("Conecte o servidor na aba Configuracoes e acesse a aba Server para editar secrets.")
            path = self.server_secret_loaded_path.strip()
            if not path:
                raise ValueError("Carregue um arquivo JSON antes de salvar.")
            content = self.server_secret_editor.get("1.0", tk.END).strip()
            if not content:
                raise ValueError("O conteudo JSON nao pode ficar vazio.")
            json.loads(content)
            result = self.remote_client.update_secret_file(path, content)
            self._apply_server_secret_file_in_ui_thread(result)
            files_payload = self.remote_client.list_secret_files()
            files_raw = files_payload.get("files")
            files = files_raw if isinstance(files_raw, list) else []
            self._apply_server_secret_files_in_ui_thread(files)
            self.log(f"Secret salvo no servidor: {path}")
            self.root.after(
                0,
                lambda: messagebox.showinfo("Secrets", f"Arquivo salvo no servidor: {path}"),
            )

        self._run_task("Salvar secret", task)

    def _apply_server_secret_files_in_ui_thread(self, files: list[object]) -> None:
        completed = threading.Event()
        errors: list[Exception] = []

        def apply() -> None:
            try:
                self.server_secret_files = [
                    item for item in files if isinstance(item, dict)
                ]
                selected_path = self._selected_server_secret_path() or self.server_secret_loaded_path
                self.server_secrets_tree.delete(*self.server_secrets_tree.get_children())
                for item in self.server_secret_files:
                    path = str(item.get("path") or "").strip()
                    if not path:
                        continue
                    modified = self._format_remote_datetime(item.get("modified_at"))
                    self.server_secrets_tree.insert(
                        "",
                        tk.END,
                        iid=path,
                        text=path,
                        values=(modified,),
                    )
                if selected_path and self.server_secrets_tree.exists(selected_path):
                    self.server_secrets_tree.selection_set(selected_path)
                    self.server_secrets_tree.see(selected_path)
                elif self.server_secret_loaded_path:
                    self.server_secret_loaded_path = ""
                    self.server_secret_path_var.set("")
                    self.server_secret_modified_var.set("-")
                    self.server_secret_size_var.set("-")
                    self.server_secret_editor.configure(state=tk.NORMAL)
                    self.server_secret_editor.delete("1.0", tk.END)
                    self.server_secret_editor.configure(state=tk.DISABLED)
                self._sync_server_secret_controls()
            except Exception as error:  # noqa: BLE001
                errors.append(error)
            finally:
                completed.set()

        self.root.after(0, apply)
        completed.wait()
        if errors:
            raise errors[0]

    def _apply_server_secret_file_in_ui_thread(self, payload: dict[str, object]) -> None:
        completed = threading.Event()
        errors: list[Exception] = []

        def apply() -> None:
            try:
                path = str(payload.get("path") or "").strip()
                content = str(payload.get("content") or "")
                self.server_secret_loaded_path = path
                self.server_secret_path_var.set(path)
                self.server_secret_modified_var.set(
                    self._format_remote_datetime(payload.get("modified_at"))
                )
                size_bytes = payload.get("size_bytes")
                self.server_secret_size_var.set(f"{size_bytes} bytes" if size_bytes is not None else "-")
                self.server_secret_editor.configure(state=tk.NORMAL)
                self.server_secret_editor.delete("1.0", tk.END)
                self.server_secret_editor.insert("1.0", content)
                self.server_secret_editor.edit_reset()
                if path and self.server_secrets_tree.exists(path):
                    self.server_secrets_tree.selection_set(path)
                    self.server_secrets_tree.see(path)
                self._sync_server_secret_controls()
            except Exception as error:  # noqa: BLE001
                errors.append(error)
            finally:
                completed.set()

        self.root.after(0, apply)
        completed.wait()
        if errors:
            raise errors[0]

    def _on_server_secret_selection_change(self) -> None:
        path = self._selected_server_secret_path()
        if not path:
            return
        if path != self.server_secret_loaded_path:
            self.server_secret_loaded_path = ""
            self.server_secret_editor.configure(state=tk.NORMAL)
            self.server_secret_editor.delete("1.0", tk.END)
            self.server_secret_editor.edit_reset()
        for item in self.server_secret_files:
            if str(item.get("path") or "").strip() != path:
                continue
            self.server_secret_path_var.set(path)
            self.server_secret_modified_var.set(self._format_remote_datetime(item.get("modified_at")))
            size_bytes = item.get("size_bytes")
            self.server_secret_size_var.set(f"{size_bytes} bytes" if size_bytes is not None else "-")
            break
        self._sync_server_secret_controls()

    def _selected_server_secret_path(self) -> str:
        selected = self.server_secrets_tree.selection()
        if not selected:
            return ""
        return str(selected[0]).strip()

    def _sync_server_secret_controls(self) -> None:
        if self.busy:
            return
        has_remote = self.remote_client is not None
        has_selected = bool(self._selected_server_secret_path())
        has_loaded = bool(self.server_secret_loaded_path)
        self.btn_refresh_server_secrets.configure(state=tk.NORMAL if has_remote else tk.DISABLED)
        self.btn_load_server_secret.configure(
            state=tk.NORMAL if has_remote and has_selected else tk.DISABLED
        )
        self.btn_save_server_secret.configure(
            state=tk.NORMAL if has_remote and has_loaded else tk.DISABLED
        )
        self.server_secret_editor.configure(state=tk.NORMAL if has_remote and has_loaded else tk.DISABLED)

    @staticmethod
    def _format_remote_datetime(value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "-"
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return raw
        return parsed.astimezone().strftime("%d/%m/%Y %H:%M:%S")

    def _reset_client_registration_form(self) -> None:
        self.client_registration_gid_var.set("")
        self.client_registration_client_name_var.set("")
        self._on_client_registration_platform_change()
        self._on_client_registration_mode_change()

    def _set_default_dates_current_month(self) -> None:
        today = date.today()
        self._set_period_dates(today.replace(day=1), today)

    def _set_default_estoque_dates_current_month(self) -> None:
        today = date.today()
        self._set_estoque_period_dates(today.replace(day=1), today)

    def _set_previous_month_period_based_on_today(self) -> None:
        today = date.today()
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        first_day_previous_month = last_day_previous_month.replace(day=1)

        self._set_period_dates(first_day_previous_month, last_day_previous_month)

    def _set_previous_estoque_month_period_based_on_today(self) -> None:
        today = date.today()
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        first_day_previous_month = last_day_previous_month.replace(day=1)

        self._set_estoque_period_dates(first_day_previous_month, last_day_previous_month)

    @staticmethod
    def _count_months_covered(start_date_iso: str, end_date_iso: str) -> int:
        start = date.fromisoformat(start_date_iso)
        end = date.fromisoformat(end_date_iso)
        return (end.year - start.year) * 12 + (end.month - start.month) + 1

    @staticmethod
    def _format_scope(sub_clients: list[str] | None) -> str:
        if sub_clients is None:
            return ALL_SUB_CLIENTS
        if len(sub_clients) <= 3:
            return ", ".join(sub_clients)
        return f"{len(sub_clients)} selecionadas"

    def _reload_catalog_ui(self) -> None:
        labels = [choice.label for choice in self.platform_choices]
        estoque_labels = [choice.label for choice in self.estoque_platform_choices]
        self.platform_combo.configure(values=labels)
        self.estoque_platform_combo.configure(values=estoque_labels)
        self.platform_var.set("")
        self.estoque_platform_var.set("")
        self.client_combo.configure(values=[])
        self.estoque_client_combo.configure(values=[])
        self.client_var.set("")
        self.estoque_client_var.set("")
        self._set_sub_client_options([])
        self._set_estoque_sub_client_options([])
        self._clear_sku_preview()
        self.client_registration_client_var.set("")
        self.client_registration_client_name_var.set("")
        self.client_registration_gid_var.set("")
        self.generator_client_var.set("")
        self.generator_client_name_var.set("")
        self.generator_gid_var.set("")
        self.generator_link_var.set("")
        self._refresh_local_fallback_visibility()
        self._sync_server_secret_controls()
        self._load_initial_values()

    def _apply_remote_connection_in_ui_thread(
        self,
        client: RemoteCFOClient,
        catalog: dict[str, object],
    ) -> None:
        completed = threading.Event()
        errors: list[Exception] = []

        def apply() -> None:
            try:
                self._activate_remote_catalog(client, catalog)
                self.server_secret_files = []
                self.server_secret_loaded_path = ""
                self.server_secret_path_var.set("")
                self.server_secret_modified_var.set("-")
                self.server_secret_size_var.set("-")
                self.server_secrets_tree.delete(*self.server_secrets_tree.get_children())
                self.server_secret_editor.configure(state=tk.NORMAL)
                self.server_secret_editor.delete("1.0", tk.END)
                self.server_secret_editor.configure(state=tk.DISABLED)
                self._reload_catalog_ui()
            except Exception as error:  # noqa: BLE001
                errors.append(error)
            finally:
                completed.set()

        self.root.after(0, apply)
        completed.wait()
        if errors:
            raise errors[0]

    def _apply_local_mode_in_ui_thread(self, config: AppConfig, pipeline: SyncPipeline) -> None:
        completed = threading.Event()
        errors: list[Exception] = []

        def apply() -> None:
            try:
                self.remote_client = None
                self.remote_catalog_sub_clients = {}
                self.server_secret_files = []
                self.server_secret_loaded_path = ""
                self.server_secret_path_var.set("")
                self.server_secret_modified_var.set("-")
                self.server_secret_size_var.set("-")
                self.server_secrets_tree.delete(*self.server_secrets_tree.get_children())
                self.server_secret_editor.configure(state=tk.NORMAL)
                self.server_secret_editor.delete("1.0", tk.END)
                self.server_secret_editor.configure(state=tk.DISABLED)
                self.config = config
                self.pipeline = pipeline
                self.platform_ui_registry = build_platform_ui_registry(self.config)
                self.platform_choices = self._build_platform_choices()
                self.choice_by_label = {choice.label: choice for choice in self.platform_choices}
                self.estoque_platform_choices = self._build_estoque_platform_choices()
                self.estoque_choice_by_label = {
                    choice.label: choice for choice in self.estoque_platform_choices
                }
                self._refresh_estoque_credentials_store()
                self.server_status_var.set("Modo local ativo (secrets)")
                self.status_var.set("Modo local ativo")
                self._reload_catalog_ui()
            except Exception as error:  # noqa: BLE001
                errors.append(error)
            finally:
                completed.set()

        self.root.after(0, apply)
        completed.wait()
        if errors:
            raise errors[0]

    def connect_server(self) -> None:
        def task() -> None:
            server_url = self.server_url_var.get().strip()
            server_token = self.server_token_var.get().strip()
            if not server_url:
                raise ValueError("Informe a URL da API do servidor.")
            if not server_token:
                raise ValueError("Informe o token Bearer do servidor.")

            self.log(f"Conectando no servidor: {server_url}")
            client = RemoteCFOClient(server_url, server_token)
            catalog = client.fetch_catalog()
            self._apply_remote_connection_in_ui_thread(client, catalog)
            self._persist_server_connection(server_url, server_token)
            self.status_var.set("Conectado ao servidor")
            self.log("Conexao com servidor estabelecida.")

        self._run_task("Conectar servidor", task)

    def activate_local_mode(self) -> None:
        def task() -> None:
            config_path = app_config_path()
            if not config_path.exists():
                raise ValueError("Arquivo local ausente: secrets/app_config.json")

            self.log(f"Ativando fallback local: {config_path}")
            config = load_app_config(config_path)
            pipeline = SyncPipeline(config)
            self._apply_local_mode_in_ui_thread(config, pipeline)
            self.log("Fallback local ativo. Operacoes usando arquivos da pasta secrets.")

        self._run_task("Ativar fallback local", task)

    def disconnect_server(self) -> None:
        self.remote_client = None
        self.remote_catalog_sub_clients = {}
        self.server_secret_files = []
        self.server_secret_loaded_path = ""
        self.server_secret_path_var.set("")
        self.server_secret_modified_var.set("-")
        self.server_secret_size_var.set("-")
        self.server_secrets_tree.delete(*self.server_secrets_tree.get_children())
        self.server_secret_editor.configure(state=tk.NORMAL)
        self.server_secret_editor.delete("1.0", tk.END)
        self.server_secret_editor.configure(state=tk.DISABLED)
        self.config = _empty_app_config()
        self.pipeline = None
        self.platform_ui_registry = build_platform_ui_registry(self.config)
        self.platform_choices = []
        self.choice_by_label = {}
        self.estoque_platform_choices = []
        self.estoque_choice_by_label = {}
        self._refresh_estoque_credentials_store()
        self.server_status_var.set("Servidor desconectado")
        self.status_var.set("Conecte ao servidor na aba Configuracoes")
        self._clear_server_connection()
        self._reload_catalog_ui()
        self.log("Servidor desconectado e sessao remota limpa.")

    @staticmethod
    def _has_local_secrets_files() -> bool:
        local_secrets = secrets_dir()
        try:
            return local_secrets.exists() and any(item.is_file() for item in local_secrets.iterdir())
        except OSError:
            return False

    def _refresh_local_fallback_visibility(self) -> None:
        if self.btn_use_local_secrets is None:
            return

        should_show = self._has_local_secrets_files()
        is_visible = self.btn_use_local_secrets.winfo_manager() == "grid"
        server_actions = self.btn_use_local_secrets.master
        if isinstance(server_actions, ttk.Frame):
            server_actions.columnconfigure(2, weight=1 if should_show else 0)
        if should_show and not is_visible:
            self.btn_use_local_secrets.grid(row=0, column=2, sticky=tk.EW)
            return
        if not should_show and is_visible:
            self.btn_use_local_secrets.grid_remove()

    def _set_update_notice(
        self,
        message: str,
        *,
        latest_version: str | None = None,
    ) -> None:
        notice = message.strip()
        self.update_notice_var.set(notice)
        if latest_version:
            self.btn_update_app.configure(text=f"{UPDATE_APP_DEFAULT_LABEL} (v{latest_version})")
        else:
            self.btn_update_app.configure(text=UPDATE_APP_DEFAULT_LABEL)
        if self.update_notice_label is None:
            return
        if notice:
            self.update_notice_label.grid()
            return
        self.update_notice_label.grid_remove()

    def _apply_update_notice_result(self, result) -> None:
        if result.status == "update_available":
            latest_version = str(result.latest_version or "").strip()
            if latest_version:
                self._set_update_notice(
                    f"Atualizacao disponivel: v{latest_version}",
                    latest_version=latest_version,
                )
                self.log(f"Aviso: atualizacao disponivel (v{latest_version}).")
                return
            self._set_update_notice("Atualizacao disponivel.")
            self.log("Aviso: atualizacao disponivel.")
            return
        if result.status == "no_asset":
            latest_version = str(result.latest_version or "").strip()
            if latest_version:
                self._set_update_notice(f"Nova versao v{latest_version} sem instalador compativel.")
                return
            self._set_update_notice("Nova versao disponivel sem instalador compativel.")
            return
        if result.status == "up_to_date":
            self._set_update_notice("")
            return
        if result.status in {"disabled", "misconfigured", "error", "installer_started"}:
            self._set_update_notice("")
            return

    def _check_updates_notice_async(self) -> None:
        def worker() -> None:
            try:
                result = check_for_updates(update_config_path())
            except Exception as error:  # noqa: BLE001
                self.log(f"Aviso: falha ao verificar atualizacoes automaticamente ({error}).")
                return
            self.root.after(0, lambda: self._apply_update_notice_result(result))

        threading.Thread(target=worker, daemon=True).start()

    def open_changelog(self) -> None:
        releases_url = get_releases_page_url(update_config_path())
        if not releases_url:
            messagebox.showwarning(
                "Changelog",
                "Configure github_repo em update_config.json para abrir o changelog.",
            )
            return
        try:
            self._open_path(releases_url)
            self.log(f"Abrindo changelog: {releases_url}")
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Erro", f"Nao foi possivel abrir o changelog.\n\n{error}")

    @staticmethod
    def _open_path(path: Path | str) -> None:
        target = str(path)
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
            return
        subprocess.Popen(["xdg-open", target])

    def _run_remote_job(
        self,
        *,
        action: str,
        platform_key: str,
        client: str,
        start_date: str,
        end_date: str,
        resource_names: list[str],
        sub_clients: list[str] | None,
    ) -> int:
        remote = self.remote_client
        if remote is None:
            raise ValueError("Cliente remoto nao inicializado.")

        payload: dict[str, object] = {
            "action": action,
            "platform_key": platform_key,
            "client": client,
            "start_date": start_date,
            "end_date": end_date,
            "resource_names": resource_names,
        }
        if sub_clients is not None:
            payload["sub_clients"] = sub_clients

        job_id = remote.create_job(payload)
        self.log(f"Job remoto criado: {job_id}")
        result = remote.wait_for_job(job_id, timeout_seconds=1800.0)
        if result.status != "completed":
            logs = remote.get_job_logs(job_id)
            if logs:
                self.log("Logs do job remoto:")
                for line in logs[-10:]:
                    self.log(line)
            raise ValueError(result.error or f"Job remoto {job_id} falhou.")
        if not result.result:
            return 0
        count = result.result.get("count")
        try:
            return int(count)
        except Exception:  # noqa: BLE001
            return 0

    def _should_update_mercado_livre_categories(self, choice: PlatformChoice) -> bool:
        return (
            choice.platform_key == "mercado_livre"
            and not self._is_estoque_tab_active()
            and bool(self.update_mercado_livre_categories_var.get())
        )

    def _update_mercado_livre_categories_before_export(
        self,
        *,
        client: str,
        start_date: str,
        end_date: str,
    ) -> None:
        self.log("Atualizando categorias Mercado Livre antes da exportacao...")
        if self.remote_client is not None:
            try:
                count = self._run_remote_job(
                    action="sync_mercado_livre_categories",
                    platform_key="mercado_livre",
                    client=client,
                    start_date=start_date,
                    end_date=end_date,
                    resource_names=["vendas"],
                    sub_clients=None,
                )
            except (RemoteApiError, ValueError) as error:
                if self._is_unsupported_remote_category_sync_error(error):
                    self.log(
                        "Servidor remoto nao reconhece a atualizacao de categorias "
                        "Mercado Livre. Atualize o CFO Sync no servidor; continuando sem "
                        "atualizar categorias."
                    )
                    return
                raise
            self.log(f"Categorias Mercado Livre atualizadas no servidor: detalhes={count}")
            return

        config = self.config
        result = sync_transaction_detail_map(
            credentials_path=config.credentials_dir / "mercado_livre_credentials.json",
            start_date=start_date,
            end_date=end_date,
            spreadsheet_id=DEFAULT_SPREADSHEET_ID,
            sheet_id=DEFAULT_SHEET_ID,
            google_credentials_path=config.credentials_dir / config.google_sheets.credentials_file,
        )
        self.log(
            "Categorias Mercado Livre atualizadas: "
            f"descobertos={result.discovered} inseridos={result.inserted} "
            f"removidos={result.removed} inalterados={result.unchanged}"
        )
        if result.pending_review:
            self.log("Categorias Mercado Livre para revisar:")
            for detail in result.pending_review:
                self.log(f"- {detail}")

    @staticmethod
    def _is_unsupported_remote_category_sync_error(error: Exception) -> bool:
        message = str(error or "").casefold()
        return (
            "acao invalida" in message
            and "collect" in message
            and "export" in message
            and "sync_mercado_livre_categories" not in message
        )

    def update_app(self) -> None:
        def task() -> None:
            self.log("Verificando atualizacao no GitHub Releases...")
            result = check_for_updates(update_config_path())
            self.root.after(0, lambda: self._apply_update_notice_result(result))
            if result.status == "disabled":
                self.log(result.message)
                self.root.after(0, lambda: messagebox.showinfo("Atualizacao", result.message))
                return
            if result.status == "misconfigured":
                self.log(result.message)
                self.root.after(0, lambda: messagebox.showwarning("Atualizacao", result.message))
                return
            if result.status == "up_to_date":
                self.log(result.message)
                self.root.after(0, lambda: messagebox.showinfo("Atualizacao", result.message))
                return
            if result.status == "no_asset":
                message = (
                    "Nova versao encontrada, mas sem instalador compativel para este sistema "
                    "na release mais recente."
                )
                self.log(message)
                self.root.after(0, lambda: messagebox.showwarning("Atualizacao", message))
                return
            if result.status == "error":
                self.log(result.message)
                self.root.after(0, lambda: messagebox.showerror("Atualizacao", result.message))
                return

            self.log(
                f"Baixando instalador da versao {result.latest_version} "
                f"({result.asset_name})..."
            )
            launch_result = download_and_launch_update(update_config_path())
            if launch_result.status != "installer_started":
                self.log(launch_result.message)
                self.root.after(0, lambda: messagebox.showerror("Atualizacao", launch_result.message))
                return

            self.log("Instalador iniciado com sucesso. Fechando app para atualizar.")
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Atualizacao",
                    "Instalador iniciado. O app sera fechado para concluir a atualizacao.",
                ),
            )
            self.root.after(500, self.root.destroy)

        self._run_task("Atualizacao", task)

    def collect_data(self) -> None:
        def task() -> None:
            choice, client, sub_clients, start_date, end_date = self._current_selection()
            if self._should_update_mercado_livre_categories(choice):
                self._update_mercado_livre_categories_before_export(
                    client=client,
                    start_date=start_date,
                    end_date=end_date,
                )
            if self.remote_client is not None:
                count = self._run_remote_job(
                    action="collect",
                    platform_key=choice.platform_key,
                    client=client,
                    start_date=start_date,
                    end_date=end_date,
                    resource_names=[choice.resource_name],
                    sub_clients=sub_clients,
                )
            else:
                if self.pipeline is None:
                    raise ValueError("Conecte o servidor na aba Configuracoes para coletar dados.")
                count = self.pipeline.collect(
                    platform_key=choice.platform_key,
                    client=client,
                    start_date=start_date,
                    end_date=end_date,
                    resource_names=[choice.resource_name],
                    sub_clients=sub_clients,
                )
            scope = self._format_scope(sub_clients)
            months = self._count_months_covered(start_date, end_date)
            self.log(
                "Coleta concluida: "
                f"{count} registros | {choice.label} | Cliente={client} | Filial/Alias={scope} | "
                f"Periodo={start_date}..{end_date} | Meses={months}"
            )

        self._run_task("Coleta", task)

    def export_data(self) -> None:
        def task() -> None:
            choice, client, sub_clients, start_date, end_date = self._current_selection()
            if self._should_update_mercado_livre_categories(choice):
                self._update_mercado_livre_categories_before_export(
                    client=client,
                    start_date=start_date,
                    end_date=end_date,
                )
            if self.remote_client is not None:
                count = self._run_remote_job(
                    action="export",
                    platform_key=choice.platform_key,
                    client=client,
                    start_date=start_date,
                    end_date=end_date,
                    resource_names=[choice.resource_name],
                    sub_clients=sub_clients,
                )
            else:
                if self.pipeline is None:
                    raise ValueError("Conecte o servidor na aba Configuracoes para exportar dados.")
                count = self.pipeline.export_to_sheets(
                    platform_key=choice.platform_key,
                    client=client,
                    start_date=start_date,
                    end_date=end_date,
                    resource_names=[choice.resource_name],
                    sub_clients=sub_clients,
                )
            scope = self._format_scope(sub_clients)
            months = self._count_months_covered(start_date, end_date)
            self.log(
                "Exportacao concluida: "
                f"{count} registros | {choice.label} | Cliente={client} | Filial/Alias={scope} | "
                f"Periodo={start_date}..{end_date} | Meses={months}"
            )
            self._notify_export_completion()

        self._run_task("Exportacao", task)

    def export_sku(self) -> None:
        if not self._is_sku_tab_active():
            return

        def task() -> None:
            if self.remote_client is not None:
                raise ValueError("Fluxo SKU remoto ainda nao habilitado nesta fase.")
            if not self.sku_preview_rows:
                raise ValueError("Nenhum SKU carregado. Clique em Buscar SKU antes de exportar.")

            choice = self._get_current_choice()
            behavior = self.platform_ui_registry.get(choice.platform_key)
            if behavior is None or not behavior.supports_sku_workflow:
                raise ValueError(f"Exportacao SKU nao disponivel para plataforma: {choice.platform_key}")

            client = self.client_var.get().strip()
            if not client:
                raise ValueError("Selecione um cliente para exportar SKU.")

            sku_resource = self._resolve_resource_by_name(platform_key=choice.platform_key, resource_name="sku")

            if self.pipeline is None:
                raise ValueError("Conecte o servidor na aba Configuracoes para exportar SKU.")
            exported = self.pipeline.exporter.export(
                client=client,
                platform_key=choice.platform_key,
                resource=sku_resource,
                rows=self.sku_preview_rows,
            )
            self.log(
                f"Exportacao SKU concluida: {exported} linhas | Cliente={client} | "
                f"Pedido={self.sku_order_number_var.get().strip()}"
            )
            self._notify_export_completion()

        self._run_task("Exportar Estoque", task)


def main() -> None:
    root = tk.Tk()
    try:
        app = CFODesktopApp(root)
    except Exception as error:  # noqa: BLE001
        root.withdraw()
        messagebox.showerror(
            "Erro ao iniciar CFO Sync",
            "Falha ao iniciar a interface.\n\n"
            "Verifique os dados de conexao com o servidor na aba Configuracoes.\n\n"
            f"Detalhe tecnico: {error}",
        )
        root.destroy()
        return
    app.log("App pronto.")
    root.mainloop()


if __name__ == "__main__":
    main()
