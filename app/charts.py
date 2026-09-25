"""Grafici plotly della dashboard."""

import pandas as pd
import plotly.graph_objects as go

from app.db import STATUSES

# Blu sempre più scuro man mano che la candidatura avanza, grigio neutro per Rejected.
# Tonalità scelte per restare leggibili sia con il tema chiaro sia con quello scuro.
STATUS_COLORS = {
    "Applied": "#86b6ef",
    "Interview": "#3987e5",
    "Offer": "#1c5cab",
    "Rejected": "#898781",
}


def status_donut(df: pd.DataFrame, background: str = "#ffffff") -> go.Figure:
    """Ciambella con la distribuzione delle candidature per status.

    `background` è il colore di sfondo della pagina: separa le fette con uno stacco di 2px.
    """
    counts = df["status"].value_counts().reindex(STATUSES, fill_value=0)
    counts = counts[counts > 0]  # plotly mostrerebbe l'etichetta "0" anche per le fette vuote
    total = len(df)

    fig = go.Figure(
        go.Pie(
            labels=counts.index,
            values=counts.values,
            hole=0.62,
            sort=False,
            direction="clockwise",
            marker={
                "colors": [STATUS_COLORS[status] for status in counts.index],
                "line": {"color": background, "width": 2},
            },
            textinfo="value",
            hovertemplate="<b>%{label}</b>: %{value} (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        annotations=[
            {
                "text": f"<b>{total}</b><br>{'candidatura' if total == 1 else 'candidature'}",
                "showarrow": False,
                "font": {"size": 16},
            }
        ],
        height=360,
        # Legenda sotto la ciambella, in un margine riservato: in colonne strette va su
        # due righe senza sovrapporsi al grafico.
        margin={"t": 10, "b": 70, "l": 10, "r": 10},
        legend={"orientation": "h", "x": 0.5, "xanchor": "center", "y": -0.04, "yanchor": "top"},
        separators=",.",
        uniformtext={"minsize": 12, "mode": "hide"},
    )
    return fig
