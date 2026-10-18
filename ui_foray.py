"""Foray tab: session rail with counts, the findings table and session creation."""

from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

import ui_common as ui


@dataclass
class ForayTab:
    picker: gr.Radio
    summary: gr.HTML
    findings: gr.HTML
    new_name: gr.Textbox
    create_button: gr.Button
    status: gr.HTML


def picker_choices(sessions: list[dict]) -> list[tuple[str, str]]:
    choices = []
    for row in sessions:
        count = row["finding_count"]
        count_label = "1 find" if count == 1 else f"{count} finds"
        choices.append((f"{row['name']} · {count_label}", str(row["id"])))
    return choices


def summary_line(sessions: list[dict]) -> str:
    if not sessions:
        return (
            '<p class="muted">Create your first foray session to start logging finds — '
            "name it in the box below.</p>"
        )
    total = sum(row["finding_count"] for row in sessions)
    label = "session" if len(sessions) == 1 else "sessions"
    finds = "1 logged find" if total == 1 else f"{total} logged finds"
    return f'<p class="muted">{len(sessions)} {label} · {finds}</p>'


def build_foray(sessions: list[dict], selected_id: int | None) -> ForayTab:
    with gr.Row(equal_height=False, elem_classes=["foray-grid"]):
        with gr.Column(scale=4, min_width=220, elem_classes=["panel"]):
            gr.HTML(ui.section_header("Your foray sessions", "owned by you only", ""))
            summary = gr.HTML(summary_line(sessions), elem_id="session-summary")
            picker = gr.Radio(
                choices=picker_choices(sessions),
                value=str(selected_id) if selected_id else None,
                label="Foray sessions",
                show_label=False,
                elem_id="session-rail",
            )
            gr.HTML(
                '<p class="muted">Pick a session to see its finds on the right.</p>'
            )
            new_name = gr.Textbox(
                label="New foray session",
                placeholder="Autumn ridge foray",
                max_lines=1,
                elem_id="new-session-name",
            )
            create_button = gr.Button("Create foray session", variant="primary", elem_id="create-session")
            status = gr.HTML("", elem_id="session-status")

        with gr.Column(scale=8, min_width=260, elem_classes=["panel"]):
            gr.HTML(ui.section_header("Finds in this session", "newest first", ""))
            findings = gr.HTML(
                ui.findings_table([], ""),
                elem_id="findings-table",
            )

    return ForayTab(
        picker=picker,
        summary=summary,
        findings=findings,
        new_name=new_name,
        create_button=create_button,
        status=status,
    )
