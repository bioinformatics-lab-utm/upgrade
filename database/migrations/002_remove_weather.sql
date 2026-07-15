-- Migration 002: Remove weather-related schema objects
-- Weather services have been removed from the platform.

DROP MATERIALIZED VIEW IF EXISTS public.mv_latest_weather_conditions CASCADE;

DROP TABLE IF EXISTS public.weather_measurements CASCADE;

DROP TYPE IF EXISTS public.weather_source CASCADE;
