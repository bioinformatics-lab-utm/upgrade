# app.py
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import folium_static
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# Конфигурация страницы
st.set_page_config(
    page_title="Weather Dashboard Romania-Moldova",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Заголовок
st.title("🌤️ Weather Analytics Romania-Moldova")
st.markdown("---")

# Координаты городов
CITIES = {
    'Romania': [
        {'name': 'Suceava', 'lat': 47.6635, 'lon': 26.2535},
        {'name': 'Bucharest', 'lat': 44.4268, 'lon': 26.1025},
        {'name': 'Cluj-Napoca', 'lat': 46.7712, 'lon': 23.6236},
        {'name': 'Timisoara', 'lat': 45.7489, 'lon': 21.2087},
        {'name': 'Constanta', 'lat': 44.1598, 'lon': 28.6348},
        {'name': 'Iasi', 'lat': 47.1585, 'lon': 27.6014},
    ],
    'Moldova': [
        {'name': 'Chisinau', 'lat': 47.0105, 'lon': 28.8638},
        {'name': 'Balti', 'lat': 47.7613, 'lon': 27.9289},
        {'name': 'Cahul', 'lat': 45.9075, 'lon': 28.1984},
        {'name': 'Soroca', 'lat': 48.1581, 'lon': 28.2956},
        {'name': 'Orhei', 'lat': 47.3697, 'lon': 28.8219},
        {'name': 'Ungheni', 'lat': 47.2086, 'lon': 27.7976},
    ]
}

@st.cache_data(ttl=3600)  # Кеш на 1 час
def fetch_weather_data():
    """Получение данных погоды из Open-Meteo API"""
    all_data = []
    
    progress_bar = st.progress(0)
    total_cities = sum(len(cities) for cities in CITIES.values())
    processed = 0
    
    for country, cities in CITIES.items():
        for city_info in cities:
            try:
                # Правильный URL для Open-Meteo
                url = "https://api.open-meteo.com/v1/forecast"
                params = {
                    'latitude': city_info['lat'],
                    'longitude': city_info['lon'],
                    'current_weather': 'true',  # Изменено
                    'hourly': 'temperature_2m,relativehumidity_2m,precipitation,surface_pressure,windspeed_10m',
                    'forecast_days': 1
                }
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if 'current_weather' in data and 'hourly' in data:
                    current = data['current_weather']
                    hourly = data['hourly']
                    
                    weather_data = {
                        'country': country,
                        'city': city_info['name'],
                        'latitude': city_info['lat'],
                        'longitude': city_info['lon'],
                        'temperature': current.get('temperature'),
                        'humidity': hourly['relativehumidity_2m'][0] if hourly['relativehumidity_2m'] else None,
                        'precipitation': hourly['precipitation'][0] if hourly['precipitation'] else 0,
                        'pressure': hourly['surface_pressure'][0] if hourly['surface_pressure'] else None,
                        'wind_speed': current.get('windspeed'),
                        'timestamp': datetime.now()
                    }
                    all_data.append(weather_data)
                
                processed += 1
                progress_bar.progress(processed / total_cities)
                time.sleep(0.1)
                
            except Exception as e:
                st.warning(f"Ошибка для {city_info['name']}: {str(e)}")
    
    progress_bar.empty()
    return pd.DataFrame(all_data)

def create_weather_map(df):
    """Создание интерактивной карты"""
    if df.empty:
        return None
    
    # Центр карты между Румынией и Молдовой
    center_lat = df['latitude'].mean()
    center_lon = df['longitude'].mean()
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles='OpenStreetMap'
    )
    
    # Цветовая схема для температуры
    min_temp = df['temperature'].min()
    max_temp = df['temperature'].max()
    
    for _, row in df.iterrows():
        # Нормализация температуры для цвета (0-1)
        temp_norm = (row['temperature'] - min_temp) / (max_temp - min_temp) if max_temp > min_temp else 0.5
        
        # Цвет от синего (холодно) до красного (жарко)
        color = f'#{int(255*temp_norm):02x}{int(100):02x}{int(255*(1-temp_norm)):02x}'
        
        popup_text = f"""
        <b>{row['city']}, {row['country']}</b><br>
        🌡️ Температура: {row['temperature']}°C<br>
        💧 Влажность: {row['humidity']}%<br>
        🌧️ Осадки: {row['precipitation']} мм<br>
        💨 Ветер: {row['wind_speed']} м/с<br>
        📊 Давление: {row['pressure']} hPa
        """
        
        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=10,
            popup=folium.Popup(popup_text, max_width=250),
            color='white',
            weight=2,
            fillColor=color,
            fillOpacity=0.8,
            tooltip=f"{row['city']}: {row['temperature']}°C"
        ).add_to(m)
    
    return m

def create_density_plots(df):
    """Создание density plots"""
    if df.empty:
        return None, None
    
    # Density plot влажности
    fig_humidity = px.histogram(
        df, 
        x='humidity', 
        color='country',
        nbins=20,
        title='Распределение влажности по странам',
        labels={'humidity': 'Влажность (%)', 'count': 'Количество городов'},
        color_discrete_map={'Romania': '#0066cc', 'Moldova': '#ff6600'}
    )
    fig_humidity.update_layout(height=400)
    
    # Density plot температуры
    fig_temp = px.histogram(
        df,
        x='temperature',
        color='country', 
        nbins=15,
        title='Распределение температуры по странам',
        labels={'temperature': 'Температура (°C)', 'count': 'Количество городов'},
        color_discrete_map={'Romania': '#0066cc', 'Moldova': '#ff6600'}
    )
    fig_temp.update_layout(height=400)
    
    return fig_humidity, fig_temp

def create_comparison_charts(df):
    """Создание сравнительных графиков"""
    if df.empty:
        return None, None
    
    # Средние показатели по странам
    country_stats = df.groupby('country').agg({
        'temperature': 'mean',
        'humidity': 'mean',
        'precipitation': 'mean',
        'wind_speed': 'mean'
    }).round(1)
    
    # Барная диаграмма средней температуры
    fig_bar = px.bar(
        x=country_stats.index,
        y=country_stats['temperature'],
        title='Средняя температура по странам',
        labels={'x': 'Страна', 'y': 'Температура (°C)'},
        color=country_stats.index,
        color_discrete_map={'Romania': '#0066cc', 'Moldova': '#ff6600'}
    )
    fig_bar.update_layout(height=400, showlegend=False)
    
    # Scatter plot влажность vs температура
    fig_scatter = px.scatter(
        df,
        x='temperature',
        y='humidity',
        color='country',
        size='wind_speed',
        hover_data=['city', 'precipitation'],
        title='Соотношение температуры и влажности',
        labels={'temperature': 'Температура (°C)', 'humidity': 'Влажность (%)'},
        color_discrete_map={'Romania': '#0066cc', 'Moldova': '#ff6600'}
    )
    fig_scatter.update_layout(height=400)
    
    return fig_bar, fig_scatter

# Основное приложение
def main():
    # Боковая панель с настройками
    st.sidebar.title("⚙️ Настройки")
    
    # Кнопка обновления данных
    if st.sidebar.button("🔄 Обновить данные"):
        st.cache_data.clear()
        st.rerun()
    
    # Фильтры
    st.sidebar.subheader("🔍 Фильтры")
    
    # Загрузка данных
    with st.spinner("Загрузка данных о погоде..."):
        df = fetch_weather_data()
    
    if df.empty:
        st.error("Не удалось загрузить данные о погоде")
        return
    
    # Фильтр по странам
    countries = st.sidebar.multiselect(
        "Выберите страны:",
        options=df['country'].unique(),
        default=df['country'].unique()
    )
    
    # Фильтрация данных
    filtered_df = df[df['country'].isin(countries)]
    
    # Показать время последнего обновления
    st.sidebar.info(f"Последнее обновление: {datetime.now().strftime('%H:%M:%S')}")
    
    # Основные метрики
    st.subheader("📊 Сводная статистика")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        avg_temp = filtered_df['temperature'].mean()
        st.metric("Средняя температура", f"{avg_temp:.1f}°C")
    
    with col2:
        avg_humidity = filtered_df['humidity'].mean()
        st.metric("Средняя влажность", f"{avg_humidity:.1f}%")
    
    with col3:
        total_precip = filtered_df['precipitation'].sum()
        st.metric("Общие осадки", f"{total_precip:.1f} мм")
    
    with col4:
        avg_wind = filtered_df['wind_speed'].mean()
        st.metric("Средний ветер", f"{avg_wind:.1f} м/с")
    
    st.markdown("---")
    
    # Главная секция с картой
    st.subheader("🗺️ Интерактивная карта погоды")
    
    weather_map = create_weather_map(filtered_df)
    if weather_map:
        folium_static(weather_map, width=1200, height=600)
    
    st.markdown("---")
    
    # Density plots
    st.subheader("📈 Анализ распределения")
    
    fig_humidity, fig_temp = create_density_plots(filtered_df)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if fig_humidity:
            st.plotly_chart(fig_humidity, use_container_width=True)
    
    with col2:
        if fig_temp:
            st.plotly_chart(fig_temp, use_container_width=True)
    
    st.markdown("---")
    
    # Сравнительные графики
    st.subheader("🔍 Сравнительный анализ")
    
    fig_bar, fig_scatter = create_comparison_charts(filtered_df)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if fig_bar:
            st.plotly_chart(fig_bar, use_container_width=True)
    
    with col2:
        if fig_scatter:
            st.plotly_chart(fig_scatter, use_container_width=True)
    
    st.markdown("---")
    
    # Таблица с данными
    st.subheader("📋 Детальные данные")
    
    # Форматирование таблицы
    display_df = filtered_df.copy()
    display_df['temperature'] = display_df['temperature'].apply(lambda x: f"{x:.1f}°C")
    display_df['humidity'] = display_df['humidity'].apply(lambda x: f"{x:.1f}%")
    display_df['precipitation'] = display_df['precipitation'].apply(lambda x: f"{x:.1f} мм")
    display_df['wind_speed'] = display_df['wind_speed'].apply(lambda x: f"{x:.1f} м/с")
    display_df['pressure'] = display_df['pressure'].apply(lambda x: f"{x:.1f} hPa")
    
    st.dataframe(
        display_df[['country', 'city', 'temperature', 'humidity', 'precipitation', 'wind_speed', 'pressure']],
        use_container_width=True,
        column_config={
            'country': 'Страна',
            'city': 'Город', 
            'temperature': 'Температура',
            'humidity': 'Влажность',
            'precipitation': 'Осадки',
            'wind_speed': 'Ветер',
            'pressure': 'Давление'
        }
    )

if __name__ == "__main__":
    main()