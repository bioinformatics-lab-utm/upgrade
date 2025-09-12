# app.py
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import psycopg2
import os
from psycopg2.extras import RealDictCursor

# Конфигурация страницы
st.set_page_config(
    page_title="UPGRADE - Environmental Genomic Surveillance",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database connection
@st.cache_resource
def init_db_connection():
    """Инициализация подключения к базе данных"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            database=os.getenv('POSTGRES_DB', 'upgrade_db'),
            user=os.getenv('POSTGRES_USER', 'upgrade'),
            password=os.getenv('POSTGRES_PASSWORD', 'upgrade123')
        )
        return conn
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return None

@st.cache_data(ttl=300)  # Кеш на 5 минут
def fetch_locations():
    """Получение списка локаций из базы данных"""
    conn = init_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = """
        SELECT location_id, city, country, location_name, 
               latitude, longitude, timezone, 
               campus_area, traffic_density, indoor_outdoor,
               created_at
        FROM locations 
        WHERE is_active = true
        ORDER BY country, city
        """
        return pd.read_sql(query, conn)
    except Exception as e:
        st.error(f"Error fetching locations: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_weather_data():
    """Получение погодных данных из базы данных"""
    conn = init_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = """
        SELECT w.weather_id, w.measurement_datetime, w.temperature, 
               w.humidity, w.apparent_temperature, w.rainfall, 
               w.windspeed, w.wind_direction, w.pressure_msl,
               w.surface_pressure, w.cloud_cover, w.uv_index,
               w.weather_code, w.is_day, w.quality_score,
               l.city, l.country, l.latitude, l.longitude,
               l.location_name
        FROM weather_measurements w
        JOIN locations l ON w.location_id = l.location_id
        WHERE w.measurement_datetime >= NOW() - INTERVAL '24 hours'
        ORDER BY w.measurement_datetime DESC
        """
        return pd.read_sql(query, conn)
    except Exception as e:
        st.error(f"Error fetching weather data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_weather_stats():
    """Получение статистики погодных измерений"""
    conn = init_db_connection()
    if not conn:
        return {}
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Общая статистика
            cur.execute("""
                SELECT 
                    COUNT(*) as total_measurements,
                    COUNT(DISTINCT location_id) as locations_count,
                    MAX(measurement_datetime) as last_measurement,
                    MIN(measurement_datetime) as first_measurement
                FROM weather_measurements
            """)
            stats = dict(cur.fetchone())
            
            # Статистика за последние 24 часа
            cur.execute("""
                SELECT 
                    COUNT(*) as recent_measurements,
                    AVG(temperature) as avg_temp,
                    AVG(humidity) as avg_humidity,
                    AVG(windspeed) as avg_wind
                FROM weather_measurements 
                WHERE measurement_datetime >= NOW() - INTERVAL '24 hours'
            """)
            recent_stats = dict(cur.fetchone())
            
            return {**stats, **recent_stats}
    except Exception as e:
        st.error(f"Error fetching stats: {e}")
        return {}

def create_weather_map(weather_df):
    """Создание карты с погодными данными"""
    if weather_df.empty:
        return None
    
    # Берем последние данные для каждого города
    latest_weather = weather_df.groupby('city').last().reset_index()
    
    center_lat = latest_weather['latitude'].mean()
    center_lon = latest_weather['longitude'].mean()
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles='OpenStreetMap'
    )
    
    # Цветовая схема по температуре
    if len(latest_weather) > 1:
        min_temp = latest_weather['temperature'].min()
        max_temp = latest_weather['temperature'].max()
    else:
        min_temp = max_temp = latest_weather['temperature'].iloc[0] if len(latest_weather) > 0 else 0
    
    for _, row in latest_weather.iterrows():
        if pd.isna(row['temperature']):
            continue
            
        # Нормализация температуры для цвета
        if max_temp > min_temp:
            temp_norm = (row['temperature'] - min_temp) / (max_temp - min_temp)
        else:
            temp_norm = 0.5
        
        # Цвет от синего (холодно) к красному (жарко)
        color = f'#{int(255*temp_norm):02x}{int(100):02x}{int(255*(1-temp_norm)):02x}'
        
        popup_html = f"""
        <div style="width: 220px;">
            <h4>{row['city']}, {row['country']}</h4>
            <p><strong>Temperature:</strong> {row['temperature']:.1f}°C</p>
            <p><strong>Humidity:</strong> {row['humidity']:.1f}%</p>
            <p><strong>Wind Speed:</strong> {row['windspeed']:.1f} m/s</p>
            <p><strong>Pressure:</strong> {row['pressure_msl']:.1f} hPa</p>
            <p><strong>Cloud Cover:</strong> {row['cloud_cover']:.0f}%</p>
            <p><strong>Last Update:</strong> {row['measurement_datetime']}</p>
        </div>
        """
        
        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=12,
            popup=folium.Popup(popup_html, max_width=250),
            color='white',
            weight=2,
            fillColor=color,
            fillOpacity=0.8,
            tooltip=f"{row['city']}: {row['temperature']:.1f}°C"
        ).add_to(m)
    
    return m

def weather_trends_chart(weather_df):
    """График трендов температуры по времени"""
    if weather_df.empty:
        return None
    
    fig = px.line(
        weather_df, 
        x='measurement_datetime', 
        y='temperature', 
        color='city',
        title='Temperature Trends (Last 24 Hours)',
        labels={'measurement_datetime': 'Time', 'temperature': 'Temperature (°C)'}
    )
    
    fig.update_layout(
        height=400,
        xaxis_title="Time",
        yaxis_title="Temperature (°C)",
        legend_title="City"
    )
    
    return fig

def weather_comparison_chart(weather_df):
    """Сравнительный график погодных параметров"""
    if weather_df.empty:
        return None
    
    # Берем последние данные для каждого города
    latest_weather = weather_df.groupby('city').last().reset_index()
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=latest_weather['city'],
        y=latest_weather['temperature'],
        mode='markers+lines',
        name='Temperature (°C)',
        yaxis='y',
        line=dict(color='red')
    ))
    
    fig.add_trace(go.Scatter(
        x=latest_weather['city'],
        y=latest_weather['humidity'],
        mode='markers+lines',
        name='Humidity (%)',
        yaxis='y2',
        line=dict(color='blue')
    ))
    
    fig.update_layout(
        title='Current Weather Comparison Across Cities',
        xaxis_title='City',
        yaxis=dict(title='Temperature (°C)', side='left', color='red'),
        yaxis2=dict(title='Humidity (%)', side='right', overlaying='y', color='blue'),
        height=400,
        legend=dict(x=0.7, y=1)
    )
    
    return fig

def dashboard_page():
    """Главная dashboard страница"""
    st.header("Environmental Genomic Surveillance Dashboard")
    
    # Загрузка данных
    with st.spinner("Loading data..."):
        locations_df = fetch_locations()
        weather_df = fetch_weather_data()
        stats = get_weather_stats()
    
    # Основные метрики
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_locations = len(locations_df)
        st.metric("Monitoring Locations", total_locations)
    
    with col2:
        total_measurements = stats.get('total_measurements', 0)
        st.metric("Total Weather Records", total_measurements)
    
    with col3:
        recent_measurements = stats.get('recent_measurements', 0)
        st.metric("Recent Measurements (24h)", recent_measurements)
    
    with col4:
        avg_temp = stats.get('avg_temp', 0)
        if avg_temp:
            st.metric("Average Temperature", f"{avg_temp:.1f}°C")
        else:
            st.metric("Average Temperature", "No data")
    
    st.markdown("---")
    
    # Карта и графики
    if not weather_df.empty:
        st.subheader("Real-time Weather Monitoring")
        
        # Карта
        weather_map = create_weather_map(weather_df)
        if weather_map:
            folium_static(weather_map, width=1200, height=500)
        
        st.markdown("---")
        
        # Графики
        col1, col2 = st.columns(2)
        
        with col1:
            trends_fig = weather_trends_chart(weather_df)
            if trends_fig:
                st.plotly_chart(trends_fig, use_container_width=True)
        
        with col2:
            comparison_fig = weather_comparison_chart(weather_df)
            if comparison_fig:
                st.plotly_chart(comparison_fig, use_container_width=True)
        
    else:
        st.info("No weather data available. Check if the weather producer is running.")

def locations_page():
    """Страница управления локациями"""
    st.header("Monitoring Locations")
    
    locations_df = fetch_locations()
    
    if not locations_df.empty:
        st.subheader(f"Total Locations: {len(locations_df)}")
        
        # Фильтры
        col1, col2 = st.columns(2)
        with col1:
            countries = ['All'] + list(locations_df['country'].unique())
            selected_country = st.selectbox("Filter by Country", countries)
        
        with col2:
            areas = ['All'] + list(locations_df['campus_area'].unique())
            selected_area = st.selectbox("Filter by Area", areas)
        
        # Применение фильтров
        filtered_df = locations_df.copy()
        if selected_country != 'All':
            filtered_df = filtered_df[filtered_df['country'] == selected_country]
        if selected_area != 'All':
            filtered_df = filtered_df[filtered_df['campus_area'] == selected_area]
        
        # Таблица локаций
        st.dataframe(
            filtered_df[['city', 'country', 'location_name', 'latitude', 
                        'longitude', 'campus_area', 'traffic_density', 'created_at']],
            use_container_width=True
        )
        
        # Статистика по странам
        country_stats = locations_df['country'].value_counts()
        fig_countries = px.pie(
            values=country_stats.values,
            names=country_stats.index,
            title='Locations by Country'
        )
        st.plotly_chart(fig_countries, use_container_width=True)
        
    else:
        st.info("No locations found in database.")

def weather_details_page():
    """Детальная страница погодных данных"""
    st.header("Weather Data Details")
    
    weather_df = fetch_weather_data()
    
    if not weather_df.empty:
        # Фильтры
        col1, col2 = st.columns(2)
        with col1:
            cities = ['All'] + list(weather_df['city'].unique())
            selected_city = st.selectbox("Select City", cities)
        
        with col2:
            hours_back = st.selectbox("Time Range", [6, 12, 24], index=2)
        
        # Применение фильтров
        filtered_df = weather_df.copy()
        if selected_city != 'All':
            filtered_df = filtered_df[filtered_df['city'] == selected_city]
        
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        filtered_df = filtered_df[filtered_df['measurement_datetime'] >= cutoff_time]
        
        if not filtered_df.empty:
            # Детальная таблица
            st.subheader("Recent Measurements")
            st.dataframe(
                filtered_df[['city', 'country', 'measurement_datetime', 'temperature', 
                           'humidity', 'windspeed', 'pressure_msl', 'quality_score']].head(20),
                use_container_width=True
            )
            
            # Детальные графики
            if len(filtered_df) > 1:
                st.subheader("Detailed Charts")
                
                # График множественных параметров
                fig_multi = go.Figure()
                
                fig_multi.add_trace(go.Scatter(
                    x=filtered_df['measurement_datetime'],
                    y=filtered_df['temperature'],
                    name='Temperature (°C)',
                    line=dict(color='red')
                ))
                
                fig_multi.add_trace(go.Scatter(
                    x=filtered_df['measurement_datetime'],
                    y=filtered_df['humidity'],
                    name='Humidity (%)',
                    yaxis='y2',
                    line=dict(color='blue')
                ))
                
                fig_multi.update_layout(
                    title=f'Weather Parameters - {selected_city if selected_city != "All" else "All Cities"}',
                    xaxis_title='Time',
                    yaxis=dict(title='Temperature (°C)', color='red'),
                    yaxis2=dict(title='Humidity (%)', overlaying='y', side='right', color='blue'),
                    height=500
                )
                
                st.plotly_chart(fig_multi, use_container_width=True)
        else:
            st.info("No data available for selected filters.")
    else:
        st.info("No weather data available.")

def main():
    """Главная функция приложения"""
    st.title("UPGRADE - Environmental Genomic Surveillance Platform")
    st.markdown("Real-time monitoring of environmental conditions across Romania and Moldova")
    
    # Боковое меню
    st.sidebar.title("Navigation")
    
    page = st.sidebar.selectbox(
        "Choose page",
        ["Dashboard", "Locations", "Weather Details", "System Status"]
    )
    
    # Информация о системе
    st.sidebar.markdown("---")
    st.sidebar.info(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
    
    if st.sidebar.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    
    # Роутинг страниц
    if page == "Dashboard":
        dashboard_page()
    elif page == "Locations":
        locations_page()
    elif page == "Weather Details":
        weather_details_page()
    elif page == "System Status":
        st.header("System Status")
        
        # Проверка подключений
        conn = init_db_connection()
        if conn:
            st.success("✅ Database connection: OK")
            
            # Статистика системы
            stats = get_weather_stats()
            if stats:
                st.subheader("System Statistics")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.metric("Total Measurements", stats.get('total_measurements', 0))
                    st.metric("Active Locations", stats.get('locations_count', 0))
                
                with col2:
                    if stats.get('last_measurement'):
                        st.metric("Last Measurement", stats['last_measurement'].strftime('%Y-%m-%d %H:%M'))
                    if stats.get('first_measurement'):
                        st.metric("First Measurement", stats['first_measurement'].strftime('%Y-%m-%d %H:%M'))
        else:
            st.error("❌ Database connection: Failed")

if __name__ == "__main__":
    main()