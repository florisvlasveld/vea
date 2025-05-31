import re
from markdown import markdown
from weasyprint import HTML, CSS
from pathlib import Path

def convert_markdown_to_pdf(summary: str, out_path: Path) -> None:
    css_path = Path(__file__).parent.parent / "assets" / "pdf.css"

    # Step 1: Convert Markdown to HTML
    html_content = markdown(summary, output_format='html5')

    # Step 2: Clean task checkboxes — just assign classes, no visual symbols
    html_content = re.sub(
        r'<li>\s*\[ \]\s*(.*?)</li>',
        r'<li class="task-item">\1</li>',
        html_content
    )
    html_content = re.sub(
        r'<li>\s*\[[xX]\]\s*(.*?)</li>',
        r'<li class="task-item done">\1</li>',
        html_content
    )
    html_content = re.sub(
        r'<li>\s*<p>\s*\[ \]\s*(.*?)</p>\s*</li>',
        r'<li class="task-item">\1</li>',
        html_content
    )
    html_content = re.sub(
        r'<li>\s*<p>\s*\[[xX]\]\s*(.*?)</p>\s*</li>',
        r'<li class="task-item done">\1</li>',
        html_content
    )

    # Step 3: Render PDF
    HTML(string=html_content).write_pdf(str(out_path), stylesheets=[CSS(filename=str(css_path))])
