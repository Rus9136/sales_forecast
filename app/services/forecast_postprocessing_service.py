"""
Forecast Post-processing Service

This service provides post-processing capabilities for sales forecasts
to make them more reliable and business-friendly.

Features:
- Forecast smoothing to prevent unrealistic jumps
- Business rules and constraints
- Anomaly detection for unusual predictions
- Confidence intervals and uncertainty estimates
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from typing import Optional, Dict, List, Tuple, Any
import logging
import warnings
from scipy import stats
from sklearn.metrics import mean_absolute_error

from ..models.branch import SalesSummary, Department
from ..agents.sales_forecaster_agent import get_forecaster_agent

logger = logging.getLogger(__name__)


class ForecastPostprocessingService:
    """Service for post-processing forecasts to improve reliability and business value"""
    
    def __init__(self, db: Session):
        self.db = db
        self.forecaster = get_forecaster_agent()
    
    def process_forecast(
        self,
        branch_id: str,
        forecast_date: date,
        raw_prediction: float,
        apply_smoothing: bool = True,
        apply_business_rules: bool = True,
        apply_anomaly_detection: bool = True,
        calculate_confidence: bool = True
    ) -> Dict[str, Any]:
        """
        Apply post-processing to a raw forecast prediction
        
        Args:
            branch_id: Department/branch ID
            forecast_date: Date being forecasted
            raw_prediction: Raw prediction from ML model
            apply_smoothing: Whether to apply smoothing
            apply_business_rules: Whether to apply business rules
            apply_anomaly_detection: Whether to check for anomalies
            calculate_confidence: Whether to calculate confidence intervals
            
        Returns:
            Dict with processed forecast and metadata
        """
        result = {
            'branch_id': str(branch_id),
            'forecast_date': forecast_date.isoformat(),
            'raw_prediction': float(raw_prediction),
            'processed_prediction': float(raw_prediction),
            'adjustments_applied': [],
            'confidence_interval': None,
            'anomaly_score': None,
            'is_anomaly': False,
            'business_flags': []
        }
        
        try:
            # Get historical context
            historical_data = self._get_historical_context(branch_id, forecast_date)
            
            if historical_data.empty:
                logger.warning(f"No historical data for branch {branch_id}, skipping post-processing")
                return result
            
            processed_value = raw_prediction
            
            # 1. Apply smoothing
            if apply_smoothing:
                smoothed_value = self._apply_smoothing(
                    processed_value, historical_data, forecast_date
                )
                if abs(smoothed_value - processed_value) > 0.01:
                    result['adjustments_applied'].append({
                        'type': 'smoothing',
                        'original': processed_value,
                        'adjusted': smoothed_value,
                        'reason': 'Reduced unrealistic jump'
                    })
                    processed_value = smoothed_value
            
            # 2. Apply business rules
            if apply_business_rules:
                rule_adjusted_value = self._apply_business_rules(
                    processed_value, historical_data, forecast_date, branch_id
                )
                if abs(rule_adjusted_value - processed_value) > 0.01:
                    result['adjustments_applied'].append({
                        'type': 'business_rules',
                        'original': processed_value,
                        'adjusted': rule_adjusted_value,
                        'reason': 'Applied business constraints'
                    })
                    processed_value = rule_adjusted_value
            
            # 3. Anomaly detection
            if apply_anomaly_detection:
                anomaly_info = self._detect_forecast_anomalies(
                    processed_value, historical_data, forecast_date
                )
                result['anomaly_score'] = anomaly_info['score']
                result['is_anomaly'] = anomaly_info['is_anomaly']
                if anomaly_info['is_anomaly']:
                    result['business_flags'].append('anomaly_detected')
            
            # 4. Calculate confidence intervals
            if calculate_confidence:
                confidence_info = self._calculate_confidence_interval(
                    processed_value, historical_data, branch_id
                )
                result['confidence_interval'] = confidence_info
            
            # Add business context flags
            result['business_flags'].extend(
                self._get_business_context_flags(forecast_date, historical_data)
            )
            
            result['processed_prediction'] = float(processed_value)
            
            logger.info(f"Post-processed forecast for {branch_id} on {forecast_date}: "
                       f"{raw_prediction:.2f} → {processed_value:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in forecast post-processing: {str(e)}")
            result['error'] = str(e)
            return result
    
    def batch_process_forecasts(
        self,
        forecasts: List[Dict[str, Any]],
        **processing_options
    ) -> List[Dict[str, Any]]:
        """
        Apply post-processing to a batch of forecasts
        
        Args:
            forecasts: List of forecast dicts with 'branch_id', 'forecast_date', 'prediction'
            **processing_options: Options to pass to process_forecast
            
        Returns:
            List of processed forecasts
        """
        processed_forecasts = []
        
        for forecast in forecasts:
            try:
                processed = self.process_forecast(
                    branch_id=forecast['branch_id'],
                    forecast_date=pd.to_datetime(forecast['forecast_date']).date(),
                    raw_prediction=forecast['prediction'],
                    **processing_options
                )
                processed_forecasts.append(processed)
                
            except Exception as e:
                logger.error(f"Error processing forecast {forecast}: {str(e)}")
                # Add error result
                error_result = forecast.copy()
                error_result['error'] = str(e)
                processed_forecasts.append(error_result)
        
        return processed_forecasts
    
    def _get_historical_context(
        self, 
        branch_id: str, 
        forecast_date: date, 
        days_back: int = 30
    ) -> pd.DataFrame:
        """Get historical sales data for context"""
        
        start_date = forecast_date - timedelta(days=days_back)
        end_date = forecast_date - timedelta(days=1)
        
        query = self.db.query(
            SalesSummary.date,
            SalesSummary.total_sales
        ).filter(
            and_(
                SalesSummary.department_id == branch_id,
                SalesSummary.date >= start_date,
                SalesSummary.date <= end_date
            )
        ).order_by(SalesSummary.date)
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=['date', 'total_sales'])
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values('date')
    
    def _apply_smoothing(
        self, 
        prediction: float, 
        historical_data: pd.DataFrame, 
        forecast_date: date,
        max_change_percent: float = 50.0
    ) -> float:
        """
        Apply smoothing to prevent unrealistic jumps
        
        Args:
            prediction: Raw prediction value
            historical_data: Historical sales data
            forecast_date: Date being forecasted
            max_change_percent: Maximum allowed percentage change
            
        Returns:
            Smoothed prediction value
        """
        if historical_data.empty or len(historical_data) < 3:
            return prediction
        
        # Calculate recent average (last 7 days)
        recent_avg = historical_data['total_sales'].tail(7).mean()
        
        # Calculate percentage change
        if recent_avg > 0:
            pct_change = ((prediction - recent_avg) / recent_avg) * 100
            
            # If change is too large, cap it
            if abs(pct_change) > max_change_percent:
                # Determine direction and apply cap
                direction = 1 if pct_change > 0 else -1
                capped_change = direction * max_change_percent
                
                smoothed_prediction = recent_avg * (1 + capped_change / 100)
                
                logger.info(f"Smoothing applied: {pct_change:.1f}% → {capped_change:.1f}%, "
                           f"prediction: {prediction:.2f} → {smoothed_prediction:.2f}")
                
                return max(0, smoothed_prediction)  # Ensure non-negative
        
        return prediction
    
    def _apply_business_rules(
        self, 
        prediction: float, 
        historical_data: pd.DataFrame, 
        forecast_date: date,
        branch_id: str
    ) -> float:
        """
        Apply business rules and constraints
        
        Args:
            prediction: Current prediction value
            historical_data: Historical sales data
            forecast_date: Date being forecasted
            branch_id: Department/branch ID
            
        Returns:
            Rule-adjusted prediction
        """
        adjusted_prediction = prediction
        
        # Rule 1: Minimum sales floor (based on historical minimum)
        if not historical_data.empty:
            historical_min = historical_data['total_sales'].min()
            min_floor = max(0, historical_min * 0.1)  # 10% of historical minimum
            
            if adjusted_prediction < min_floor:
                adjusted_prediction = min_floor
                logger.info(f"Applied minimum floor: {prediction:.2f} → {adjusted_prediction:.2f}")
        
        # Rule 2: Maximum sales ceiling (based on historical maximum)
        if not historical_data.empty:
            historical_max = historical_data['total_sales'].max()
            max_ceiling = historical_max * 2.0  # 200% of historical maximum
            
            if adjusted_prediction > max_ceiling:
                adjusted_prediction = max_ceiling
                logger.info(f"Applied maximum ceiling: {prediction:.2f} → {adjusted_prediction:.2f}")
        
        # Rule 3: Weekend adjustment for specific business types
        department = self.db.query(Department).filter(Department.id == branch_id).first()
        if department and forecast_date.weekday() >= 5:  # Weekend
            if hasattr(department, 'segment_type') and department.segment_type in ['coffeehouse', 'cafe']:
                # Coffeehouses typically have higher weekend sales
                weekend_boost = 1.1  # 10% boost
                adjusted_prediction *= weekend_boost
        
        # Rule 4: Holiday proximity adjustment
        if self._is_near_holiday(forecast_date):
            holiday_adjustment = 1.15  # 15% increase near holidays
            adjusted_prediction *= holiday_adjustment
        
        return max(0, adjusted_prediction)  # Ensure non-negative
    
    def _detect_forecast_anomalies(
        self, 
        prediction: float, 
        historical_data: pd.DataFrame, 
        forecast_date: date,
        z_threshold: float = 3.0
    ) -> Dict[str, Any]:
        """
        Detect if forecast is anomalous compared to historical patterns
        
        Args:
            prediction: Prediction value to check
            historical_data: Historical sales data
            forecast_date: Date being forecasted  
            z_threshold: Z-score threshold for anomaly detection
            
        Returns:
            Dict with anomaly information
        """
        if historical_data.empty or len(historical_data) < 7:
            return {'score': 0.0, 'is_anomaly': False, 'reason': 'insufficient_data'}
        
        # Calculate z-score relative to historical mean and std
        historical_mean = historical_data['total_sales'].mean()
        historical_std = historical_data['total_sales'].std()
        
        if historical_std == 0:
            z_score = 0.0
        else:
            z_score = abs((prediction - historical_mean) / historical_std)
        
        is_anomaly = z_score > z_threshold
        
        result = {
            'score': float(z_score),
            'is_anomaly': bool(is_anomaly),
            'historical_mean': float(historical_mean),
            'historical_std': float(historical_std),
            'threshold': float(z_threshold)
        }
        
        if is_anomaly:
            result['reason'] = f'z_score_{z_score:.2f}_exceeds_threshold_{z_threshold}'
            logger.warning(f"Anomaly detected: prediction {prediction:.2f}, "
                          f"z-score {z_score:.2f} > {z_threshold}")
        
        return result
    
    def _calculate_confidence_interval(
        self, 
        prediction: float, 
        historical_data: pd.DataFrame, 
        branch_id: str,
        confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """
        Calculate confidence intervals for the prediction
        
        Args:
            prediction: Central prediction value
            historical_data: Historical sales data
            branch_id: Department/branch ID
            confidence_level: Confidence level (0.95 = 95%)
            
        Returns:
            Dict with confidence interval information
        """
        if historical_data.empty or len(historical_data) < 3:
            return {
                'lower_bound': prediction * 0.8,
                'upper_bound': prediction * 1.2,
                'confidence_level': confidence_level,
                'method': 'default_range'
            }
        
        # Method 1: Based on historical volatility
        historical_std = historical_data['total_sales'].std()
        historical_mean = historical_data['total_sales'].mean()
        
        # Calculate coefficient of variation
        cv = historical_std / historical_mean if historical_mean > 0 else 0.3
        
        # Use normal distribution assumption
        alpha = 1 - confidence_level
        z_critical = stats.norm.ppf(1 - alpha/2)
        
        # Estimate prediction standard error as fraction of prediction
        prediction_std = prediction * min(cv, 0.5)  # Cap at 50% CV
        
        margin_of_error = z_critical * prediction_std
        
        lower_bound = max(0, prediction - margin_of_error)
        upper_bound = prediction + margin_of_error
        
        return {
            'lower_bound': float(lower_bound),
            'upper_bound': float(upper_bound),
            'confidence_level': float(confidence_level),
            'method': 'historical_volatility',
            'coefficient_of_variation': float(cv),
            'margin_of_error': float(margin_of_error)
        }
    
    def _get_business_context_flags(
        self, 
        forecast_date: date, 
        historical_data: pd.DataFrame
    ) -> List[str]:
        """Get business context flags for the forecast date"""
        flags = []
        
        # Day of week context
        if forecast_date.weekday() >= 5:
            flags.append('weekend')
        if forecast_date.weekday() == 4:
            flags.append('friday')
        if forecast_date.weekday() == 0:
            flags.append('monday')
        
        # Month context
        if forecast_date.day <= 7:
            flags.append('month_start')
        if forecast_date.day >= 25:
            flags.append('month_end')
        
        # Holiday context
        if self._is_near_holiday(forecast_date):
            flags.append('near_holiday')
        if self._is_kazakhstan_holiday(forecast_date):
            flags.append('holiday')
        
        # Data quality context
        if not historical_data.empty:
            recent_data_points = len(historical_data.tail(7))
            if recent_data_points < 7:
                flags.append('limited_recent_data')
            
            # Check for recent volatility
            if len(historical_data) >= 7:
                recent_cv = historical_data['total_sales'].tail(7).std() / historical_data['total_sales'].tail(7).mean()
                if recent_cv > 0.5:
                    flags.append('high_recent_volatility')
        
        return flags
    
    def _is_near_holiday(self, date_obj: date, days_before: int = 3) -> bool:
        """Check if date is near a holiday"""
        for i in range(1, days_before + 1):
            check_date = date_obj + timedelta(days=i)
            if self._is_kazakhstan_holiday(check_date):
                return True
        return False
    
    def _is_kazakhstan_holiday(self, date_obj: date) -> bool:
        """Check if date is a Kazakhstan holiday"""
        month = date_obj.month
        day = date_obj.day
        
        # Fixed holidays
        fixed_holidays = [
            (1, 1), (1, 2),   # New Year
            (3, 8),           # Women's Day
            (3, 21), (3, 22), (3, 23),  # Nauryz
            (5, 1),           # Unity Day
            (5, 7),           # Defender's Day
            (5, 9),           # Victory Day
            (7, 6),           # Capital Day
            (8, 30),          # Constitution Day
            (12, 1),          # First President Day
            (12, 16), (12, 17) # Independence Day
        ]
        
        return (month, day) in fixed_holidays


def get_forecast_postprocessing_service(db: Session) -> ForecastPostprocessingService:
    """Factory function to get ForecastPostprocessingService instance"""
    return ForecastPostprocessingService(db)