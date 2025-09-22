"""
Chart components for data visualization
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import Dict, List, Optional
import numpy as np

def create_temperature_chart(weather_df: pd.DataFrame) -> Optional[go.Figure]:
    """Create temperature trend chart"""
    if weather_df.empty:
        return None
    
    fig = px.line(
        weather_df.sort_values('measurement_datetime').tail(100),
        x='measurement_datetime',
        y='temperature',
        color='city',
        title='Temperature Trends by Location',
        labels={'measurement_datetime': 'Time', 'temperature': 'Temperature (°C)'},
        template='plotly_white'
    )
    
    fig.update_layout(
        height=400,
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    return fig

def create_humidity_chart(weather_df: pd.DataFrame) -> Optional[go.Figure]:
    """Create humidity trend chart"""
    if weather_df.empty:
        return None
    
    fig = px.line(
        weather_df.sort_values('measurement_datetime').tail(100),
        x='measurement_datetime',
        y='humidity',
        color='city',
        title='Humidity Trends by Location',
        labels={'measurement_datetime': 'Time', 'humidity': 'Humidity (%)'},
        template='plotly_white'
    )
    
    fig.update_layout(
        height=400,
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    return fig

def create_weather_map(weather_df: pd.DataFrame) -> Optional[go.Figure]:
    """Create weather data map visualization"""
    if weather_df.empty or 'latitude' not in weather_df.columns or 'longitude' not in weather_df.columns:
        return None
    
    # Get the most recent data for each location
    latest_data = weather_df.sort_values('measurement_datetime').groupby('city').tail(1)
    
    fig = px.scatter_mapbox(
        latest_data,
        lat="latitude",
        lon="longitude",
        hover_name="city",
        hover_data={"temperature": True, "humidity": True, "measurement_datetime": True},
        color="temperature",
        size="humidity",
        color_continuous_scale="RdYlBu_r",
        size_max=15,
        zoom=3,
        title="Current Weather Conditions by Location"
    )
    
    fig.update_layout(
        mapbox_style="open-street-map",
        height=500,
        margin={"r": 0, "t": 50, "l": 0, "b": 0}
    )
    
    return fig

def create_pipeline_status_chart(pipeline_data: pd.DataFrame) -> Optional[go.Figure]:
    """Create pipeline status distribution chart"""
    if pipeline_data.empty:
        return None
    
    status_counts = pipeline_data['status'].value_counts()
    
    colors = {
        'completed': '#28a745',
        'running': '#17a2b8',
        'failed': '#dc3545',
        'queued': '#ffc107'
    }
    
    fig = px.pie(
        values=status_counts.values,
        names=status_counts.index,
        title='Pipeline Status Distribution',
        color_discrete_map=colors
    )
    
    fig.update_layout(height=400)
    
    return fig

def create_metrics_dashboard_chart(metrics_data: Dict) -> go.Figure:
    """Create dashboard metrics chart"""
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Active Locations', 'Recent Analyses', 'Success Rate', 'System Health'),
        specs=[[{"type": "indicator"}, {"type": "indicator"}],
               [{"type": "indicator"}, {"type": "indicator"}]]
    )
    
    # Active Locations
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=metrics_data.get('locations', 0),
            title={"text": "Active Locations"},
        ),
        row=1, col=1
    )
    
    # Recent Analyses
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=metrics_data.get('analyses', 0),
            title={"text": "Recent Analyses"},
        ),
        row=1, col=2
    )
    
    # Success Rate
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=metrics_data.get('success_rate', 0),
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Success Rate (%)"},
            gauge={'axis': {'range': [None, 100]},
                   'bar': {'color': "darkblue"},
                   'steps': [
                       {'range': [0, 50], 'color': "lightgray"},
                       {'range': [50, 100], 'color': "gray"}],
                   'threshold': {'line': {'color': "red", 'width': 4},
                                'thickness': 0.75, 'value': 90}}
        ),
        row=2, col=1
    )
    
    # System Health
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=metrics_data.get('system_health', 0),
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "System Health (%)"},
            gauge={'axis': {'range': [None, 100]},
                   'bar': {'color': "green"},
                   'steps': [
                       {'range': [0, 50], 'color': "lightgray"},
                       {'range': [50, 100], 'color': "gray"}],
                   'threshold': {'line': {'color': "red", 'width': 4},
                                'thickness': 0.75, 'value': 80}}
        ),
        row=2, col=2
    )
    
    fig.update_layout(height=600)
    
    return fig

def create_genomic_analysis_chart(analysis_data: pd.DataFrame) -> Optional[go.Figure]:
    """Create genomic analysis results chart"""
    if analysis_data.empty:
        return None
    
    fig = px.bar(
        analysis_data,
        x='sample_id',
        y='species_count',
        color='location',
        title='Species Diversity by Sample Location',
        labels={'sample_id': 'Sample ID', 'species_count': 'Number of Species'}
    )
    
    fig.update_layout(
        height=400,
        xaxis_tickangle=-45,
        template='plotly_white'
    )
    
    return fig

def create_environmental_heatmap(env_data: pd.DataFrame) -> Optional[go.Figure]:
    """Create environmental parameters heatmap"""
    if env_data.empty:
        return None
    
    # Pivot data for heatmap
    if 'parameter' in env_data.columns and 'value' in env_data.columns and 'location' in env_data.columns:
        pivot_data = env_data.pivot_table(
            values='value', 
            index='location', 
            columns='parameter', 
            aggfunc='mean'
        )
        
        fig = px.imshow(
            pivot_data,
            title='Environmental Parameters by Location',
            color_continuous_scale='Viridis',
            aspect='auto'
        )
        
        fig.update_layout(height=400)
        return fig
    
    return None

def create_time_series_chart(data: pd.DataFrame, x_col: str, y_col: str, 
                           color_col: str = None, title: str = "Time Series") -> go.Figure:
    """Create generic time series chart"""
    if color_col and color_col in data.columns:
        fig = px.line(data, x=x_col, y=y_col, color=color_col, title=title)
    else:
        fig = px.line(data, x=x_col, y=y_col, title=title)
    
    fig.update_layout(
        height=400,
        template='plotly_white',
        hovermode='x unified'
    )
    
    return fig

def create_bar_chart(data: pd.DataFrame, x_col: str, y_col: str, 
                    color_col: str = None, title: str = "Bar Chart") -> go.Figure:
    """Create bar chart"""
    if color_col and color_col in data.columns:
        fig = px.bar(data, x=x_col, y=y_col, color=color_col, title=title)
    else:
        fig = px.bar(data, x=x_col, y=y_col, title=title)
    
    fig.update_layout(
        height=400,
        template='plotly_white'
    )
    
    return fig

def create_scatter_plot(data: pd.DataFrame, x_col: str, y_col: str,
                       color_col: str = None, size_col: str = None,
                       title: str = "Scatter Plot") -> go.Figure:
    """Create scatter plot"""
    fig = px.scatter(
        data, x=x_col, y=y_col,
        color=color_col if color_col and color_col in data.columns else None,
        size=size_col if size_col and size_col in data.columns else None,
        title=title
    )
    
    fig.update_layout(
        height=400,
        template='plotly_white'
    )
    
    return fig

def create_heatmap(data: pd.DataFrame, title: str = "Heatmap") -> go.Figure:
    """Create correlation heatmap"""
    numeric_data = data.select_dtypes(include=['float64', 'int64'])
    
    if numeric_data.empty:
        # Create empty heatmap
        fig = go.Figure()
        fig.add_annotation(
            text="No numeric data available for heatmap",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font=dict(size=16)
        )
        fig.update_layout(height=400, title=title)
        return fig
    
    correlation_matrix = numeric_data.corr()
    
    fig = px.imshow(
        correlation_matrix,
        title=title,
        color_continuous_scale='RdBu_r',
        aspect='auto'
    )
    
    fig.update_layout(height=400)
    
    return fig

def create_sample_chart(sample_size: int = 10) -> go.Figure:
    """Create a sample chart with dummy data for testing"""
    # Generate sample data
    dates = pd.date_range('2024-01-01', periods=sample_size, freq='D')
    data = {
        'date': dates,
        'temperature': np.random.normal(20, 5, sample_size),
        'humidity': np.random.normal(60, 10, sample_size),
        'location': np.random.choice(['Location A', 'Location B', 'Location C'], sample_size)
    }
    df = pd.DataFrame(data)
    
    fig = px.line(
        df,
        x='date',
        y='temperature',
        color='location',
        title='Sample Environmental Data',
        labels={'date': 'Date', 'temperature': 'Temperature (°C)'}
    )
    
    fig.update_layout(
        height=400,
        template='plotly_white'
    )
    
    return fig