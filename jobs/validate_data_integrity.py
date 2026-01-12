#!/usr/bin/env python3
"""
Data Integrity Validator

Validates data files before running main jobs to prevent:
1. Git merge conflict markers from corrupting data
2. Malformed JSON files
3. Missing critical files

This script should be run BEFORE main.py to ensure data integrity.
"""

import os
import sys
import json
import glob
from pathlib import Path

# ANSI colors for output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

DATA_DIR = Path(__file__).parent.parent / 'data'
CRITICAL_FILES = [
    'paper_portfolio.json',
    'insider_trades_history.csv',
    'insider_tracking_queue.json',
]

def check_conflict_markers(file_path):
    """Check if a file contains git merge conflict markers"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        conflict_markers = ['<<<<<<< HEAD', '=======', '>>>>>>>']
        found_markers = []

        for marker in conflict_markers:
            if marker in content:
                found_markers.append(marker)

        return found_markers
    except Exception as e:
        return [f"Error reading file: {e}"]

def validate_json_file(file_path):
    """Validate that a JSON file is properly formatted"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json.load(f)
        return True, None
    except json.JSONDecodeError as e:
        return False, f"JSON parsing error: {e}"
    except Exception as e:
        return False, f"Error reading file: {e}"

def validate_csv_structure(file_path):
    """Basic validation that CSV has proper structure"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if not lines:
            return False, "CSV file is empty"

        # Check header exists
        if ',' not in lines[0]:
            return False, "CSV header appears malformed"

        return True, None
    except Exception as e:
        return False, f"Error reading file: {e}"

def main():
    """Run all validation checks"""
    errors = []
    warnings = []
    files_checked = 0

    print(f"{YELLOW}{'='*70}{RESET}")
    print(f"{YELLOW}DATA INTEGRITY VALIDATION{RESET}")
    print(f"{YELLOW}{'='*70}{RESET}\n")

    # Check 1: Verify DATA_DIR exists
    if not DATA_DIR.exists():
        errors.append(f"Data directory not found: {DATA_DIR}")
        print(f"{RED}✗ Data directory missing{RESET}")
    else:
        print(f"{GREEN}✓ Data directory exists{RESET}")

    # Check 2: Verify critical files exist
    print(f"\n{YELLOW}Checking critical files...{RESET}")
    for filename in CRITICAL_FILES:
        file_path = DATA_DIR / filename
        if not file_path.exists():
            errors.append(f"Critical file missing: {filename}")
            print(f"{RED}✗ {filename} - MISSING{RESET}")
        else:
            print(f"{GREEN}✓ {filename} - exists{RESET}")

    # Check 3: Scan all data files for merge conflict markers
    print(f"\n{YELLOW}Scanning for git merge conflict markers...{RESET}")
    data_files = list(DATA_DIR.glob('*.json')) + list(DATA_DIR.glob('*.csv'))

    for file_path in data_files:
        files_checked += 1
        markers = check_conflict_markers(file_path)

        if markers:
            errors.append(f"{file_path.name} contains merge conflict markers: {markers}")
            print(f"{RED}✗ {file_path.name} - CONFLICT MARKERS FOUND: {markers}{RESET}")
        else:
            print(f"{GREEN}✓ {file_path.name} - clean{RESET}")

    # Check 4: Validate JSON files
    print(f"\n{YELLOW}Validating JSON files...{RESET}")
    json_files = list(DATA_DIR.glob('*.json'))

    for file_path in json_files:
        is_valid, error = validate_json_file(file_path)

        if not is_valid:
            errors.append(f"{file_path.name}: {error}")
            print(f"{RED}✗ {file_path.name} - INVALID: {error}{RESET}")
        else:
            print(f"{GREEN}✓ {file_path.name} - valid JSON{RESET}")

    # Check 5: Validate critical CSV files
    print(f"\n{YELLOW}Validating CSV files...{RESET}")
    csv_files = [DATA_DIR / 'insider_trades_history.csv', DATA_DIR / 'paper_trades.csv']

    for file_path in csv_files:
        if file_path.exists():
            is_valid, error = validate_csv_structure(file_path)

            if not is_valid:
                errors.append(f"{file_path.name}: {error}")
                print(f"{RED}✗ {file_path.name} - INVALID: {error}{RESET}")
            else:
                print(f"{GREEN}✓ {file_path.name} - valid CSV{RESET}")

    # Check 6: Specific paper_portfolio.json validation
    print(f"\n{YELLOW}Validating paper trading portfolio...{RESET}")
    portfolio_file = DATA_DIR / 'paper_portfolio.json'

    if portfolio_file.exists():
        try:
            with open(portfolio_file, 'r') as f:
                portfolio = json.load(f)

            # Check required fields
            required_fields = ['starting_capital', 'cash', 'positions', 'total_trades']
            missing_fields = [f for f in required_fields if f not in portfolio]

            if missing_fields:
                errors.append(f"Portfolio missing required fields: {missing_fields}")
                print(f"{RED}✗ Portfolio missing fields: {missing_fields}{RESET}")
            else:
                print(f"{GREEN}✓ Portfolio has required fields{RESET}")

            # Sanity checks
            if portfolio.get('cash', 0) < 0:
                errors.append("Portfolio has negative cash balance!")
                print(f"{RED}✗ Negative cash balance detected!{RESET}")

            if portfolio.get('cash', 0) == 10000 and not portfolio.get('positions'):
                warnings.append("Portfolio appears to be in default reset state")
                print(f"{YELLOW}⚠ Portfolio appears to be reset to default state{RESET}")
            else:
                print(f"{GREEN}✓ Portfolio state looks reasonable{RESET}")

        except Exception as e:
            errors.append(f"Error validating portfolio: {e}")
            print(f"{RED}✗ Portfolio validation error: {e}{RESET}")

    # Summary
    print(f"\n{YELLOW}{'='*70}{RESET}")
    print(f"{YELLOW}VALIDATION SUMMARY{RESET}")
    print(f"{YELLOW}{'='*70}{RESET}")
    print(f"Files checked: {files_checked}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")

    if errors:
        print(f"\n{RED}ERRORS FOUND:{RESET}")
        for error in errors:
            print(f"  {RED}• {error}{RESET}")

    if warnings:
        print(f"\n{YELLOW}WARNINGS:{RESET}")
        for warning in warnings:
            print(f"  {YELLOW}• {warning}{RESET}")

    if not errors:
        print(f"\n{GREEN}✓ All validation checks passed!{RESET}")
        return 0
    else:
        print(f"\n{RED}✗ Validation failed! DO NOT run main job until errors are resolved.{RESET}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
