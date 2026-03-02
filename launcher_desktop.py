from __future__ import annotations

import queue
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
from cfo_sync.platforms.meta_ads.credentials import MetaAdsCredentialsStore
from cfo_sync.platforms.yampi.api import fetch_orders_by_number
from cfo_sync.platforms.yampi.credentials import YampiCredentialsStore


ALL_SUB_CLIENTS = "Todos"

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


@dataclass(frozen=True)
class PlatformChoice:
    label: str
    platform_key: str
    resource_name: str


class CFODesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CFO Sync")
        self.root.geometry("1240x760")
        self.root.minsize(1120, 680)
        self.root.resizable(True, True)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.busy = False

        self.config = load_app_config(PROJECT_DIR / "secrets" / "app_config.json")
        self.pipeline = SyncPipeline(self.config)

        self.yampi_store = YampiCredentialsStore.from_file(
            self.config.credentials_dir / self.config.yampi.credentials_file
        )
        self.meta_ads_store = MetaAdsCredentialsStore.from_file(
            self.config.credentials_dir / self.config.meta_ads.credentials_file
        )

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
            for resource in platform.resources:
                if platform.key == "yampi" and resource.name == "sku":
                    # SKU usa aba dedicada e exportacao propria; nao aparece no seletor principal.
                    continue
                label = self._platform_resource_label(platform.key, platform.label, resource.name)
                choices.append(
                    PlatformChoice(label=label, platform_key=platform.key, resource_name=resource.name)
                )
        return choices

    def _clients_for_platform(self, platform_key: str) -> list[str]:
        key = platform_key.lower()
        if key == "yampi":
            return self.yampi_store.companies()
        if key == "meta_ads":
            return self.meta_ads_store.companies()
        return []

    @staticmethod
    def _platform_resource_label(platform_key: str, platform_label: str, resource_name: str) -> str:
        key = platform_key.lower()
        resource = resource_name.lower()
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
            text="Selecione plataforma, cliente e filial/alias para coletar e exportar.",
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

        self.tabs.add(config_tab, text="Pedidos")
        self.tabs.add(self.sku_tab, text="SKU")

        ttk.Label(config_tab, text="Pedidos", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 12)
        )

        ttk.Label(config_tab, text="Plataforma", style="Field.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 10), pady=6
        )
        self.platform_combo = ttk.Combobox(
            config_tab,
            textvariable=self.platform_var,
            state="readonly",
            values=[choice.label for choice in self.platform_choices],
            style="Dark.TCombobox",
            width=30,
        )
        self.platform_combo.grid(row=1, column=1, sticky=tk.EW, pady=6)

        ttk.Label(config_tab, text="Cliente", style="Field.TLabel").grid(
            row=2, column=0, sticky=tk.W, padx=(0, 10), pady=6
        )
        self.client_combo = ttk.Combobox(
            config_tab,
            textvariable=self.client_var,
            state="readonly",
            style="Dark.TCombobox",
            width=30,
        )
        self.client_combo.grid(row=2, column=1, sticky=tk.EW, pady=6)

        ttk.Label(config_tab, text="Filial / Alias", style="Field.TLabel").grid(
            row=3, column=0, sticky=tk.W, padx=(0, 10), pady=6
        )
        sub_client_panel = ttk.Frame(config_tab, style="Card.TFrame")
        sub_client_panel.grid(row=3, column=1, sticky=tk.NSEW, pady=6)
        sub_client_panel.columnconfigure(0, weight=1)
        sub_client_panel.rowconfigure(1, weight=1)

        ttk.Label(sub_client_panel, textvariable=self.sub_client_summary_var, style="FieldValue.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 6)
        )

        sub_client_actions = ttk.Frame(sub_client_panel, style="Card.TFrame")
        sub_client_actions.grid(row=0, column=1, sticky=tk.E, pady=(0, 6))

        self.btn_select_all_sub_clients = ttk.Button(
            sub_client_actions,
            text="Todos",
            style="Secondary.TButton",
            command=self._select_all_sub_clients,
        )
        self.btn_select_all_sub_clients.pack(side=tk.LEFT, padx=(0, 6))

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
            height=10,
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
        sub_client_scroll.grid(row=0, column=1, sticky=tk.NS, padx=(6, 0))
        self.sub_client_listbox.configure(yscrollcommand=sub_client_scroll.set)

        ttk.Label(config_tab, text="Data inicial (DD/MM/AAAA)", style="Field.TLabel").grid(
            row=4, column=0, sticky=tk.W, padx=(0, 10), pady=6
        )
        self.start_entry = ttk.Entry(
            config_tab,
            textvariable=self.start_date_var,
            width=32,
            style="Dark.TEntry",
        )
        self.start_entry.grid(row=4, column=1, sticky=tk.EW, pady=6)

        ttk.Label(config_tab, text="Data final (DD/MM/AAAA)", style="Field.TLabel").grid(
            row=5, column=0, sticky=tk.W, padx=(0, 10), pady=6
        )
        self.end_entry = ttk.Entry(
            config_tab,
            textvariable=self.end_date_var,
            width=32,
            style="Dark.TEntry",
        )
        self.end_entry.grid(row=5, column=1, sticky=tk.EW, pady=6)

        period_actions = ttk.Frame(config_tab, style="Card.TFrame")
        period_actions.grid(row=6, column=1, sticky=tk.W, pady=(8, 10))

        period_btn = ttk.Button(
            period_actions,
            text="Mês atual",
            style="Secondary.TButton",
            command=self._set_default_dates_current_month,
        )
        period_btn.pack(side=tk.LEFT, padx=(0, 8))

        previous_month_btn = ttk.Button(
            period_actions,
            text="Mês anterior",
            style="Secondary.TButton",
            command=self._set_previous_month_period_based_on_today,
        )
        previous_month_btn.pack(side=tk.LEFT)

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

        sku_columns = ("sku_id", "item_sku", "price_cost", "quantity")
        self.sku_tree = ttk.Treeview(
            sku_table_frame,
            columns=sku_columns,
            show="headings",
            style="Dark.Treeview",
        )
        self.sku_tree.heading("sku_id", text="SKU_ID")
        self.sku_tree.heading("item_sku", text="ITEM_SKU")
        self.sku_tree.heading("price_cost", text="PRICE_COST")
        self.sku_tree.heading("quantity", text="QUANTITY")
        self.sku_tree.column("sku_id", anchor=tk.CENTER, stretch=False)
        self.sku_tree.column("item_sku", anchor=tk.W, stretch=False)
        self.sku_tree.column("price_cost", anchor=tk.E, stretch=False)
        self.sku_tree.column("quantity", anchor=tk.CENTER, stretch=False)
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
        ttk.Label(log_card, text="Log", style="CardTitle.TLabel").pack(anchor=tk.W, pady=(0, 10))

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
            ("sku_id", 0.18),
            ("item_sku", 0.46),
            ("price_cost", 0.20),
            ("quantity", 0.16),
        ]

        used = 0
        for column_name, ratio in ratios[:-1]:
            col_width = int(available * ratio)
            self.sku_tree.column(column_name, width=col_width)
            used += col_width

        # Ajusta a ultima coluna com a sobra para ocupar 100% da largura visivel.
        last_column = ratios[-1][0]
        self.sku_tree.column(last_column, width=max(20, available - used))

    def _bind_events(self) -> None:
        self.platform_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_platform_change())
        self.client_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_client_change())
        self.sub_client_listbox.bind("<<ListboxSelect>>", lambda _event: self._update_sub_client_summary())
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self._on_tab_changed())
        self.sku_order_entry.bind("<Return>", lambda _event: self.search_sku())

    def _load_initial_values(self) -> None:
        if not self.platform_choices:
            raise RuntimeError("Nenhuma plataforma/recurso configurado em secrets/app_config.json")

        first = self.platform_choices[0]
        self.platform_var.set(first.label)
        self.on_platform_change()
        self._update_export_sku_button_state()

    def log(self, message: str) -> None:
        self.log_queue.put(message)

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
            self.btn_select_all_sub_clients.configure(state=tk.DISABLED)
            self.btn_clear_sub_clients.configure(state=tk.DISABLED)
            self.sub_client_listbox.configure(state=tk.DISABLED)
            self.btn_search_sku.configure(state=tk.DISABLED)
            self.sku_order_entry.configure(state=tk.DISABLED)
            return

        self.btn_collect.configure(state=tk.NORMAL)
        self.btn_export.configure(state=tk.NORMAL)
        self._update_export_sku_button_state()

        has_sub_clients = bool(self.sub_client_options)
        controls_state = tk.NORMAL if has_sub_clients else tk.DISABLED
        self.btn_select_all_sub_clients.configure(state=controls_state)
        self.btn_clear_sub_clients.configure(state=controls_state)
        self.sub_client_listbox.configure(state=controls_state)
        self.btn_search_sku.configure(state=tk.NORMAL)
        self.sku_order_entry.configure(state=tk.NORMAL)

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

    def _is_sku_tab_active(self) -> bool:
        selected_tab_id = self.tabs.select()
        return selected_tab_id == str(self.sku_tab)

    def _update_export_sku_button_state(self) -> None:
        if self._is_sku_tab_active():
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

    @staticmethod
    def _to_sku_price_cost(raw_item: dict[str, object], raw_sku: dict[str, object]) -> float:
        for raw_value in (raw_item.get("price_cost"), raw_sku.get("price_cost"), raw_item.get("price")):
            if raw_value in (None, ""):
                continue
            try:
                return float(raw_value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        return 0.0

    @staticmethod
    def _extract_items_from_order(order: dict[str, object]) -> list[dict[str, object]]:
        items = order.get("items")
        if isinstance(items, dict):
            data = items.get("data")
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return []

    def _build_sku_preview_rows(self, order: dict[str, object]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for raw_item in self._extract_items_from_order(order):
            raw_sku_wrapper = raw_item.get("sku")
            raw_sku: dict[str, object] = {}
            if isinstance(raw_sku_wrapper, dict):
                nested = raw_sku_wrapper.get("data")
                if isinstance(nested, dict):
                    raw_sku = nested

            sku_id = raw_item.get("sku_id") or raw_sku.get("id")
            item_sku = raw_item.get("item_sku") or raw_sku.get("sku")
            quantity = raw_item.get("quantity") or 0
            price_cost = self._to_sku_price_cost(raw_item, raw_sku)

            rows.append(
                {
                    "sku_id": str(sku_id or "").strip(),
                    "item_sku": str(item_sku or "").strip(),
                    "price_cost": round(float(price_cost), 2),
                    "quantity": int(quantity) if str(quantity).isdigit() else quantity,
                }
            )

        unique: dict[tuple[str, str, float, str], dict[str, object]] = {}
        for row in rows:
            key = (
                str(row["sku_id"]),
                str(row["item_sku"]),
                float(row["price_cost"]),
                str(row["quantity"]),
            )
            if key not in unique:
                unique[key] = row
        return list(unique.values())

    def _render_sku_preview(self) -> None:
        self.sku_tree.delete(*self.sku_tree.get_children())
        for row in self.sku_preview_rows:
            self.sku_tree.insert(
                "",
                tk.END,
                values=(
                    row.get("sku_id", ""),
                    row.get("item_sku", ""),
                    f"{float(row.get('price_cost', 0.0)):.2f}",
                    row.get("quantity", 0),
                ),
            )

    def _clear_sku_preview(self) -> None:
        self.sku_preview_rows = []
        self._render_sku_preview()

    @staticmethod
    def _order_matches_number(order: dict[str, object], order_number: str) -> bool:
        candidate_number = str(order.get("number") or "").strip()
        candidate_id = str(order.get("id") or "").strip()
        number = order_number.strip()
        if not number:
            return False
        return candidate_number == number or candidate_id == number

    def search_sku(self) -> None:
        def task() -> None:
            choice = self._get_current_choice()
            if choice.platform_key != "yampi":
                raise ValueError("Busca SKU disponivel apenas para Yampi no momento.")

            client = self.client_var.get().strip()
            if not client:
                raise ValueError("Selecione um cliente.")

            order_number = self.sku_order_number_var.get().strip()
            if not order_number:
                raise ValueError("Informe o numero do pedido para buscar SKU.")

            selected_alias_names = self._selected_sub_clients()
            alias_credentials = self.yampi_store.aliases_for_company(client)
            if selected_alias_names:
                selected_set = {name.strip() for name in selected_alias_names if name.strip()}
                alias_credentials = [
                    credential for credential in alias_credentials if credential.alias in selected_set
                ]

            if not alias_credentials:
                raise ValueError("Nenhum alias selecionado para buscar SKU.")

            found_orders: list[dict[str, object]] = []
            found_aliases: list[str] = []
            for credential in alias_credentials:
                orders = fetch_orders_by_number(credential=credential, order_number=order_number)
                matched_orders = [order for order in orders if self._order_matches_number(order, order_number)]
                if matched_orders:
                    found_orders.extend(matched_orders)
                    found_aliases.append(credential.alias)

            if not found_orders:
                self.root.after(0, self._clear_sku_preview)
                raise ValueError(f"Pedido {order_number} nao encontrado nos aliases selecionados.")

            rows: list[dict[str, object]] = []
            for order in found_orders:
                rows.extend(self._build_sku_preview_rows(order))

            # Evita duplicidade quando o mesmo pedido aparece em mais de uma tentativa.
            unique_rows: dict[tuple[str, str, float, str], dict[str, object]] = {}
            for row in rows:
                key = (
                    str(row.get("sku_id", "")),
                    str(row.get("item_sku", "")),
                    float(row.get("price_cost", 0.0)),
                    str(row.get("quantity", "")),
                )
                if key not in unique_rows:
                    unique_rows[key] = row

            self.sku_preview_rows = list(unique_rows.values())
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

    @staticmethod
    def _normalize_monthly_period(choice: PlatformChoice, start_date: date, end_date: date) -> tuple[date, date]:
        if choice.platform_key != "yampi" or choice.resource_name != "financeiro":
            return start_date, end_date

        # Financeiro e mensal. Quando inicio/fim estao no dia 1, consideramos o mes inteiro.
        if start_date.day != 1 or end_date.day != 1:
            return start_date, end_date

        if start_date > end_date:
            return start_date, end_date

        today = date.today()
        if end_date.year == today.year and end_date.month == today.month:
            return start_date, today

        next_month = date(end_date.year + (1 if end_date.month == 12 else 0), (end_date.month % 12) + 1, 1)
        return start_date, next_month - timedelta(days=1)

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

    def on_client_change(self) -> None:
        choice = self.choice_by_label[self.platform_var.get()]
        client = self.client_var.get().strip()
        options: list[str] = []
        self._clear_sku_preview()

        try:
            if choice.platform_key == "yampi":
                options.extend(self.yampi_store.alias_names_for_company(client))
            elif choice.platform_key == "meta_ads":
                options.extend(self.meta_ads_store.ad_account_names_for_company(client))
        except Exception as error:  # noqa: BLE001
            self.log(f"Aviso ao carregar filiais/aliases: {error}")

        self._set_sub_client_options(options)

    def _set_sub_client_options(self, options: list[str]) -> None:
        self.sub_client_options = options
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
        self.start_date_var.set(today.replace(day=1).strftime("%d/%m/%Y"))
        self.end_date_var.set(today.strftime("%d/%m/%Y"))

    def _set_previous_month_period_based_on_today(self) -> None:
        today = date.today()
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        first_day_previous_month = last_day_previous_month.replace(day=1)

        self.start_date_var.set(first_day_previous_month.strftime("%d/%m/%Y"))
        self.end_date_var.set(last_day_previous_month.strftime("%d/%m/%Y"))

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

        self._run_task("Exportacao", task)

    def export_sku(self) -> None:
        if not self._is_sku_tab_active():
            return

        def task() -> None:
            if not self.sku_preview_rows:
                raise ValueError("Nenhum SKU carregado. Clique em Buscar SKU antes de exportar.")

            choice = self._get_current_choice()
            if choice.platform_key != "yampi":
                raise ValueError("Exportacao SKU disponivel apenas para Yampi no momento.")

            client = self.client_var.get().strip()
            if not client:
                raise ValueError("Selecione um cliente para exportar SKU.")

            sku_resource = self._resolve_resource_by_name(platform_key="yampi", resource_name="sku")

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

        self._run_task("Exportar SKU", task)


def main() -> None:
    root = tk.Tk()
    app = CFODesktopApp(root)
    app.log("App pronto.")
    root.mainloop()


if __name__ == "__main__":
    main()
