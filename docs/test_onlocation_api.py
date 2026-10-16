#!/usr/bin/env python3
"""
Simple test script to verify OnLocation API access and view employee presence data.
"""

import requests
import json

# ==============================================================================
# CONFIGURATION - Replace with your actual API key
# ==============================================================================
API_KEY = "Vc7hPAiiIHxbG5SN"
API_BASE_URL = "https://api.whosonlocation.com/v1"

# ==============================================================================
# Test the API connection
# ==============================================================================

def test_api_connection():
    """
    Makes a simple GET request to the /staff endpoint to:
    1. Verify the API key works
    2. See what employee data is returned
    3. Check the onsite_status field
    """
    
    print("=" * 70)
    print("OnLocation API Test")
    print("=" * 70)
    print()
    
    # Set up the request
    url = f"{API_BASE_URL}/staff"
    headers = {
        "Authorization": f"APIKEY {API_KEY}",  # OnLocation uses "APIKEY" not "Bearer"
        "Accept": "application/json"
    }
    
    # Optional: limit to just a few records for testing
    params = {
        "limit": 10  # Start with just 10 employees
    }
    
    print(f"Testing connection to: {url}")
    print(f"Fetching up to {params['limit']} employee records...")
    print()
    
    try:
        # Make the API request
        response = requests.get(url, headers=headers, params=params)
        
        # Check if request was successful
        response.raise_for_status()
        
        # Parse the JSON response
        data = response.json()
        
        # Handle if API returns a dict with a 'data' key or similar
        if isinstance(data, dict):
            # Try common wrapper keys
            employees = data.get('data', data.get('staff', data.get('employees', [])))
            if not employees:
                # If still empty, maybe the dict itself is the single employee
                employees = [data] if data else []
        else:
            employees = data
        
        print(f"✓ Success! Received {len(employees)} employee records")
        print()
        print("=" * 70)
        print("Sample Employee Data:")
        print("=" * 70)
        print()
        
        # Display the first few employees with relevant fields
        for i, employee in enumerate(employees[:5] if len(employees) > 5 else employees, 1):
            print(f"Employee {i}:")
            print(f"  ID: {employee.get('id')}")
            print(f"  Name: {employee.get('name')}")
            print(f"  Onsite Status: {employee.get('onsite_status')} {'🟢' if employee.get('onsite_status') == 'onsite' else '🔴'}")
            print(f"  Location: {employee.get('location')}")
            print(f"  Department: {employee.get('department')}")
            print(f"  Email: {employee.get('email')}")
            print()
        
        print("=" * 70)
        print("Summary:")
        print("=" * 70)
        
        # Count onsite vs offsite
        onsite_count = sum(1 for emp in employees if emp.get('onsite_status') == 'onsite')
        offsite_count = sum(1 for emp in employees if emp.get('onsite_status') == 'offsite')
        
        print(f"Onsite: {onsite_count} 🟢")
        print(f"Offsite: {offsite_count} 🔴")
        print()
        
        # Show all available fields from first employee
        if employees:
            print("=" * 70)
            print("All available fields in response:")
            print("=" * 70)
            print(json.dumps(employees[0], indent=2))
        
        return True
        
    except requests.exceptions.HTTPError as e:
        print(f"✗ HTTP Error: {e}")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 401:
            print()
            print("⚠ Authentication failed - check your API key")
        elif response.status_code == 403:
            print()
            print("⚠ Access denied - your API key may not have permission to access /staff endpoint")
        
        return False
        
    except requests.exceptions.ConnectionError:
        print("✗ Connection Error: Could not reach OnLocation API")
        print("Check your internet connection")
        return False
        
    except requests.exceptions.Timeout:
        print("✗ Request timed out")
        return False
        
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    # Check if API key has been set
    if API_KEY == "YOUR_API_KEY_HERE":
        print("⚠ Error: Please replace 'YOUR_API_KEY_HERE' with your actual API key")
        print()
        print("Edit this file and update the API_KEY variable at the top")
        exit(1)
    
    # Run the test
    success = test_api_connection()
    
    if success:
        print()
        print("✓ API test completed successfully!")
        print()
        print("Next steps:")
        print("  1. Review the data structure above")
        print("  2. Confirm 'onsite_status' field shows 'onsite' or 'offsite'")
        print("  3. We can now build the dashboard!")
    else:
        print()
        print("✗ API test failed - see errors above")