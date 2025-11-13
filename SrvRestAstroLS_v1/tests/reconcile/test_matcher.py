import pandas as pd

from routes.v1.reconcile_start import _match_one_to_one_by_amount_and_date_window


def _pilaga_df(rows):
    data = []
    for fecha, monto, documento in rows:
        data.append(
            {
                "fecha": pd.Timestamp(fecha),
                "monto": monto,
                "documento": documento,
                "ingreso_bruto": max(monto, 0.0),
                "egreso_bruto": max(-monto, 0.0),
                "origen": "PILAGA",
            }
        )
    return pd.DataFrame(data)


def _banco_df(rows):
    return pd.DataFrame(
        {
            "fecha": [pd.Timestamp(fecha) for fecha, _, _ in rows],
            "monto": [monto for _, monto, _ in rows],
            "documento": [documento for _, _, documento in rows],
            "origen": ["EXTRACTO"] * len(rows),
        }
    )


def test_match_handles_duplicate_amounts_without_dropping_pairs():
    pilaga = _pilaga_df(
        [
            ("2025-09-03", 5_040_000.00, "DI01: 6484/2025"),
            ("2025-09-03", 5_040_000.00, "DI01: 6485/2025"),
        ]
    )
    banco = _banco_df(
        [
            ("2025-09-02", 5_040_000.00, "6209261"),
            ("2025-09-02", 5_040_000.00, "6209264"),
        ]
    )

    pairs, sobrantes_p, sobrantes_b = _match_one_to_one_by_amount_and_date_window(pilaga, banco, days_window=5)

    assert len(pairs) == 2
    assert sobrantes_p.empty
    assert sobrantes_b.empty
    assert set(pairs["documento_p"]) == {"DI01: 6484/2025", "DI01: 6485/2025"}
    assert set(pairs["documento_b"]) == {"6209261", "6209264"}
