from collections import deque
import textwrap
from typing import Optional

import click

DEBUG_EVENT_LIMIT = 15
_debug_mode_enabled = False
_debug_events: deque[str] = deque(maxlen=DEBUG_EVENT_LIMIT)


def _rule(width: int = 62) -> str:
    return "-" * width


def set_debug_mode(enabled: bool) -> None:
    global _debug_mode_enabled
    _debug_mode_enabled = enabled
    if not enabled:
        _debug_events.clear()


def add_debug_event(event: str) -> None:
    if not _debug_mode_enabled:
        return
    for line in event.splitlines():
        cleaned = line.strip()
        if cleaned:
            _debug_events.append(cleaned)


def get_debug_panel_lines() -> list[str]:
    if not _debug_mode_enabled or not _debug_events:
        return []
    lines = [f"[DEBUG] (last {DEBUG_EVENT_LIMIT} events)"]
    lines.extend(_debug_events)
    return lines


def render_debug_panel() -> None:
    for line in get_debug_panel_lines():
        click.echo(line)


def print_phase(
    title: str, step: int, total_steps: int, current_step: Optional[str] = None, replace_screen: bool = False
) -> None:
    if replace_screen:
        click.clear()
    click.echo("")
    click.echo(_rule())
    click.echo("MPC Autofill")
    click.echo(f"Phase: {title} ({step}/{total_steps})")
    if current_step:
        click.echo(f"Current step: {current_step}")
    click.echo(_rule())
    render_debug_panel()
    click.echo("")


def print_question(question_number: int, total_questions: int, title: str, helper_text: str) -> None:
    click.echo(f"[QUESTION {question_number}/{total_questions}] {title}")
    click.echo(helper_text)
    click.echo("")


def print_info(message: str) -> None:
    for line in textwrap.dedent(message).strip().splitlines():
        click.echo(f"[INFO] {line.strip()}")


def print_action_required(message: str) -> None:
    click.echo("")
    for line in textwrap.dedent(message).strip().splitlines():
        click.echo(f"[ACTION REQUIRED] {line.strip()}")
    render_debug_panel()
    click.echo("")


def print_state(state: str, action: Optional[str] = None) -> None:
    if action:
        click.echo(f"[STATE] {state} - {action}")
    else:
        click.echo(f"[STATE] {state}")
    render_debug_panel()
