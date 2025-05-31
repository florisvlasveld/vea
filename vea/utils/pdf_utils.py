import logging
import re
from markdown import markdown
from weasyprint import HTML, CSS
from pathlib import Path

logger = logging.getLogger(__name__)


def fix_multiline_list_items(md: str) -> str:
    """
    Ensures that list items don't accidentally include following lines.
    Assumes bullet items are always one line in the Markdown source.
    """
    lines = md.splitlines()
    fixed_lines = []
    previous_line_was_list_item = False

    for line in lines:
        stripped = line.strip()
        is_list_item = bool(re.match(r'^(\s*)([-*+]|\d+\.)\s+', line))

        if not is_list_item and previous_line_was_list_item and stripped != '':
            # Insert a blank line to prevent paragraph continuation in list
            fixed_lines.append('')

        fixed_lines.append(line)
        previous_line_was_list_item = is_list_item

    return '\n'.join(fixed_lines)


def convert_markdown_to_pdf(summary: str, out_path: Path, debug: bool = False) -> None:
    css_path = Path(__file__).parent.parent / "assets" / "pdf.css"

    # Preprocess: fix multi-line list items
    summary = fix_multiline_list_items(summary)

    # Step 1: Convert Markdown to HTML with soft line breaks
    html_content = markdown(summary, output_format='html5', extensions=['nl2br'])

    if debug:
        logger.debug("========== BEGIN MARKDOWN TO HTML OUTPUT ==========")
        logger.debug(html_content)
        logger.debug("=========== END MARKDOWN TO HTML OUTPUT ===========")

    # Step 2: Wrap all <li> content in <p> tags
    html_content = re.sub(r'<li>(?!<p>)(.*?)</li>', r'<li><p>\1</p></li>', html_content)

    # Step 3: Format task checkboxes
    html_content = re.sub(
        r'<li><p>\s*\[ \]\s*(.*?)</p></li>',
        r'<li class="task-item"><p>\1</p></li>',
        html_content
    )
    html_content = re.sub(
        r'<li><p>\s*\[[xX]\]\s*(.*?)</p></li>',
        r'<li class="task-item done"><p>\1</p></li>',
        html_content
    )

    if debug:
        logger.debug("========== BEGIN POST-PROCESSED HTML OUTPUT ===========")
        logger.debug(html_content)
        logger.debug("=========== END POST-PROCESSED HTML OUTPUT ============")

    # Step 4: Render PDF
    HTML(string=html_content).write_pdf(str(out_path), stylesheets=[CSS(filename=str(css_path))])
    