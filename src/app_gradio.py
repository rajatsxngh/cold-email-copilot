# src/app_gradio.py
"""The Gradio web app. Run it with:  python -m src.app_gradio"""
from __future__ import annotations

import logging
from html import escape

import gradio as gr

from . import config
from .config import MissingKeyError
from .n8n_client import send_via_n8n
from .pipeline import STEPS, CopilotResult, InputError, build_gmail_link, run_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

TARGET_WORDS = (120, 180)
VISIBLE_MATCHES = 3

# -----------------------------
# Look and feel
# -----------------------------
POSTAL_BLUE = gr.themes.Color(
    c50="#eef3fc", c100="#dce6f9", c200="#b9ccf2", c300="#8eabe8", c400="#5f85da", c500="#3d69cc",
    c600="#2a57c0", c700="#2347a0", c800="#1f3b80", c900="#1c3166", c950="#121f42", name="postal_blue",
)
DESK_SLATE = gr.themes.Color(
    c50="#f4f6f9", c100="#e6ebf2", c200="#d3dae5", c300="#b4bfcf", c400="#8a97ac", c500="#667389",
    c600="#4d586c", c700="#3a4456", c800="#262f3f", c900="#1c2740", c950="#121826", name="desk_slate",
)

THEME = gr.themes.Base(
    primary_hue=POSTAL_BLUE,
    secondary_hue=POSTAL_BLUE,
    neutral_hue=DESK_SLATE,
    font=[gr.themes.GoogleFont("Instrument Sans"), "ui-sans-serif", "system-ui", "sans-serif"],
    font_mono=["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
).set(
    body_background_fill="#e6ebf2",
    body_background_fill_dark="#121826",
    body_text_color="#1c2740",
    body_text_color_dark="#e4e9f2",
    body_text_color_subdued="#5b6577",
    body_text_color_subdued_dark="#9aa6ba",
    background_fill_primary="#ffffff",
    background_fill_primary_dark="#1b2233",
    background_fill_secondary="#f4f6f9",
    background_fill_secondary_dark="#161d2c",
    block_background_fill="#ffffff",
    block_background_fill_dark="#1b2233",
    block_border_color="#d3dae5",
    block_border_color_dark="#2c3548",
    block_radius="12px",
    block_shadow="none",
    block_shadow_dark="none",
    block_label_text_color="#3a4456",
    block_label_text_color_dark="#c3cbd8",
    block_label_text_weight="600",
    block_title_text_weight="600",
    input_background_fill="#ffffff",
    input_background_fill_dark="#141b29",
    input_border_color="#c9d1dd",
    input_border_color_dark="#334058",
    input_border_color_focus="#2a57c0",
    input_border_color_focus_dark="#6f95e8",
    input_shadow_focus="0 0 0 3px rgba(42, 87, 192, 0.18)",
    input_shadow_focus_dark="0 0 0 3px rgba(111, 149, 232, 0.25)",
    input_radius="8px",
    input_placeholder_color="#8a97ac",
    input_placeholder_color_dark="#6b7890",
    button_primary_background_fill="#2a57c0",
    button_primary_background_fill_dark="#3d69cc",
    button_primary_background_fill_hover="#2347a0",
    button_primary_background_fill_hover_dark="#2a57c0",
    button_primary_text_color="#ffffff",
    button_primary_text_color_dark="#ffffff",
    button_primary_border_color="#2a57c0",
    button_primary_border_color_dark="#3d69cc",
    button_secondary_background_fill="#ffffff",
    button_secondary_background_fill_dark="#1b2233",
    button_secondary_background_fill_hover="#eef3fc",
    button_secondary_background_fill_hover_dark="#232c40",
    button_secondary_text_color="#1c2740",
    button_secondary_text_color_dark="#e4e9f2",
    button_secondary_border_color="#b4bfcf",
    button_secondary_border_color_dark="#3a4456",
    button_large_radius="8px",
    button_medium_radius="8px",
    button_large_text_weight="600",
    color_accent="#2a57c0",
    color_accent_soft="#eef3fc",
    color_accent_soft_dark="#1f2a44",
    loader_color="#2a57c0",
    loader_color_dark="#6f95e8",
    link_text_color="#2a57c0",
    link_text_color_dark="#8eabe8",
)

# Newsreader (a serif) is used for the title and the email itself, so the draft reads like a letter.
HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">
"""

CSS = """
:root {
  --cec-ink: #1c2740;
  --cec-muted: #5b6577;
  --cec-paper: #ffffff;
  --cec-line: #d9dfe8;
  --cec-blue: #2a57c0;
  --cec-blue-soft: #eef3fc;
  --cec-red: #c2382f;
  --cec-track: #e6ebf2;
  --cec-serif: "Newsreader", Georgia, "Times New Roman", serif;
}
.dark {
  --cec-ink: #e4e9f2;
  --cec-muted: #9aa6ba;
  --cec-paper: #1b2233;
  --cec-line: #2c3548;
  --cec-blue: #8eabe8;
  --cec-blue-soft: #1f2a44;
  --cec-red: #e0675e;
  --cec-track: #263046;
}

.gradio-container { max-width: 1240px !important; margin: 0 auto !important; padding: 28px 20px 40px !important; }
.cec-html .html-container { padding: 0 !important; }
.cec-html .prose { max-width: none !important; }

/* Header */
.cec-header { display: flex; flex-wrap: wrap; gap: 16px 32px; align-items: flex-end; justify-content: space-between; margin-bottom: 8px; }
.cec-header h1 { font-family: var(--cec-serif); font-weight: 500; font-size: 2.25rem; line-height: 1.1; letter-spacing: -0.01em; color: var(--cec-ink); margin: 0 0 6px; }
.cec-header p { margin: 0; color: var(--cec-muted); font-size: 1.02rem; max-width: 60ch; }
.cec-services { display: flex; flex-wrap: wrap; gap: 8px; list-style: none; margin: 0; padding: 0; }
.cec-services li { display: inline-flex; align-items: center; gap: 7px; height: 30px; box-sizing: border-box; margin: 0 !important; line-height: 1; padding: 0 11px; border-radius: 999px; font-size: 0.85rem; font-weight: 500;
  color: var(--cec-muted); border: 1px solid var(--cec-line); background: var(--cec-paper); cursor: default; }
.cec-services li::before { content: ""; width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid currentColor; box-sizing: border-box; }
.cec-services li.on { color: var(--cec-ink); }
.cec-services li.on::before { background: #2f9e62; border-color: #2f9e62; }
.cec-notice { margin: 4px 0 0; padding: 10px 14px; border-radius: 8px; border-left: 3px solid var(--cec-red); background: var(--cec-paper); color: var(--cec-ink); font-size: 0.95rem; }

/* Step headings */
.cec-step { display: flex; align-items: center; gap: 10px; margin: 6px 0 2px; }
.cec-step span { display: inline-grid; place-items: center; width: 26px; height: 26px; border-radius: 50%; background: var(--cec-ink); color: var(--cec-paper); font-weight: 600; font-size: 0.85rem; flex: none; }
.cec-step h2 { margin: 0; font-size: 1.1rem; font-weight: 600; color: var(--cec-ink); }

/* How you match */
.cec-panel { background: var(--cec-paper); border: 1px solid var(--cec-line); border-radius: 12px; padding: 18px 20px; color: var(--cec-ink); }
.cec-empty { color: var(--cec-muted); margin: 0; line-height: 1.55; }
.cec-role h3 { font-family: var(--cec-serif); font-weight: 500; font-size: 1.45rem; line-height: 1.2; margin: 0 0 2px; color: var(--cec-ink); }
.cec-role p { margin: 0 0 12px; color: var(--cec-muted); }
.cec-skills { display: flex; flex-wrap: wrap; gap: 6px; list-style: none; padding: 0 !important; margin: 0 0 20px !important; }
.cec-skills li { margin: 0 !important; background: var(--cec-blue-soft); color: var(--cec-blue); padding: 3px 10px; border-radius: 6px; font-size: 0.85rem; font-weight: 500; }
.cec-panel h4 { margin: 0 0 10px; font-size: 0.95rem; font-weight: 600; color: var(--cec-ink); }
.cec-matches { list-style: none; padding: 0 !important; margin: 0 !important; display: grid; gap: 14px; }
.cec-match-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.cec-bar { flex: 1; height: 5px; border-radius: 3px; background: var(--cec-track); overflow: hidden; }
.cec-bar i { display: block; height: 100%; border-radius: 3px; background: var(--cec-blue); }
.cec-strength { font-size: 0.8rem; font-weight: 600; color: var(--cec-muted); min-width: 96px; text-align: right; }
.cec-matches li { margin: 0 !important; }
.cec-matches p { margin: 0; font-size: 0.92rem; line-height: 1.5; color: var(--cec-ink); }
.cec-panel details { margin-top: 14px; }
.cec-panel summary { cursor: pointer; color: var(--cec-blue); font-weight: 500; font-size: 0.92rem; }
.cec-panel details .cec-matches { margin-top: 12px; }
.cec-source { margin: 14px 0 0; font-size: 0.82rem; color: var(--cec-muted); }

/* The draft: a sheet of letter paper with an airmail edge */
.cec-sheet { position: relative; background: var(--cec-paper) !important; border: 1px solid var(--cec-line) !important; border-radius: 12px !important;
  padding: 26px 26px 18px !important; overflow: hidden; box-shadow: 0 1px 0 var(--cec-line), 0 12px 32px -18px rgba(28, 39, 64, 0.35); }
.cec-sheet::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 7px;
  background: repeating-linear-gradient(-45deg, var(--cec-red) 0 12px, transparent 12px 20px, #2a57c0 20px 32px, transparent 32px 40px); }
.cec-sheet { gap: 0 !important; }
.cec-sheet .block { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
.cec-sheet .form { background: transparent !important; border: none !important; box-shadow: none !important; }
.cec-line-field label { display: grid !important; grid-template-columns: 74px 1fr; align-items: center; column-gap: 8px; border-bottom: 1px solid var(--cec-line); padding: 4px 0 !important; }
.cec-line-field label > span, .cec-line-field [data-testid="block-info"] { margin: 0 !important; color: var(--cec-muted) !important; font-weight: 500 !important; }
.cec-line-field input, .cec-line-field textarea { border: none !important; box-shadow: none !important; background: transparent !important; padding: 8px 0 !important; font-size: 1rem !important; color: var(--cec-ink) !important; }
.cec-line-field.cec-subject input, .cec-line-field.cec-subject textarea { font-weight: 600 !important; }
.cec-recruiter-note { margin: 6px 0 10px 82px; font-size: 0.84rem; color: var(--cec-muted); min-height: 1.2em; }
.cec-recruiter-note.found { color: #2f8457; }
.dark .cec-recruiter-note.found { color: #6fcf97; }
.cec-letter textarea { font-family: var(--cec-serif) !important; font-size: 1.1rem !important; line-height: 1.65 !important; color: var(--cec-ink) !important;
  border: none !important; box-shadow: none !important; background: transparent !important; padding: 16px 0 8px !important; }
.cec-letter label > span, .cec-letter [data-testid="block-info"] { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.cec-count { font-size: 0.84rem; color: var(--cec-muted); padding-top: 8px; border-top: 1px solid var(--cec-line); margin-top: 4px; }
.cec-count.off { color: var(--cec-red); }
.cec-actions { margin-top: 10px; gap: 10px !important; }
.cec-status { font-size: 0.92rem; color: var(--cec-ink); min-height: 1.3em; }
.cec-footnote { color: var(--cec-muted); font-size: 0.85rem; margin-top: 18px; text-align: center; }

@media (max-width: 720px) {
  .cec-header h1 { font-size: 1.8rem; }
  .cec-sheet { padding: 22px 16px 14px !important; }
  .cec-line-field label { grid-template-columns: 62px 1fr; }
  .cec-recruiter-note { margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
"""

# -----------------------------
# HTML pieces
# -----------------------------
SERVICE_HELP = {
    "OpenAI": ("Ready", "Required. Add OPENAI_API_KEY to .env"),
    "Pinecone": ("Ready", "Not set up. Resume search runs in memory"),
    "Hunter": ("Ready", "Not set up. Type the recruiter's email yourself"),
    "n8n": ("Ready", "Not set up. Use “Open in Gmail” to send"),
}


def header_html() -> str:
    pills = []
    for name, ready in config.service_status().items():
        on_text, off_text = SERVICE_HELP[name]
        tip = on_text if ready else off_text
        pills.append(f'<li class="{"on" if ready else ""}" title="{escape(tip)}">{name}</li>')
    notice = ""
    if not config.OPENAI_API_KEY:
        notice = '<p class="cec-notice">Add <code>OPENAI_API_KEY</code> to your <code>.env</code> file and restart the app to start writing emails.</p>'
    return f"""
<header class="cec-header">
  <div>
    <h1>Cold Email Copilot</h1>
    <p>Turn a job post and your resume into a short, personal email to the recruiter.</p>
  </div>
  <ul class="cec-services" aria-label="Services that are set up">{''.join(pills)}</ul>
</header>{notice}"""


def step_html(number: int, title: str) -> str:
    return f'<div class="cec-step"><span>{number}</span><h2>{escape(title)}</h2></div>'


EMPTY_MATCH_HTML = (
    '<div class="cec-panel"><p class="cec-empty">After you write your email, you’ll see what the job asks for '
    "and the parts of your resume that fit it best.</p></div>"
)


def _strength(score: float) -> str:
    if score >= 0.6:
        return "Strong match"
    if score >= 0.25:
        return "Good match"
    return "Some overlap"


def _match_items(snippets: list[dict]) -> str:
    items = []
    for s in snippets:
        width = max(4, round(s["score"] * 100))
        items.append(
            f'<li><div class="cec-match-head"><div class="cec-bar" aria-hidden="true"><i style="width:{width}%"></i></div>'
            f'<span class="cec-strength">{_strength(s["score"])}</span></div><p>{escape(s["text"])}</p></li>'
        )
    return f'<ol class="cec-matches">{"".join(items)}</ol>'


def match_html(result: CopilotResult) -> str:
    jd = result.jd
    role = escape(jd.get("role_title") or "Role not found")
    where = ", ".join(escape(x) for x in (jd.get("company_name"), jd.get("location")) if x)
    skills = "".join(f"<li>{escape(s)}</li>" for s in jd.get("top_skills", []))
    parts = [f'<div class="cec-panel"><div class="cec-role"><h3>{role}</h3><p>{where or "&nbsp;"}</p>']
    if skills:
        parts.append(f'<ul class="cec-skills" aria-label="Top skills">{skills}</ul>')
    parts.append("</div><h4>Resume lines that fit this job</h4>")
    if result.snippets:
        shown, rest = result.snippets[:VISIBLE_MATCHES], result.snippets[VISIBLE_MATCHES:]
        parts.append(_match_items(shown))
        if rest:
            parts.append(f"<details><summary>Show {len(rest)} more</summary>{_match_items(rest)}</details>")
        where_searched = "Pinecone" if result.search_source == "pinecone" else "an in-memory search"
        parts.append(f'<p class="cec-source">Found with {where_searched}, then re-ranked by a cross-encoder.</p>')
    else:
        parts.append('<p class="cec-empty">No close matches found in your resume.</p>')
    parts.append("</div>")
    return "".join(parts)


def recruiter_note_html(text: str = "", found: bool = False) -> str:
    return f'<p class="cec-recruiter-note{" found" if found else ""}">{escape(text)}</p>'


def word_count_html(body: str) -> str:
    words = len((body or "").split())
    low, high = TARGET_WORDS
    if not words:
        return '<div class="cec-count">0 words</div>'
    off = not (low <= words <= high)
    return f'<div class="cec-count{" off" if off else ""}">{words} words (aim for {low}–{high})</div>'


def status_html(text: str = "") -> str:
    return f'<div class="cec-status">{escape(text)}</div>'


# -----------------------------
# Event handlers
# -----------------------------
def write_email(resume_path, jd_text, recruiter_name, company_domain, progress=gr.Progress()):
    def report(step: int, label: str):
        progress((step, len(STEPS)), desc=label)

    try:
        result = run_pipeline(resume_path, jd_text, recruiter_name, company_domain, report)
    except (InputError, MissingKeyError) as exc:
        raise gr.Error(str(exc), title="Can't write the email yet")
    except Exception as exc:
        log.exception("Pipeline failed")
        raise gr.Error(f"Something went wrong: {exc}", title="Email not written")

    recruiter = result.recruiter
    note = recruiter_note_html(
        f"{recruiter.message} Confidence {recruiter.confidence}%." if recruiter.email and recruiter.confidence
        else recruiter.message,
        found=bool(recruiter.email),
    )
    job_meta = {"job_title": result.jd.get("role_title", ""), "company": result.jd.get("company_name", "")}
    return (
        match_html(result),
        recruiter.email or "",
        note,
        result.subject,
        result.body,
        status_html(),
        job_meta,
    )


def refresh_draft(to: str, subject: str, body: str):
    """Keep the Gmail link and word count in step with every edit."""
    has_draft = bool((subject or "").strip() or (body or "").strip())
    return (
        gr.Button(link=build_gmail_link(to, subject, body), interactive=has_draft),
        word_count_html(body),
    )


def send_email(to: str, subject: str, body: str, job_meta: dict | None):
    job_meta = job_meta or {}
    return status_html(send_via_n8n(to, subject, body, job_meta.get("job_title", ""), job_meta.get("company", "")))


# -----------------------------
# Layout
# -----------------------------
with gr.Blocks(title="Cold Email Copilot") as demo:
    gr.HTML(header_html(), elem_classes="cec-html")

    with gr.Row(equal_height=False):
        with gr.Column(scale=5, min_width=320):
            gr.HTML(step_html(1, "Add your resume and the job"), elem_classes="cec-html")
            resume_file = gr.File(label="Resume (PDF)", file_types=[".pdf"], type="filepath", height=120)
            jd_text = gr.Textbox(
                label="Job description",
                lines=9,
                max_lines=18,
                autoscroll=False,
                placeholder="Paste the full job post from LinkedIn or the company's careers page.",
            )
            with gr.Row():
                recruiter_name = gr.Textbox(label="Recruiter's name", placeholder="e.g. Natalya Lowe", min_width=160)
                company_domain = gr.Textbox(label="Company website", placeholder="e.g. acme.com", min_width=160)
            write_btn = gr.Button("Write my email", variant="primary", size="lg")

            gr.HTML(step_html(2, "How you match"), elem_classes="cec-html")
            match_out = gr.HTML(EMPTY_MATCH_HTML, elem_classes="cec-html")

        with gr.Column(scale=7, min_width=340):
            gr.HTML(step_html(3, "Edit and send"), elem_classes="cec-html")
            with gr.Column(elem_classes="cec-sheet"):
                to_box = gr.Textbox(label="To", placeholder="recruiter@company.com", elem_classes="cec-line-field")
                recruiter_note = gr.HTML(recruiter_note_html(), elem_classes="cec-html")
                subject_box = gr.Textbox(
                    label="Subject",
                    placeholder="Your subject line",
                    html_attributes=gr.InputHTMLAttributes(spellcheck=True),
                    elem_classes="cec-line-field cec-subject",
                )
                body_box = gr.Textbox(
                    label="Email",
                    lines=15,
                    max_lines=40,
                    buttons=["copy"],
                    html_attributes=gr.InputHTMLAttributes(spellcheck=True),
                    placeholder="Your email will appear here. Add your resume and the job description, then select “Write my email”.",
                    elem_classes="cec-letter",
                )
                word_count = gr.HTML(word_count_html(""), elem_classes="cec-html")
            with gr.Row(elem_classes="cec-actions"):
                gmail_btn = gr.Button("Open in Gmail", variant="primary", link=build_gmail_link("", "", ""), link_target="_blank", interactive=False)
                send_btn = gr.Button("Send with n8n", variant="secondary", interactive=bool(config.N8N_WEBHOOK_URL))
            status_out = gr.HTML(status_html(), elem_classes="cec-html")
            job_meta = gr.State({})

    gr.HTML('<p class="cec-footnote">Always read the email before you send it.</p>', elem_classes="cec-html")

    write_btn.click(
        write_email,
        inputs=[resume_file, jd_text, recruiter_name, company_domain],
        outputs=[match_out, to_box, recruiter_note, subject_box, body_box, status_out, job_meta],
    )
    gr.on(
        triggers=[to_box.change, subject_box.change, body_box.change],
        fn=refresh_draft,
        inputs=[to_box, subject_box, body_box],
        outputs=[gmail_btn, word_count],
        show_progress="hidden",
        trigger_mode="always_last",
    )
    send_btn.click(send_email, inputs=[to_box, subject_box, body_box, job_meta], outputs=[status_out])


def main():
    demo.launch(theme=THEME, css=CSS, head=HEAD)


if __name__ == "__main__":
    main()
