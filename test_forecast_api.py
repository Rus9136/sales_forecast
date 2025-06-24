#!/usr/bin/env python3
"""
Script to test forecast API endpoints
"""
import requests
import json
from datetime import date, timedelta

# Base URL (adjust port if needed)
BASE_URL = "http://localhost:8002"

def test_forecast_endpoint():
    """Test the forecast endpoint"""
    print("=" * 60)
    print("TESTING FORECAST API ENDPOINTS")
    print("=" * 60)
    
    # First, get a department to test with
    print("\n1. Getting list of departments...")
    response = requests.get(f"{BASE_URL}/api/departments/")
    
    if response.status_code == 200:
        departments = response.json()
        if departments:
            # Use first department
            test_dept = departments[0]
            dept_id = test_dept['id']
            dept_name = test_dept['name']
            
            print(f"   Found {len(departments)} departments")
            print(f"   Using: {dept_name} (ID: {dept_id})")
            
            # Test forecast for tomorrow
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            
            print(f"\n2. Testing forecast for {tomorrow}...")
            print(f"\n   CURL command:")
            print(f"   curl http://localhost:8002/api/forecast/{tomorrow}/{dept_id}")
            
            # Make the forecast request
            forecast_url = f"{BASE_URL}/api/forecast/{tomorrow}/{dept_id}"
            response = requests.get(forecast_url)
            
            print(f"\n   Response status: {response.status_code}")
            print(f"   Response JSON:")
            print(json.dumps(response.json(), indent=2))
            
            # Test forecast for next week
            next_week = (date.today() + timedelta(days=7)).isoformat()
            print(f"\n3. Testing forecast for {next_week}...")
            
            forecast_url = f"{BASE_URL}/api/forecast/{next_week}/{dept_id}"
            response = requests.get(forecast_url)
            
            print(f"   Response status: {response.status_code}")
            print(f"   Response JSON:")
            print(json.dumps(response.json(), indent=2))
            
        else:
            print("   No departments found in database!")
    else:
        print(f"   Error getting departments: {response.status_code}")
    
    # Test model info endpoint
    print("\n4. Testing model info endpoint...")
    print("\n   CURL command:")
    print("   curl http://localhost:8002/api/forecast/model/info")
    
    response = requests.get(f"{BASE_URL}/api/forecast/model/info")
    print(f"\n   Response status: {response.status_code}")
    print(f"   Response JSON:")
    print(json.dumps(response.json(), indent=2))
    
    print("\n" + "=" * 60)
    print("WHERE THE FORECAST HAPPENS")
    print("=" * 60)
    print("""
The forecast() function is called in:
- File: app/routers/forecast.py
- Line: ~45
- Code snippet:
    
    # Call forecast function
    predicted_sales = forecaster.forecast(
        branch_id=branch_id,
        forecast_date=forecast_date,
        db=db
    )

The flow is:
1. API request comes to GET /api/forecast/{date}/{branch_id}
2. Router validates the branch exists
3. Gets the forecaster agent (singleton)
4. Calls forecaster.forecast() with the parameters
5. Returns JSON response with prediction or null if insufficient data
""")

    print("\n" + "=" * 60)
    print("ADDITIONAL ENDPOINTS")
    print("=" * 60)
    print("""
1. Retrain model:
   curl -X POST http://localhost:8002/api/forecast/retrain

2. Get model info:
   curl http://localhost:8002/api/forecast/model/info

3. Get forecast:
   curl http://localhost:8002/api/forecast/2025-07-01/branch-uuid
""")

if __name__ == "__main__":
    test_forecast_endpoint()