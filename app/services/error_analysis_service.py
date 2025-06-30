"""
Error Analysis Service for Sales Forecasting Model

This service provides comprehensive error analysis and visualization 
for identifying problematic segments and improving model performance.
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from typing import Optional, Dict, List, Tuple, Any
import logging
import json

from ..models.branch import SalesSummary, Department
from ..agents.sales_forecaster_agent import get_forecaster_agent

logger = logging.getLogger(__name__)


class ErrorAnalysisService:
    """Service for analyzing prediction errors and identifying problem segments"""
    
    def __init__(self, db: Session):
        self.db = db
        self.forecaster = get_forecaster_agent()
    
    def analyze_errors_by_segment(
        self,
        from_date: date,
        to_date: date,
        segment_type: str = 'department'
    ) -> Dict[str, Any]:
        """
        Analyze prediction errors by different segments
        
        Args:
            from_date: Start date for analysis
            to_date: End date for analysis  
            segment_type: Type of segmentation ('department', 'day_of_week', 'month', 'location')
            
        Returns:
            Dict with error analysis by segments
        """
        logger.info(f"Analyzing errors by {segment_type} from {from_date} to {to_date}")
        
        # Get actual sales and predictions
        comparison_data = self._get_forecast_comparison_data(from_date, to_date)
        
        if not comparison_data:
            return {"error": "No data available for analysis"}
        
        # Convert to DataFrame for analysis
        df = pd.DataFrame(comparison_data)
        df = df.dropna(subset=['predicted_sales', 'actual_sales', 'error_percentage'])
        
        if df.empty:
            return {"error": "No valid predictions available for analysis"}
        
        # Perform segmentation analysis
        if segment_type == 'department':
            return self._analyze_by_department(df)
        elif segment_type == 'day_of_week':
            return self._analyze_by_day_of_week(df)
        elif segment_type == 'month':
            return self._analyze_by_month(df)
        elif segment_type == 'location':
            return self._analyze_by_location(df)
        else:
            return {"error": f"Unknown segment type: {segment_type}"}
    
    def identify_problematic_branches(
        self,
        from_date: date,
        to_date: date,
        min_samples: int = 5,
        mape_threshold: float = 15.0
    ) -> List[Dict[str, Any]]:
        """
        Identify branches with consistently high prediction errors
        
        Args:
            from_date: Start date for analysis
            to_date: End date for analysis
            min_samples: Minimum number of predictions required
            mape_threshold: MAPE threshold for considering branch problematic
            
        Returns:
            List of problematic branches with error statistics
        """
        logger.info(f"Identifying problematic branches with MAPE > {mape_threshold}%")
        
        # Get comparison data
        comparison_data = self._get_forecast_comparison_data(from_date, to_date)
        df = pd.DataFrame(comparison_data)
        df = df.dropna(subset=['predicted_sales', 'actual_sales', 'error_percentage'])
        
        # Group by department and calculate statistics
        branch_stats = df.groupby(['department_id', 'department_name']).agg({
            'error_percentage': ['count', 'mean', 'std', 'min', 'max'],
            'error': ['mean', 'std'],
            'actual_sales': ['mean', 'sum'],
            'predicted_sales': ['mean']
        }).round(2)
        
        # Flatten column names
        branch_stats.columns = [f"{col[1]}_{col[0]}" if col[1] else col[0] for col in branch_stats.columns]
        branch_stats = branch_stats.reset_index()
        
        # Filter problematic branches
        problematic = branch_stats[
            (branch_stats['count_error_percentage'] >= min_samples) &
            (branch_stats['mean_error_percentage'] > mape_threshold)
        ].sort_values('mean_error_percentage', ascending=False)
        
        # Convert to list of dicts
        result = []
        for _, row in problematic.iterrows():
            result.append({
                'department_id': row['department_id'],
                'department_name': row['department_name'],
                'predictions_count': int(row['count_error_percentage']),
                'avg_mape': round(row['mean_error_percentage'], 2),
                'mape_std': round(row['std_error_percentage'], 2),
                'min_mape': round(row['min_error_percentage'], 2),
                'max_mape': round(row['max_error_percentage'], 2),
                'avg_actual_sales': round(row['mean_actual_sales'], 2),
                'avg_predicted_sales': round(row['mean_predicted_sales'], 2),
                'total_actual_sales': round(row['sum_actual_sales'], 2),
                'avg_error': round(row['mean_error'], 2),
                'error_consistency': round(row['std_error'], 2)
            })
        
        logger.info(f"Found {len(result)} problematic branches")
        return result
    
    def analyze_temporal_errors(
        self,
        from_date: date,
        to_date: date
    ) -> Dict[str, Any]:
        """
        Analyze how prediction errors vary over time
        
        Returns:
            Temporal error analysis with trends and patterns
        """
        logger.info(f"Analyzing temporal error patterns from {from_date} to {to_date}")
        
        comparison_data = self._get_forecast_comparison_data(from_date, to_date)
        df = pd.DataFrame(comparison_data)
        df = df.dropna(subset=['predicted_sales', 'actual_sales', 'error_percentage'])
        
        if df.empty:
            return {"error": "No data available for temporal analysis"}
        
        # Convert date column
        df['date'] = pd.to_datetime(df['date'])
        df['day_of_week'] = df['date'].dt.dayofweek
        df['day_name'] = df['date'].dt.day_name()
        df['week'] = df['date'].dt.isocalendar().week
        df['month'] = df['date'].dt.month
        
        # Daily aggregation
        daily_errors = df.groupby('date').agg({
            'error_percentage': ['mean', 'std', 'count'],
            'error': ['mean', 'std'],
            'actual_sales': 'sum',
            'predicted_sales': 'sum'
        }).round(2)
        
        daily_errors.columns = [f"{col[1]}_{col[0]}" if col[1] else col[0] for col in daily_errors.columns]
        daily_errors = daily_errors.reset_index()
        
        # Day of week analysis
        dow_errors = df.groupby(['day_of_week', 'day_name']).agg({
            'error_percentage': ['mean', 'std', 'count'],
            'actual_sales': 'mean'
        }).round(2)
        
        dow_errors.columns = [f"{col[1]}_{col[0]}" if col[1] else col[0] for col in dow_errors.columns]
        dow_errors = dow_errors.reset_index()
        
        # Monthly analysis  
        monthly_errors = df.groupby('month').agg({
            'error_percentage': ['mean', 'std', 'count']
        }).round(2)
        
        monthly_errors.columns = [f"{col[1]}_{col[0]}" if col[1] else col[0] for col in monthly_errors.columns]
        monthly_errors = monthly_errors.reset_index()
        
        return {
            'daily_errors': daily_errors.to_dict('records'),
            'day_of_week_errors': dow_errors.to_dict('records'),
            'monthly_errors': monthly_errors.to_dict('records'),
            'overall_stats': {
                'total_predictions': len(df),
                'avg_mape': round(df['error_percentage'].mean(), 2),
                'mape_std': round(df['error_percentage'].std(), 2),
                'best_day_mape': round(dow_errors['mean_error_percentage'].min(), 2),
                'worst_day_mape': round(dow_errors['mean_error_percentage'].max(), 2),
                'date_range': f"{from_date} to {to_date}"
            }
        }
    
    def get_error_distribution(
        self,
        from_date: date,
        to_date: date,
        department_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get distribution of prediction errors for statistical analysis
        
        Returns:
            Error distribution statistics and percentiles
        """
        logger.info("Analyzing error distribution")
        
        comparison_data = self._get_forecast_comparison_data(from_date, to_date, department_id)
        df = pd.DataFrame(comparison_data)
        df = df.dropna(subset=['predicted_sales', 'actual_sales', 'error_percentage'])
        
        if df.empty:
            return {"error": "No data available for distribution analysis"}
        
        errors = df['error_percentage']
        
        # Calculate distribution statistics
        stats = {
            'count': len(errors),
            'mean': round(errors.mean(), 2),
            'median': round(errors.median(), 2),
            'std': round(errors.std(), 2),
            'min': round(errors.min(), 2),
            'max': round(errors.max(), 2),
            'percentiles': {
                'p5': round(errors.quantile(0.05), 2),
                'p10': round(errors.quantile(0.10), 2),
                'p25': round(errors.quantile(0.25), 2),
                'p75': round(errors.quantile(0.75), 2),
                'p90': round(errors.quantile(0.90), 2),
                'p95': round(errors.quantile(0.95), 2),
                'p99': round(errors.quantile(0.99), 2)
            },
            'outliers': {
                'high_error_count': len(errors[errors > 20]),  # MAPE > 20%
                'very_high_error_count': len(errors[errors > 50]),  # MAPE > 50%
                'low_error_count': len(errors[errors < 5])  # MAPE < 5%
            }
        }
        
        # Error ranges distribution
        ranges = [
            (0, 5, 'Excellent'),
            (5, 10, 'Good'),
            (10, 15, 'Acceptable'),
            (15, 25, 'Poor'),
            (25, float('inf'), 'Very Poor')
        ]
        
        range_distribution = []
        for min_val, max_val, label in ranges:
            if max_val == float('inf'):
                count = len(errors[errors >= min_val])
            else:
                count = len(errors[(errors >= min_val) & (errors < max_val)])
            
            percentage = round((count / len(errors)) * 100, 1) if len(errors) > 0 else 0
            range_distribution.append({
                'range': f"{min_val}-{max_val if max_val != float('inf') else '∞'}%",
                'label': label,
                'count': count,
                'percentage': percentage
            })
        
        return {
            'statistics': stats,
            'range_distribution': range_distribution,
            'sample_size': len(df),
            'date_range': f"{from_date} to {to_date}"
        }
    
    def _get_forecast_comparison_data(
        self,
        from_date: date,
        to_date: date,
        department_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get forecast comparison data from database"""
        
        # Get actual sales data
        sales_query = self.db.query(SalesSummary).filter(
            and_(
                SalesSummary.date >= from_date,
                SalesSummary.date <= to_date
            )
        )
        
        if department_id:
            sales_query = sales_query.filter(SalesSummary.department_id == department_id)
        
        sales_data = sales_query.all()
        
        results = []
        for sale in sales_data:
            # Get department info
            department = self.db.query(Department).filter(Department.id == sale.department_id).first()
            
            # Get prediction
            try:
                prediction = self.forecaster.forecast(str(sale.department_id), sale.date, self.db)
            except Exception as pred_error:
                logger.warning(f"Failed to get prediction for {sale.date}, {sale.department_id}: {pred_error}")
                prediction = None
            
            # Calculate error if we have both values
            error = None
            error_percentage = None
            if prediction and sale.total_sales:
                error = prediction - sale.total_sales
                error_percentage = (abs(error) / sale.total_sales) * 100
            
            results.append({
                "date": sale.date.isoformat(),
                "department_id": str(sale.department_id),
                "department_name": department.name if department else "Unknown",
                "department_type": department.type if department else None,
                "segment_type": department.segment_type if department else None,
                "predicted_sales": round(prediction, 2) if prediction else None,
                "actual_sales": sale.total_sales,
                "error": round(error, 2) if error else None,
                "error_percentage": round(error_percentage, 2) if error_percentage else None
            })
        
        return results
    
    def _analyze_by_department(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze errors by department"""
        dept_analysis = df.groupby('department_name').agg({
            'error_percentage': ['count', 'mean', 'std'],
            'actual_sales': 'mean'
        }).round(2)
        
        dept_analysis.columns = [f"{col[1]}_{col[0]}" for col in dept_analysis.columns]
        dept_analysis = dept_analysis.reset_index()
        dept_analysis = dept_analysis.sort_values('mean_error_percentage', ascending=False)
        
        return {
            'segment_type': 'department',
            'analysis': dept_analysis.head(20).to_dict('records'),  # Top 20 worst performing
            'summary': {
                'total_departments': len(dept_analysis),
                'avg_mape': round(df['error_percentage'].mean(), 2),
                'best_department': dept_analysis.iloc[-1]['department_name'],
                'worst_department': dept_analysis.iloc[0]['department_name'],
                'best_mape': round(dept_analysis.iloc[-1]['mean_error_percentage'], 2),
                'worst_mape': round(dept_analysis.iloc[0]['mean_error_percentage'], 2)
            }
        }
    
    def _analyze_by_day_of_week(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze errors by day of week"""
        df['date'] = pd.to_datetime(df['date'])
        df['day_of_week'] = df['date'].dt.day_name()
        
        dow_analysis = df.groupby('day_of_week').agg({
            'error_percentage': ['count', 'mean', 'std'],
            'actual_sales': 'mean'
        }).round(2)
        
        dow_analysis.columns = [f"{col[1]}_{col[0]}" for col in dow_analysis.columns]
        dow_analysis = dow_analysis.reset_index()
        
        # Order by day of week
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        dow_analysis['day_order'] = dow_analysis['day_of_week'].map({day: i for i, day in enumerate(day_order)})
        dow_analysis = dow_analysis.sort_values('day_order')
        
        return {
            'segment_type': 'day_of_week',
            'analysis': dow_analysis.to_dict('records'),
            'summary': {
                'avg_mape': round(df['error_percentage'].mean(), 2),
                'best_day': dow_analysis.loc[dow_analysis['mean_error_percentage'].idxmin(), 'day_of_week'],
                'worst_day': dow_analysis.loc[dow_analysis['mean_error_percentage'].idxmax(), 'day_of_week'],
                'weekend_vs_weekday': {
                    'weekend_mape': round(df[df['date'].dt.dayofweek.isin([5, 6])]['error_percentage'].mean(), 2),
                    'weekday_mape': round(df[~df['date'].dt.dayofweek.isin([5, 6])]['error_percentage'].mean(), 2)
                }
            }
        }
    
    def _analyze_by_month(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze errors by month"""
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.month
        df['month_name'] = df['date'].dt.month_name()
        
        month_analysis = df.groupby(['month', 'month_name']).agg({
            'error_percentage': ['count', 'mean', 'std'],
            'actual_sales': 'mean'
        }).round(2)
        
        month_analysis.columns = [f"{col[1]}_{col[0]}" for col in month_analysis.columns]
        month_analysis = month_analysis.reset_index()
        month_analysis = month_analysis.sort_values('month')
        
        return {
            'segment_type': 'month',
            'analysis': month_analysis.to_dict('records'),
            'summary': {
                'avg_mape': round(df['error_percentage'].mean(), 2),
                'best_month': month_analysis.loc[month_analysis['mean_error_percentage'].idxmin(), 'month_name'],
                'worst_month': month_analysis.loc[month_analysis['mean_error_percentage'].idxmax(), 'month_name'],
                'seasonal_variation': round(month_analysis['mean_error_percentage'].std(), 2)
            }
        }
    
    def _analyze_by_location(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze errors by location (based on department names)"""
        # Extract location from department names
        df['location'] = 'Other'
        df.loc[df['department_name'].str.contains('Алматы|Almaty', na=False), 'location'] = 'Almaty'
        df.loc[df['department_name'].str.contains('Астана|Astana|Нур-Султан', na=False), 'location'] = 'Astana'
        df.loc[df['department_name'].str.contains('Шымкент|Shymkent', na=False), 'location'] = 'Shymkent'
        
        location_analysis = df.groupby('location').agg({
            'error_percentage': ['count', 'mean', 'std'],
            'actual_sales': 'mean'
        }).round(2)
        
        location_analysis.columns = [f"{col[1]}_{col[0]}" for col in location_analysis.columns]
        location_analysis = location_analysis.reset_index()
        location_analysis = location_analysis.sort_values('mean_error_percentage', ascending=False)
        
        return {
            'segment_type': 'location',
            'analysis': location_analysis.to_dict('records'),
            'summary': {
                'avg_mape': round(df['error_percentage'].mean(), 2),
                'best_location': location_analysis.iloc[-1]['location'],
                'worst_location': location_analysis.iloc[0]['location'],
                'location_count': len(location_analysis)
            }
        }


def get_error_analysis_service(db: Session) -> ErrorAnalysisService:
    """Factory function to get ErrorAnalysisService instance"""
    return ErrorAnalysisService(db)