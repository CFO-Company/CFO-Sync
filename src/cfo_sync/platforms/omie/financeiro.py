from __future__ import annotations

from datetime import date, datetime
from typing import Any

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.omie.api import call_omie_api
from cfo_sync.platforms.omie.credentials import OmieCredential


def fetch_financeiro(
    client: str,
    resource: ResourceConfig,
    credentials: list[OmieCredential],
    start_date: str | None = None,
    end_date: str | None = None,
    sub_clients: list[str] | None = None,
) -> list[RawRecord]:
    del resource
    period_start, period_end = _normalize_period(start_date, end_date)

    selected_credentials = credentials
    if sub_clients:
        selected_names = {name.strip() for name in sub_clients if str(name).strip()}
        selected_credentials = [
            credential for credential in credentials if credential.alias_name in selected_names
        ]

    if not selected_credentials:
        raise ValueError(f"Nenhuma filial/alias da Omie selecionada para o cliente '{client}'.")

    rows: list[RawRecord] = []
    for credential in selected_credentials:
        lookup_clientes = _fetch_lookup_clientes(credential)
        lookup_categorias = _fetch_lookup_categorias(credential)
        lookup_departamentos = _fetch_lookup_departamentos(credential)

        rows.extend(
            _fetch_conta_corrente(
                credential=credential,
                period_start=period_start,
                period_end=period_end,
                lookup_clientes=lookup_clientes,
                lookup_categorias=lookup_categorias,
                lookup_departamentos=lookup_departamentos,
            )
        )

        if credential.include_accounts_payable:
            rows.extend(
                _fetch_contas_a_pagar(
                    credential=credential,
                    period_start=period_start,
                    period_end=period_end,
                    lookup_clientes=lookup_clientes,
                    lookup_categorias=lookup_categorias,
                    lookup_departamentos=lookup_departamentos,
                )
            )

        if credential.include_accounts_receivable:
            rows.extend(
                _fetch_contas_a_receber(
                    credential=credential,
                    period_start=period_start,
                    period_end=period_end,
                    lookup_clientes=lookup_clientes,
                    lookup_categorias=lookup_categorias,
                    lookup_departamentos=lookup_departamentos,
                )
            )

    rows.sort(key=lambda row: (str(row.get("origem", "")).lower(), str(row.get("fonte", "")).lower()))
    rows.sort(key=lambda row: _sort_date_key(str(row.get("data", ""))))
    return rows


def _fetch_lookup_clientes(credential: OmieCredential) -> dict[str, str]:
    rows = _paginate(
        credential=credential,
        call="ListarClientes",
        endpoint="geral/clientes/",
        base_params={"registros_por_pagina": 500, "apenas_importado_api": "N"},
        page_param="pagina",
        total_pages_field="total_de_paginas",
        items_field="clientes_cadastro",
    )
    lookup: dict[str, str] = {}
    for item in rows:
        code = str(item.get("codigo_cliente_omie", "")).strip()
        name = str(item.get("nome_fantasia") or item.get("razao_social") or "").strip()
        if code:
            lookup[code] = name
    return lookup


def _fetch_lookup_categorias(credential: OmieCredential) -> dict[str, str]:
    rows = _paginate(
        credential=credential,
        call="ListarCategorias",
        endpoint="geral/categorias/",
        base_params={"registros_por_pagina": 500},
        page_param="pagina",
        total_pages_field="total_de_paginas",
        items_field="categoria_cadastro",
    )
    lookup: dict[str, str] = {}
    for item in rows:
        code = str(item.get("codigo", "")).strip()
        name = str(item.get("descricao") or "").strip()
        if code:
            lookup[code] = name
    return lookup


def _fetch_lookup_departamentos(credential: OmieCredential) -> dict[str, str]:
    rows = _paginate(
        credential=credential,
        call="ListarDepartamentos",
        endpoint="geral/departamentos/",
        base_params={"registros_por_pagina": 500},
        page_param="pagina",
        total_pages_field="total_de_paginas",
        items_field="departamentos",
    )
    lookup: dict[str, str] = {}
    for item in rows:
        code = str(item.get("codigo", "")).strip()
        name = str(item.get("descricao") or "").strip()
        if code:
            lookup[code] = name
    return lookup


def _fetch_conta_corrente(
    credential: OmieCredential,
    period_start: date,
    period_end: date,
    lookup_clientes: dict[str, str],
    lookup_categorias: dict[str, str],
    lookup_departamentos: dict[str, str],
) -> list[RawRecord]:
    rows: list[RawRecord] = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        response = call_omie_api(
            credential=credential,
            call="ListarLancCC",
            endpoint="financas/contacorrentelancamentos/",
            params={
                "nPagina": page,
                "nRegPorPagina": 500,
                "dtPagInicial": _format_omie_date(period_start),
                "dtPagFinal": _format_omie_date(period_end),
            },
        )
        if not response:
            break

        total_pages = int(response.get("nTotPaginas") or 1)
        for lancamento in response.get("listaLancamentos") or []:
            cabecalho = lancamento.get("cabecalho") or {}
            detalhes = lancamento.get("detalhes") or {}
            diversos = lancamento.get("diversos") or {}
            info = lancamento.get("info") or {}

            data_lancamento = str(cabecalho.get("dDtLanc") or "").strip()
            if not _is_date_in_period(data_lancamento, period_start, period_end):
                continue

            valor_total = _to_float(cabecalho.get("nValorLanc"))
            natureza = str(diversos.get("cNatureza") or "").strip().upper() or "P"
            lancamento_id = str(
                lancamento.get("nCodLanc") or lancamento.get("cCodIntLanc") or ""
            ).strip()

            departamentos = lancamento.get("departamentos") or [{"cCodDep": "", "nPerDep": 100}]
            categorias = detalhes.get("aCodCateg") or [
                {"cCodCateg": detalhes.get("cCodCateg") or "", "nPerc": 100}
            ]

            for rateio in _build_rateios(
                total_value=valor_total,
                departamentos=departamentos,
                categorias=categorias,
                dep_percent_key="nPerDep",
                cat_percent_key="nPerc",
                dep_code_key="cCodDep",
                cat_code_key="cCodCateg",
            ):
                departamento_code = rateio["dep_code"]
                categoria_code = rateio["cat_code"]
                cliente_code = str(detalhes.get("nCodCliente") or "").strip()
                valor_rateado = rateio["value"]
                valor_sinal = valor_rateado if natureza == "R" else -valor_rateado

                rows.append(
                    _build_row(
                        origem=credential.app_name,
                        fonte="Recebido" if natureza == "R" else "Pago",
                        data=data_lancamento,
                        conta_corrente=str(cabecalho.get("nCodCC") or "").strip(),
                        valor_lancamento=valor_rateado,
                        departamento=lookup_departamentos.get(departamento_code, ""),
                        categoria=lookup_categorias.get(categoria_code, ""),
                        observacao=str(detalhes.get("cObs") or "").strip(),
                        cliente=lookup_clientes.get(cliente_code, ""),
                        natureza=natureza,
                        valor_percentual=valor_rateado,
                        valor_sinal=valor_sinal,
                        data_registro=str(info.get("dInc") or "").strip(),
                        unique_key="||".join(
                            [
                                _normalize_origin(credential.app_name),
                                "CC",
                                lancamento_id,
                                str(cabecalho.get("nCodCC") or "").strip(),
                                data_lancamento,
                                _stringify_number(valor_total),
                                cliente_code,
                                departamento_code,
                                categoria_code,
                            ]
                        ),
                    )
                )
        page += 1

    return rows


def _fetch_contas_a_pagar(
    credential: OmieCredential,
    period_start: date,
    period_end: date,
    lookup_clientes: dict[str, str],
    lookup_categorias: dict[str, str],
    lookup_departamentos: dict[str, str],
) -> list[RawRecord]:
    rows: list[RawRecord] = []

    for status in ("EMABERTO", "PAGO"):
        page = 1
        total_pages = 1
        while page <= total_pages:
            response = call_omie_api(
                credential=credential,
                call="ListarContasPagar",
                endpoint="financas/contapagar/",
                params={
                    "pagina": page,
                    "registros_por_pagina": 500,
                    "apenas_importado_api": "N",
                    "filtrar_por_status": status,
                },
            )
            if not response:
                break

            total_pages = int(response.get("total_de_paginas") or 1)
            for cadastro in response.get("conta_pagar_cadastro") or []:
                data_previsao = str(cadastro.get("data_previsao") or "").strip()
                if not _is_date_in_period(data_previsao, period_start, period_end):
                    continue

                valor_documento = _to_float(cadastro.get("valor_documento"))
                lancamento_id = str(
                    cadastro.get("codigo_lancamento_omie") or cadastro.get("codigo_lancamento_integracao") or ""
                ).strip()
                cliente_code = str(cadastro.get("codigo_cliente_fornecedor") or "").strip()
                categorias = cadastro.get("categorias") or [
                    {"codigo_categoria": cadastro.get("codigo_categoria") or "", "percentual": 100}
                ]
                distribuicao = cadastro.get("distribuicao") or [{"cCodDep": "", "nPerDep": 100}]

                for rateio in _build_rateios(
                    total_value=valor_documento,
                    departamentos=distribuicao,
                    categorias=categorias,
                    dep_percent_key="nPerDep",
                    cat_percent_key="percentual",
                    dep_code_key="cCodDep",
                    cat_code_key="codigo_categoria",
                ):
                    departamento_code = rateio["dep_code"]
                    categoria_code = rateio["cat_code"]
                    valor_rateado = rateio["value"]

                    rows.append(
                        _build_row(
                            origem=credential.app_name,
                            fonte="Pago" if status == "PAGO" else "A pagar",
                            data=data_previsao,
                            conta_corrente=str(cadastro.get("id_conta_corrente") or "").strip(),
                            valor_lancamento=valor_documento,
                            departamento=lookup_departamentos.get(departamento_code, ""),
                            categoria=lookup_categorias.get(categoria_code, ""),
                            observacao=str(cadastro.get("observacao") or "").strip(),
                            cliente=lookup_clientes.get(cliente_code, ""),
                            natureza="P",
                            valor_percentual=valor_rateado,
                            valor_sinal=-valor_rateado,
                            data_registro=str(cadastro.get("data_emissao") or "").strip(),
                            unique_key="||".join(
                                [
                                    _normalize_origin(credential.app_name),
                                    "CAP",
                                    lancamento_id,
                                    str(cadastro.get("id_conta_corrente") or "").strip(),
                                    data_previsao,
                                    _stringify_number(valor_documento),
                                    cliente_code,
                                    departamento_code,
                                    categoria_code,
                                    status,
                                ]
                            ),
                        )
                    )
            page += 1

    return rows


def _fetch_contas_a_receber(
    credential: OmieCredential,
    period_start: date,
    period_end: date,
    lookup_clientes: dict[str, str],
    lookup_categorias: dict[str, str],
    lookup_departamentos: dict[str, str],
) -> list[RawRecord]:
    rows: list[RawRecord] = []

    for status in ("EMABERTO", "PAGO"):
        page = 1
        total_pages = 1
        while page <= total_pages:
            response = call_omie_api(
                credential=credential,
                call="ListarContasReceber",
                endpoint="financas/contareceber/",
                params={
                    "pagina": page,
                    "registros_por_pagina": 200,
                    "apenas_importado_api": "N",
                    "filtrar_por_status": status,
                },
            )
            if not response:
                break

            total_pages = int(response.get("total_de_paginas") or 1)
            for cadastro in response.get("conta_receber_cadastro") or []:
                data_lancamento = _resolve_conta_receber_data(cadastro, status)
                if not _is_date_in_period(data_lancamento, period_start, period_end):
                    continue

                valor_documento = _to_float(cadastro.get("valor_documento"))
                lancamento_id = str(
                    cadastro.get("codigo_lancamento_omie") or cadastro.get("codigo_lancamento_integracao") or ""
                ).strip()
                cliente_code = str(cadastro.get("codigo_cliente_fornecedor") or "").strip()
                categorias = cadastro.get("categorias") or [
                    {"codigo_categoria": cadastro.get("codigo_categoria") or "", "percentual": 100}
                ]
                distribuicao = cadastro.get("distribuicao") or [{"cCodDep": "", "nPerDep": 100}]

                for rateio in _build_rateios(
                    total_value=valor_documento,
                    departamentos=distribuicao,
                    categorias=categorias,
                    dep_percent_key="nPerDep",
                    cat_percent_key="percentual",
                    dep_code_key="cCodDep",
                    cat_code_key="codigo_categoria",
                ):
                    departamento_code = rateio["dep_code"]
                    categoria_code = rateio["cat_code"]
                    valor_rateado = rateio["value"]

                    rows.append(
                        _build_row(
                            origem=credential.app_name,
                            fonte="Recebido" if status == "PAGO" else "A receber",
                            data=data_lancamento,
                            conta_corrente=str(cadastro.get("id_conta_corrente") or "").strip(),
                            valor_lancamento=valor_documento,
                            departamento=lookup_departamentos.get(departamento_code, ""),
                            categoria=lookup_categorias.get(categoria_code, ""),
                            observacao=str(cadastro.get("observacao") or "").strip(),
                            cliente=lookup_clientes.get(cliente_code, ""),
                            natureza="R",
                            valor_percentual=valor_rateado,
                            valor_sinal=valor_rateado,
                            data_registro=str(cadastro.get("data_registro") or "").strip(),
                            unique_key="||".join(
                                [
                                    _normalize_origin(credential.app_name),
                                    "CAR",
                                    lancamento_id,
                                    str(cadastro.get("id_conta_corrente") or "").strip(),
                                    data_lancamento,
                                    _stringify_number(valor_documento),
                                    cliente_code,
                                    departamento_code,
                                    categoria_code,
                                    status,
                                ]
                            ),
                        )
                    )
            page += 1

    return rows


def _paginate(
    credential: OmieCredential,
    call: str,
    endpoint: str,
    base_params: dict[str, Any],
    page_param: str,
    total_pages_field: str,
    items_field: str,
) -> list[dict[str, Any]]:
    page = 1
    total_pages = 1
    rows: list[dict[str, Any]] = []

    while page <= total_pages:
        params = dict(base_params)
        params[page_param] = page
        response = call_omie_api(
            credential=credential,
            call=call,
            endpoint=endpoint,
            params=params,
        )
        if not response:
            break

        rows.extend([item for item in response.get(items_field) or [] if isinstance(item, dict)])
        total_pages = int(response.get(total_pages_field) or 1)
        page += 1

    return rows


def _build_rateios(
    total_value: float,
    departamentos: list[dict[str, Any]],
    categorias: list[dict[str, Any]],
    dep_percent_key: str,
    cat_percent_key: str,
    dep_code_key: str,
    cat_code_key: str,
) -> list[dict[str, Any]]:
    combos: list[dict[str, Any]] = []
    total_preliminary = 0.0

    dep_rows = departamentos or [{dep_code_key: "", dep_percent_key: 100}]
    cat_rows = categorias or [{cat_code_key: "", cat_percent_key: 100}]

    for dep in dep_rows:
        dep_percent = _to_float(dep.get(dep_percent_key) or 100) / 100.0
        for cat in cat_rows:
            cat_percent = _to_float(cat.get(cat_percent_key) or 100) / 100.0
            value = round(total_value * dep_percent * cat_percent, 2)
            combos.append(
                {
                    "dep_code": str(dep.get(dep_code_key) or "").strip(),
                    "cat_code": str(cat.get(cat_code_key) or "").strip(),
                    "value": value,
                }
            )
            total_preliminary += value

    if combos:
        residual = round(total_value - total_preliminary, 2)
        combos[-1]["value"] = round(float(combos[-1]["value"]) + residual, 2)

    return combos


def _build_row(
    origem: str,
    fonte: str,
    data: str,
    conta_corrente: str,
    valor_lancamento: float,
    departamento: str,
    categoria: str,
    observacao: str,
    cliente: str,
    natureza: str,
    valor_percentual: float,
    valor_sinal: float,
    data_registro: str,
    unique_key: str,
) -> RawRecord:
    formatted_origem = _normalize_origin_label(origem)
    formatted_data = _normalize_date_output(data)
    formatted_data_registro = _normalize_date_output(data_registro)
    formatted_valor_lancamento = _format_decimal_pt_br(valor_lancamento)
    formatted_valor_percentual = _format_decimal_pt_br(valor_percentual)
    formatted_valor_sinal = _format_decimal_pt_br(valor_sinal)
    return {
        "origem": formatted_origem,
        "fonte": str(fonte or "").strip(),
        "data": formatted_data,
        "conta_corrente": conta_corrente,
        "valor_lancamento": formatted_valor_lancamento,
        "departamento": str(departamento or "").strip(),
        "codigo_categoria": str(categoria or "").strip(),
        "observacao": str(observacao or "").strip(),
        "cliente": str(cliente or "").strip(),
        "natureza": str(natureza or "").strip().upper(),
        "valor_percentual": formatted_valor_percentual,
        "categoria": str(categoria or "").strip(),
        "departamento_desc": str(departamento or "").strip(),
        "cliente_desc": str(cliente or "").strip(),
        "valor_sinal": formatted_valor_sinal,
        "data_registro": formatted_data_registro,
        "unique_key": unique_key,
    }


def _normalize_period(start_date: str | None, end_date: str | None) -> tuple[date, date]:
    today = date.today()
    default_start = today.replace(day=1)
    start = date.fromisoformat(start_date) if start_date else default_start
    end = date.fromisoformat(end_date) if end_date else today
    if start > end:
        raise ValueError("Data inicial nao pode ser maior que data final.")
    return start, end


def _resolve_conta_receber_data(cadastro: dict[str, Any], status: str) -> str:
    if status == "PAGO":
        recebimento = cadastro.get("recebimento")
        if isinstance(recebimento, dict):
            data_recebimento = str(recebimento.get("data") or "").strip()
            if data_recebimento:
                return data_recebimento
    return str(cadastro.get("data_previsao") or "").strip()


def _format_omie_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _parse_omie_date(raw_value: str) -> date | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    if " " in text:
        text = text.split(" ", maxsplit=1)[0]
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None


def _is_date_in_period(raw_value: str, period_start: date, period_end: date) -> bool:
    parsed = _parse_omie_date(raw_value)
    if parsed is None:
        return False
    return period_start <= parsed <= period_end


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return 0.0


def _stringify_number(value: float) -> str:
    return f"{round(float(value), 2):.2f}"


def _normalize_origin(value: str) -> str:
    return str(value or "").strip().upper()


def _normalize_origin_label(value: str) -> str:
    return str(value or "").strip()


def _normalize_date_output(raw_value: str) -> str:
    parsed = _parse_omie_date(raw_value)
    if parsed is None:
        return str(raw_value or "").strip()
    return parsed.strftime("%d/%m/%Y")


def _format_decimal_pt_br(value: Any) -> str:
    rounded = round(_to_float(value), 2)
    text = f"{rounded:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _sort_date_key(raw_value: str) -> tuple[int, int, int]:
    parsed = _parse_omie_date(raw_value)
    if parsed is None:
        return (9999, 12, 31)
    return (parsed.year, parsed.month, parsed.day)
