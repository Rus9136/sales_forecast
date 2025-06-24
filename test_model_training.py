#!/usr/bin/env python3
"""
Script to test model training and forecasting
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta
from app.db import get_db
from app.agents.sales_forecaster_agent import get_forecaster_agent
from app.models.branch import Department
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    # Get database session
    db = next(get_db())
    
    # Get forecaster agent
    forecaster = get_forecaster_agent()
    
    print("=" * 60)
    print("SALES FORECASTING MODEL TRAINING")
    print("=" * 60)
    
    # Train the model
    print("\n1. Training model on historical data...")
    try:
        metrics = forecaster.train_model(db, test_size=0.2, save_model=True)
        
        print("\n📊 Training Results:")
        print(f"   MAE (Mean Absolute Error): {metrics['mae']:,.2f}")
        print(f"   MAPE (Mean Absolute Percentage Error): {metrics['mape']:.2f}%")
        print(f"   R² Score: {metrics['r2']:.4f}")
        print(f"   RMSE (Root Mean Square Error): {metrics['rmse']:,.2f}")
        print(f"   Training samples: {metrics['train_samples']}")
        print(f"   Test samples: {metrics['test_samples']}")
        
    except Exception as e:
        print(f"❌ Error during training: {str(e)}")
        return
    
    print("\n" + "=" * 60)
    print("TESTING FORECAST FUNCTION")
    print("=" * 60)
    
    # Get a sample department for testing
    sample_dept = db.query(Department).first()
    
    if sample_dept:
        # Test forecast for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        
        print(f"\n2. Testing forecast for department: {sample_dept.name}")
        print(f"   Department ID: {sample_dept.id}")
        print(f"   Forecast date: {tomorrow}")
        
        prediction = forecaster.forecast(
            branch_id=str(sample_dept.id),
            forecast_date=tomorrow,
            db=db
        )
        
        if prediction is not None:
            print(f"\n✅ Forecast result: {prediction:,.2f}")
        else:
            print("\n⚠️  Could not generate forecast (insufficient historical data)")
    else:
        print("\n⚠️  No departments found in database")
    
    # Show model info
    print("\n" + "=" * 60)
    print("MODEL INFORMATION")
    print("=" * 60)
    
    model_info = forecaster.get_model_info()
    print(f"\nModel status: {model_info['status']}")
    print(f"Model path: {model_info['model_path']}")
    if model_info['status'] == 'loaded':
        print(f"Model type: {model_info['model_type']}")
        print(f"Number of features: {model_info['n_features']}")
        print(f"Features: {', '.join(model_info['feature_names'][:5])}...")
    
    print("\n" + "=" * 60)
    print("HOW TO RETRAIN MODEL")
    print("=" * 60)
    print("""
To retrain the model with updated data:

1. From Python code:
   ```python
   from app.db import get_db
   from app.agents.sales_forecaster_agent import get_forecaster_agent
   
   db = next(get_db())
   forecaster = get_forecaster_agent()
   metrics = forecaster.retrain_model(db)
   ```

2. Via API endpoint (after Step 3):
   ```bash
   curl -X POST http://localhost:8002/api/forecast/retrain
   ```

3. Schedule automatic retraining:
   - Daily at night
   - After significant data updates
   - When accuracy drops below threshold
""")

if __name__ == "__main__":
    main()