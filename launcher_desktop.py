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

from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.models import ResourceConfig
from cfo_sync.core.pipeline import SyncPipeline
from cfo_sync.core.runtime_paths import (
    app_config_path,
    available_sound_dirs,
    custom_sounds_dir,
    desktop_settings_path,
    ensure_runtime_layout,
    secrets_dir,
    update_config_path,
)
from cfo_sync.core.updater import check_for_updates, download_and_launch_update, get_releases_page_url
from cfo_sync.platforms.ui_registry import build_platform_ui_registry
from cfo_sync.version import __version__


ALL_SUB_CLIENTS = "Todos"
NO_NOTIFICATION_SOUND = "Sem som"
DESKTOP_SETTINGS_PATH = desktop_settings_path()
SOUNDS_DIR = custom_sounds_dir()

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
        self.config = load_app_config(app_config_path())
        self.pipeline = SyncPipeline(self.config)
        self.platform_ui_registry = build_platform_ui_registry(self.config)

        self.platform_choices = self._build_platform_choices()
        self.choice_by_label = {choice.label: choice for choice in self.platform_choices}

        self.platform_var = tk.StringVar()
        self.client_var = tk.StringVar()
        self.sub_client_options: list[str] = []
        self.sub_client_summary_var = tk.StringVar(value=ALL_SUB_CLIENTS)
        self.start_date_var = tk.StringVar()
        self.end_date_var = tk.StringVar()
        self.sku_order_number_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto")
        self.sku_preview_rows: list[dict[str, object]] = []
        self.notification_sound_var = tk.StringVar(value=NO_NOTIFICATION_SOUND)
        self.notification_sound_options: list[str] = [NO_NOTIFICATION_SOUND]
        self._date_picker_window: tk.Toplevel | None = None
        self._date_picker_month_label_var = tk.StringVar()
        self._date_picker_hint_var = tk.StringVar()
        self._date_picker_grid_frame: ttk.Frame | None = None
        self._date_picker_month = date.today().replace(day=1)
        self._date_picker_selection_start: date | None = None
        self._date_picker_selection_end: date | None = None

        self.style = ttk.Style(self.root)
        self._apply_theme()
        self._build_ui()
        self.root.after(50, self._apply_native_titlebar_color)
        self._bind_events()
        self._set_default_dates_current_month()
        self._load_initial_values()
        self._poll_logs()

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

    def _build_platform_choices(self) -> list[PlatformChoice]:
        choices: list[PlatformChoice] = []
        for platform in self.config.platforms:
            if not self._clients_for_platform(platform.key):
                continue
            platform_behavior = self.platform_ui_registry.get(platform.key)
            for resource in platform.resources:
                if platform_behavior and platform_behavior.uses_dedicated_resource_tab(resource.name):
                    # Recursos dedicados usam aba propria e exportacao especifica.
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
        self.sku_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=16)
        self.settings_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=16)

        self.tabs.add(config_tab, text="Pedidos")
        self.tabs.add(self.sku_tab, text="SKU")
        self.tabs.add(self.settings_tab, text="Configurações")

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

        self.settings_tab.columnconfigure(1, weight=1)

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

        app_actions = ttk.Frame(self.settings_tab, style="Card.TFrame")
        app_actions.grid(row=3, column=1, sticky=tk.W, pady=(8, 0))

        self.btn_update_app = ttk.Button(
            app_actions,
            text="Atualizar app",
            style="Secondary.TButton",
            command=self.update_app,
        )
        self.btn_update_app.pack(fill=tk.X, pady=(0, 8))

        self.btn_open_changelog = ttk.Button(
            app_actions,
            text="Ver changelog",
            style="Secondary.TButton",
            command=self.open_changelog,
        )
        self.btn_open_changelog.pack(fill=tk.X, pady=(0, 8))

        self.btn_open_secrets = ttk.Button(
            app_actions,
            text="Abrir pasta de config",
            style="Secondary.TButton",
            command=self.open_secrets_folder,
        )
        self.btn_open_secrets.pack(fill=tk.X)

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
            text="Exportar para Sheets",
            style="Secondary.TButton",
            command=self.export_data,
        )
        self.btn_export.pack(fill=tk.X, pady=(0, 8))

        self.btn_export_sku = ttk.Button(
            buttons,
            text="Exportar SKU",
            style="Sku.TButton",
            command=self.export_sku,
            cursor="no",
        )
        self.btn_export_sku.pack(fill=tk.X)

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
        self.sub_client_listbox.bind("<<ListboxSelect>>", lambda _event: self._update_sub_client_summary())
        self.notification_sound_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_notification_sound_change(),
        )
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self._on_tab_changed())
        self.sku_order_entry.bind("<Return>", lambda _event: self.search_sku())

    def _open_date_range_picker(self) -> None:
        try:
            start = self._parse_ui_date(self.start_date_var.get().strip())
            end = self._parse_ui_date(self.end_date_var.get().strip())
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

        self._set_period_dates(start, end)
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
        if start > end:
            start, end = end, start

        self.start_date_var.set(start.strftime("%d/%m/%Y"))
        self.end_date_var.set(end.strftime("%d/%m/%Y"))

        if self._date_picker_window is not None and self._date_picker_window.winfo_exists():
            self._date_picker_selection_start = start
            self._date_picker_selection_end = end
            self._date_picker_month = start.replace(day=1)
            self._refresh_date_picker_grid()

    def _load_initial_values(self) -> None:
        if not self.platform_choices:
            self.status_var.set("Sem plataformas configuradas")
            self.log(f"Nenhuma plataforma/recurso configurado em {app_config_path()}")
            return

        first = self.platform_choices[0]
        self.platform_var.set(first.label)
        self.on_platform_change()
        self._refresh_notification_sounds(preserve_current=False)
        self._update_export_sku_button_state()

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
            self.btn_open_secrets.configure(state=tk.DISABLED)
            self.btn_select_all_sub_clients.configure(state=tk.DISABLED)
            self.btn_clear_sub_clients.configure(state=tk.DISABLED)
            self.sub_client_listbox.configure(state=tk.DISABLED)
            self.notification_sound_combo.configure(state=tk.DISABLED)
            self.btn_refresh_sounds.configure(state=tk.DISABLED)
            self.btn_search_sku.configure(state=tk.DISABLED)
            self.sku_order_entry.configure(state=tk.DISABLED)
            self.btn_pick_period.configure(state=tk.DISABLED)
            return

        self.btn_collect.configure(state=tk.NORMAL)
        self.btn_export.configure(state=tk.NORMAL)
        self._update_export_sku_button_state()
        self.btn_update_app.configure(state=tk.NORMAL)
        self.btn_open_changelog.configure(state=tk.NORMAL)
        self.btn_open_secrets.configure(state=tk.NORMAL)

        has_sub_clients = bool(self.sub_client_options)
        controls_state = tk.NORMAL if has_sub_clients else tk.DISABLED
        self.btn_select_all_sub_clients.configure(state=controls_state)
        self.btn_clear_sub_clients.configure(state=controls_state)
        self.sub_client_listbox.configure(state=controls_state)
        self.notification_sound_combo.configure(state="readonly")
        self.btn_refresh_sounds.configure(state=tk.NORMAL)
        sku_state = tk.NORMAL if self._platform_supports_sku_workflow() else tk.DISABLED
        self.btn_search_sku.configure(state=sku_state)
        self.sku_order_entry.configure(state=sku_state)
        self.btn_pick_period.configure(state=tk.NORMAL)

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
        self._update_export_sku_button_state()

    def _platform_supports_sku_workflow(self) -> bool:
        choice = self.choice_by_label.get(self.platform_var.get())
        if choice is None:
            return False
        behavior = self.platform_ui_registry.get(choice.platform_key)
        return behavior is not None and behavior.supports_sku_workflow

    def _is_sku_tab_active(self) -> bool:
        selected_tab_id = self.tabs.select()
        return selected_tab_id == str(self.sku_tab)

    def _update_export_sku_button_state(self) -> None:
        try:
            choice = self._get_current_choice()
        except ValueError:
            self.btn_export_sku.configure(state=tk.DISABLED, cursor="no")
            return

        behavior = self.platform_ui_registry.get(choice.platform_key)
        can_use_sku = behavior is not None and behavior.supports_sku_workflow

        if self._is_sku_tab_active() and can_use_sku:
            self.btn_export_sku.configure(state=tk.NORMAL, cursor="hand2")
            return
        self.btn_export_sku.configure(state=tk.DISABLED, cursor="no")

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
        choice = self.choice_by_label.get(self.platform_var.get())
        if choice is None:
            raise ValueError("Selecione uma plataforma valida.")

        client = self.client_var.get().strip()
        if not client:
            raise ValueError("Selecione um cliente.")

        sub_clients = self._selected_sub_clients()

        start_date_obj = self._parse_ui_date(self.start_date_var.get().strip())
        end_date_obj = self._parse_ui_date(self.end_date_var.get().strip())
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

    def on_client_change(self) -> None:
        choice = self.choice_by_label[self.platform_var.get()]
        client = self.client_var.get().strip()
        options: list[str] = []
        self._clear_sku_preview()

        try:
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

    def _set_default_dates_current_month(self) -> None:
        today = date.today()
        self._set_period_dates(today.replace(day=1), today)

    def _set_previous_month_period_based_on_today(self) -> None:
        today = date.today()
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        first_day_previous_month = last_day_previous_month.replace(day=1)

        self._set_period_dates(first_day_previous_month, last_day_previous_month)

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

    def open_secrets_folder(self) -> None:
        target = secrets_dir()
        target.mkdir(parents=True, exist_ok=True)
        try:
            self._open_path(target)
            self.log(f"Pasta de configuracao aberta: {target}")
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Erro", f"Nao foi possivel abrir a pasta de configuracao.\n\n{error}")

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

    def update_app(self) -> None:
        def task() -> None:
            self.log("Verificando atualizacao no GitHub Releases...")
            result = check_for_updates(update_config_path())
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

        self._run_task("Exportar SKU", task)


def main() -> None:
    root = tk.Tk()
    try:
        app = CFODesktopApp(root)
    except Exception as error:  # noqa: BLE001
        root.withdraw()
        messagebox.showerror(
            "Erro ao iniciar CFO Sync",
            "Falha ao carregar configuracao/credenciais.\n\n"
            f"Arquivo principal esperado: {app_config_path()}\n\n"
            f"Detalhe tecnico: {error}",
        )
        root.destroy()
        return
    app.log("App pronto.")
    root.mainloop()


if __name__ == "__main__":
    main()
