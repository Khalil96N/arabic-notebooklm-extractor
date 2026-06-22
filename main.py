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

app = typer.Typer()


@app.command()
def extract(
    profile_name: str = typer.Option(None, "--profile", help="اسم الحساب (Profile Name)"),
    notebook_name: str = typer.Option(None, "--notebook", help="اسم دفتر الملاحظات (Notebook Name)"),
    lecture_name: str = typer.Option(None, "--lecture", help="اسم المحاضرة (Lecture Name)"),
    book_name: str = typer.Option(None, "--book", help="اسم الكتاب (Book Name)")
):
    """
    Automates NotebookLM to extract a structured Arabic transcript and generate section prompts.
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
        
    # Save the new state
    StateManager.save_state(profile_name, notebook_name)
    
    output_name = asyncio.run(
        run_workflow(profile_name, notebook_name, lecture_name, book_name)
    )
    if output_name is None:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
