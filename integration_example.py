#!/usr/bin/env python3
"""
Sales Forecast API Integration Example
This script demonstrates how to integrate with the Sales Forecast API
"""

import requests
from datetime import date, datetime, timedelta
import json
import pandas as pd

# Configuration
API_BASE_URL = "https://aqniet.site/api/forecast"
# For local testing use: http://localhost:8002/api/forecast

# Example branch IDs (replace with your actual branch IDs)
BRANCH_IDS = [
    "0785c2e6-d6c6-4ffb-bf5d-6744496e40a6",  # Sandyq Astana
    "18fc94ec-d9d1-4019-bd63-58c3b2042775",  # Salam Bro Ayusai
]


class SalesForecastClient:
    """Client for Sales Forecast API"""
    
    def __init__(self, base_url=API_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
    
    def get_single_forecast(self, branch_id: str, forecast_date: date) -> dict:
        """Get forecast for a single branch on a specific date"""
        url = f"{self.base_url}/{forecast_date.isoformat()}/{branch_id}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_batch_forecasts(self, from_date: date, to_date: date, branch_id: str = None) -> list:
        """Get forecasts for a date range"""
        params = {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat()
        }
        if branch_id:
            params["department_id"] = branch_id
        
        response = self.session.get(f"{self.base_url}/batch", params=params)
        response.raise_for_status()
        return response.json()
    
    def get_forecasts_with_postprocessing(self, from_date: date, to_date: date, branch_id: str = None) -> list:
        """Get forecasts with advanced post-processing"""
        params = {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "apply_postprocessing": True
        }
        if branch_id:
            params["department_id"] = branch_id
        
        response = self.session.get(f"{self.base_url}/batch_with_postprocessing", params=params)
        response.raise_for_status()
        return response.json()
    
    def get_forecast_comparison(self, from_date: date, to_date: date, branch_id: str = None) -> list:
        """Compare forecasts with actual sales"""
        params = {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat()
        }
        if branch_id:
            params["department_id"] = branch_id
        
        response = self.session.get(f"{self.base_url}/comparison", params=params)
        response.raise_for_status()
        return response.json()
    
    def export_to_csv(self, from_date: date, to_date: date, filename: str, include_actual: bool = False):
        """Export forecasts to CSV file"""
        params = {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "include_actual": include_actual
        }
        
        response = self.session.get(f"{self.base_url}/export/csv", params=params)
        response.raise_for_status()
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"Exported forecasts to {filename}")
    
    def postprocess_single_forecast(self, branch_id: str, forecast_date: date, raw_prediction: float) -> dict:
        """Apply post-processing to a single forecast"""
        data = {
            "branch_id": branch_id,
            "forecast_date": forecast_date.isoformat(),
            "raw_prediction": raw_prediction,
            "apply_smoothing": True,
            "apply_business_rules": True,
            "apply_anomaly_detection": True,
            "calculate_confidence": True
        }
        
        response = self.session.post(f"{self.base_url}/postprocess", json=data)
        response.raise_for_status()
        return response.json()
    
    def get_model_info(self) -> dict:
        """Get information about the current model"""
        response = self.session.get(f"{self.base_url}/model/info")
        response.raise_for_status()
        return response.json()


def main():
    """Example usage of the Sales Forecast API client"""
    
    # Initialize client
    client = SalesForecastClient()
    
    # Example 1: Get model information
    print("=== Model Information ===")
    model_info = client.get_model_info()
    print(f"Model Type: {model_info.get('model_type', 'Unknown')}")
    print(f"Features Count: {model_info.get('features_count', 0)}")
    print(f"Training Date: {model_info.get('training_date', 'Unknown')}")
    if 'training_metrics' in model_info:
        metrics = model_info['training_metrics']
        print(f"Test MAPE: {metrics.get('test_mape', 'N/A')}%")
        print(f"R² Score: {metrics.get('r2_score', 'N/A')}")
    print()
    
    # Example 2: Get forecast for tomorrow for a specific branch
    tomorrow = date.today() + timedelta(days=1)
    branch_id = BRANCH_IDS[0]
    
    print(f"=== Tomorrow's Forecast for Branch {branch_id} ===")
    try:
        forecast = client.get_single_forecast(branch_id, tomorrow)
        print(f"Date: {tomorrow}")
        print(f"Predicted Sales: {forecast.get('predicted_sales', 0):,.2f} KZT")
    except Exception as e:
        print(f"Error: {e}")
    print()
    
    # Example 3: Get weekly forecast with post-processing
    start_date = date.today()
    end_date = start_date + timedelta(days=7)
    
    print(f"=== Weekly Forecast with Post-processing ({start_date} to {end_date}) ===")
    forecasts = client.get_forecasts_with_postprocessing(start_date, end_date, branch_id)
    
    for forecast in forecasts[:3]:  # Show first 3 days
        print(f"\nDate: {forecast['date']}")
        print(f"Branch: {forecast['department_name']}")
        print(f"Raw Prediction: {forecast.get('raw_prediction', 0):,.2f} KZT")
        print(f"Processed Prediction: {forecast.get('processed_prediction', forecast.get('predicted_sales', 0)):,.2f} KZT")
        
        if 'confidence_interval' in forecast:
            ci = forecast['confidence_interval']
            print(f"95% Confidence Interval: [{ci.get('lower', 0):,.2f}, {ci.get('upper', 0):,.2f}]")
        
        if 'adjustments_applied' in forecast:
            print(f"Adjustments: {', '.join(forecast['adjustments_applied'])}")
        
        if 'business_flags' in forecast:
            print(f"Business Flags: {', '.join(forecast['business_flags'])}")
    print()
    
    # Example 4: Get comparison with actual sales (for past dates)
    comparison_start = date.today() - timedelta(days=30)
    comparison_end = date.today() - timedelta(days=1)
    
    print(f"=== Forecast vs Actual Comparison ({comparison_start} to {comparison_end}) ===")
    comparisons = client.get_forecast_comparison(comparison_start, comparison_end, branch_id)
    
    if comparisons:
        # Convert to DataFrame for analysis
        df = pd.DataFrame(comparisons)
        if not df.empty and 'error_percentage' in df.columns:
            avg_mape = df['error_percentage'].mean()
            print(f"Average MAPE: {avg_mape:.2f}%")
            print(f"Total Comparisons: {len(df)}")
            
            # Show sample
            print("\nSample comparisons:")
            for _, row in df.head(3).iterrows():
                print(f"  {row['date']}: Predicted={row.get('predicted_sales', 0):,.0f}, "
                      f"Actual={row.get('actual_sales', 0):,.0f}, "
                      f"Error={row.get('error_percentage', 0):.1f}%")
    print()
    
    # Example 5: Export monthly forecast to CSV
    export_start = date.today()
    export_end = export_start + timedelta(days=30)
    filename = f"forecast_{export_start.strftime('%Y%m')}.csv"
    
    print(f"=== Exporting Monthly Forecast ===")
    client.export_to_csv(export_start, export_end, filename)
    
    # Example 6: Post-process a manual forecast
    print("\n=== Post-processing Example ===")
    manual_prediction = 150000.0
    result = client.postprocess_single_forecast(branch_id, tomorrow, manual_prediction)
    
    if result['status'] == 'success':
        processed = result['result']
        print(f"Raw Prediction: {processed['raw_prediction']:,.2f} KZT")
        print(f"Processed Prediction: {processed['processed_prediction']:,.2f} KZT")
        print(f"Adjustments Applied: {', '.join(processed.get('adjustments_applied', []))}")
        
        if processed.get('is_anomaly'):
            print(f"⚠️ Anomaly detected! Score: {processed.get('anomaly_score', 0):.2f}")


if __name__ == "__main__":
    main()