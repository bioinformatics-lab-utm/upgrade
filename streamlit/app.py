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

def get_db_config():
    """Получить конфигурацию базы данных"""
    return {
        'host': os.getenv('POSTGRES_HOST', 'postgres'),
        'database': os.getenv('POSTGRES_DB', 'upgrade_db'),
        'user': os.getenv('POSTGRES_USER', 'upgrade'),
        'password': os.getenv('POSTGRES_PASSWORD', 'upgrade123')
    }

def create_db_connection():
    """Создать новое подключение к базе данных"""
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config)
        return conn
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return None

def test_db_connection():
    """Тестировать подключение к базе данных"""
    conn = create_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False
        finally:
            conn.close()
    return False

@st.cache_data(ttl=300)
def fetch_locations():
    """Получение списка локаций из базы данных"""
    conn = create_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = """
        SELECT location_id, 
               COALESCE(city, 'Unknown') as city, 
               COALESCE(country, 'Unknown') as country, 
               COALESCE(location_name, city, 'Unknown') as location_name, 
               latitude, longitude, timezone, 
               COALESCE(campus_area, 'Unknown') as campus_area, 
               COALESCE(traffic_density, 'Unknown') as traffic_density, 
               COALESCE(indoor_outdoor, 'Unknown') as indoor_outdoor,
               created_at
        FROM locations 
        WHERE is_active = true
          AND latitude IS NOT NULL 
          AND longitude IS NOT NULL
        ORDER BY country, city
        """
        df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        st.error(f"Error fetching locations: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

@st.cache_data(ttl=300)
def fetch_weather_data():
    """Получение погодных данных из базы данных"""
    conn = create_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = """
        SELECT w.weather_id, w.measurement_datetime AT TIME ZONE 'UTC' as measurement_datetime, 
               COALESCE(w.temperature, 0) as temperature, 
               COALESCE(w.humidity, 0) as humidity, 
               COALESCE(w.apparent_temperature, w.temperature, 0) as apparent_temperature, 
               COALESCE(w.rainfall, 0) as rainfall, 
               COALESCE(w.windspeed, 0) as windspeed, 
               COALESCE(w.wind_direction, 0) as wind_direction, 
               COALESCE(w.pressure_msl, 1013.25) as pressure_msl,
               COALESCE(w.surface_pressure, w.pressure_msl, 1013.25) as surface_pressure, 
               COALESCE(w.cloud_cover, 0) as cloud_cover, 
               COALESCE(w.uv_index, 0) as uv_index,
               COALESCE(w.weather_code, 0) as weather_code, 
               COALESCE(w.is_day, true) as is_day, 
               COALESCE(w.quality_score, 1.0) as quality_score,
               COALESCE(l.city, 'Unknown') as city, 
               COALESCE(l.country, 'Unknown') as country, 
               l.latitude, l.longitude,
               COALESCE(l.location_name, l.city, 'Unknown') as location_name
        FROM weather_measurements w
        JOIN locations l ON w.location_id = l.location_id
        WHERE w.measurement_datetime >= NOW() - INTERVAL '24 hours'
          AND l.latitude IS NOT NULL 
          AND l.longitude IS NOT NULL
        ORDER BY w.measurement_datetime DESC
        """
        
        df = pd.read_sql(query, conn)
        
        if not df.empty:
            # Приводим datetime к UTC без timezone info для унифицированного сравнения
            df['measurement_datetime'] = pd.to_datetime(df['measurement_datetime'])
            if df['measurement_datetime'].dt.tz is not None:
                df['measurement_datetime'] = df['measurement_datetime'].dt.tz_localize(None)
            
            # Валидация числовых колонок
            numeric_columns = ['temperature', 'humidity', 'windspeed', 'pressure_msl', 'cloud_cover', 'uv_index']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        return df
        
    except Exception as e:
        st.error(f"Error fetching weather data: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

@st.cache_data(ttl=600)
def get_weather_stats():
    """Получение статистики погодных измерений"""
    conn = create_db_connection()
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
            stats_row = cur.fetchone()
            stats = dict(stats_row) if stats_row else {}
            
            # Статистика за последние 24 часа
            cur.execute("""
                SELECT 
                    COUNT(*) as recent_measurements,
                    AVG(CASE WHEN temperature BETWEEN -50 AND 60 THEN temperature END) as avg_temp,
                    AVG(CASE WHEN humidity BETWEEN 0 AND 100 THEN humidity END) as avg_humidity,
                    AVG(CASE WHEN windspeed BETWEEN 0 AND 200 THEN windspeed END) as avg_wind
                FROM weather_measurements 
                WHERE measurement_datetime >= NOW() - INTERVAL '24 hours'
            """)
            recent_row = cur.fetchone()
            recent_stats = dict(recent_row) if recent_row else {}
            
            return {**stats, **recent_stats}
            
    except Exception as e:
        st.error(f"Error fetching stats: {e}")
        return {}
    finally:
        conn.close()

def safe_format_value(value, format_string="{:.1f}", default="N/A"):
    """Безопасное форматирование значений"""
    try:
        if value is None or pd.isna(value):
            return default
        return format_string.format(float(value))
    except (ValueError, TypeError):
        return default

def create_weather_map(weather_df):
    """Создание карты с погодными данными"""
    if weather_df.empty:
        return None
    
    # Берем последние данные для каждого города
    latest_weather = weather_df.groupby('city').last().reset_index()
    latest_weather = latest_weather.dropna(subset=['latitude', 'longitude'])
    
    if latest_weather.empty:
        return None
    
    center_lat = latest_weather['latitude'].mean()
    center_lon = latest_weather['longitude'].mean()
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles='OpenStreetMap'
    )
    
    # Цветовая схема по температуре
    temp_values = latest_weather['temperature'].dropna()
    temp_values = temp_values[(temp_values >= -50) & (temp_values <= 60)]  # Разумные пределы
    
    if len(temp_values) > 1:
        min_temp = temp_values.min()
        max_temp = temp_values.max()
    elif len(temp_values) == 1:
        min_temp = max_temp = temp_values.iloc[0]
    else:
        min_temp, max_temp = 10, 25  # Значения по умолчанию
    
    for _, row in latest_weather.iterrows():
        # Валидация координат
        lat, lon = row['latitude'], row['longitude']
        if pd.isna(lat) or pd.isna(lon) or lat < -90 or lat > 90 or lon < -180 or lon > 180:
            continue
            
        # Безопасное получение значений
        temperature = safe_format_value(row['temperature'], "{:.1f}", "N/A")
        humidity = safe_format_value(row['humidity'], "{:.1f}", "N/A")
        windspeed = safe_format_value(row['windspeed'], "{:.1f}", "N/A")
        pressure_msl = safe_format_value(row['pressure_msl'], "{:.1f}", "N/A")
        cloud_cover = safe_format_value(row['cloud_cover'], "{:.0f}", "N/A")
        
        city = str(row['city']) if row['city'] is not None else 'Unknown'
        country = str(row['country']) if row['country'] is not None else 'Unknown'
        
        # Цвет маркера
        temp_val = row['temperature']
        if pd.notna(temp_val) and max_temp > min_temp:
            temp_norm = max(0, min(1, (temp_val - min_temp) / (max_temp - min_temp)))
            red_component = int(255 * temp_norm)
            blue_component = int(255 * (1 - temp_norm))
            color = f'#{red_component:02x}64{blue_component:02x}'
        else:
            color = '#6464FF'  # Синий по умолчанию
        
        # Форматирование времени
        measurement_time = row['measurement_datetime']
        try:
            if pd.notna(measurement_time):
                time_str = measurement_time.strftime('%Y-%m-%d %H:%M')
            else:
                time_str = 'No data'
        except (AttributeError, ValueError):
            time_str = 'No data'
        
        popup_html = f"""
        <div style="width: 220px;">
            <h4>{city}, {country}</h4>
            <p><strong>Temperature:</strong> {temperature}°C</p>
            <p><strong>Humidity:</strong> {humidity}%</p>
            <p><strong>Wind Speed:</strong> {windspeed} m/s</p>
            <p><strong>Pressure:</strong> {pressure_msl} hPa</p>
            <p><strong>Cloud Cover:</strong> {cloud_cover}%</p>
            <p><strong>Last Update:</strong> {time_str}</p>
        </div>
        """
        
        folium.CircleMarker(
            location=[float(lat), float(lon)],
            radius=12,
            popup=folium.Popup(popup_html, max_width=250),
            color='white',
            weight=2,
            fillColor=color,
            fillOpacity=0.8,
            tooltip=f"{city}: {temperature}°C"
        ).add_to(m)
    
    return m

def weather_trends_chart(weather_df):
    """График трендов температуры по времени"""
    if weather_df.empty:
        return None
    
    # Фильтрация данных
    clean_df = weather_df.copy()
    clean_df = clean_df.dropna(subset=['temperature', 'measurement_datetime'])
    clean_df = clean_df[(clean_df['temperature'] >= -50) & (clean_df['temperature'] <= 60)]
    
    if clean_df.empty:
        return None
    
    try:
        fig = px.line(
            clean_df, 
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
    except Exception as e:
        st.error(f"Error creating temperature trends chart: {e}")
        return None

def weather_comparison_chart(weather_df):
    """Сравнительный график погодных параметров"""
    if weather_df.empty:
        return None
    
    latest_weather = weather_df.groupby('city').last().reset_index()
    latest_weather = latest_weather.dropna(subset=['temperature', 'humidity'])
    latest_weather = latest_weather[
        (latest_weather['temperature'] >= -50) & (latest_weather['temperature'] <= 60) &
        (latest_weather['humidity'] >= 0) & (latest_weather['humidity'] <= 100)
    ]
    
    if latest_weather.empty:
        return None
    
    try:
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=latest_weather['city'],
            y=latest_weather['temperature'],
            mode='markers+lines',
            name='Temperature (°C)',
            yaxis='y',
            line=dict(color='red'),
            marker=dict(size=8)
        ))
        
        fig.add_trace(go.Scatter(
            x=latest_weather['city'],
            y=latest_weather['humidity'],
            mode='markers+lines',
            name='Humidity (%)',
            yaxis='y2',
            line=dict(color='blue'),
            marker=dict(size=8)
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
    except Exception as e:
        st.error(f"Error creating weather comparison chart: {e}")
        return None

def dashboard_page():
    """Главная dashboard страница"""
    st.header("Environmental Genomic Surveillance Dashboard")
    
    with st.spinner("Loading data..."):
        locations_df = fetch_locations()
        weather_df = fetch_weather_data()
        stats = get_weather_stats()
    
    # Основные метрики
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Monitoring Locations", len(locations_df))
    
    with col2:
        total_measurements = stats.get('total_measurements', 0)
        st.metric("Total Weather Records", f"{total_measurements:,}" if total_measurements else "0")
    
    with col3:
        recent_measurements = stats.get('recent_measurements', 0)
        st.metric("Recent Measurements (24h)", recent_measurements if recent_measurements else "0")
    
    with col4:
        avg_temp = stats.get('avg_temp')
        if avg_temp is not None and -50 <= avg_temp <= 60:
            st.metric("Average Temperature", f"{avg_temp:.1f}°C")
        else:
            st.metric("Average Temperature", "No data")
    
    st.markdown("---")
    
    if not weather_df.empty:
        st.subheader("Real-time Weather Monitoring")
        
        try:
            weather_map = create_weather_map(weather_df)
            if weather_map:
                folium_static(weather_map, width=1200, height=500)
            else:
                st.warning("Unable to create weather map - insufficient location data")
        except Exception as e:
            st.error(f"Error creating weather map: {e}")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            try:
                trends_fig = weather_trends_chart(weather_df)
                if trends_fig:
                    st.plotly_chart(trends_fig, use_container_width=True)
                else:
                    st.info("No temperature trend data available")
            except Exception as e:
                st.error(f"Error creating temperature chart: {e}")
        
        with col2:
            try:
                comparison_fig = weather_comparison_chart(weather_df)
                if comparison_fig:
                    st.plotly_chart(comparison_fig, use_container_width=True)
                else:
                    st.info("No weather comparison data available")
            except Exception as e:
                st.error(f"Error creating comparison chart: {e}")
    else:
        st.info("No weather data available. Check if the weather producer is running.")

def locations_page():
    """Страница управления локациями"""
    st.header("Monitoring Locations")
    
    locations_df = fetch_locations()
    
    if not locations_df.empty:
        st.subheader(f"Total Locations: {len(locations_df)}")
        
        col1, col2 = st.columns(2)
        with col1:
            countries = ['All'] + sorted(locations_df['country'].unique().tolist())
            selected_country = st.selectbox("Filter by Country", countries)
        
        with col2:
            areas = ['All'] + sorted(locations_df['campus_area'].unique().tolist())
            selected_area = st.selectbox("Filter by Area", areas)
        
        filtered_df = locations_df.copy()
        if selected_country != 'All':
            filtered_df = filtered_df[filtered_df['country'] == selected_country]
        if selected_area != 'All':
            filtered_df = filtered_df[filtered_df['campus_area'] == selected_area]
        
        st.dataframe(
            filtered_df[['city', 'country', 'location_name', 'latitude', 
                        'longitude', 'campus_area', 'traffic_density', 'created_at']],
            use_container_width=True
        )
        
        if len(locations_df) > 0:
            country_stats = locations_df['country'].value_counts()
            try:
                fig_countries = px.pie(
                    values=country_stats.values,
                    names=country_stats.index,
                    title='Locations by Country'
                )
                st.plotly_chart(fig_countries, use_container_width=True)
            except Exception as e:
                st.error(f"Error creating locations chart: {e}")
    else:
        st.info("No locations found in database.")

def weather_details_page():
    """Детальная страница погодных данных"""
    st.header("Weather Data Details")
    
    weather_df = fetch_weather_data()
    
    if not weather_df.empty:
        col1, col2 = st.columns(2)
        with col1:
            cities = ['All'] + sorted(weather_df['city'].unique().tolist())
            selected_city = st.selectbox("Select City", cities)
        
        with col2:
            hours_back = st.selectbox("Time Range", [6, 12, 24], index=2)
        
        filtered_df = weather_df.copy()
        if selected_city != 'All':
            filtered_df = filtered_df[filtered_df['city'] == selected_city]
        
        # Исправленное сравнение datetime
        if not filtered_df.empty:
            try:
                # Получаем текущее время
                now = pd.Timestamp.now()
                
                # Проверяем timezone у measurement_datetime
                if filtered_df['measurement_datetime'].dt.tz is not None:
                    # Если колонка имеет timezone, приводим now к тому же timezone
                    cutoff_time = now.tz_localize('UTC') - pd.Timedelta(hours=hours_back)
                else:
                    # Если колонка naive, используем naive datetime
                    cutoff_time = now - pd.Timedelta(hours=hours_back)
                
                filtered_df = filtered_df[filtered_df['measurement_datetime'] >= cutoff_time]
                
            except Exception as e:
                st.warning(f"Error filtering by time: {e}. Showing all available data.")
        
        if not filtered_df.empty:
            st.subheader("Recent Measurements")
            display_df = filtered_df[['city', 'country', 'measurement_datetime', 'temperature', 
                       'humidity', 'windspeed', 'pressure_msl', 'quality_score']].head(20)
            st.dataframe(display_df, use_container_width=True)
            
            if len(filtered_df) > 1:
                st.subheader("Detailed Charts")
                
                try:
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
                except Exception as e:
                    st.error(f"Error creating detailed charts: {e}")
        else:
            st.info("No data available for selected filters.")
    else:
        st.info("No weather data available.")

def system_status_page():
    """Страница системного статуса"""
    st.header("System Status")
    
    # Проверка подключения
    if test_db_connection():
        st.success("Database connection: OK")
        
        # Получение статистики
        conn = create_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_measurements,
                            COUNT(DISTINCT location_id) as locations_count,
                            MAX(measurement_datetime) as last_measurement,
                            MIN(measurement_datetime) as first_measurement
                        FROM weather_measurements
                    """)
                    stats_row = cur.fetchone()
                    
                    if stats_row:
                        stats = dict(stats_row)
                        st.subheader("System Statistics")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.metric("Total Measurements", stats.get('total_measurements', 0))
                            st.metric("Active Locations", stats.get('locations_count', 0))
                        
                        with col2:
                            last_measure = stats.get('last_measurement')
                            if last_measure:
                                try:
                                    if hasattr(last_measure, 'strftime'):
                                        st.metric("Last Measurement", last_measure.strftime('%Y-%m-%d %H:%M'))
                                    else:
                                        st.metric("Last Measurement", str(last_measure))
                                except Exception:
                                    st.metric("Last Measurement", "Invalid date")
                            
                            first_measure = stats.get('first_measurement')
                            if first_measure:
                                try:
                                    if hasattr(first_measure, 'strftime'):
                                        st.metric("First Measurement", first_measure.strftime('%Y-%m-%d %H:%M'))
                                    else:
                                        st.metric("First Measurement", str(first_measure))
                                except Exception:
                                    st.metric("First Measurement", "Invalid date")
                    else:
                        st.info("No statistics available")
                        
            except Exception as e:
                st.error(f"Error fetching system statistics: {e}")
            finally:
                conn.close()
    else:
        st.error("Database connection: Failed")

def main():
    """Главная функция приложения"""
    st.title("UPGRADE - Environmental Genomic Surveillance Platform")
    st.markdown("Real-time monitoring of environmental conditions across Romania and Moldova")
    
    st.sidebar.title("Navigation")
    
    page = st.sidebar.selectbox(
        "Choose page",
        ["Dashboard", "Locations", "Weather Details", "System Status"]
    )
    
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
        system_status_page()

if __name__ == "__main__":
    main()