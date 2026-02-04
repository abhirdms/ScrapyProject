"""
CSV Handler utility for storing scraped data.
"""
import csv
import os
from typing import List, Dict, Any, Optional


# Standard columns that should always be present in the CSV
# All scrapers should try to populate these fields, but they can be empty if not available
STANDARD_COLUMNS = [
    "listingUrl",
    "displayAddress",
    "price",
    "propertySubType",
    "propertyImage",
    "detailedDescription",
    "sizeFt",
    "sizeAc",
    "postalCode",
    "brochureUrl",
    "agentCompanyName",
    "agentName",
    "agentCity",
    "agentEmail",
    "agentPhone",
    "agentStreet",
    "agentPostcode",
    "tenure",
    "saleType",
]


def store_data_to_csv(
    data: List[Dict[str, Any]],
    filepath: str = "data/data.csv",
    mode: str = "append"
) -> bool:
    """
    Store scraped data to a CSV file.
    
    Handles scenarios where not all columns are present in the data.
    Uses predefined STANDARD_COLUMNS to ensure consistent CSV structure.
    Any columns not provided by scrapers will be left empty.
    
    Args:
        data: List of dictionaries containing the scraped data.
              Each dictionary represents a row, keys are column names.
        filepath: Path to the CSV file (default: data/data.csv)
        mode: 'append' to add to existing data, 'overwrite' to replace file
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not data:
        print("No data to store.")
        return False
    
    try:
        # Ensure the directory exists
        dir_path = os.path.dirname(filepath)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
        
        # Get all unique columns from the new data
        new_columns = set()
        for row in data:
            new_columns.update(row.keys())
        
        existing_data = []
        existing_columns = set()
        
        # If appending and file exists, read existing data and columns
        if mode == "append" and os.path.exists(filepath):
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                if reader.fieldnames:
                    existing_columns = set(reader.fieldnames)
                existing_data = list(reader)
        
        # Start with standard columns, then add any extra columns from existing or new data
        all_columns = list(STANDARD_COLUMNS)
        
        # Add any extra columns that are not in standard columns (from existing data or new data)
        extra_columns = (existing_columns.union(new_columns)) - set(STANDARD_COLUMNS)
        all_columns.extend(sorted(extra_columns))
        
        # Write data to CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=all_columns, extrasaction='ignore')
            writer.writeheader()
            
            # Write existing data (if appending)
            if mode == "append":
                for row in existing_data:
                    # Fill missing columns with empty string
                    complete_row = {col: row.get(col, '') for col in all_columns}
                    writer.writerow(complete_row)
            
            # Write new data
            for row in data:
                # Fill missing columns with empty string
                complete_row = {col: row.get(col, '') for col in all_columns}
                writer.writerow(complete_row)
        
        print(f"Successfully stored {len(data)} records to {filepath}")
        return True
        
    except Exception as e:
        print(f"Error storing data to CSV: {e}")
        return False


def get_existing_columns(filepath: str = "data/data.csv") -> List[str]:
    """
    Get the list of columns from an existing CSV file.
    
    Args:
        filepath: Path to the CSV file
        
    Returns:
        List of column names, empty list if file doesn't exist
    """
    if not os.path.exists(filepath):
        return []
    
    try:
        with open(filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return list(reader.fieldnames) if reader.fieldnames else []
    except Exception as e:
        print(f"Error reading CSV columns: {e}")
        return []
