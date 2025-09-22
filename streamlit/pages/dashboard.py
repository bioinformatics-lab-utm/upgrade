# pages/dashboard.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from components.header import create_header
from components.cards import create_metrics_row
from components.charts import create_weather_map
from database.queries import fetch_locations, fetch_weather_data, get_pipeline_runs_from_db
from config.settings import THEME_CONFIG

def dashboard_page():
    """Main dashboard page"""
    
    # Enhanced header
    create_header(
        title="Environmental Genomic Surveillance Dashboard",
        subtitle="UPGRADE Project",
        description="Monitoring antimicrobial resistance and pathogens in urban environments"
    )
    
    with st.spinner("Loading dashboard data..."):
        locations_df = fetch_locations()
        weather_df = fetch_weather_data()
        pipeline_runs_df = get_pipeline_runs_from_db()
    
    # Key Performance Indicators
    st.markdown("### Key Performance Indicators")
    
    metrics = [
        {
            'label': 'Active Locations',
            'value': str(len(locations_df) if not locations_df.empty else 0),
            'icon': '🌍',
            'color': THEME_CONFIG['success_color']
        },
        {
            'label': 'Weather Updates (24h)', 
            'value': str(len(weather_df[weather_df['measurement_datetime'] >= datetime.now() - timedelta(hours=24)]) if not weather_df.empty else 0),
            'icon': '🌡️',
            'color': THEME_CONFIG['info_color']
        },
        {
            'label': 'Recent Analyses (7d)',
            'value': str(len(pipeline_runs_df[pipeline_runs_df['start_time'] >= datetime.now() - timedelta(days=7)]) if not pipeline_runs_df.empty else 0),
            'icon': '🧬',
            'color': '#6f42c1'
        },
        {
            'label': 'Success Rate',
            'value': f"{(len(pipeline_runs_df[pipeline_runs_df['status'] == 'completed']) / len(pipeline_runs_df) * 100):.1f}%" if not pipeline_runs_df.empty else "0%",
            'icon': '✅',
            'color': THEME_CONFIG['success_color']
        }
    ]
    
    create_metrics_row(metrics)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Environmental Monitoring Map
    st.markdown("### 🗺️ Environmental Monitoring Locations")
    
    if not weather_df.empty:
        weather_map = create_weather_map(weather_df)
        if weather_map:
            st.components.v1.html(weather_map._repr_html_(), width=1200, height=450)
        else:
            st.warning("No weather data available for map display")
    else:
        st.info("No weather data available. Connect weather monitoring stations to see real-time environmental data.")
    
    # Recent Activity Section
    st.markdown("### 📊 Recent Activity")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**🌡️ Latest Weather Measurements**")
        if not weather_df.empty:
            recent_weather = weather_df.head(10)[['city', 'country', 'temperature', 'humidity', 'measurement_datetime']].copy()
            recent_weather.columns = ['City', 'Country', 'Temperature (°C)', 'Humidity (%)', 'Last Update']
            recent_weather['Last Update'] = recent_weather['Last Update'].dt.strftime('%Y-%m-%d %H:%M')
            st.dataframe(recent_weather, use_container_width=True, hide_index=True)
        else:
            st.info("No recent weather data available")
    
    with col2:
        st.markdown("**🧬 Recent Pipeline Runs**")
        if not pipeline_runs_df.empty:
            recent_pipelines = pipeline_runs_df.head(10)[['sample_id', 'status', 'sample_type', 'start_time']].copy()
            recent_pipelines.columns = ['Sample ID', 'Status', 'Type', 'Started']
            recent_pipelines['Started'] = pd.to_datetime(recent_pipelines['Started']).dt.strftime('%Y-%m-%d %H:%M')
            
            def style_status(val):
                if val == 'completed':
                    return 'background-color: #d4edda; color: #155724'
                elif val == 'running':
                    return 'background-color: #d1ecf1; color: #0c5460'
                elif val == 'failed':
                    return 'background-color: #f8d7da; color: #721c24'
                else:
                    return 'background-color: #fff3cd; color: #856404'
            
            styled_df = recent_pipelines.style.applymap(style_status, subset=['Status'])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info("No recent pipeline runs")
    
    # Environmental Trends
    if not weather_df.empty and len(weather_df) > 1:
        st.markdown("### 📈 Environmental Trends")
        
        import plotly.express as px
        
        tab1, tab2 = st.tabs(["🌡️ Temperature Trends", "💧 Humidity Trends"])
        
        with tab1:
            fig_temp = px.line(
                weather_df.sort_values('measurement_datetime').tail(100),
                x='measurement_datetime',
                y='temperature',
                color='city',
                title='Temperature Trends by Location (Last 100 Measurements)',
                labels={'measurement_datetime': 'Time', 'temperature': 'Temperature (°C)'},
                template='plotly_white'
            )
            fig_temp.update_layout(
                height=400,
                hovermode='x unified',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_temp, use_container_width=True)
        
        with tab2:
            fig_humidity = px.line(
                weather_df.sort_values('measurement_datetime').tail(100),
                x='measurement_datetime',
                y='humidity',
                color='city',
                title='Humidity Trends by Location (Last 100 Measurements)',
                labels={'measurement_datetime': 'Time', 'humidity': 'Humidity (%)'},
                template='plotly_white'
            )
            fig_humidity.update_layout(
                height=400,
                hovermode='x unified',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_humidity, use_container_width=True)