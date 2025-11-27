#!/usr/bin/env python3
"""
Script to add missing departments that exist in iiko API but not in database
"""
import asyncio
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add app directory to path
sys.path.insert(0, '/app')

from app.models.branch import Department
from app.services.iiko_sales_loader import IikoSalesLoaderService
from app.db import get_db


async def find_missing_departments():
    """
    Fetch sales data and identify departments that don't exist in DB
    """
    print("Fetching recent sales data from iiko API...")

    # Get database session
    db = next(get_db())

    try:
        # Create sales loader service
        sales_loader = IikoSalesLoaderService(db)

        # Fetch sales from last 3 days to get department IDs
        from_date = date.today() - timedelta(days=3)
        to_date = date.today()

        sales_data = await sales_loader.fetch_sales_from_iiko(from_date, to_date)

        if not sales_data:
            print("No sales data found")
            return []

        print(f"Found {len(sales_data)} sales records")

        # Extract unique department IDs
        dept_ids_in_sales = set()
        for record in sales_data:
            dept_id = record.get('Department.Id')
            if dept_id:
                dept_ids_in_sales.add(dept_id)

        print(f"Found {len(dept_ids_in_sales)} unique department IDs in sales data")

        # Check which ones are missing from database
        missing_depts = []
        for dept_id in dept_ids_in_sales:
            exists = db.query(Department).filter(Department.id == dept_id).first()
            if not exists:
                missing_depts.append(dept_id)

        print(f"\n{'='*60}")
        print(f"Missing departments: {len(missing_depts)}")
        print(f"{'='*60}\n")

        for i, dept_id in enumerate(missing_depts, 1):
            print(f"{i}. {dept_id}")

        return missing_depts

    finally:
        db.close()


def add_departments_to_db(department_ids: list):
    """
    Add missing departments to database with placeholder names
    """
    if not department_ids:
        print("\nNo departments to add")
        return

    print(f"\n{'='*60}")
    print(f"Adding {len(department_ids)} departments to database...")
    print(f"{'='*60}\n")

    db = next(get_db())

    try:
        # Get one of the existing organizations as parent
        # Organizations have parent_id = NULL
        organizations = db.query(Department).filter(Department.parent_id == None).all()

        if not organizations:
            print("ERROR: No organizations found in database!")
            return

        # Use first organization as default parent
        parent_org = organizations[0]
        print(f"Using organization '{parent_org.name}' (ID: {parent_org.id}) as parent")
        print()

        added_count = 0

        for i, dept_id in enumerate(department_ids, 1):
            # Check if already exists
            exists = db.query(Department).filter(Department.id == dept_id).first()
            if exists:
                print(f"{i}. SKIP: {dept_id} already exists as '{exists.name}'")
                continue

            # Create new department with placeholder name
            new_dept = Department(
                id=dept_id,
                parent_id=parent_org.id,
                name=f"Unknown iiko Department {i}",
                type="branch",
                segment_type="restaurant",
                code=f"IIKO_{dept_id[:8]}",
                code_tco=None
            )

            db.add(new_dept)
            print(f"{i}. ADD: {dept_id} → 'Unknown iiko Department {i}'")
            added_count += 1

        # Commit all changes
        db.commit()

        print(f"\n{'='*60}")
        print(f"✅ Successfully added {added_count} departments to database")
        print(f"{'='*60}")
        print("\nYou can now:")
        print("1. Update department names through the admin panel")
        print("2. Run sales sync to load their sales data")

    except Exception as e:
        db.rollback()
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


async def main():
    print("="*60)
    print("Missing Departments Detection & Addition Script")
    print("="*60)
    print()

    # Step 1: Find missing departments
    missing_depts = await find_missing_departments()

    if not missing_depts:
        print("\n✅ No missing departments found!")
        print("All departments from iiko API already exist in database.")
        return

    # Step 2: Ask for confirmation
    print("\nDo you want to add these departments to the database?")
    print("They will be added with placeholder names that you can update later.")

    response = input("\nContinue? (yes/no): ").strip().lower()

    if response in ['yes', 'y']:
        add_departments_to_db(missing_depts)
    else:
        print("\n❌ Operation cancelled")


if __name__ == "__main__":
    asyncio.run(main())
