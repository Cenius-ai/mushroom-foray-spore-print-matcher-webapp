"""Dashboard tab: KPI strip and four charts fed by ``/api/dashboard`` aggregates."""

from __future__ import annotations

from dataclasses import dataclass

import gradio as gr
import pandas as pd

import ui_common as ui

# Chart series colours are HEX only: canvas/vega charting cannot parse oklch(),
# and each of these clears 3:1 against the card background.
CHART_ACCENT = "#1F7F5B"
BAND_COLOURS = {"Low": "#1F7F5B", "Moderate": "#B26B00", "High": "#C9302D"}
SERIES_LABEL = "Finds"


@dataclass
class DashboardTab:
    filter: gr.Dropdown
    kpis: gr.HTML
    charts_row: gr.Column
    swatch_chart: gr.BarPlot
    conf_chart: gr.BarPlot
    band_chart: gr.BarPlot
    scatter: gr.ScatterPlot
    swatch_key: gr.HTML
    empty: gr.HTML


def filter_choices(sessions: list[dict]) -> list[tuple[str, str]]:
    return [("All sessions", "all")] + [(row["name"], str(row["id"])) for row in sessions]


def swatch_frame(payload: dict) -> pd.DataFrame:
    rows = payload["swatch_counts"]
    return pd.DataFrame(
        {
            "Swatch class": [row["name"] for row in rows],
            "Finds": [row["count"] for row in rows],
            "Series": [SERIES_LABEL] * len(rows),
        }
    )


def confidence_frame(payload: dict) -> pd.DataFrame:
    rows = payload["confidence_bins"]
    return pd.DataFrame(
        {
            "Confidence": [row["bin"] for row in rows],
            "Finds": [row["count"] for row in rows],
            "Series": [SERIES_LABEL] * len(rows),
        }
    )


def band_frame(payload: dict) -> pd.DataFrame:
    rows = payload["risk_bands"]
    return pd.DataFrame(
        {
            "Risk band": [row["band"].capitalize() for row in rows],
            "Finds": [row["count"] for row in rows],
            "Band": [row["band"].capitalize() for row in rows],
        }
    )


def scatter_frame(payload: dict) -> pd.DataFrame:
    rows = payload["scatter"]
    return pd.DataFrame(
        {
            "Cap diameter (mm)": [row["cap_diameter_mm"] for row in rows],
            "Gill spacing (mm)": [row["gill_spacing"] for row in rows],
            "Risk band": [row["risk_band"].capitalize() for row in rows],
        }
    )


def empty_panel(session_label: str) -> str:
    return ui.empty_state(
        "No finds in this session yet",
        f"{session_label} has no logged finds, so there is nothing to chart. "
        "Save a match from the Matcher tab and the panels fill in immediately.",
        "Charts stay hidden until at least one find exists.",
    )


def build_dashboard(sessions: list[dict], selected_value: str, payload: dict, session_label: str) -> DashboardTab:
    has_data = payload["total_findings"] > 0
    with gr.Column(elem_classes=["panel", "dashboard-panel"]):
        with gr.Row(equal_height=False, elem_classes=["dashboard-head"]):
            gr.HTML(ui.section_header("Foray dashboard", "aggregates over your own finds", ""))
            dashboard_filter = gr.Dropdown(
                choices=filter_choices(sessions),
                value=selected_value,
                label="Foray session filter",
                show_label=True,
                allow_custom_value=True,
                elem_id="dashboard-filter",
                scale=0,
            )
        kpis = gr.HTML(ui.kpi_strip(payload, session_label), elem_id="kpi-strip")
        swatch_key = gr.HTML(ui.swatch_key(payload), elem_id="swatch-key")

        empty = gr.HTML(
            "" if has_data else empty_panel(session_label),
            visible=not has_data,
            elem_id="dashboard-empty",
        )

        with gr.Column(visible=has_data, elem_id="charts-row") as charts_row:
            with gr.Row(equal_height=False):
                with gr.Column(scale=8, min_width=240, elem_classes=["chart-card"]):
                    gr.HTML(ui.section_header("Finds per swatch class", "six seeded classes"))
                    swatch_chart = gr.BarPlot(
                        swatch_frame(payload),
                        x="Swatch class",
                        y="Finds",
                        color="Series",
                        color_map={SERIES_LABEL: CHART_ACCENT},
                        color_title="Count",
                        x_label_angle=-18,
                        height=250,
                        show_label=False,
                        elem_id="swatch-chart",
                    )
                with gr.Column(scale=4, min_width=200, elem_classes=["chart-card"]):
                    gr.HTML(ui.section_header("Risk bands", "server-side banding"))
                    band_chart = gr.BarPlot(
                        band_frame(payload),
                        x="Risk band",
                        y="Finds",
                        color="Band",
                        color_map=BAND_COLOURS,
                        color_title="Band",
                        height=250,
                        show_label=False,
                        elem_id="band-chart",
                    )
            with gr.Row(equal_height=False):
                with gr.Column(scale=6, min_width=230, elem_classes=["chart-card"]):
                    gr.HTML(ui.section_header("Match confidence", "percentage bins"))
                    conf_chart = gr.BarPlot(
                        confidence_frame(payload),
                        x="Confidence",
                        y="Finds",
                        color="Series",
                        color_map={SERIES_LABEL: CHART_ACCENT},
                        color_title="Count",
                        height=250,
                        show_label=False,
                        elem_id="confidence-chart",
                    )
                with gr.Column(scale=6, min_width=230, elem_classes=["chart-card"]):
                    gr.HTML(ui.section_header("Cap diameter vs gill spacing", "coloured by risk band"))
                    scatter = gr.ScatterPlot(
                        scatter_frame(payload),
                        x="Cap diameter (mm)",
                        y="Gill spacing (mm)",
                        color="Risk band",
                        color_map=BAND_COLOURS,
                        color_title="Risk band",
                        height=250,
                        show_label=False,
                        elem_id="scatter-chart",
                    )

    return DashboardTab(
        filter=dashboard_filter,
        kpis=kpis,
        charts_row=charts_row,
        swatch_chart=swatch_chart,
        conf_chart=conf_chart,
        band_chart=band_chart,
        scatter=scatter,
        swatch_key=swatch_key,
        empty=empty,
    )


def refresh_outputs(payload: dict, session_label: str) -> tuple:
    """Everything a filter change or a saved find needs to re-render."""
    has_data = payload["total_findings"] > 0
    return (
        ui.kpi_strip(payload, session_label),
        swatch_frame(payload),
        confidence_frame(payload),
        band_frame(payload),
        scatter_frame(payload),
        ui.swatch_key(payload),
        gr.update(visible=not has_data),
        gr.update(visible=has_data),
    )
