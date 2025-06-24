import httpx
from sqlalchemy.orm import Session
from typing import List
from xml.etree import ElementTree as ET
from datetime import datetime
from ..models.branch import Department
from ..services.iiko_auth import IikoAuthService
import logging

logger = logging.getLogger(__name__)


class IikoDepartmentLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [
            "https://sandy-co-co.iiko.it",
            "https://madlen-group-so.iiko.it"
        ]
    
    async def fetch_departments_from_single_domain(self, base_url: str) -> List[dict]:
        """Fetch departments from a single iiko domain"""
        try:
            auth_service = IikoAuthService(base_url)
            token = await auth_service.get_auth_token()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/resto/api/corporation/departments",
                    params={
                        "key": token,
                        "revisionFrom": -1
                    }
                )
                response.raise_for_status()
                
                # Parse XML response
                departments = self._parse_departments_xml(response.text)
                logger.info(f"Fetched {len(departments)} departments from {base_url}")
                return departments
                
        except httpx.HTTPError as e:
            logger.error(f"Error fetching departments from {base_url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error from {base_url}: {e}")
            raise
    
    async def fetch_departments_from_iiko(self) -> List[dict]:
        """Fetch departments from all iiko domains"""
        all_departments = []
        
        for domain in self.domains:
            try:
                departments = await self.fetch_departments_from_single_domain(domain)
                all_departments.extend(departments)
            except Exception as e:
                logger.error(f"Failed to fetch from {domain}: {e}")
                # Continue with other domains even if one fails
                continue
        
        logger.info(f"Total fetched {len(all_departments)} departments from all domains")
        return all_departments
    
    def _parse_departments_xml(self, xml_text: str) -> List[dict]:
        """Parse XML response from iiko API"""
        departments = []
        
        try:
            root = ET.fromstring(xml_text)
            
            for item in root.findall('corporateItemDto'):
                dept_id = item.find('id')
                parent_id = item.find('parentId')
                code = item.find('code')
                name = item.find('name')
                dept_type = item.find('type')
                taxpayer_id = item.find('taxpayerIdNumber')
                
                department = {
                    'id': dept_id.text if dept_id is not None else None,
                    'parent_id': parent_id.text if parent_id is not None else None,
                    'code': code.text if code is not None else None,
                    'name': name.text if name is not None else '',
                    'type': dept_type.text if dept_type is not None else 'DEPARTMENT',
                    'taxpayer_id_number': taxpayer_id.text if taxpayer_id is not None and taxpayer_id.text else None
                }
                
                departments.append(department)
            
            return departments
            
        except ET.ParseError as e:
            logger.error(f"Error parsing XML response: {e}")
            raise
    
    async def sync_departments(self) -> int:
        """Sync departments from iiko API to database"""
        try:
            iiko_departments = await self.fetch_departments_from_iiko()
            
            new_count = 0
            updated_count = 0
            processed_departments = set()
            remaining_departments = {dept['id']: dept for dept in iiko_departments if dept['id']}
            
            # Process departments in multiple passes to handle parent-child dependencies
            max_iterations = len(iiko_departments)
            iteration = 0
            
            while remaining_departments and iteration < max_iterations:
                iteration += 1
                departments_processed_this_iteration = 0
                
                for dept_id, iiko_dept in list(remaining_departments.items()):
                    # Check if this department can be processed
                    parent_id = iiko_dept['parent_id']
                    can_process = (parent_id is None or 
                                 parent_id in processed_departments or
                                 self.db.query(Department).filter(Department.id == parent_id).first() is not None)
                    
                    if can_process:
                        existing_dept = self.db.query(Department).filter(
                            Department.id == dept_id
                        ).first()
                        
                        if existing_dept:
                            # Update existing department
                            existing_dept.code = iiko_dept['code']
                            existing_dept.name = iiko_dept['name']
                            existing_dept.type = iiko_dept['type']
                            existing_dept.taxpayer_id_number = iiko_dept['taxpayer_id_number']
                            existing_dept.parent_id = parent_id
                            existing_dept.updated_at = datetime.utcnow()
                            existing_dept.synced_at = datetime.utcnow()
                            updated_count += 1
                        else:
                            # Create new department
                            new_dept = Department(
                                id=dept_id,
                                parent_id=parent_id,
                                code=iiko_dept['code'],
                                name=iiko_dept['name'],
                                type=iiko_dept['type'],
                                taxpayer_id_number=iiko_dept['taxpayer_id_number'],
                                synced_at=datetime.utcnow()
                            )
                            self.db.add(new_dept)
                            self.db.commit()  # Commit immediately for new records
                            new_count += 1
                        
                        processed_departments.add(dept_id)
                        del remaining_departments[dept_id]
                        departments_processed_this_iteration += 1
                
                # If no departments were processed in this iteration, break to avoid infinite loop
                if departments_processed_this_iteration == 0:
                    logger.warning(f"Could not process {len(remaining_departments)} departments due to missing parent dependencies")
                    for dept_id, dept in remaining_departments.items():
                        logger.warning(f"Department {dept_id} ({dept['name']}) has missing parent {dept['parent_id']}")
                    break
            
            # Commit any remaining updates
            self.db.commit()
            total_processed = new_count + updated_count
            logger.info(f"Successfully synced {new_count} new and {updated_count} updated departments")
            
            if remaining_departments:
                logger.warning(f"{len(remaining_departments)} departments could not be processed due to dependency issues")
            
            return total_processed
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error syncing departments: {e}")
            raise