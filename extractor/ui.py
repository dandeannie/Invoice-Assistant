"""
Shared look-and-feel: Authentic Neobrutalist design system matching the reference
design language:
  - Typography: Space Mono (700 bold retro slab/typewriter) for headings and badges,
    Plus Jakarta Sans for high-contrast, ultra-legible body text.
  - Palette: Mint/sage green sidebar (#A3D9B8), warm cream canvas (#FBF9F1),
    sunshine yellow hero card (#F8CD53), pastel lilac/orchid card (#F6C8FB),
    crisp white cards (#FFFFFF), and solid black ink borders/shadows (#000000).
  - Tactile Neobrutalism: 2.5px solid black borders, hard offset drop shadows (4px 4px 0px #000),
    pill buttons, and square framed icon boxes.
  - Mobile-first responsiveness: fluid layouts, media queries for phone/tablet,
    comfortable touch targets (>= 44px), and zero horizontal overflow.
"""
from __future__ import annotations
import html
from typing import List, Tuple, Optional, Dict
import streamlit as st

CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Space+Mono:ital,wght@0,400;0,700;1,400;1,700&display=swap');

  /* ==========================================================================
     1. GLOBAL RESET & BASE THEMING (Strict Box-Sizing & Viewport Boundary)
     ========================================================================== */
  :root {
      --nb-black: #000000;
      --nb-text: #121212;
      --nb-bg: #FBF9F1;
      --nb-white: #FFFFFF;
      --nb-mint: #A3D9B8;
      --nb-mint-glass: rgba(163, 217, 184, 0.85);
      --nb-yellow: #F8CD53;
      --nb-pink: #F6C8FB;
      --nb-blue: #BAE6FD;
      --nb-border: 2.5px solid #000000;
      --nb-border-sm: 2px solid #000000;
      --nb-shadow: 4px 4px 0px #000000;
      --nb-shadow-sm: 3px 3px 0px #000000;
      --nb-shadow-hover: 6px 6px 0px #000000;
      --nb-radius: 10px;
      --nb-radius-pill: 999px;
  }

  *, *::before, *::after {
      box-sizing: border-box !important;
  }

  html, body {
      background-color: var(--nb-bg) !important;
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
      color: var(--nb-text) !important;
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden !important;
      max-width: 100vw !important;
  }

  /* The entire canvas behind & around sidebar must remain the warm canvas (#FBF9F1), NEVER solid black */
  .stApp,
  div[data-testid="stAppViewContainer"],
  div[data-testid="stAppViewBlockContainer"],
  section.main,
  header[data-testid="stHeader"] {
      background-color: var(--nb-bg) !important;
  }

  /* Header styling: Elevated, click-through, clean headroom */
  header[data-testid="stHeader"] {
      background: transparent !important;
      z-index: 900 !important;
      height: 3.6rem !important;
  }

  header[data-testid="stHeader"] > div {
      pointer-events: none !important;
  }

  header[data-testid="stHeader"] button,
  header[data-testid="stHeader"] a {
      pointer-events: auto !important;
  }

  .stApp {
      overflow-x: clip !important;
      max-width: 100vw !important;
      width: 100% !important;
  }

  .block-container {
      padding-top: 3.6rem !important;
      padding-bottom: 3.5rem !important;
      padding-left: 1.5rem !important;
      padding-right: 1.5rem !important;
      max-width: 1240px !important;
      width: 100% !important;
      box-sizing: border-box !important;
  }

  /* Headings: Signature retro-monospace / typewriter slab */
  h1, h2, h3, h4, .nb-heading, .stHeading {
      font-family: 'Space Mono', monospace !important;
      font-weight: 700 !important;
      color: var(--nb-black) !important;
      letter-spacing: -0.02em !important;
      line-height: 1.2 !important;
      overflow-wrap: break-word !important;
      word-break: break-word !important;
  }

  h1 { font-size: clamp(1.6rem, 3.5vw, 2.15rem) !important; margin-bottom: 0.6rem !important; }
  h2 { font-size: clamp(1.3rem, 2.8vw, 1.6rem) !important; margin-top: 1.2rem !important; }
  h3 { font-size: clamp(1.1rem, 2.2vw, 1.28rem) !important; }
  h4 { font-size: clamp(0.95rem, 1.8vw, 1.05rem) !important; }

  p, span, label, div {
      font-family: 'Plus Jakarta Sans', sans-serif;
  }

  /* ==========================================================================
     2. TRANSLUCENT MINT GLASS SIDEBAR (No Solid Black Background)
     ========================================================================== */
  section[data-testid="stSidebar"] {
      background: var(--nb-mint-glass) !important;
      backdrop-filter: blur(20px) saturate(160%) !important;
      -webkit-backdrop-filter: blur(20px) saturate(160%) !important;
      border-right: 2.5px solid var(--nb-black) !important;
      box-shadow: 4px 0px 24px rgba(0, 0, 0, 0.06) !important;
      z-index: 1000 !important;
      transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), margin-left 0.25s ease !important;
  }

  section[data-testid="stSidebar"][aria-expanded="true"] {
      min-width: 260px !important;
      max-width: min(320px, 85vw) !important;
  }

  section[data-testid="stSidebar"][aria-expanded="false"] {
      display: none !important;
  }

  /* Ensure internal sidebar containers are 100% transparent and never inject black */
  section[data-testid="stSidebar"] > div:first-child,
  div[data-testid="stSidebarContent"],
  div[data-testid="stSidebarUserContent"],
  div[data-testid="stSidebarNav"],
  div[data-testid="stSidebarNavItems"] {
      background: transparent !important;
      background-color: transparent !important;
  }

  /* Disable Streamlit scroll gradient pseudo-elements that create dark bands */
  section[data-testid="stSidebar"] div[data-testid="stSidebarContent"]::before,
  section[data-testid="stSidebar"] div[data-testid="stSidebarContent"]::after,
  section[data-testid="stSidebar"] *::before,
  section[data-testid="stSidebar"] *::after {
      background-image: none !important;
      box-shadow: none !important;
  }

  /* Sidebar backdrop (mobile / overlay mode) MUST NOT be solid black */
  div[data-testid="stSidebarBackdrop"] {
      background-color: rgba(18, 18, 18, 0.20) !important;
      backdrop-filter: blur(4px) !important;
      -webkit-backdrop-filter: blur(4px) !important;
  }

  /* ==========================================================================
     2.1 STREAMLIT HAMBURGER & COLLAPSE CONTROLS (Iconic Neobrutalist Design)
     ========================================================================== */
  button[data-testid="stExpandSidebarButton"],
  [data-testid="stSidebarCollapsedControl"] button {
      background: var(--nb-yellow) !important;
      border: 2.5px solid #000000 !important;
      border-radius: 8px !important;
      box-shadow: 3px 3px 0px #000000 !important;
      width: 44px !important;
      height: 44px !important;
      min-width: 44px !important;
      min-height: 44px !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      cursor: pointer !important;
      margin: 6px 0 0 12px !important;
      padding: 0 !important;
      transition: all 0.15s ease-in-out !important;
      z-index: 1000 !important;
  }

  button[data-testid="stExpandSidebarButton"]:hover,
  [data-testid="stSidebarCollapsedControl"] button:hover {
      background: #FFF2A8 !important;
      transform: translate(-1px, -1px) !important;
      box-shadow: 4px 4px 0px #000000 !important;
  }

  button[data-testid="stExpandSidebarButton"]:active,
  [data-testid="stSidebarCollapsedControl"] button:active {
      transform: translate(1px, 1px) !important;
      box-shadow: 1px 1px 0px #000000 !important;
  }

  /* Replace Streamlit default arrow text with crisp 3-bar black hamburger */
  button[data-testid="stExpandSidebarButton"] span,
  button[data-testid="stExpandSidebarButton"] svg,
  [data-testid="stSidebarCollapsedControl"] button span,
  [data-testid="stSidebarCollapsedControl"] button svg {
      display: none !important;
  }

  button[data-testid="stExpandSidebarButton"]::after,
  [data-testid="stSidebarCollapsedControl"] button::after {
      content: "" !important;
      display: block !important;
      width: 20px !important;
      height: 2.5px !important;
      background: #000000 !important;
      box-shadow: 0 -6px 0 0 #000000, 0 6px 0 0 #000000 !important;
      border-radius: 1px !important;
  }

  /* Sidebar collapse button inside open sidebar */
  div[data-testid="stSidebarCollapseButton"] button {
      background: rgba(255, 255, 255, 0.95) !important;
      border: 2px solid var(--nb-black) !important;
      border-radius: 8px !important;
      box-shadow: 2px 2px 0px var(--nb-black) !important;
      width: 40px !important;
      height: 40px !important;
      min-width: 40px !important;
      min-height: 40px !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      color: var(--nb-black) !important;
      backdrop-filter: blur(8px) !important;
      -webkit-backdrop-filter: blur(8px) !important;
      cursor: pointer !important;
      transition: all 0.15s ease-in-out !important;
  }
  div[data-testid="stSidebarCollapseButton"] button:hover {
      background: var(--nb-yellow) !important;
      transform: translate(-1px, -1px) !important;
      box-shadow: 3px 3px 0px var(--nb-black) !important;
  }
  div[data-testid="stSidebarCollapseButton"] svg {
      fill: var(--nb-black) !important;
      stroke: var(--nb-black) !important;
  }

  /* Sidebar typography: High-contrast without wildcard color pollution */
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] h1,
  section[data-testid="stSidebar"] h2,
  section[data-testid="stSidebar"] h3,
  section[data-testid="stSidebar"] h4,
  section[data-testid="stSidebar"] caption {
      color: var(--nb-black) !important;
  }

  /* Sidebar header brand */
  .nb-sidebar-brand {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 12px 14px;
      background: rgba(255, 255, 255, 0.90);
      border: var(--nb-border-sm);
      border-radius: 8px;
      box-shadow: var(--nb-shadow-sm);
      margin: 10px 10px 20px 10px;
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
  }

  .nb-sidebar-brand-icon {
      background: var(--nb-black);
      color: var(--nb-white) !important;
      font-family: 'Space Mono', monospace;
      font-weight: 700;
      font-size: 0.95rem;
      padding: 4px 8px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
  }

  .nb-sidebar-brand-title {
      font-family: 'Space Mono', monospace;
      font-weight: 700;
      font-size: 1.15rem;
      letter-spacing: -0.02em;
      color: var(--nb-black) !important;
  }

  /* Sidebar navigation items styling: Clean white pill with crisp black border & text */
  section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"],
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
  section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] a,
  section[data-testid="stSidebar"] ul li a,
  [data-testid="stSidebarNavLink"],
  [data-testid="stSidebarNavLinkContainer"] a {
      border: var(--nb-border-sm) !important;
      border-radius: var(--nb-radius-pill) !important;
      background: rgba(255, 255, 255, 0.95) !important;
      background-color: rgba(255, 255, 255, 0.95) !important;
      backdrop-filter: blur(8px) !important;
      -webkit-backdrop-filter: blur(8px) !important;
      margin: 4px 8px !important;
      padding: 0.6rem 1.1rem !important;
      box-shadow: var(--nb-shadow-sm) !important;
      transition: all 0.15s ease-in-out !important;
      min-height: 44px !important;
      display: flex !important;
      align-items: center !important;
      gap: 10px !important;
      text-decoration: none !important;
  }

  section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] *,
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a *,
  [data-testid="stSidebarNavLink"] * {
      font-family: 'Space Mono', monospace !important;
      font-size: 0.94rem !important;
      font-weight: 700 !important;
      color: #000000 !important;
  }

  section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] svg,
  [data-testid="stSidebarNavLink"] svg {
      fill: #000000 !important;
      stroke: #000000 !important;
  }

  section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover,
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover,
  [data-testid="stSidebarNavLink"]:hover {
      transform: translate(-2px, -2px) !important;
      box-shadow: 4px 4px 0px var(--nb-black) !important;
      background: #FFF2A8 !important;
      background-color: #FFF2A8 !important;
  }

  /* Universal Active / Selected Page Item: Sunshine Yellow with 8px black accent, bold black text (NEVER solid black) */
  section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"],
  section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][data-active="true"],
  section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:focus,
  section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:active,
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"],
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[data-active="true"],
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:focus,
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:active,
  section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] a[aria-current="page"],
  section[data-testid="stSidebar"] ul li a[aria-current="page"],
  section[data-testid="stSidebar"] li[aria-selected="true"] a,
  section[data-testid="stSidebar"] [aria-current="page"],
  section[data-testid="stSidebar"] a[aria-current="page"],
  [data-testid="stSidebarNavLink"][aria-current="page"],
  [data-testid="stSidebarNavLinkContainer"] a[aria-current="page"],
  [data-testid="stSidebarNavLinkContainer"] [aria-current="page"] {
      background: #F8CD53 !important;
      background-color: #F8CD53 !important;
      border: 2.5px solid #000000 !important;
      border-left: 8px solid #000000 !important;
      border-radius: var(--nb-radius-pill) !important;
      box-shadow: 4px 4px 0px #000000 !important;
      transform: translate(-1px, -1px) !important;
  }

  section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] *,
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] *,
  section[data-testid="stSidebar"] [aria-current="page"] *,
  section[data-testid="stSidebar"] a[aria-current="page"] *,
  [data-testid="stSidebarNavLink"][aria-current="page"] *,
  [data-testid="stSidebarNavLinkContainer"] a[aria-current="page"] *,
  [data-testid="stSidebarNavLinkContainer"] [aria-current="page"] * {
      color: #000000 !important;
      font-weight: 800 !important;
      fill: #000000 !important;
      stroke: #000000 !important;
  }

  /* Clear any container backgrounds */
  [data-testid="stSidebarNavLinkContainer"],
  [data-testid="stSidebarNavItems"] li,
  [data-testid="stSidebarNavItems"] {
      background: transparent !important;
      background-color: transparent !important;
  }

  /* Dropdowns & Popovers: Never turn solid black on select or hover */
  ul[data-baseweb="menu"] li,
  div[data-baseweb="popover"] li,
  li[role="option"] {
      color: var(--nb-black) !important;
      background-color: var(--nb-white) !important;
      font-family: 'Space Mono', monospace !important;
      font-weight: 600 !important;
  }
  ul[data-baseweb="menu"] li:hover,
  ul[data-baseweb="menu"] li[aria-selected="true"],
  div[data-baseweb="popover"] li:hover,
  div[data-baseweb="popover"] li[aria-selected="true"] {
      background-color: var(--nb-yellow) !important;
      color: var(--nb-black) !important;
      font-weight: 700 !important;
  }

  /* Any widgets inside sidebar: Clean white inputs, clear contrast */
  section[data-testid="stSidebar"] .stTextInput input,
  section[data-testid="stSidebar"] .stNumberInput input,
  section[data-testid="stSidebar"] .stTextArea textarea,
  section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
      background: rgba(255, 255, 255, 0.95) !important;
      color: var(--nb-black) !important;
      border: var(--nb-border-sm) !important;
      box-shadow: var(--nb-shadow-sm) !important;
  }

  /* ==========================================================================
     3. APP HEADER / TOP ACTION BAR (Responsive & Fluid)
     ========================================================================== */
  .nb-topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 16px;
      background: var(--nb-white);
      border: var(--nb-border);
      border-radius: var(--nb-radius);
      box-shadow: var(--nb-shadow);
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
      max-width: 100%;
      box-sizing: border-box;
  }

  .nb-topbar-left {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
      flex: 1 1 auto;
  }

  .nb-topbar-btn-sq {
      width: 40px;
      height: 40px;
      min-width: 40px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--nb-white);
      border: var(--nb-border-sm);
      border-radius: 6px;
      box-shadow: 2px 2px 0px #000;
      font-family: 'Space Mono', monospace;
      font-weight: 700;
      font-size: 1.1rem;
      cursor: pointer;
      text-decoration: none;
      color: var(--nb-black) !important;
      transition: all 0.15s ease;
      flex-shrink: 0;
  }

  .nb-topbar-btn-sq:hover {
      transform: translate(-1px, -1px);
      box-shadow: 3px 3px 0px #000;
      background: var(--nb-yellow);
  }

  .nb-topbar-brand-tag {
      font-family: 'Space Mono', monospace;
      font-weight: 700;
      font-size: clamp(0.88rem, 2.4vw, 1.05rem);
      color: var(--nb-black);
      letter-spacing: -0.02em;
      white-space: normal;
      word-break: break-word;
      overflow-wrap: break-word;
  }

  .nb-topbar-right {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
  }

  .nb-topbar-search {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--nb-bg);
      border: var(--nb-border-sm);
      border-radius: var(--nb-radius-pill);
      padding: 6px 14px;
      font-size: 0.9rem;
      font-weight: 600;
      color: #333333;
      box-shadow: 2px 2px 0px #000;
      min-width: 0;
      flex: 1 1 180px;
      max-width: 100%;
      box-sizing: border-box;
  }

  .nb-topbar-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--nb-mint);
      border: var(--nb-border-sm);
      border-radius: var(--nb-radius-pill);
      padding: 6px 12px;
      font-family: 'Space Mono', monospace;
      font-size: 0.84rem;
      font-weight: 700;
      box-shadow: 2px 2px 0px #000;
      flex-shrink: 0;
  }

  /* ==========================================================================
     3.1 QUICK NAVIGATION HAMBURGER DROPDOWN (In Top Bar)
     ========================================================================== */
  .nb-menu-dropdown {
      position: relative;
      display: inline-block;
  }

  .nb-menu-dropdown summary {
      list-style: none !important;
      outline: none !important;
  }

  .nb-menu-dropdown summary::-webkit-details-marker {
      display: none !important;
  }

  .nb-menu-dropdown[open] summary::before {
      content: "";
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.12);
      z-index: 9998;
      cursor: default;
  }

  .nb-menu-dropdown-content {
      position: absolute;
      top: calc(100% + 8px);
      left: 0;
      width: 270px;
      max-width: 90vw;
      background: #FFFFFF;
      border: 2.5px solid #000000;
      border-radius: 10px;
      box-shadow: 6px 6px 0px #000000;
      padding: 8px;
      z-index: 9999;
      animation: nbSlideDown 0.15s ease-out;
      box-sizing: border-box;
  }

  @keyframes nbSlideDown {
      from { opacity: 0; transform: translateY(-6px); }
      to { opacity: 1; transform: translateY(0); }
  }

  .nb-menu-header {
      font-family: 'Space Mono', monospace;
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      color: #555555;
      padding: 6px 8px;
      letter-spacing: 0.04em;
      border-bottom: 2px solid #000000;
      margin-bottom: 6px;
  }

  .nb-menu-link {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 9px 12px;
      margin: 3px 0;
      font-family: 'Space Mono', monospace;
      font-size: 0.88rem;
      font-weight: 700;
      color: #000000 !important;
      text-decoration: none !important;
      border: 1.5px solid transparent;
      border-radius: 6px;
      transition: all 0.12s ease;
  }

  .nb-menu-link:hover {
      background: #F8CD53;
      border-color: #000000;
      box-shadow: 2px 2px 0px #000000;
      transform: translate(-1px, -1px);
  }

  .nb-menu-link.active {
      background: #F8CD53;
      border: 2px solid #000000;
      border-left: 6px solid #000000;
      box-shadow: 2px 2px 0px #000000;
  }

  .nb-menu-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 22px;
      flex-shrink: 0;
  }

  .nb-menu-icon svg {
      width: 18px;
      height: 18px;
  }

  /* ==========================================================================
     4. HERO CARD (Warm Yellow - Hillary Bale Style, Zero Overflow)
     ========================================================================== */
  .nb-hero-card {
      background: var(--nb-yellow);
      border: var(--nb-border);
      border-radius: var(--nb-radius);
      box-shadow: var(--nb-shadow);
      padding: 24px;
      margin-bottom: 2rem;
      position: relative;
      max-width: 100%;
      box-sizing: border-box;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-hero-layout {
      display: flex;
      gap: 24px;
      align-items: flex-start;
      min-width: 0;
      max-width: 100%;
  }

  .nb-hero-avatar-box {
      width: 120px;
      height: 120px;
      min-width: 120px;
      flex-shrink: 0;
      border: var(--nb-border-sm);
      border-radius: 8px;
      background: var(--nb-white);
      box-shadow: var(--nb-shadow-sm);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      font-size: 3rem;
  }

  .nb-hero-content {
      flex: 1 1 0%;
      min-width: 0;
      max-width: 100%;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-hero-header-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 12px;
      min-width: 0;
      max-width: 100%;
  }

  .nb-hero-title {
      font-family: 'Space Mono', monospace;
      font-size: clamp(1.4rem, 3.2vw, 1.85rem);
      font-weight: 700;
      color: var(--nb-black);
      margin: 0 0 4px 0;
      letter-spacing: -0.02em;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-hero-sub {
      font-size: clamp(0.92rem, 1.8vw, 1.02rem);
      font-weight: 600;
      color: #1a1a1a;
      margin: 0;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-hero-tags {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      max-width: 100%;
  }

  .nb-tag-sq {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 32px;
      height: 32px;
      padding: 2px 8px;
      background: var(--nb-white);
      border: var(--nb-border-sm);
      border-radius: 6px;
      box-shadow: 2px 2px 0px #000;
      font-family: 'Space Mono', monospace;
      font-size: 0.85rem;
      font-weight: 700;
  }

  /* Fluid Stat Grid inside Hero: auto-reflows without pushing outside container */
  .nb-stat-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 12px;
      margin: 16px 0;
      min-width: 0;
      max-width: 100%;
  }

  .nb-stat-box {
      background: var(--nb-white);
      border: var(--nb-border-sm);
      border-radius: 8px;
      box-shadow: var(--nb-shadow-sm);
      padding: 10px 12px;
      text-align: left;
      transition: transform 0.15s ease;
      min-width: 0;
      overflow-wrap: break-word;
      word-break: break-word;
      box-sizing: border-box;
  }

  .nb-stat-box:hover {
      transform: translate(-1px, -1px);
      box-shadow: 4px 4px 0px #000;
  }

  .nb-stat-num {
      font-family: 'Space Mono', monospace;
      font-size: clamp(1.1rem, 2vw, 1.35rem);
      font-weight: 700;
      color: var(--nb-black);
      line-height: 1.2;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-stat-lbl {
      font-size: 0.78rem;
      font-weight: 700;
      color: #333333;
      text-transform: lowercase;
      letter-spacing: 0.02em;
      margin-top: 2px;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-hero-desc {
      font-size: 0.95rem;
      font-weight: 600;
      color: #1a1a1a;
      line-height: 1.45;
      margin: 10px 0 16px 0;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-hero-actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      max-width: 100%;
  }

  /* ==========================================================================
     5. SECTION HEADERS & PILL BADGES
     ========================================================================== */
  .nb-section-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 1.8rem;
      margin-bottom: 1rem;
      flex-wrap: wrap;
      max-width: 100%;
  }

  .nb-step-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--nb-black);
      color: var(--nb-white);
      font-family: 'Space Mono', monospace;
      font-size: 0.88rem;
      font-weight: 700;
      padding: 4px 12px;
      border-radius: var(--nb-radius-pill);
      letter-spacing: 0.04em;
      flex-shrink: 0;
  }

  .nb-step-title {
      font-family: 'Space Mono', monospace;
      font-size: clamp(1.15rem, 2.4vw, 1.38rem);
      font-weight: 700;
      color: var(--nb-black);
      letter-spacing: -0.02em;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  /* ==========================================================================
     6. NEOBRUTALIST CARDS (Zero Overflow, Responsive Padding)
     ========================================================================== */
  .nb-card, .nb-sparkline-card, .nb-review-card, .nb-metric-box, .nb-activity-card {
      max-width: 100% !important;
      box-sizing: border-box !important;
      overflow-wrap: break-word !important;
      word-break: break-word !important;
      min-width: 0 !important;
  }

  .nb-card {
      background: var(--nb-white);
      border: var(--nb-border);
      border-radius: var(--nb-radius);
      box-shadow: var(--nb-shadow);
      padding: 20px 24px;
      margin-bottom: 20px;
  }

  .nb-card-yellow { background: var(--nb-yellow) !important; }
  .nb-card-pink { background: var(--nb-pink) !important; }
  .nb-card-mint { background: var(--nb-mint) !important; }
  .nb-card-blue { background: var(--nb-blue) !important; }

  /* Stacked Activity Cards */
  .nb-activity-card {
      background: var(--nb-white);
      border: var(--nb-border);
      border-radius: var(--nb-radius);
      box-shadow: var(--nb-shadow-sm);
      padding: 14px 18px;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 14px;
      transition: all 0.15s ease;
      min-width: 0;
      max-width: 100%;
  }

  .nb-activity-card:hover {
      transform: translate(-2px, -2px);
      box-shadow: var(--nb-shadow);
  }

  .nb-activity-icon-sq {
      width: 44px;
      height: 44px;
      min-width: 44px;
      background: var(--nb-bg);
      border: var(--nb-border-sm);
      border-radius: 6px;
      box-shadow: 2px 2px 0px #000;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 1.3rem;
      flex-shrink: 0;
  }

  .nb-activity-content {
      flex: 1 1 0%;
      min-width: 0;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-activity-title {
      font-family: 'Space Mono', monospace;
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--nb-black);
      margin: 0;
      line-height: 1.3;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-activity-sub {
      font-size: 0.85rem;
      font-weight: 600;
      color: #444444;
      margin-top: 2px;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-activity-meta {
      font-family: 'Space Mono', monospace;
      font-size: 0.8rem;
      color: #666666;
      margin-top: 2px;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  /* ==========================================================================
     7. LILAC / PINK RATING & SPARKLINE CARD
     ========================================================================== */
  .nb-sparkline-card {
      background: var(--nb-pink);
      border: var(--nb-border);
      border-radius: var(--nb-radius);
      box-shadow: var(--nb-shadow);
      padding: 18px 22px;
      margin-bottom: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 160px;
  }

  .nb-sparkline-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 8px;
  }

  .nb-sparkline-score {
      font-family: 'Space Mono', monospace;
      font-size: 1.45rem;
      font-weight: 700;
      color: var(--nb-black);
      display: flex;
      align-items: center;
      gap: 6px;
  }

  .nb-sparkline-pill-btn {
      background: var(--nb-white);
      border: var(--nb-border-sm);
      border-radius: var(--nb-radius-pill);
      padding: 4px 12px;
      font-family: 'Space Mono', monospace;
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--nb-black);
      box-shadow: 2px 2px 0px #000;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
  }

  .nb-sparkline-pill-btn:hover {
      transform: translate(-1px, -1px);
      box-shadow: 3px 3px 0px #000;
      background: var(--nb-yellow);
  }

  .nb-sparkline-body {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
  }

  .nb-sparkline-count {
      font-family: 'Space Mono', monospace;
      font-size: 1.6rem;
      font-weight: 700;
      line-height: 1.1;
      color: var(--nb-black);
  }

  .nb-sparkline-count-lbl {
      font-size: 0.82rem;
      font-weight: 700;
      color: #333333;
      margin-top: 4px;
  }

  .nb-sparkline-svg {
      width: 140px;
      height: 48px;
      max-width: 100%;
  }

  /* ==========================================================================
     8. REVIEW / VERIFICATION CARDS
     ========================================================================== */
  .nb-review-card {
      background: var(--nb-white);
      border: var(--nb-border);
      border-radius: var(--nb-radius);
      box-shadow: var(--nb-shadow-sm);
      padding: 16px 20px;
      margin-bottom: 14px;
      transition: all 0.15s ease;
  }

  .nb-review-card:hover {
      transform: translate(-2px, -2px);
      box-shadow: var(--nb-shadow);
  }

  .nb-review-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
      flex-wrap: wrap;
      gap: 6px;
  }

  .nb-review-author {
      font-family: 'Space Mono', monospace;
      font-size: 0.96rem;
      font-weight: 700;
      color: var(--nb-black);
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-review-badge {
      font-family: 'Space Mono', monospace;
      font-size: 0.85rem;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      flex-shrink: 0;
  }

  .nb-review-role {
      font-size: 0.82rem;
      font-weight: 600;
      color: #555555;
      margin-bottom: 8px;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-review-body {
      font-size: 0.88rem;
      font-weight: 500;
      color: #222222;
      line-height: 1.45;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  /* ==========================================================================
     9. METRIC STAT CARDS
     ========================================================================== */
  .nb-metric-box {
      background: var(--nb-white);
      border: var(--nb-border);
      border-radius: var(--nb-radius);
      padding: 16px 18px;
      box-shadow: var(--nb-shadow-sm);
      text-align: left;
      transition: transform 0.15s ease;
      min-height: 104px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
  }

  .nb-metric-box:hover {
      transform: translate(-2px, -2px);
      box-shadow: var(--nb-shadow);
  }

  .nb-metric-value {
      font-family: 'Space Mono', monospace;
      font-size: clamp(1.4rem, 2.8vw, 1.75rem);
      font-weight: 700;
      color: var(--nb-black);
      line-height: 1.15;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-metric-label {
      font-size: 0.84rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #333333;
      margin-top: 4px;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  .nb-metric-sub {
      font-size: 0.78rem;
      font-weight: 600;
      color: #666666;
      margin-top: 2px;
      overflow-wrap: break-word;
      word-break: break-word;
  }

  /* ==========================================================================
     10. STREAMLIT WIDGETS, BUTTONS & RESPONSIVE COLUMNS
     ========================================================================== */
  /* Prevent Streamlit multi-columns from breaking parent containers horizontally */
  div[data-testid="stHorizontalBlock"] {
      max-width: 100% !important;
      min-width: 0 !important;
  }

  div[data-testid="column"] {
      min-width: 0 !important;
      max-width: 100% !important;
      overflow-wrap: break-word !important;
      word-break: break-word !important;
  }

  label, .stSelectbox label, .stTextInput label, .stFileUploader label,
  .stRadio label, .stCheckbox label, .stMultiSelect label, .stNumberInput label {
      font-family: 'Space Mono', monospace !important;
      font-size: 0.94rem !important;
      font-weight: 700 !important;
      color: var(--nb-black) !important;
      letter-spacing: -0.01em !important;
  }

  .stTextInput input, .stNumberInput input, .stTextArea textarea,
  div[data-baseweb="select"] > div {
      border: var(--nb-border-sm) !important;
      border-radius: 8px !important;
      background-color: var(--nb-white) !important;
      box-shadow: var(--nb-shadow-sm) !important;
      font-weight: 600 !important;
      font-size: 0.95rem !important;
      color: var(--nb-black) !important;
      min-height: 44px !important;
      max-width: 100% !important;
      box-sizing: border-box !important;
  }

  .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus,
  div[data-baseweb="select"] > div:focus-within {
      border-color: var(--nb-black) !important;
      box-shadow: 4px 4px 0px var(--nb-black) !important;
  }

  /* Standard & Primary Buttons: full text wrap to prevent mobile blowout */
  .stButton, .stDownloadButton {
      max-width: 100% !important;
  }

  .stButton button, .stDownloadButton button {
      font-family: 'Space Mono', monospace !important;
      font-size: 0.96rem !important;
      font-weight: 700 !important;
      border: var(--nb-border) !important;
      border-radius: var(--nb-radius-pill) !important;
      background: var(--nb-white) !important;
      color: var(--nb-black) !important;
      box-shadow: var(--nb-shadow-sm) !important;
      transition: all 0.15s ease-in-out !important;
      padding: 0.6rem 1.4rem !important;
      min-height: 44px !important;
      height: auto !important;
      cursor: pointer !important;
      white-space: normal !important;
      word-break: break-word !important;
      max-width: 100% !important;
      box-sizing: border-box !important;
  }

  .stButton button:hover, .stDownloadButton button:hover {
      transform: translate(-2px, -2px) !important;
      box-shadow: var(--nb-shadow-hover) !important;
      background: var(--nb-yellow) !important;
      color: var(--nb-black) !important;
  }

  .stButton button:active, .stDownloadButton button:active {
      transform: translate(1px, 1px) !important;
      box-shadow: 2px 2px 0px var(--nb-black) !important;
  }

  /* Inverted Primary Button: Solid Black with White Text */
  .stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
      background: var(--nb-black) !important;
      color: var(--nb-white) !important;
      box-shadow: 4px 4px 0px var(--nb-black) !important;
  }

  .stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover {
      background: #1e1e1e !important;
      color: var(--nb-yellow) !important;
      box-shadow: var(--nb-shadow-hover) !important;
  }

  /* Alerts & Callouts */
  div[data-testid="stAlert"] {
      border: var(--nb-border) !important;
      border-radius: var(--nb-radius) !important;
      box-shadow: var(--nb-shadow-sm) !important;
      font-weight: 600 !important;
      color: var(--nb-black) !important;
      background: var(--nb-white) !important;
      max-width: 100% !important;
      box-sizing: border-box !important;
  }

  /* File Uploader styling */
  div[data-testid="stFileUploader"] section {
      border: 2.5px dashed var(--nb-black) !important;
      border-radius: var(--nb-radius) !important;
      background: var(--nb-white) !important;
      box-shadow: var(--nb-shadow-sm) !important;
      padding: 1.5rem !important;
      transition: all 0.15s ease;
      max-width: 100% !important;
      box-sizing: border-box !important;
  }

  div[data-testid="stFileUploader"] section:hover {
      background: #FDFCF7 !important;
      box-shadow: var(--nb-shadow) !important;
  }

  /* DataTables & Data Editors: native horizontal scroll within the table without page blowout */
  .stDataFrame, .stDataEditor {
      border: var(--nb-border) !important;
      border-radius: var(--nb-radius) !important;
      box-shadow: var(--nb-shadow) !important;
      background: var(--nb-white) !important;
      max-width: 100% !important;
      width: 100% !important;
      box-sizing: border-box !important;
      overflow-x: auto !important;
  }

  .stDataFrame > div, .stDataEditor > div {
      max-width: 100% !important;
  }

  /* Expanders */
  div[data-testid="stExpander"] {
      border: var(--nb-border) !important;
      border-radius: var(--nb-radius) !important;
      box-shadow: var(--nb-shadow-sm) !important;
      background: var(--nb-white) !important;
      margin-bottom: 14px !important;
      max-width: 100% !important;
      box-sizing: border-box !important;
  }

  div[data-testid="stExpander"] summary {
      font-family: 'Space Mono', monospace !important;
      font-weight: 700 !important;
      font-size: 1.02rem !important;
      color: var(--nb-black) !important;
  }

  /* Code blocks, code tags & pre */
  pre, code, .stCodeBlock {
      max-width: 100% !important;
      box-sizing: border-box !important;
      overflow-x: auto !important;
      word-break: break-word !important;
      overflow-wrap: break-word !important;
  }

  /* Images & Custom Component iFrames */
  div[data-testid="stImage"] {
      max-width: 100% !important;
      overflow-x: auto !important;
  }
  div[data-testid="stImage"] img {
      max-width: 100% !important;
      height: auto !important;
  }
  iframe {
      max-width: 100% !important;
      box-sizing: border-box !important;
  }

  /* Progress Bar */
  div[data-testid="stProgress"] > div > div > div > div {
      background-color: var(--nb-black) !important;
      border: 1px solid var(--nb-black) !important;
  }
  div[data-testid="stProgress"] > div > div {
      border: var(--nb-border-sm) !important;
      border-radius: 999px !important;
      background-color: var(--nb-white) !important;
      box-shadow: 2px 2px 0px #000 !important;
      height: 18px !important;
  }

  #MainMenu, footer { visibility: hidden; }

  /* ==========================================================================
     11. COMPREHENSIVE MULTI-RATIO RESPONSIVE BREAKPOINTS
     ========================================================================== */

  /* 1. Laptops & Small Desktops (max-width: 1024px) */
  @media (max-width: 1024px) {
      .block-container {
          padding-left: 1.2rem !important;
          padding-right: 1.2rem !important;
      }
      .nb-hero-card {
          padding: 20px !important;
      }
      .nb-stat-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
          gap: 10px !important;
      }
  }

  /* 2. Tablets & Mobile Landscape (max-width: 768px) */
  @media (max-width: 768px) {
      .block-container {
          padding-top: 3.8rem !important; /* Clears top hamburger button cleanly */
          padding-left: 1rem !important;
          padding-right: 1rem !important;
          padding-bottom: 3rem !important;
      }

      /* Stack all multi-column layouts */
      div[data-testid="stHorizontalBlock"] {
          flex-wrap: wrap !important;
          gap: 14px !important;
      }
      div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
          flex: 1 1 100% !important;
          min-width: 100% !important;
          max-width: 100% !important;
          margin-bottom: 6px !important;
      }

      /* Sidebar full-height slide-over drawer */
      section[data-testid="stSidebar"][aria-expanded="true"] {
          position: fixed !important;
          top: 0 !important;
          left: 0 !important;
          bottom: 0 !important;
          width: 85vw !important;
          max-width: 320px !important;
          min-width: 260px !important;
          box-shadow: 10px 0px 30px rgba(0, 0, 0, 0.25) !important;
          z-index: 1000 !important;
      }

      section[data-testid="stSidebar"][aria-expanded="false"] {
          display: none !important;
      }

      /* Hero layout stacks cleanly */
      .nb-hero-layout {
          flex-direction: column !important;
          align-items: flex-start !important;
          gap: 16px !important;
      }
      .nb-hero-avatar-box {
          width: 72px !important;
          height: 72px !important;
          min-width: 72px !important;
          font-size: 2rem !important;
      }
      .nb-stat-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
          gap: 10px !important;
      }

      /* Topbar responsive re-ordering */
      .nb-topbar {
          padding: 10px 12px !important;
          gap: 10px !important;
      }
      .nb-topbar-left {
          width: 100% !important;
          justify-content: flex-start !important;
          gap: 8px !important;
      }
      .nb-topbar-right {
          width: 100% !important;
          justify-content: flex-start !important;
          gap: 8px !important;
          flex-wrap: wrap !important;
      }
      .nb-topbar-search {
          flex: 1 1 100% !important;
          min-width: 100% !important;
      }

      /* Buttons touch targets: 100% width on stacked layout */
      .stButton, .stDownloadButton {
          width: 100% !important;
      }
      .stButton button, .stDownloadButton button {
          width: 100% !important;
          min-height: 48px !important;
          font-size: 1rem !important;
      }

      /* Input elements: prevent iOS zooming by ensuring >= 16px */
      .stTextInput input, .stNumberInput input, .stTextArea textarea,
      div[data-baseweb="select"] > div {
          font-size: 16px !important;
          min-height: 48px !important;
      }

      /* Sparkline card responsive wrap */
      .nb-sparkline-body {
          flex-direction: column !important;
          align-items: flex-start !important;
          gap: 12px !important;
      }
      .nb-sparkline-svg {
          width: 100% !important;
          max-width: 160px !important;
      }
  }

  /* 3. Small Mobile Phones (max-width: 480px) */
  @media (max-width: 480px) {
      .block-container {
          padding-top: 3.8rem !important;
          padding-left: 0.65rem !important;
          padding-right: 0.65rem !important;
      }
      .nb-hero-card {
          padding: 14px 12px !important;
          margin-bottom: 1.25rem !important;
      }
      .nb-hero-title {
          font-size: 1.35rem !important;
      }
      .nb-hero-avatar-box {
          width: 60px !important;
          height: 60px !important;
          min-width: 60px !important;
          font-size: 1.7rem !important;
      }
      .nb-stat-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
          gap: 6px !important;
      }
      .nb-stat-box {
          padding: 8px 10px !important;
      }
      .nb-stat-num {
          font-size: 1.1rem !important;
      }
      .nb-stat-lbl {
          font-size: 0.72rem !important;
      }

      .nb-card, .nb-metric-box, .nb-activity-card, .nb-review-card {
          padding: 12px 14px !important;
          margin-bottom: 10px !important;
      }

      .nb-activity-card {
          gap: 10px !important;
      }
      .nb-activity-icon-sq {
          width: 38px !important;
          height: 38px !important;
          min-width: 38px !important;
      }

      /* Top bar ultra-compact */
      .nb-topbar-brand-tag {
          font-size: 0.85rem !important;
      }
      .nb-topbar-btn-sq {
          width: 38px !important;
          height: 38px !important;
          min-width: 38px !important;
      }
      .nb-topbar-badge {
          font-size: 0.76rem !important;
          padding: 4px 8px !important;
      }

      /* Dataframes & Data Editors */
      .stDataFrame, .stDataEditor {
          font-size: 0.82rem !important;
      }
  }

  /* 4. Ultra-compact devices (max-width: 360px) */
  @media (max-width: 360px) {
      .block-container {
          padding-left: 0.5rem !important;
          padding-right: 0.5rem !important;
      }
      .nb-stat-grid {
          grid-template-columns: 1fr !important;
      }
      .nb-hero-tags {
          display: none !important;
      }
  }
</style>
"""


def apply_theme():
    """Injects the Neobrutalist styling across all Streamlit pages."""
    st.markdown(CSS, unsafe_allow_html=True)


def _clean_html(html_str: str) -> str:
    """Strips leading whitespace from each line to prevent Markdown from treating indented HTML as a code block."""
    return "\n".join(line.strip() for line in html_str.splitlines() if line.strip())


# Sleek monochrome Neobrutalist SVG icons (2.5px solid black stroke)
ICON_DOCUMENT = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>'
ICON_AI = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>'
ICON_PLUS = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>'
ICON_FOLDER = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
ICON_RULES = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="16" x2="13" y2="16"/></svg>'
ICON_SHIELD = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
ICON_BUILDING = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><line x1="9" y1="22" x2="9" y2="22.01"/><line x1="15" y1="22" x2="15" y2="22.01"/><line x1="9" y1="6" x2="9" y2="6.01"/><line x1="15" y1="6" x2="15" y2="6.01"/><line x1="9" y1="10" x2="9" y2="10.01"/><line x1="15" y1="10" x2="15" y2="10.01"/><line x1="9" y1="14" x2="9" y2="14.01"/><line x1="15" y1="14" x2="15" y2="14.01"/></svg>'
ICON_BOLT = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
ICON_CHECK = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
ICON_ALERT = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'


def top_nav_bar(page_title: str = "INVOICE EXTRACTOR",
                search_placeholder: str = "Find vendors, templates, invoices...",
                badge_text: str = "Local Engine"):
    """
    Renders the signature Neobrutalist top bar:
    Hamburger menu dropdown, square back button, brand tag, search bar, notification bell, and user status badge.
    """
    grid_svg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>'
    search_svg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
    bell_svg = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>'

    is_p1 = "AI" in page_title and "GENERIC" in page_title
    is_p2 = "BUILDER" in page_title
    is_p3 = "MANAGEMENT" in page_title
    is_p4 = "RULES" in page_title
    is_p5 = "SECURITY" in page_title
    is_main = not (is_p1 or is_p2 or is_p3 or is_p4 or is_p5)

    raw_html = f"""<div class="nb-topbar">
<div class="nb-topbar-left">
<details class="nb-menu-dropdown">
<summary class="nb-topbar-btn-sq nb-menu-btn" title="Quick Navigation Menu">
{grid_svg}
</summary>
<div class="nb-menu-dropdown-content">
<div class="nb-menu-header">Quick Navigation</div>
<a href="/" target="_self" class="nb-menu-link {'active' if is_main else ''}"><span class="nb-menu-icon">{ICON_DOCUMENT}</span><span>Main Extractor</span></a>
<a href="/Extract_Any_Invoice" target="_self" class="nb-menu-link {'active' if is_p1 else ''}"><span class="nb-menu-icon">{ICON_AI}</span><span>Extract Any Invoice</span></a>
<a href="/Add_New_Vendor" target="_self" class="nb-menu-link {'active' if is_p2 else ''}"><span class="nb-menu-icon">{ICON_PLUS}</span><span>Add New Vendor</span></a>
<a href="/Manage" target="_self" class="nb-menu-link {'active' if is_p3 else ''}"><span class="nb-menu-icon">{ICON_FOLDER}</span><span>Manage Templates</span></a>
<a href="/Business_Rules" target="_self" class="nb-menu-link {'active' if is_p4 else ''}"><span class="nb-menu-icon">{ICON_RULES}</span><span>Business Rules</span></a>
<a href="/Security_and_Logs" target="_self" class="nb-menu-link {'active' if is_p5 else ''}"><span class="nb-menu-icon">{ICON_SHIELD}</span><span>Security &amp; Logs</span></a>
</div>
</details>
<a href="/" target="_self" class="nb-topbar-btn-sq" title="Back / Home">←</a>
<span class="nb-topbar-brand-tag">{html.escape(page_title)}</span>
</div>
<div class="nb-topbar-right">
<div class="nb-topbar-search">
<span>{search_svg}</span>
<span>{html.escape(search_placeholder)}</span>
</div>
<div class="nb-topbar-btn-sq" title="System Notifications">{bell_svg}</div>
<div class="nb-topbar-badge">
<span>●</span> {html.escape(badge_text)}
</div>
</div>
</div>"""
    st.markdown(_clean_html(raw_html), unsafe_allow_html=True)


def hero_card(title: str,
              subtitle: str = "",
              meta_tags: Optional[List[str]] = None,
              stat_items: Optional[List[Tuple[str, str]]] = None,
              desc: str = "",
              color: str = "#F8CD53",
              icon: str = ICON_DOCUMENT):
    """
    Renders the signature Hillary Bale style Warm Yellow Hero Card from the reference image:
    Thick 2.5px black border, hard shadow, media/avatar box, title, meta badges,
    4-box stat grid, description, and action button container.
    """
    safe_title = html.escape(title)
    safe_sub = html.escape(subtitle)
    safe_desc = html.escape(desc)
    safe_icon = icon if icon.strip().startswith("<svg") else html.escape(icon)

    tags_html = ""
    if meta_tags:
        tags_html = '<div class="nb-hero-tags">' + "".join(
            f'<span class="nb-tag-sq">{html.escape(t)}</span>' for t in meta_tags
        ) + '</div>'

    stats_html = ""
    if stat_items:
        stat_boxes = [
            f'<div class="nb-stat-box"><div class="nb-stat-num">{html.escape(str(val))}</div><div class="nb-stat-lbl">{html.escape(lbl)}</div></div>'
            for val, lbl in stat_items[:4]
        ]
        stats_html = f'<div class="nb-stat-grid">{"".join(stat_boxes)}</div>'

    desc_html = f'<div class="nb-hero-desc">{safe_desc}</div>' if safe_desc else ""
    sub_html = f'<p class="nb-hero-sub">{safe_sub}</p>' if safe_sub else ""

    raw_html = f"""<div class="nb-hero-card" style="background: {color};">
<div class="nb-hero-layout">
<div class="nb-hero-avatar-box">
<span>{safe_icon}</span>
</div>
<div class="nb-hero-content">
<div class="nb-hero-header-row">
<div>
<h1 class="nb-hero-title">{safe_title}</h1>
{sub_html}
</div>
{tags_html}
</div>
{stats_html}
{desc_html}
</div>
</div>
</div>"""
    st.markdown(_clean_html(raw_html), unsafe_allow_html=True)


def hero(title: str, subtitle: str = "", color: str = "#F8CD53"):
    """Legacy-compatible hero wrapper rendered in full Neobrutalist aesthetic."""
    safe_title = html.escape(title)
    safe_sub = html.escape(subtitle)
    sub = f"<p style='margin:0.5rem 0 0;font-size:1.02rem;font-weight:600;color:#121212;'>{safe_sub}</p>" if safe_sub else ""
    raw_html = f"""<div class="nb-card" style="background:{color}; margin-bottom: 24px; border: 2.5px solid #000000; box-shadow: 4px 4px 0px #000000;">
<h1 style="margin:0; font-size: 2.05rem; font-weight: 700; color: #000000; font-family: 'Space Mono', monospace;">{safe_title}</h1>
{sub}
</div>"""
    st.markdown(_clean_html(raw_html), unsafe_allow_html=True)


def section_header(step_num: str, title: str):
    """Renders a Neobrutalist section header with a solid black pill step badge and bold title."""
    badge = f'<span class="nb-step-badge">{html.escape(step_num)}</span>' if step_num else ''
    raw_html = f"""<div class="nb-section-header">
{badge}
<span class="nb-step-title">{html.escape(title)}</span>
</div>"""
    st.markdown(_clean_html(raw_html), unsafe_allow_html=True)


def metric_card(label: str, value: str | int | float, bg_color: str = "#FFFFFF", subtext: str = ""):
    """Renders a tactile Neobrutalist stat/metric card."""
    sub_html = f'<div class="nb-metric-sub">{html.escape(subtext)}</div>' if subtext else ""
    raw_html = f"""<div class="nb-metric-box" style="background: {bg_color};">
<div>
<div class="nb-metric-value">{html.escape(str(value))}</div>
<div class="nb-metric-label">{html.escape(label)}</div>
</div>
{sub_html}
</div>"""
    st.markdown(_clean_html(raw_html), unsafe_allow_html=True)


def analytics_sparkline_card(title: str = "Accuracy",
                            rating: str = "99.8%",
                            count_text: str = "127 invoices processed",
                            btn_text: str = "See stats",
                            bg_color: str = "#F6C8FB"):
    """
    Renders the signature Lilac/Pink rating card from the bottom-left of the reference image:
    Star rating badge, pill button, minimalist SVG sparkline trend, and counter text.
    """
    count_parts = count_text.split()
    count_num = count_parts[0] if count_parts else ""
    count_lbl = ' '.join(count_parts[1:]) if len(count_parts) > 1 else ""
    raw_html = f"""<div class="nb-sparkline-card" style="background: {bg_color};">
<div class="nb-sparkline-header">
<div class="nb-sparkline-score">{html.escape(rating)}</div>
<span class="nb-sparkline-pill-btn">{html.escape(btn_text)}</span>
</div>
<div class="nb-sparkline-body">
<div>
<div class="nb-sparkline-count">{html.escape(count_num)}</div>
<div class="nb-sparkline-count-lbl">{html.escape(count_lbl)}</div>
</div>
<svg class="nb-sparkline-svg" viewBox="0 0 140 48" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M 4 36 Q 24 12, 44 28 T 80 16 T 108 34 T 136 18" stroke="#000000" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>
</div>
</div>"""
    st.markdown(_clean_html(raw_html), unsafe_allow_html=True)


def activity_card(icon: str, title: str, subtitle: str, meta: str = ""):
    """
    Renders a stacked white card with a square bordered icon box on the left,
    matching the 'Work experience' list cards from the reference image.
    """
    meta_html = f'<div class="nb-activity-meta">{html.escape(meta)}</div>' if meta else ""
    safe_icon = icon if icon.strip().startswith("<svg") else html.escape(icon)
    raw_html = f"""<div class="nb-activity-card">
<div class="nb-activity-icon-sq">{safe_icon}</div>
<div class="nb-activity-content">
<h4 class="nb-activity-title">{html.escape(title)}</h4>
<div class="nb-activity-sub">{html.escape(subtitle)}</div>
{meta_html}
</div>
</div>"""
    st.markdown(_clean_html(raw_html), unsafe_allow_html=True)


def review_card(author: str, role: str, rating: str, comment: str, status_icon: str = "PASS"):
    """
    Renders a verification/review card matching the 'Students reviews' cards
    from the bottom of the reference image.
    """
    safe_status = status_icon if status_icon.strip().startswith("<svg") else html.escape(status_icon)
    raw_html = f"""<div class="nb-review-card">
<div class="nb-review-head">
<span class="nb-review-author">{html.escape(author)}</span>
<span class="nb-review-badge">{safe_status} {html.escape(rating)}</span>
</div>
<div class="nb-review-role">{html.escape(role)}</div>
<div class="nb-review-body">{html.escape(comment)}</div>
</div>"""
    st.markdown(_clean_html(raw_html), unsafe_allow_html=True)


def status_pill(text: str, status: str = "default") -> str:
    """Returns HTML for an inline status pill tag."""
    colors = {
        "success": ("#A3D9B8", "#000000"),
        "warning": ("#F8CD53", "#000000"),
        "error": ("#FFC6D9", "#000000"),
        "info": ("#BAE6FD", "#000000"),
        "default": ("#FFFFFF", "#000000"),
    }
    bg, fg = colors.get(status, colors["default"])
    return (f'<span style="display:inline-block;padding:2px 10px;background:{bg};'
            f'color:{fg};border:2px solid #000;border-radius:999px;font-family:\'Space Mono\',monospace;'
            f'font-size:0.8rem;font-weight:700;box-shadow:1.5px 1.5px 0px #000;">{html.escape(text)}</span>')
