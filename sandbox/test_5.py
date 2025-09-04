# openmeteo_params_test.py
import asyncio
import aiohttp
import json
from datetime import datetime

class OpenMeteoParameterTester:
    def __init__(self):
        self.base_url = 'https://api.open-meteo.com/v1/forecast'
        self.test_location = {'lat': 44.4268, 'lon': 26.1025, 'name': 'Bucharest'}
        
        # All possible current parameters
        self.current_params = [
            'temperature_2m', 'relative_humidity_2m', 'apparent_temperature', 'is_day',
            'precipitation', 'rain', 'showers', 'snowfall', 'weather_code',
            'cloud_cover', 'surface_pressure', 'sea_level_pressure',
            'wind_speed_10m', 'wind_direction_10m', 'wind_gusts_10m',
            'visibility', 'uv_index', 'pressure_msl'
        ]
        
        # All possible hourly parameters
        self.hourly_params = [
            'temperature_2m', 'relative_humidity_2m', 'dew_point_2m', 'apparent_temperature',
            'pressure_msl', 'surface_pressure', 'cloud_cover', 'cloud_cover_low', 
            'cloud_cover_mid', 'cloud_cover_high', 'visibility', 'evapotranspiration',
            'et0_fao_evapotranspiration', 'vapour_pressure_deficit', 'wind_speed_10m', 
            'wind_direction_10m', 'wind_gusts_10m', 'temperature_80m', 'temperature_120m',
            'temperature_180m', 'soil_temperature_0cm', 'soil_temperature_6cm',
            'soil_temperature_18cm', 'soil_temperature_54cm', 'soil_moisture_0_1cm',
            'soil_moisture_1_3cm', 'soil_moisture_3_9cm', 'soil_moisture_9_27cm',
            'soil_moisture_27_81cm', 'precipitation', 'rain', 'showers', 'snowfall',
            'snow_depth', 'weather_code', 'shortwave_radiation', 'direct_radiation',
            'diffuse_radiation', 'direct_normal_irradiance', 'global_tilted_irradiance',
            'terrestrial_radiation', 'shortwave_radiation_instant', 'diffuse_radiation_instant',
            'direct_normal_irradiance_instant', 'global_tilted_irradiance_instant',
            'terrestrial_radiation_instant', 'uv_index', 'uv_index_clear_sky', 'is_day'
        ]
        
        # All possible daily parameters
        self.daily_params = [
            'weather_code', 'temperature_2m_max', 'temperature_2m_min', 'apparent_temperature_max',
            'apparent_temperature_min', 'sunrise', 'sunset', 'daylight_duration',
            'sunshine_duration', 'uv_index_max', 'uv_index_clear_sky_max',
            'precipitation_sum', 'rain_sum', 'showers_sum', 'snowfall_sum',
            'precipitation_hours', 'wind_speed_10m_max', 'wind_gusts_10m_max',
            'wind_direction_10m_dominant', 'shortwave_radiation_sum', 'et0_fao_evapotranspiration'
        ]

    async def test_parameter_group(self, session, param_type, params_list, batch_size=5):
        """Test parameters in batches to find which ones work"""
        print(f"\n🔍 Testing {param_type.upper()} parameters...")
        print(f"📊 Total parameters to test: {len(params_list)}")
        
        working_params = []
        failed_params = []
        
        # Test parameters in batches
        for i in range(0, len(params_list), batch_size):
            batch = params_list[i:i + batch_size]
            print(f"⏳ Testing batch {i//batch_size + 1}: {batch}")
            
            # Test this batch
            test_params = {
                'latitude': self.test_location['lat'],
                'longitude': self.test_location['lon'],
                param_type: ','.join(batch),
                'timezone': 'auto'
            }
            
            try:
                async with session.get(self.base_url, params=test_params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check which parameters actually have data
                        if param_type in data:
                            param_data = data[param_type]
                            for param in batch:
                                if param in param_data and param_data[param] is not None:
                                    working_params.append(param)
                                    print(f"  ✅ {param}: {param_data[param]}")
                                else:
                                    failed_params.append(param)
                                    print(f"  ❌ {param}: Not available/null")
                        else:
                            failed_params.extend(batch)
                            print(f"  ❌ No {param_type} data in response")
                    else:
                        failed_params.extend(batch)
                        response_text = await response.text()
                        print(f"  ❌ HTTP {response.status}: {response_text[:100]}...")
                        
            except Exception as e:
                failed_params.extend(batch)
                print(f"  💥 Error: {e}")
            
            # Small delay between batches
            await asyncio.sleep(0.5)
        
        return working_params, failed_params

    async def test_individual_parameters(self, session, param_type, params_list):
        """Test each parameter individually to get precise results"""
        print(f"\n🎯 Individual testing for {param_type.upper()} parameters...")
        
        working_params = {}
        failed_params = []
        
        for param in params_list:
            print(f"🔬 Testing: {param}")
            
            test_params = {
                'latitude': self.test_location['lat'],
                'longitude': self.test_location['lon'],
                param_type: param,
                'timezone': 'auto'
            }
            
            try:
                async with session.get(self.base_url, params=test_params, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if param_type in data and param in data[param_type]:
                            value = data[param_type][param]
                            if value is not None:
                                working_params[param] = value
                                print(f"  ✅ {param}: {value}")
                            else:
                                failed_params.append(param)
                                print(f"  ⚠️  {param}: null value")
                        else:
                            failed_params.append(param)
                            print(f"  ❌ {param}: not in response")
                    else:
                        failed_params.append(param)
                        print(f"  ❌ {param}: HTTP {response.status}")
                        
            except Exception as e:
                failed_params.append(param)
                print(f"  💥 {param}: {e}")
            
            await asyncio.sleep(0.2)  # Small delay between requests
        
        return working_params, failed_params

    async def test_combined_parameters(self, session, working_params):
        """Test combinations of working parameters to find optimal sets"""
        print(f"\n🔗 Testing parameter combinations...")
        
        # Test different combinations
        combinations = {
            'basic_weather': {
                'current': ['temperature_2m', 'weather_code', 'wind_speed_10m'],
                'hourly': ['temperature_2m', 'precipitation', 'weather_code'],
                'daily': ['temperature_2m_max', 'temperature_2m_min', 'precipitation_sum']
            },
            'extended_weather': {
                'current': ['temperature_2m', 'relative_humidity_2m', 'apparent_temperature', 
                           'weather_code', 'wind_speed_10m', 'cloud_cover'],
                'hourly': ['temperature_2m', 'relative_humidity_2m', 'precipitation', 
                          'weather_code', 'wind_speed_10m', 'cloud_cover'],
                'daily': ['temperature_2m_max', 'temperature_2m_min', 'precipitation_sum',
                         'wind_speed_10m_max', 'weather_code']
            },
            'comprehensive_weather': {
                'current': ['temperature_2m', 'relative_humidity_2m', 'apparent_temperature',
                           'weather_code', 'precipitation', 'wind_speed_10m', 'wind_direction_10m',
                           'cloud_cover', 'surface_pressure', 'visibility'],
                'hourly': ['temperature_2m', 'relative_humidity_2m', 'dew_point_2m',
                          'precipitation', 'weather_code', 'wind_speed_10m', 'cloud_cover',
                          'shortwave_radiation', 'uv_index', 'soil_temperature_0cm'],
                'daily': ['temperature_2m_max', 'temperature_2m_min', 'precipitation_sum',
                         'wind_speed_10m_max', 'weather_code', 'sunrise', 'sunset',
                         'uv_index_max', 'shortwave_radiation_sum']
            }
        }
        
        successful_combinations = {}
        
        for combo_name, combo_params in combinations.items():
            print(f"\n🧪 Testing combination: {combo_name}")
            
            # Filter only working parameters
            filtered_params = {}
            for param_type, params in combo_params.items():
                if param_type in working_params:
                    filtered_params[param_type] = [p for p in params if p in [param.split(':')[0] for param in working_params[param_type]]]
            
            test_params = {
                'latitude': self.test_location['lat'],
                'longitude': self.test_location['lon'],
                'timezone': 'auto'
            }
            
            for param_type, params in filtered_params.items():
                if params:
                    test_params[param_type] = ','.join(params)
            
            try:
                async with session.get(self.base_url, params=test_params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        data_size = len(str(data))
                        
                        print(f"  ✅ {combo_name}: Success! ({data_size} chars)")
                        successful_combinations[combo_name] = {
                            'params': filtered_params,
                            'data_size': data_size,
                            'sample_data': {k: str(v)[:100] + '...' if len(str(v)) > 100 else v 
                                          for k, v in data.items() if k != 'hourly'}
                        }
                    else:
                        print(f"  ❌ {combo_name}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  💥 {combo_name}: {e}")
        
        return successful_combinations

    async def run_comprehensive_test(self):
        """Run comprehensive parameter testing"""
        print("🌤️  Open-Meteo API Comprehensive Parameter Test")
        print("=" * 60)
        print(f"📍 Test location: {self.test_location['name']} ({self.test_location['lat']}, {self.test_location['lon']})")
        
        async with aiohttp.ClientSession() as session:
            all_working_params = {}
            
            # Test each parameter type
            for param_type, params_list in [
                ('current', self.current_params),
                ('hourly', self.hourly_params),
                ('daily', self.daily_params)
            ]:
                working, failed = await self.test_individual_parameters(session, param_type, params_list)
                all_working_params[param_type] = working
                
                print(f"\n📊 {param_type.upper()} Results:")
                print(f"  ✅ Working: {len(working)}/{len(params_list)} ({len(working)/len(params_list)*100:.1f}%)")
                print(f"  ❌ Failed: {len(failed)}")
                
                if working:
                    print(f"  🎯 Working parameters:")
                    for param, value in list(working.items())[:10]:  # Show first 10
                        print(f"    • {param}: {value}")
                    if len(working) > 10:
                        print(f"    ... and {len(working)-10} more")
            
            # Test combinations
            combinations = await self.test_combined_parameters(session, all_working_params)
            
            # Summary
            print(f"\n🎉 FINAL SUMMARY")
            print("=" * 40)
            
            total_working = sum(len(params) for params in all_working_params.values())
            total_possible = len(self.current_params) + len(self.hourly_params) + len(self.daily_params)
            
            print(f"📈 Total working parameters: {total_working}/{total_possible} ({total_working/total_possible*100:.1f}%)")
            
            print(f"\n🔧 RECOMMENDED PARAMETER SETS:")
            for combo_name, combo_data in combinations.items():
                print(f"\n  {combo_name.upper()}:")
                for param_type, params in combo_data['params'].items():
                    if params:
                        print(f"    {param_type}: {', '.join(params)}")
            
            # Generate code snippets
            print(f"\n💻 CODE SNIPPETS:")
            if combinations:
                best_combo = max(combinations.items(), key=lambda x: x[1]['data_size'])
                combo_name, combo_data = best_combo
                
                print(f"\n  # Best combination: {combo_name}")
                print(f"  params = {{")
                print(f"      'latitude': city['lat'],")
                print(f"      'longitude': city['lon'],")
                for param_type, params in combo_data['params'].items():
                    if params:
                        print(f"      '{param_type}': '{','.join(params)}',")
                print(f"      'timezone': 'auto'")
                print(f"  }}")
            
            return all_working_params, combinations

async def main():
    tester = OpenMeteoParameterTester()
    working_params, combinations = await tester.run_comprehensive_test()
    
    # Save results to file
    results = {
        'timestamp': datetime.now().isoformat(),
        'test_location': tester.test_location,
        'working_parameters': {k: list(v.keys()) for k, v in working_params.items()},
        'successful_combinations': {k: v['params'] for k, v in combinations.items()},
        'detailed_results': working_params
    }
    
    with open('openmeteo_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: openmeteo_test_results.json")

if __name__ == "__main__":
    asyncio.run(main())