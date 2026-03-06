from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.pipeline import SyncPipeline
from cfo_sync.platforms.ui_registry import build_platform_ui_registry


def run_dashboard() -> None:
    st.set_page_config(page_title="CFO Sync", layout="wide")
    st.title("CFO Sync")
    st.caption("Coleta de APIs por plataforma e exportacao para Google Sheets")

    config = load_app_config(Path("secrets/app_config.json"))
    pipeline = SyncPipeline(config)
    ui_registry = build_platform_ui_registry(config)

    platforms = {p.key: p for p in config.platforms}
    platform_labels = {p.label: p.key for p in config.platforms}
    selected_platform_label = st.selectbox("Plataforma", list(platform_labels.keys()), index=0)
    platform_key = platform_labels[selected_platform_label]
    selected_platform = platforms[platform_key]
    platform_behavior = ui_registry[platform_key]

    client_options = platform_behavior.companies(selected_platform.clients)
    if not client_options:
        st.warning("Nenhum cliente disponivel para esta plataforma.")
        return
    client = st.selectbox("Cliente", client_options, index=0)

    selected_sub_clients: list[str] | None = None
    sub_client_options = platform_behavior.sub_client_names(client)
    if sub_client_options:
        if platform_key == "omie":
            sub_client_label = "Filiais / Alias"
        elif platform_key == "mercado_livre":
            sub_client_label = "Alias / Filial"
        else:
            sub_client_label = "Subcliente / Conta"
        default_selected = sub_client_options if len(sub_client_options) == 1 else []
        selected_sub_clients = st.multiselect(
            sub_client_label,
            options=sub_client_options,
            default=default_selected,
            placeholder="Selecione um ou mais itens",
        )

    available_resources = [resource.name for resource in selected_platform.resources]
    if not available_resources:
        st.warning("Nenhum recurso configurado para esta plataforma.")
        return

    selected_resource = st.selectbox("Recurso", available_resources, index=0)

    today = date.today()
    first_day_of_month = today.replace(day=1)
    period = st.date_input(
        "Periodo (inicio e fim)",
        value=(first_day_of_month, today),
        format="DD/MM/YYYY",
    )

    if not isinstance(period, (tuple, list)) or len(period) != 2:
        st.warning("Selecione data inicial e data final.")
        return

    start_date = period[0]
    end_date = period[1]
    start_date_str = start_date.isoformat()
    end_date_str = end_date.isoformat()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Coletar e salvar no banco local", use_container_width=True):
            count = pipeline.collect(
                platform_key=platform_key,
                client=client,
                start_date=start_date_str,
                end_date=end_date_str,
                resource_names=[selected_resource],
                sub_clients=selected_sub_clients,
            )
            st.success(f"{count} registros coletados e salvos localmente.")

    with c2:
        if st.button("Exportar para Sheets", use_container_width=True):
            count = pipeline.export_to_sheets(
                platform_key=platform_key,
                client=client,
                start_date=start_date_str,
                end_date=end_date_str,
                resource_names=[selected_resource],
                sub_clients=selected_sub_clients,
            )
            st.success(f"{count} registros enviados para exportacao.")

    st.divider()
    st.subheader("Arquitetura aplicada")
    st.write("- UI unica em `src/cfo_sync/ui`")
    st.write("- Conector separado por plataforma em `src/cfo_sync/platforms`")
    st.write("- Config central para clientes/plataformas em `secrets/app_config.json`")
