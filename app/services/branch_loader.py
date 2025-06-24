import httpx
from sqlalchemy.orm import Session
from typing import List
from ..models.branch import Branch
from ..schemas.branch import APIBranchResponse
from ..config import settings
import logging

logger = logging.getLogger(__name__)


class BranchLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.api_url = f"{settings.API_BASE_URL}/objects"
    
    async def fetch_branches_from_api(self) -> List[APIBranchResponse]:
        """Fetch branches from external API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.api_url)
                response.raise_for_status()
                data = response.json()
                
                branches = []
                for item in data:
                    branches.append(APIBranchResponse(**item))
                
                logger.info(f"Fetched {len(branches)} branches from API")
                return branches
        except httpx.HTTPError as e:
            logger.error(f"Error fetching branches from API: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise
    
    async def sync_branches(self) -> int:
        """Sync branches from API to database"""
        try:
            api_branches = await self.fetch_branches_from_api()
            
            new_count = 0
            updated_count = 0
            processed_branches = set()
            remaining_branches = {branch.object_code: branch for branch in api_branches}
            
            # Process branches in multiple passes to handle parent-child dependencies
            max_iterations = len(api_branches)
            iteration = 0
            
            while remaining_branches and iteration < max_iterations:
                iteration += 1
                branches_processed_this_iteration = 0
                
                for branch_id, api_branch in list(remaining_branches.items()):
                    # Check if this branch can be processed
                    parent_id = api_branch.object_parent if api_branch.object_parent != "0" else None
                    can_process = (parent_id is None or 
                                 parent_id in processed_branches or
                                 self.db.query(Branch).filter(Branch.branch_id == parent_id).first() is not None)
                    
                    if can_process:
                        existing_branch = self.db.query(Branch).filter(
                            Branch.branch_id == api_branch.object_code
                        ).first()
                        
                        if existing_branch:
                            # Update existing branch
                            existing_branch.name = api_branch.object_name
                            existing_branch.parent_id = parent_id
                            existing_branch.organization_name = api_branch.object_company
                            existing_branch.organization_bin = api_branch.object_bin
                            updated_count += 1
                        else:
                            # Create new branch
                            new_branch = Branch(
                                branch_id=api_branch.object_code,
                                name=api_branch.object_name,
                                parent_id=parent_id,
                                organization_name=api_branch.object_company,
                                organization_bin=api_branch.object_bin
                            )
                            self.db.add(new_branch)
                            self.db.commit()  # Commit immediately for new records
                            new_count += 1
                        
                        processed_branches.add(branch_id)
                        del remaining_branches[branch_id]
                        branches_processed_this_iteration += 1
                
                # If no branches were processed in this iteration, break to avoid infinite loop
                if branches_processed_this_iteration == 0:
                    logger.warning(f"Could not process {len(remaining_branches)} branches due to missing parent dependencies")
                    for branch_id, branch in remaining_branches.items():
                        logger.warning(f"Branch {branch_id} has missing parent {branch.object_parent}")
                    break
            
            # Commit any remaining updates
            self.db.commit()
            total_processed = new_count + updated_count
            logger.info(f"Successfully synced {new_count} new and {updated_count} updated branches")
            
            if remaining_branches:
                logger.warning(f"{len(remaining_branches)} branches could not be processed due to dependency issues")
            
            return total_processed
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error syncing branches: {e}")
            raise