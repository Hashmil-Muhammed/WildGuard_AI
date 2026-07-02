def get_weather(location: str) -> str:
    """Get the current weather for a given location to help rescue teams."""
    
    # Mock weather data (This will be replaced by a real API call later)
    weather_data = {
        "sector 9": "Heavy Rain Warning ⛈️",
        "sector 4": "Clear Sky ☀️",
        "munnar": "Misty and Cold 🌫️"
    }
    
    # Return weather information based on location or default to Sunny
    return weather_data.get(location.lower(), "Sunny 🌤️")