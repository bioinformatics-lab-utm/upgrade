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
import hashlib
import uuid
from pathlib import Path
import minio
from minio.error import S3Error

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

def get_minio_client():
    """Создать клиент MinIO для хранения файлов"""
    try:
        client = minio.Minio(
            endpoint=os.getenv('MINIO_ENDPOINT', 'minio:9000'),
            access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
            secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
            secure=False
        )
        return client
    except Exception as e:
        st.error(f"MinIO connection error: {e}")
        return None

def validate_genomic_file(uploaded_file):
    """Валидация загружаемых геномных файлов"""
    allowed_extensions = ['.fastq', '.fastq.gz', '.fq', '.fq.gz', '.fasta', '.fa', '.bam', '.sam', '.vcf', '.vcf.gz']
    max_size_mb = 500  # Максимальный размер файла 500MB
    
    errors = []
    
    # Проверка расширения файла
    file_extension = Path(uploaded_file.name).suffix.lower()
    if file_extension not in allowed_extensions:
        errors.append(f"Неподдерживаемый тип файла: {file_extension}")
    
    # Проверка размера файла
    if uploaded_file.size > max_size_mb * 1024 * 1024:
        errors.append(f"Файл слишком большой: {uploaded_file.size / (1024*1024):.1f}MB (максимум {max_size_mb}MB)")
    
    # Базовая проверка содержимого для FASTQ файлов
    if file_extension in ['.fastq', '.fq'] and uploaded_file.size < 1024 * 1024:  # Проверяем только маленькие файлы
        try:
            content = uploaded_file.read(1000).decode('utf-8')
            uploaded_file.seek(0)  # Возвращаем указатель в начало
            
            if not content.startswith('@'):
                errors.append("Файл не является корректным FASTQ файлом")
        except UnicodeDecodeError:
            # Возможно, сжатый файл, пропускаем проверку содержимого
            uploaded_file.seek(0)
    
    return errors

def save_file_to_minio(uploaded_file, bucket_name='genomic-data'):
    """Сохранить файл в MinIO"""
    client = get_minio_client()
    if not client:
        return None, "MinIO client not available"
    
    try:
        # Создаем bucket если не существует
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
        
        # Генерируем уникальное имя файла
        file_extension = Path(uploaded_file.name).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        object_name = f"uploads/{datetime.now().strftime('%Y/%m/%d')}/{unique_filename}"
        
        # Сохраняем файл
        client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=uploaded_file,
            length=uploaded_file.size,
            content_type='application/octet-stream'
        )
        
        return object_name, None
        
    except S3Error as e:
        return None, f"MinIO error: {e}"
    except Exception as e:
        return None, f"Unexpected error: {e}"

def save_upload_metadata(filename, original_name, file_size, file_hash, minio_path, location_id, sample_type, description):
    """Сохранить метаданные загрузки в базу данных"""
    conn = create_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            # Создаем таблицу если не существует
            cur.execute("""
                CREATE TABLE IF NOT EXISTS genomic_uploads (
                    upload_id SERIAL PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    original_filename VARCHAR(255) NOT NULL,
                    file_size BIGINT NOT NULL,
                    file_hash VARCHAR(64) NOT NULL,
                    minio_path VARCHAR(500) NOT NULL,
                    location_id INTEGER REFERENCES locations(location_id),
                    sample_type VARCHAR(100),
                    description TEXT,
                    upload_datetime TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    processing_status VARCHAR(50) DEFAULT 'uploaded',
                    created_by VARCHAR(100) DEFAULT 'streamlit_user'
                )
            """)
            
            # Вставляем запись
            cur.execute("""
                INSERT INTO genomic_uploads 
                (filename, original_filename, file_size, file_hash, minio_path, 
                 location_id, sample_type, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (filename, original_name, file_size, file_hash, minio_path, 
                  location_id, sample_type, description))
            
            conn.commit()
            return True
            
    except Exception as e:
        st.error(f"Database error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_upload_history():
    """Получить историю загрузок"""
    conn = create_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = """
        SELECT u.upload_id, u.original_filename, u.file_size, u.sample_type,
               u.description, u.upload_datetime, u.processing_status,
               l.city, l.country, l.location_name
        FROM genomic_uploads u
        LEFT JOIN locations l ON u.location_id = l.location_id
        ORDER BY u.upload_datetime DESC
        LIMIT 100
        """
        df = pd.read_sql(query, conn)
        
        if not df.empty:
            df['upload_datetime'] = pd.to_datetime(df['upload_datetime'])
            df['file_size_mb'] = (df['file_size'] / (1024 * 1024)).round(2)
            
        return df
        
    except Exception as e:
        st.error(f"Error fetching upload history: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

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

def genomic_upload_page():
    """Страница загрузки геномных файлов"""
    st.header("Genomic Data Upload")
    st.markdown("Upload genomic sequencing files for pathogen and AMR analysis")
    
    # Информационная панель
    with st.expander("📋 Supported File Types & Guidelines"):
        st.markdown("""
        ### Supported File Types:
        - **FASTQ files**: `.fastq`, `.fastq.gz`, `.fq`, `.fq.gz`
        - **FASTA files**: `.fasta`, `.fa`  
        - **Alignment files**: `.bam`, `.sam`
        - **Variant files**: `.vcf`, `.vcf.gz`
        
        ### Guidelines:
        - **Maximum file size**: 500MB per file
        - Files are stored securely in encrypted object storage
        - All uploads are logged with timestamps and metadata
        """)
    
    # Основная форма загрузки
    st.subheader("Upload New File")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Загрузка файла
        uploaded_file = st.file_uploader(
            "Choose genomic file",
            type=['fastq', 'fq', 'fasta', 'fa', 'bam', 'sam', 'vcf', 'gz'],
            help="Select a genomic data file to upload"
        )
        
        if uploaded_file:
            st.success(f"File selected: {uploaded_file.name} ({uploaded_file.size / (1024*1024):.2f} MB)")
            
            # Валидация файла
            validation_errors = validate_genomic_file(uploaded_file)
            if validation_errors:
                for error in validation_errors:
                    st.error(error)
                st.stop()
    
    with col2:
        if uploaded_file:
            st.markdown("**File Details**")
            st.write(f"Name: {uploaded_file.name}")
            st.write(f"Size: {uploaded_file.size:,} bytes")
            st.write(f"Type: {uploaded_file.type or 'Unknown'}")
    
    # Метаданные
    if uploaded_file:
        st.subheader("Sample Information")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Получаем список локаций для выбора
            locations_df = fetch_locations()
            if not locations_df.empty:
                location_options = ["None"] + [
                    f"{row['city']}, {row['country']} - {row['location_name']}" 
                    for _, row in locations_df.iterrows()
                ]
                selected_location = st.selectbox("Sample Location", location_options)
                
                # Получаем location_id
                location_id = None
                if selected_location != "None":
                    location_index = location_options.index(selected_location) - 1
                    location_id = locations_df.iloc[location_index]['location_id']
            else:
                st.warning("No locations available. Add locations first.")
                location_id = None
            
            sample_type = st.selectbox(
                "Sample Type",
                ["Environmental", "Clinical", "Wastewater", "Soil", "Air", "Surface", "Other"]
            )
        
        with col2:
            description = st.text_area(
                "Sample Description",
                placeholder="Enter details about the sample, collection method, etc.",
                height=100
            )
        
        # Кнопка загрузки
        if st.button("Upload File", type="primary"):
            if not description.strip():
                st.warning("Please provide a sample description")
                st.stop()
            
            with st.spinner("Uploading file..."):
                # Вычисляем хеш файла
                uploaded_file.seek(0)
                file_content = uploaded_file.read()
                file_hash = hashlib.sha256(file_content).hexdigest()
                
                # Возвращаем указатель в начало для upload
                uploaded_file.seek(0)
                
                # Загружаем в MinIO
                minio_path, error = save_file_to_minio(uploaded_file)
                
                if error:
                    st.error(f"Upload failed: {error}")
                    st.stop()
                
                # Сохраняем метаданные в БД
                success = save_upload_metadata(
                    filename=Path(uploaded_file.name).stem,
                    original_name=uploaded_file.name,
                    file_size=uploaded_file.size,
                    file_hash=file_hash,
                    minio_path=minio_path,
                    location_id=location_id,
                    sample_type=sample_type,
                    description=description.strip()
                )
                
                if success:
                    st.success(f"File '{uploaded_file.name}' uploaded successfully!")
                    st.balloons()
                    # Очистка кеша для обновления истории
                    st.cache_data.clear()
                else:
                    st.error("Failed to save file metadata")
    
    # История загрузок
    st.markdown("---")
    st.subheader("Upload History")
    
    history_df = get_upload_history()
    
    if not history_df.empty:
        # Фильтры
        col1, col2, col3 = st.columns(3)
        
        with col1:
            sample_types = ['All'] + sorted(history_df['sample_type'].unique().tolist())
            filter_type = st.selectbox("Filter by Sample Type", sample_types, key="history_filter")
        
        with col2:
            locations = ['All'] + sorted([loc for loc in history_df['city'].unique() if pd.notna(loc)])
            filter_location = st.selectbox("Filter by Location", locations, key="location_filter")
        
        with col3:
            statuses = ['All'] + sorted(history_df['processing_status'].unique().tolist())
            filter_status = st.selectbox("Filter by Status", statuses, key="status_filter")
        
        # Применение фильтров
        filtered_df = history_df.copy()
        if filter_type != 'All':
            filtered_df = filtered_df[filtered_df['sample_type'] == filter_type]
        if filter_location != 'All':
            filtered_df = filtered_df[filtered_df['city'] == filter_location]
        if filter_status != 'All':
            filtered_df = filtered_df[filtered_df['processing_status'] == filter_status]
        
        # Отображение таблицы
        st.dataframe(
            filtered_df[['original_filename', 'file_size_mb', 'sample_type', 'city', 
                        'country', 'processing_status', 'upload_datetime']].rename(columns={
                'original_filename': 'Filename',
                'file_size_mb': 'Size (MB)',
                'sample_type': 'Sample Type',
                'city': 'City',
                'country': 'Country',
                'processing_status': 'Status',
                'upload_datetime': 'Upload Time'
            }),
            use_container_width=True
        )
        
        # Статистика
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Files", len(history_df))
        with col2:
            total_size = history_df['file_size_mb'].sum()
            st.metric("Total Size", f"{total_size:.2f} MB")
        with col3:
            processed = len(history_df[history_df['processing_status'] == 'processed'])
            st.metric("Processed", processed)
        with col4:
            pending = len(history_df[history_df['processing_status'] == 'uploaded'])
            st.metric("Pending", pending)
        
    else:
        st.info("No files uploaded yet")

def system_status_page():
    """Страница системного статуса"""
    st.header("System Status")
    
    # Проверка подключения к базе данных
    if test_db_connection():
        st.success("Database connection: OK")
        
        # Проверка MinIO
        minio_client = get_minio_client()
        if minio_client:
            st.success("MinIO connection: OK")
        else:
            st.error("MinIO connection: Failed")
        
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
    
    # Выпадающее меню в сайдбаре
    with st.sidebar:
        st.title("Navigation")
        
        # Основные разделы
        st.markdown("### Main Sections")
        main_section = st.selectbox(
            "Choose main section:",
            ["Dashboard", "Data Management", "Analytics", "System"],
            label_visibility="collapsed"
        )
        
        # Подразделы в зависимости от выбранного раздела
        if main_section == "Dashboard":
            st.markdown("### Dashboard Options")
            page = st.selectbox(
                "Dashboard view:",
                ["Overview", "Real-time Monitoring"],
                key="dashboard_sub",
                label_visibility="collapsed"
            )
            page = "Dashboard"  # Всегда направляем на dashboard
            
        elif main_section == "Data Management":
            st.markdown("### Data Management")
            page = st.selectbox(
                "Data options:",
                ["Locations", "Weather Details", "Genomic Upload"],
                key="data_sub",
                label_visibility="collapsed"
            )
            
        elif main_section == "Analytics":
            st.markdown("### Analytics Options") 
            page = st.selectbox(
                "Analytics view:",
                ["Weather Analytics", "Genomic Analysis", "Reports"],
                key="analytics_sub",
                label_visibility="collapsed"
            )
            # Пока направляем на Weather Details для аналитики
            page = "Weather Details"
            
        elif main_section == "System":
            st.markdown("### System Management")
            page = st.selectbox(
                "System options:",
                ["System Status", "Configuration", "Logs"],
                key="system_sub", 
                label_visibility="collapsed"
            )
            page = "System Status"  # Направляем на системный статус
        
        st.markdown("---")
        
        # Информация о системе
        st.info(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
        
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        # Статус соединений
        st.markdown("### Connection Status")
        if test_db_connection():
            st.success("Database: Connected")
        else:
            st.error("Database: Disconnected")
            
        minio_client = get_minio_client()
        if minio_client:
            st.success("Storage: Connected") 
        else:
            st.error("Storage: Disconnected")
    
    # Роутинг страниц
    if page == "Dashboard":
        dashboard_page()
    elif page == "Locations":
        locations_page()
    elif page == "Weather Details":
        weather_details_page()
    elif page == "Genomic Upload":
        genomic_upload_page()
    elif page == "System Status":
        system_status_page()

if __name__ == "__main__":
    main()