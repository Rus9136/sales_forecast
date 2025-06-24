#!/usr/bin/env python3
"""
Script to test the forecast UI functionality
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta
from app.db import get_db
from app.agents.sales_forecaster_agent import get_forecaster_agent
from app.models.branch import Department, SalesSummary
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    print("=" * 60)
    print("TESTING FORECAST UI FUNCTIONALITY")
    print("=" * 60)
    
    # Get database session
    db = next(get_db())
    
    # Check if model exists
    forecaster = get_forecaster_agent()
    model_info = forecaster.get_model_info()
    
    if model_info['status'] != 'loaded':
        print("\n⚠️  Model not loaded. Training model first...")
        metrics = forecaster.train_model(db)
        print(f"✅ Model trained. MAPE: {metrics['mape']:.2f}%")
    else:
        print("\n✅ Model already loaded and ready")
    
    # Get sample data info
    dept_count = db.query(Department).count()
    sales_count = db.query(SalesSummary).count()
    
    print(f"\nDatabase status:")
    print(f"  - Departments: {dept_count}")
    print(f"  - Sales records: {sales_count}")
    
    # Test endpoints
    print("\n" + "=" * 60)
    print("API ENDPOINTS FOR UI")
    print("=" * 60)
    
    print("\n1. Forecast by Branch:")
    print("   GET /api/forecast/batch?from_date=2025-07-01&to_date=2025-07-07")
    print("   - Returns forecasts for all branches for the date range")
    
    print("\n2. Forecast Comparison:")
    print("   GET /api/forecast/comparison?from_date=2025-06-01&to_date=2025-06-30")
    print("   - Compares predictions with actual sales")
    
    print("\n3. Export to CSV:")
    print("   GET /api/forecast/export/csv?from_date=2025-07-01&to_date=2025-07-31")
    print("   - Downloads CSV file with forecasts")
    
    print("\n4. Model Info:")
    print("   GET /api/forecast/model/info")
    print("   - Returns model status and metadata")
    
    print("\n5. Retrain Model:")
    print("   POST /api/forecast/retrain")
    print("   - Retrains model with latest data")
    
    print("\n" + "=" * 60)
    print("UI NAVIGATION")
    print("=" * 60)
    
    print("\nTo access the forecast features:")
    print("1. Open http://localhost:8002/")
    print("2. In the sidebar, look for 'ПРОГНОЗ ПРОДАЖ' section")
    print("3. Click on:")
    print("   - 📈 Прогноз по филиалам - View forecasts by branch")
    print("   - 📊 Сравнение факт/прогноз - Compare predictions with actuals")
    print("   - 📤 Экспорт прогноза - Export forecasts to CSV")
    
    print("\n" + "=" * 60)
    print("TESTING CHECKLIST")
    print("=" * 60)
    
    print("\n✓ Check that new menu items appear in sidebar")
    print("✓ Test 'Прогноз по филиалам' page:")
    print("  - Select date range")
    print("  - Click 'Обновить прогноз'")
    print("  - Verify forecasts display with ₸ formatting")
    
    print("\n✓ Test 'Сравнение факт/прогноз' page:")
    print("  - Select historical date range")
    print("  - Click 'Загрузить'")
    print("  - Verify error percentages show")
    print("  - Test sorting by clicking column headers")
    
    print("\n✓ Test 'Экспорт прогноза' page:")
    print("  - Select date range")
    print("  - Toggle 'Include actual data' checkbox")
    print("  - Click 'Экспорт в CSV'")
    print("  - Verify file downloads")
    
    print("\n✓ Test model retraining:")
    print("  - Go to Export page")
    print("  - Click '🔄 Переобучить модель'")
    print("  - Verify training completes and metrics show")

if __name__ == "__main__":
    main()