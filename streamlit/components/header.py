# components/header.py
import streamlit as st

def create_header(title: str, subtitle: str = "", description: str = ""):
    """Create enhanced header with custom styling"""
    header_content = f"""
    <div class="main-header">
        <h1 style="margin: 0; font-size: 2.5rem;">{title}</h1>
        {f'<p style="margin: 0.5rem 0 0 0; font-size: 1.2rem; opacity: 0.9;">{subtitle}</p>' if subtitle else ''}
        {f'<div style="font-size: 1rem; opacity: 0.8; margin-top: 0.5rem;">{description}</div>' if description else ''}
    </div>
    """
    st.markdown(header_content, unsafe_allow_html=True)