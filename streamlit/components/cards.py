"""
Reusable card components for the Streamlit application
"""
import streamlit as st
from typing import Optional

def create_status_card(title: str, status: str, details: str = ""):
    """Create a status card component"""
    if status.lower() in ["connected", "active", "online", "running", "success"]:
        color = "#28a745"
        icon = "🟢"
        bg_color = "#f8fff9"
    elif status.lower() in ["disconnected", "offline", "failed", "error"]:
        color = "#dc3545"
        icon = "🔴"
        bg_color = "#fff8f8"
    elif status.lower() in ["warning", "pending", "queued"]:
        color = "#ffc107"
        icon = "🟡"
        bg_color = "#fffcf0"
    else:
        color = "#17a2b8"
        icon = "🔵"
        bg_color = "#f0f9ff"
    
    st.markdown(f"""
    <div style="
        background-color: {bg_color};
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid {color};
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    ">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div>
                <h4 style="margin: 0; color: #333;">{title}</h4>
                <p style="margin: 0; color: {color}; font-weight: bold;">{status}</p>
                {f'<p style="margin: 0.5rem 0 0 0; color: #6c757d; font-size: 0.9rem;">{details}</p>' if details else ''}
            </div>
            <div style="font-size: 1.5rem;">{icon}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def create_metric_card(title: str, value: str, delta: Optional[str] = None, icon: str = "📊"):
    """Create a metric card component"""
    delta_html = ""
    if delta:
        delta_color = "#28a745" if delta.startswith("+") else "#dc3545" if delta.startswith("-") else "#6c757d"
        delta_html = f'<p style="margin: 0; color: {delta_color}; font-size: 0.9rem;">{delta}</p>'
    
    st.markdown(f"""
    <div style="
        background-color: white;
        padding: 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
        text-align: center;
        border-top: 3px solid #007bff;
    ">
        <div style="font-size: 2rem; margin-bottom: 0.5rem;">{icon}</div>
        <h3 style="margin: 0; color: #333; font-size: 2rem;">{value}</h3>
        <p style="margin: 0; color: #6c757d; font-size: 0.9rem;">{title}</p>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)

def create_pipeline_status_card(pipeline_id: str, status: str, progress: int = 0, 
                               sample_id: str = "", description: str = ""):
    """Create a pipeline status card"""
    status_colors = {
        "queued": "#ffc107",
        "running": "#17a2b8", 
        "completed": "#28a745",
        "success": "#28a745",
        "failed": "#dc3545",
        "cancelled": "#6c757d",
        "error": "#dc3545"
    }
    
    status_icons = {
        "queued": "⏳",
        "running": "🔄",
        "completed": "✅",
        "success": "✅",
        "failed": "❌",
        "cancelled": "⏹️",
        "error": "❌"
    }
    
    color = status_colors.get(status.lower(), "#6c757d")
    icon = status_icons.get(status.lower(), "❔")
    
    # Create progress bar HTML
    progress_html = f"""
    <div style="background-color: #e9ecef; border-radius: 10px; height: 8px; margin: 0.5rem 0;">
        <div style="background-color: {color}; height: 100%; border-radius: 10px; width: {progress}%;"></div>
    </div>
    """ if progress > 0 else ""
    
    st.markdown(f"""
    <div style="
        background-color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid {color};
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    ">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
            <div>
                <h4 style="margin: 0; color: #333;">{sample_id}</h4>
                <p style="margin: 0; color: #6c757d; font-size: 0.8rem;">{pipeline_id}</p>
            </div>
            <div style="text-align: right;">
                <span style="font-size: 1.2rem;">{icon}</span>
                <p style="margin: 0; color: {color}; font-weight: bold; font-size: 0.9rem;">{status.upper()}</p>
            </div>
        </div>
        
        {progress_html}
        
        <p style="margin: 0; color: #6c757d; font-size: 0.8rem; margin-top: 0.5rem;">{description}</p>
        
        {f'<p style="margin: 0; color: #6c757d; font-size: 0.8rem; text-align: right;">Progress: {progress}%</p>' if progress > 0 else ''}
    </div>
    """, unsafe_allow_html=True)

def create_info_card(title: str, content: str, icon: str = "ℹ️"):
    """Create an information card"""
    st.markdown(f"""
    <div style="
        background-color: #e7f3ff;
        border: 1px solid #b8daff;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    ">
        <div style="display: flex; align-items: flex-start;">
            <div style="font-size: 1.5rem; margin-right: 1rem;">{icon}</div>
            <div>
                <h4 style="margin: 0 0 0.5rem 0; color: #004085;">{title}</h4>
                <p style="margin: 0; color: #004085;">{content}</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def create_warning_card(title: str, content: str, icon: str = "⚠️"):
    """Create a warning card"""
    st.markdown(f"""
    <div style="
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    ">
        <div style="display: flex; align-items: flex-start;">
            <div style="font-size: 1.5rem; margin-right: 1rem;">{icon}</div>
            <div>
                <h4 style="margin: 0 0 0.5rem 0; color: #856404;">{title}</h4>
                <p style="margin: 0; color: #856404;">{content}</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def create_error_card(title: str, content: str, icon: str = "❌"):
    """Create an error card"""
    st.markdown(f"""
    <div style="
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    ">
        <div style="display: flex; align-items: flex-start;">
            <div style="font-size: 1.5rem; margin-right: 1rem;">{icon}</div>
            <div>
                <h4 style="margin: 0 0 0.5rem 0; color: #721c24;">{title}</h4>
                <p style="margin: 0; color: #721c24;">{content}</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def create_success_card(title: str, content: str, icon: str = "✅"):
    """Create a success card"""
    st.markdown(f"""
    <div style="
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    ">
        <div style="display: flex; align-items: flex-start;">
            <div style="font-size: 1.5rem; margin-right: 1rem;">{icon}</div>
            <div>
                <h4 style="margin: 0 0 0.5rem 0; color: #155724;">{title}</h4>
                <p style="margin: 0; color: #155724;">{content}</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def create_metrics_row(metrics: list):
    """Create a row of metric cards"""
    if not metrics:
        return
    
    cols = st.columns(len(metrics))
    
    for col, metric in zip(cols, metrics):
        with col:
            create_metric_card(
                title=metric.get('title', ''),
                value=metric.get('value', ''),
                delta=metric.get('delta'),
                icon=metric.get('icon', '📊')
            )

def create_simple_card(content: str, card_type: str = "info"):
    """Create a simple card with basic styling"""
    type_styles = {
        "info": {"bg": "#e7f3ff", "border": "#b8daff", "text": "#004085"},
        "warning": {"bg": "#fff3cd", "border": "#ffeaa7", "text": "#856404"},
        "error": {"bg": "#f8d7da", "border": "#f5c6cb", "text": "#721c24"},
        "success": {"bg": "#d4edda", "border": "#c3e6cb", "text": "#155724"},
        "default": {"bg": "#f8f9fa", "border": "#dee2e6", "text": "#495057"}
    }
    
    style = type_styles.get(card_type, type_styles["default"])
    
    st.markdown(f"""
    <div style="
        background-color: {style['bg']};
        border: 1px solid {style['border']};
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        color: {style['text']};
    ">
        {content}
    </div>
    """, unsafe_allow_html=True)