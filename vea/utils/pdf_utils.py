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


def insert_blank_line_before_lists(md: str) -> str:
    """
    Ensures that a blank line exists between a paragraph (e.g., bolded title)
    and a following bullet list.
    """
    lines = md.splitlines()
    fixed_lines = []

    for i, line in enumerate(lines):
        fixed_lines.append(line)
        if line.strip().startswith("**") and i + 1 < len(lines):
            next_line = lines[i + 1]
            if re.match(r'^\s*[-*+] ', next_line):
                fixed_lines.append('')  # Insert blank line

    return '\n'.join(fixed_lines)


def replace_double_brackets_with_strong(md: str) -> str:
    """
    Replaces all instances of [[...]] with <strong>...</strong>.
    """
    return re.sub(r'\[\[(.+?)\]\]', r'<strong>\1</strong>', md)


def convert_markdown_to_pdf(summary: str, out_path: Path, debug: bool = False) -> None:
    css_path = Path(__file__).parent.parent / "assets" / "pdf.css"

    # Preprocess
    summary = fix_multiline_list_items(summary)
    summary = insert_blank_line_before_lists(summary)
    summary = replace_double_brackets_with_strong(summary)

    # Step 1: Convert Markdown to HTML
    html_content = markdown(summary, output_format='html5')  # 'nl2br' removed

    if debug:
        logger.debug("========== BEGIN MARKDOWN TO HTML OUTPUT ==========")
        logger.debug(html_content)
        logger.debug("=========== END MARKDOWN TO HTML OUTPUT ===========")

    # Step 2: Wrap all <li> content in <p> tags
    html_content = re.sub(r'<li>(?!<p>)(.*?)</li>', r'<li><p>\1</p></li>', html_content)

    # Step 3: Format task checkboxes
    html_content = re.sub(
        r'<li><p>\s*\[ \]\s*(.*?)</p></li>',
        r'<li class="task-item unchecked"><p>\1</p></li>',
        html_content
    )
    html_content = re.sub(
        r'<li><p>\s*\[[xX]\]\s*(.*?)</p></li>',
        r'<li class="task-item checked"><p>\1</p></li>',
        html_content
    )

    if debug:
        logger.debug("========== BEGIN POST-PROCESSED HTML OUTPUT ===========")
        logger.debug(html_content)
        logger.debug("=========== END POST-PROCESSED HTML OUTPUT ============")

    # Step 4: Render PDF
    HTML(string=html_content).write_pdf(str(out_path), stylesheets=[CSS(filename=str(css_path))])
