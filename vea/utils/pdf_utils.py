import re
from markdown import markdown
from weasyprint import HTML, CSS
from pathlib import Path

def convert_markdown_to_pdf(summary: str, out_path: Path) -> None:
    css_path = Path(__file__).parent.parent / "assets" / "pdf.css"

    # Convert Markdown to HTML
    html_content = markdown(summary, output_format='html5')

    # Normalize whitespace to avoid issues
    html_content = re.sub(r'\s+', ' ', html_content)

    # Handle <li> with plain task text
    html_content = re.sub(
        r'<li>\s*\[ \]\s*(.*?)</li>',
        r'<li class="task-item">☐ \1</li>',
        html_content
    )
    html_content = re.sub(
        r'<li>\s*\[[xX]\]\s*(.*?)</li>',
        r'<li class="task-item done">☑ \1</li>',
        html_content
    )

    # Handle <li><p>[ ] ...</p></li> or variants
    html_content = re.sub(
        r'<li>\s*<p>\s*\[ \]\s*(.*?)</p>\s*</li>',
        r'<li class="task-item">☐ \1</li>',
        html_content
    )
    html_content = re.sub(
        r'<li>\s*<p>\s*\[[xX]\]\s*(.*?)</p>\s*</li>',
        r'<li class="task-item done">☑ \1</li>',
        html_content
    )

    # Render PDF
    HTML(string=html_content).write_pdf(str(out_path), stylesheets=[CSS(filename=str(css_path))])
