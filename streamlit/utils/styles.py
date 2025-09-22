import streamlit as st
import os
from pathlib import Path

def load_css(file_name: str) -> str:
    """Load CSS from file"""
    css_path = Path(__file__).parent.parent / "static" / file_name
    try:
        with open(css_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"CSS file not found: {css_path}")
        return ""
    except Exception as e:
        st.error(f"Error loading CSS: {e}")
        return ""

def inject_custom_css(css_file: str = "styles.css"):
    """Inject custom CSS into Streamlit app"""
    css_content = load_css(css_file)
    if css_content:
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

def load_component_css(component_name: str) -> str:
    """Load CSS for specific component"""
    return load_css(f"components/{component_name}.css")

# Theme configuration
class ThemeConfig:
    """Theme configuration for the application"""
    
    # Color palette
    PRIMARY_COLOR = "#007bff"
    SECONDARY_COLOR = "#6c757d"
    SUCCESS_COLOR = "#28a745"
    WARNING_COLOR = "#ffc107"
    ERROR_COLOR = "#dc3545"
    INFO_COLOR = "#17a2b8"
    
    # Gradients
    HEADER_GRADIENT = "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
    BUTTON_GRADIENT = "linear-gradient(135deg, #007bff, #0056b3)"
    
    # Spacing
    BORDER_RADIUS = "10px"
    PADDING_LARGE = "2rem"
    PADDING_MEDIUM = "1.5rem"
    PADDING_SMALL = "1rem"
    
    # Shadows
    CARD_SHADOW = "0 2px 8px rgba(0,0,0,0.1)"
    LIGHT_SHADOW = "0 2px 4px rgba(0,0,0,0.1)"

def get_status_class(status: str) -> str:
    """Get CSS class for status"""
    status_classes = {
        'success': 'status-success',
        'completed': 'status-success',
        'error': 'status-error',
        'failed': 'status-error',
        'warning': 'status-warning',
        'pending': 'status-warning',
        'running': 'status-info',
        'queued': 'status-warning'
    }
    return status_classes.get(status.lower(), 'status-card')

def create_card_html(content: str, card_class: str = "status-card") -> str:
    """Create HTML card with custom styling"""
    return f"""
    <div class="{card_class}">
        {content}
    </div>
    """

def create_metric_card(label: str, value: str, icon: str = "", color: str = "#007bff") -> str:
    """Create metric card HTML"""
    return f"""
    <div class="metric-container">
        <div class="metric-label">{icon} {label}</div>
        <div class="metric-value" style="color: {color}">{value}</div>
    </div>
    """