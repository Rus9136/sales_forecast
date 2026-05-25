import httpx
from sqlalchemy.orm import Session
from typing import List
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from datetime import datetime
from ..models.branch import Department
from ..services.iiko_auth import IikoAuthService
from ..config import settings
import logging

logger = logging.getLogger(__name__)


def _domain_host(url: str) -> str:
    """Extract bare hostname from a base URL so the stored value is stable
    across scheme/path changes. Mirrors `scripts.backfill_iiko_source_domain._host`."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.hostname or url


class IikoDepartmentLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]
    
    async def fetch_departments_from_single_domain(self, base_url: str) -> List[dict]:
        """Fetch departments from a single iiko domain.

        Each returned dict is tagged with ``iiko_source_domain`` (the bare hostname)
        so downstream code can persist the source without losing context to merging.
        """
        try:
            auth_service = IikoAuthService(base_url)
            token = await auth_service.get_auth_token()
            host = _domain_host(base_url)

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
                for dept in departments:
                    dept['iiko_source_domain'] = host
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

                # iiko stores BIN/ИИН in two different locations depending on type:
                # - DEPARTMENT: top-level <taxpayerIdNumber>
                # - JURPERSON: nested <jurPersonAdditionalPropertiesDto><taxpayerId>
                taxpayer_id_value = None
                top_tin = item.find('taxpayerIdNumber')
                if top_tin is not None and top_tin.text and top_tin.text.strip():
                    taxpayer_id_value = top_tin.text.strip()
                else:
                    nested = item.find('jurPersonAdditionalPropertiesDto/taxpayerId')
                    if nested is not None and nested.text and nested.text.strip():
                        taxpayer_id_value = nested.text.strip()

                department = {
                    'id': dept_id.text if dept_id is not None else None,
                    'parent_id': parent_id.text if parent_id is not None else None,
                    'code': code.text if code is not None else None,
                    'name': name.text if name is not None else '',
                    'type': dept_type.text if dept_type is not None else 'DEPARTMENT',
                    'taxpayer_id_number': taxpayer_id_value
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

            # Pre-load all existing department IDs and objects to avoid N+1 queries
            existing_departments = {
                str(dept.id): dept
                for dept in self.db.query(Department).all()
            }
            existing_ids = set(existing_departments.keys())

            # Process departments in multiple passes to handle parent-child dependencies
            max_iterations = len(iiko_departments)
            iteration = 0

            while remaining_departments and iteration < max_iterations:
                iteration += 1
                departments_processed_this_iteration = 0

                for dept_id, iiko_dept in list(remaining_departments.items()):
                    # Check if this department can be processed (in-memory lookup).
                    # If parent is also in this iiko batch, wait for it first so
                    # children inherit the freshly-synced parent BIN.
                    parent_id = iiko_dept['parent_id']
                    parent_pending = parent_id in remaining_departments
                    can_process = (parent_id is None or
                                 parent_id in processed_departments or
                                 (parent_id in existing_ids and not parent_pending))

                    if can_process:
                        existing_dept = existing_departments.get(dept_id)
                        parent_dept = existing_departments.get(parent_id) if parent_id else None

                        # BIN resolution priority:
                        #   1. iiko (authoritative when non-empty)
                        #   2. existing manual value (preserve UI edits)
                        #   3. inherit from parent JURPERSON (covers iiko gaps)
                        iiko_bin = iiko_dept['taxpayer_id_number']
                        existing_bin = existing_dept.taxpayer_id_number if existing_dept else None
                        parent_bin = parent_dept.taxpayer_id_number if parent_dept else None
                        resolved_bin = iiko_bin or existing_bin or parent_bin or None

                        if existing_dept:
                            # iiko-managed fields only — DO NOT touch manual-only
                            # columns (segment_type, season_*, brand, location_type,
                            # tourist_traffic_dependent, is_24_7, opening_hour,
                            # closing_hour, seasonality_intensity, city, opened_date,
                            # season_start_month, season_end_month). Those are filled
                            # via the UI and feed the ML model.
                            existing_dept.code = iiko_dept['code']
                            existing_dept.name = iiko_dept['name']
                            existing_dept.type = iiko_dept['type']
                            existing_dept.taxpayer_id_number = resolved_bin
                            existing_dept.parent_id = parent_id
                            existing_dept.iiko_source_domain = iiko_dept['iiko_source_domain']
                            existing_dept.updated_at = datetime.utcnow()
                            existing_dept.synced_at = datetime.utcnow()
                            updated_count += 1
                        else:
                            new_dept = Department(
                                id=dept_id,
                                parent_id=parent_id,
                                code=iiko_dept['code'],
                                name=iiko_dept['name'],
                                type=iiko_dept['type'],
                                taxpayer_id_number=resolved_bin,
                                iiko_source_domain=iiko_dept['iiko_source_domain'],
                                synced_at=datetime.utcnow()
                            )
                            self.db.add(new_dept)
                            self.db.flush()  # Flush to make FK visible in this session
                            existing_departments[dept_id] = new_dept
                            existing_ids.add(dept_id)
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

            # Commit all changes at once
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