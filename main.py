import asyncio
import sys
import os

# Fix Windows console encoding for Arabic text
os.environ["PYTHONUTF8"] = "1"
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import typer
from app.workflow import run_workflow
from app.prompts.profiles import DEFAULT_CONTENT_TYPE, validate_content_type

app = typer.Typer()


@app.command()
def extract(
    profile_name: str = typer.Option(None, "--profile", help="اسم الحساب (Profile Name)"),
    notebook_name: str = typer.Option(None, "--notebook", help="اسم دفتر الملاحظات (Notebook Name)"),
    lecture_name: str = typer.Option(None, "--lecture", help="اسم المحاضرة (Lecture Name)"),
    book_name: str = typer.Option(None, "--book", help="اسم الكتاب (Book Name)"),
    content_type: str = typer.Option(
        DEFAULT_CONTENT_TYPE,
        "--content-type",
        help="نوع المحتوى: arabic أو english أو russian",
    ),
):
    """
    Extracts Arabic lectures, English courses, or Russian courses with the
    selected prompt family.
    """
    from rich.prompt import Prompt
    from app.config.state import StateManager
    
    state = StateManager.get_state()
    default_profile = state.get("profile_name", "default")
    default_notebook = state.get("notebook_name", "")
    
    if not profile_name:
        profile_name = Prompt.ask("[bold cyan]اسم الحساب (Profile Name)[/bold cyan]", default=default_profile)
        
    if not notebook_name:
        notebook_name = Prompt.ask("[bold cyan]اسم دفتر الملاحظات (Notebook Name)[/bold cyan]", default=default_notebook)
        
    if not lecture_name:
        lecture_name = Prompt.ask("[bold cyan]اسم المحاضرة (Lecture Name)[/bold cyan]")
        
    try:
        selected_content_type = validate_content_type(content_type)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--content-type") from exc

    # Save the new state
    StateManager.save_state(
        profile_name,
        notebook_name,
        selected_content_type,
    )
    
    output_name = asyncio.run(
        run_workflow(
            profile_name,
            notebook_name,
            lecture_name,
            book_name,
            selected_content_type,
        )
    )
    if output_name is None:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
