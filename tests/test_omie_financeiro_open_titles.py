from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from cfo_sync.platforms.omie.credentials import OmieCredential
from cfo_sync.platforms.omie.financeiro import (
    _fetch_contas_a_pagar,
    _fetch_contas_a_receber,
)


class OmieFinanceiroOpenTitlesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.credential = OmieCredential(
            company_name="Empresa",
            alias_name="Filial",
            app_key="key",
            app_secret="secret",
            app_name="Omie Teste",
            include_accounts_payable=True,
            include_accounts_receivable=True,
            gid="123",
        )

    def test_contas_a_pagar_keeps_only_open_titles(self) -> None:
        response = {
            "total_de_paginas": 1,
            "conta_pagar_cadastro": [
                {
                    "codigo_lancamento_omie": "open-1",
                    "status_titulo": "EMABERTO",
                    "data_previsao": "15/01/2026",
                    "valor_documento": 100,
                    "pagamento": {"data": "", "valor": 0},
                },
                {
                    "codigo_lancamento_omie": "paid-1",
                    "status_titulo": "PAGO",
                    "data_previsao": "16/01/2026",
                    "valor_documento": 200,
                    "pagamento": {"data": "16/01/2026"},
                },
                {
                    "codigo_lancamento_omie": "settled-1",
                    "status_titulo": "EMABERTO",
                    "data_previsao": "17/01/2026",
                    "valor_documento": 300,
                    "data_baixa": "17/01/2026",
                },
            ],
        }

        with patch("cfo_sync.platforms.omie.financeiro.call_omie_api", return_value=response) as api:
            rows = _fetch_contas_a_pagar(
                credential=self.credential,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                lookup_clientes={},
                lookup_categorias={},
                lookup_departamentos={},
                lookup_contas_correntes={},
            )

        self.assertEqual([row["fonte"] for row in rows], ["A pagar"])
        self.assertEqual(rows[0]["valor_lancamento"], "100")
        self.assertEqual(api.call_args.kwargs["params"]["filtrar_por_status"], "EMABERTO")

    def test_contas_a_receber_keeps_only_open_titles(self) -> None:
        response = {
            "total_de_paginas": 1,
            "conta_receber_cadastro": [
                {
                    "codigo_lancamento_omie": "open-1",
                    "status_titulo": "EMABERTO",
                    "data_previsao": "15/01/2026",
                    "valor_documento": 100,
                    "recebimento": {"data": "", "valor": 0},
                },
                {
                    "codigo_lancamento_omie": "received-1",
                    "status_titulo": "RECEBIDO",
                    "data_previsao": "16/01/2026",
                    "valor_documento": 200,
                    "recebimento": {"data": "16/01/2026"},
                },
                {
                    "codigo_lancamento_omie": "settled-1",
                    "status_titulo": "EMABERTO",
                    "data_previsao": "17/01/2026",
                    "valor_documento": 300,
                    "data_recebimento": "17/01/2026",
                },
            ],
        }

        with patch("cfo_sync.platforms.omie.financeiro.call_omie_api", return_value=response) as api:
            rows = _fetch_contas_a_receber(
                credential=self.credential,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                lookup_clientes={},
                lookup_categorias={},
                lookup_departamentos={},
                lookup_contas_correntes={},
            )

        self.assertEqual([row["fonte"] for row in rows], ["A receber"])
        self.assertEqual(rows[0]["valor_lancamento"], "100")
        self.assertEqual(api.call_args.kwargs["params"]["filtrar_por_status"], "EMABERTO")


if __name__ == "__main__":
    unittest.main()
