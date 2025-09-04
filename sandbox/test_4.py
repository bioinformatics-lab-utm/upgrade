# simple_weather_test.py
import asyncio
import aiohttp
import json
from datetime import datetime

async def test_simple_weather():
    """Test with the simplest possible Open-Meteo request"""
    
    # Test coordinates for Bucharest
    lat, lon = 44.4268, 26.1025
    
    # Minimal parameters
    params = {
        'latitude': lat,
        'longitude': lon,
        'current': 'temperature_2m,weather_code',
        'timezone': 'auto'
    }
    
    # Try different URLs
    urls_to_test = [
        'http://api.open-meteo.com/v1/forecast',
        'https://api.open-meteo.com/v1/forecast'
    ]
    
    for url in urls_to_test:
        print(f"\n🔍 Testing URL: {url}")
        print(f"📍 Parameters: {params}")
        
        try:
            # Create session with different SSL settings
            connector = aiohttp.TCPConnector(ssl=False) if url.startswith('http:') else None
            
            async with aiohttp.ClientSession(connector=connector) as session:
                print(f"⏳ Making request...")
                
                async with session.get(url, params=params, timeout=10) as response:
                    print(f"📊 Response Status: {response.status}")
                    print(f"📋 Response Headers: {dict(response.headers)}")
                    
                    response_text = await response.text()
                    print(f"📝 Response Length: {len(response_text)} chars")
                    
                    if response.status == 200:
                        try:
                            data = json.loads(response_text)
                            print(f"✅ SUCCESS! JSON Data Keys: {list(data.keys())}")
                            if 'current' in data:
                                print(f"🌡️  Current temp: {data['current'].get('temperature_2m')}°C")
                                print(f"🌤️  Weather code: {data['current'].get('weather_code')}")
                            print(f"📄 Full response: {json.dumps(data, indent=2)[:500]}...")
                            return True
                        except json.JSONDecodeError as e:
                            print(f"❌ JSON Error: {e}")
                            print(f"📄 Raw response: {response_text[:500]}...")
                    else:
                        print(f"❌ HTTP Error {response.status}")
                        print(f"📄 Error response: {response_text[:500]}...")
                        
        except Exception as e:
            print(f"❌ Request failed: {type(e).__name__}: {e}")
    
    return False

async def test_multiple_cities():
    """Test requests for multiple Romanian cities with minimal parameters"""
    
    cities = [
        {'name': 'Bucharest', 'lat': 44.4268, 'lon': 26.1025},
        {'name': 'Cluj-Napoca', 'lat': 46.7712, 'lon': 23.6236},
        {'name': 'Suceava', 'lat': 47.6635, 'lon': 26.2535}
    ]
    
    url = 'https://api.open-meteo.com/v1/forecast'
    
    print(f"\n🏙️  Testing multiple cities...")
    
    async with aiohttp.ClientSession() as session:
        for city in cities:
            print(f"\n📍 Testing {city['name']}...")
            
            params = {
                'latitude': city['lat'],
                'longitude': city['lon'],
                'current': 'temperature_2m',
                'timezone': 'auto'
            }
            
            try:
                async with session.get(url, params=params, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        temp = data.get('current', {}).get('temperature_2m', 'N/A')
                        print(f"✅ {city['name']}: {temp}°C")
                    else:
                        print(f"❌ {city['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"❌ {city['name']}: {type(e).__name__}: {e}")

async def main():
    print("🌤️  Open-Meteo API Simple Test")
    print("=" * 50)
    
    # Test 1: Simple single request
    print("\n📋 Test 1: Simple API request")
    success = await test_simple_weather()
    
    if success:
        # Test 2: Multiple cities
        print("\n📋 Test 2: Multiple cities")
        await test_multiple_cities()
    else:
        print("\n❌ Basic test failed - check your internet connection")
        print("💡 Try running with different network settings")
    
    print(f"\n✨ Test completed at {datetime.now()}")

if __name__ == "__main__":
    asyncio.run(main())