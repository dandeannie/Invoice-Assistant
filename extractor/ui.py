"""
Shared look-and-feel for every page: larger, higher-contrast type and a bold,
readable sidebar menu. Call apply_theme() right after st.set_page_config().
"""
import html
import streamlit as st

# tuned for readability: base text ~17px, menu ~18px, strong contrast
CSS = """
<style>
  /* ---------- base type ---------- */
  html, body, [class*="css"], .stMarkdown, .stText,
  div[data-testid="stMarkdownContainer"] p,
  div[data-testid="stMarkdownContainer"] li {
      font-size: 1.06rem !important;
      line-height: 1.62 !important;
      color: #14243A !important;
  }
  .block-container { padding-top: 2rem; }

  h1 { font-size: 2.15rem !important; font-weight: 800 !important; letter-spacing:-.02em; }
  h2 { font-size: 1.62rem !important; font-weight: 750 !important; }
  h3 { font-size: 1.32rem !important; font-weight: 700 !important; }

  /* ---------- sidebar menu: bigger + brighter ---------- */
  section[data-testid="stSidebar"] {
      background: linear-gradient(180deg,#123A63 0%,#0E2E50 100%) !important;
      min-width: 310px !important;
  }
  section[data-testid="stSidebar"] * { color: #F2F7FF !important; }
  section[data-testid="stSidebar"] a,
  section[data-testid="stSidebar"] a span,
  section[data-testid="stSidebar"] div[data-testid="stSidebarNav"] span {
      font-size: 1.16rem !important;
      font-weight: 650 !important;
      letter-spacing: .1px;
  }
  section[data-testid="stSidebar"] a {
      border-radius: 10px !important;
      padding: .5rem .7rem !important;
      margin: 3px 6px !important;
      transition: background .15s ease;
  }
  section[data-testid="stSidebar"] a:hover { background: rgba(255,255,255,.14) !important; }
  section[data-testid="stSidebar"] a[aria-current="page"] {
      background: #FFB020 !important;
  }
  section[data-testid="stSidebar"] a[aria-current="page"] span {
      color: #14243A !important; font-weight: 800 !important;
  }

  /* ---------- widgets ---------- */
  label, .stSelectbox label, .stTextInput label, .stFileUploader label,
  .stRadio label, .stCheckbox label, .stMultiSelect label, .stNumberInput label {
      font-size: 1.06rem !important; font-weight: 650 !important; color:#14243A !important;
  }
  div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input,
  .stTextArea textarea { font-size: 1.05rem !important; }
  .stRadio div[role="radiogroup"] label p { font-size: 1.05rem !important; }

  .stButton button, .stDownloadButton button {
      font-size: 1.06rem !important; font-weight: 700 !important;
      border-radius: 10px !important; padding: .55rem 1.05rem !important;
  }
  .stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
      background: #1B6FCB !important; border-color:#1B6FCB !important;
  }

  /* ---------- tables & messages ---------- */
  .stDataFrame, .stDataEditor, .stDataFrame div, .stDataEditor div {
      font-size: 1.0rem !important;
  }
  div[data-testid="stMetricValue"] { font-size: 2.0rem !important; font-weight: 800 !important; }
  div[data-testid="stMetricLabel"] { font-size: 1.02rem !important; font-weight: 650 !important; }
  div[data-testid="stAlert"] { font-size: 1.05rem !important; border-radius: 10px !important; }
  div[data-testid="stExpander"] summary p { font-size: 1.08rem !important; font-weight: 700 !important; }
  .stCaption, div[data-testid="stCaptionContainer"] p {
      font-size: .97rem !important; color:#40546E !important;
  }
  #MainMenu, footer { visibility: hidden; }
</style>
"""


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str = "", color: str = "#1B4F86"):
    """Consistent page banner."""
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    sub = f"<p style='margin:.4rem 0 0;opacity:.94;font-size:1.06rem'>{safe_subtitle}</p>" if safe_subtitle else ""
    st.markdown(
        f"""<div style="background:{color};color:#fff;border-radius:14px;
                 padding:22px 26px;margin-bottom:20px;">
              <h1 style="margin:0;font-size:1.95rem;font-weight:800;color:#fff;">{safe_title}</h1>
              {sub}
            </div>""", unsafe_allow_html=True)
