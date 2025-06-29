import httpx
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime, date, timedelta
from ..models.branch import SalesSummary, SalesByHour, Department
from ..services.iiko_auth import IikoAuthService
import logging
import pandas as pd
from collections import defaultdict

logger = logging.getLogger(__name__)


class IikoSalesLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [
            "https://sandy-co-co.iiko.it",
            "https://madlen-group-so.iiko.it"
        ]
    
    async def fetch_sales_from_single_domain(self, base_url: str, from_date: date, to_date: date) -> List[dict]:
        """Fetch sales data from a single iiko domain"""
        try:
            # Always get fresh token before making request
            auth_service = IikoAuthService(base_url)
            token = await auth_service._refresh_token()  # Force fresh token
            logger.info(f"Got fresh token for {base_url}: {token[:10]}...")
            
            # Prepare request body
            request_body = {
                "reportType": "SALES",
                "groupByRowFields": [
                    "Department.Id",
                    "CloseTime",
                    "OrderNum"
                ],
                "aggregateFields": [
                    "DishSumInt"
                ],
                "filters": {
                    "OpenDate.Typed": {
                        "filterType": "DateRange",
                        "periodType": "CUSTOM",
                        "from": from_date.strftime("%Y-%m-%d"),
                        "to": to_date.strftime("%Y-%m-%d")
                    },
                    "OrderDeleted": {
                        "filterType": "IncludeValues",
                        "values": ["NOT_DELETED"]
                    },
                    "DeletedWithWriteoff": {
                        "filterType": "IncludeValues",
                        "values": ["NOT_DELETED"]
                    }
                }
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{base_url}/resto/api/v2/reports/olap",
                    params={"key": token},
                    json=request_body
                )
                response.raise_for_status()
                
                # Check if response is valid JSON
                try:
                    response_data = response.json()
                except Exception as json_error:
                    logger.error(f"Invalid JSON response from {base_url}. Status: {response.status_code}, Text: {response.text[:200]}")
                    raise Exception(f"Invalid JSON response: {json_error}")
                
                # Extract data from the response wrapper
                sales_data = response_data.get('data', [])
                logger.info(f"Fetched {len(sales_data)} sales records from {base_url}")
                return sales_data
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error fetching sales from {base_url}: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response status: {e.response.status_code}, text: {e.response.text[:200]}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error from {base_url}: {e}")
            return []
    
    async def fetch_sales_from_iiko(self, from_date: date, to_date: date) -> List[dict]:
        """Fetch sales data from all iiko domains"""
        all_sales = []
        
        logger.info(f"Fetching sales from {len(self.domains)} domains")
        
        for domain in self.domains:
            try:
                logger.info(f"Trying to fetch from domain: {domain}")
                sales = await self.fetch_sales_from_single_domain(domain, from_date, to_date)
                logger.info(f"Got {len(sales)} records from {domain}")
                all_sales.extend(sales)
            except Exception as e:
                logger.error(f"Failed to fetch sales from {domain}: {e}")
                # Continue with other domains even if one fails
                continue
        
        logger.info(f"Total fetched {len(all_sales)} sales records from all domains")
        logger.info(f"About to return sales data: {all_sales is not None}")
        return all_sales
    
    def process_sales_data(self, sales_data: List[dict]) -> tuple[List[dict], List[dict]]:
        """Process sales data to create summary and hourly records"""
        if not sales_data:
            return [], []
        
        # Convert to DataFrame for easier processing
        df = pd.DataFrame(sales_data)
        
        # Debug: log the first few records to understand structure
        logger.info(f"Sales data sample: {sales_data[:2] if len(sales_data) > 0 else 'empty'}")
        logger.info(f"DataFrame columns: {df.columns.tolist()}")
        
        # Parse datetime and extract components - handle mixed formats
        df['CloseTime'] = pd.to_datetime(df['CloseTime'], format='mixed')
        df['date'] = df['CloseTime'].dt.date
        df['hour'] = df['CloseTime'].dt.hour
        
        # Group by department and date for daily summary
        sales_summary = df.groupby(['Department.Id', 'date']).agg(
            total_sales=('DishSumInt', 'sum')
        ).reset_index()
        
        # Group by department, date, and hour for hourly summary
        sales_by_hour = df.groupby(['Department.Id', 'date', 'hour']).agg(
            sales_amount=('DishSumInt', 'sum')
        ).reset_index()
        
        # Convert to dictionaries
        summary_records = []
        for _, row in sales_summary.iterrows():
            summary_records.append({
                'department_id': row['Department.Id'],
                'date': row['date'],
                'total_sales': float(row['total_sales'])
            })
        
        hourly_records = []
        for _, row in sales_by_hour.iterrows():
            hourly_records.append({
                'department_id': row['Department.Id'],
                'date': row['date'],
                'hour': int(row['hour']),
                'sales_amount': float(row['sales_amount'])
            })
        
        logger.info(f"Processed {len(summary_records)} daily summary records and {len(hourly_records)} hourly records")
        return summary_records, hourly_records
    
    def sync_sales_summary(self, summary_records: List[dict]) -> int:
        """Sync sales summary records to database"""
        new_count = 0
        updated_count = 0
        
        for record in summary_records:
            # Check if department exists
            dept = self.db.query(Department).filter(Department.id == record['department_id']).first()
            if not dept:
                logger.warning(f"Department {record['department_id']} not found, skipping sales record")
                continue
            
            # Check if record already exists
            existing_record = self.db.query(SalesSummary).filter(
                SalesSummary.department_id == record['department_id'],
                SalesSummary.date == record['date']
            ).first()
            
            if existing_record:
                # Update existing record
                existing_record.total_sales = record['total_sales']
                existing_record.updated_at = datetime.utcnow()
                existing_record.synced_at = datetime.utcnow()
                updated_count += 1
            else:
                # Create new record
                new_record = SalesSummary(
                    department_id=record['department_id'],
                    date=record['date'],
                    total_sales=record['total_sales'],
                    synced_at=datetime.utcnow()
                )
                self.db.add(new_record)
                new_count += 1
        
        self.db.commit()
        logger.info(f"Synced {new_count} new and {updated_count} updated sales summary records")
        return new_count + updated_count
    
    def sync_sales_by_hour(self, hourly_records: List[dict]) -> int:
        """Sync sales by hour records to database"""
        new_count = 0
        updated_count = 0
        
        for record in hourly_records:
            # Check if department exists
            dept = self.db.query(Department).filter(Department.id == record['department_id']).first()
            if not dept:
                logger.warning(f"Department {record['department_id']} not found, skipping hourly sales record")
                continue
            
            # Check if record already exists
            existing_record = self.db.query(SalesByHour).filter(
                SalesByHour.department_id == record['department_id'],
                SalesByHour.date == record['date'],
                SalesByHour.hour == record['hour']
            ).first()
            
            if existing_record:
                # Update existing record
                existing_record.sales_amount = record['sales_amount']
                existing_record.updated_at = datetime.utcnow()
                existing_record.synced_at = datetime.utcnow()
                updated_count += 1
            else:
                # Create new record
                new_record = SalesByHour(
                    department_id=record['department_id'],
                    date=record['date'],
                    hour=record['hour'],
                    sales_amount=record['sales_amount'],
                    synced_at=datetime.utcnow()
                )
                self.db.add(new_record)
                new_count += 1
        
        self.db.commit()
        logger.info(f"Synced {new_count} new and {updated_count} updated hourly sales records")
        return new_count + updated_count
    
    async def sync_sales(self, from_date: date = None, to_date: date = None) -> dict:
        """Main method to sync sales data from iiko"""
        error_details = []
        
        try:
            # Default to current date if no dates provided
            if not from_date:
                from_date = date.today() - timedelta(days=1)  # Yesterday
            if not to_date:
                to_date = from_date
            
            logger.info(f"Starting sales sync from {from_date} to {to_date}")
            
            # Fetch sales data from iiko API
            try:
                sales_data = await self.fetch_sales_from_iiko(from_date, to_date)
            except Exception as fetch_error:
                error_msg = f"Failed to fetch data from iiko API: {str(fetch_error)}"
                logger.error(error_msg)
                error_details.append(error_msg)
                raise Exception(error_msg)
            
            if not sales_data:
                logger.info("No sales data found - returning success response")
                result = {
                    "status": "success",
                    "message": "No sales data found for the specified date range",
                    "summary_records": 0,
                    "hourly_records": 0,
                    "total_raw_records": 0,
                    "details": "No sales transactions were found in iiko API for the given period"
                }
                logger.info(f"Returning result: {result}")
                return result
            
            # Debug: log sample data before processing
            logger.info(f"About to process {len(sales_data)} sales records")
            if sales_data:
                logger.info(f"First record: {sales_data[0]}")
            
            # Process sales data
            try:
                summary_records, hourly_records = self.process_sales_data(sales_data)
            except Exception as process_error:
                error_msg = f"Failed to process sales data: {str(process_error)}"
                logger.error(error_msg)
                error_details.append(error_msg)
                raise Exception(error_msg)
            
            # Sync to database
            try:
                summary_count = self.sync_sales_summary(summary_records)
                hourly_count = self.sync_sales_by_hour(hourly_records)
            except Exception as db_error:
                error_msg = f"Database sync failed: {str(db_error)}"
                logger.error(error_msg)
                error_details.append(error_msg)
                raise Exception(error_msg)
            
            result = {
                "status": "success",
                "message": f"Successfully synced sales data from {from_date} to {to_date}",
                "summary_records": summary_count,
                "hourly_records": hourly_count,
                "total_raw_records": len(sales_data),
                "details": f"Processed {len(sales_data)} raw records into {summary_count} daily summaries and {hourly_count} hourly records"
            }
            
            logger.info(f"Sales sync completed: {result}")
            return result
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error syncing sales: {e}")
            
            # Prepare detailed error message
            if error_details:
                detailed_error = " → ".join(error_details)
            else:
                detailed_error = str(e)
                
            return {
                "status": "error",
                "message": f"Sales sync failed: {detailed_error}",
                "summary_records": 0,
                "hourly_records": 0,
                "total_raw_records": 0,
                "details": f"Error occurred during sync process. Check logs for more information. Error: {detailed_error}",
                "error_type": type(e).__name__
            }