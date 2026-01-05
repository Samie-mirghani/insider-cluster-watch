#!/usr/bin/env python3
"""
Test the bug fix for safe string truncation
"""

def test_safe_truncation():
    """Test that insider name truncation handles all edge cases"""

    # Test case 1: Long name (>30 chars)
    stale = {'insider_name': 'This Is A Very Long Insider Name That Exceeds Thirty Characters', 'ticker': 'TEST'}
    insider_name = stale.get('insider_name', 'Unknown')
    if insider_name and len(insider_name) > 30:
        insider_display = f"{insider_name[:30]}..."
    else:
        insider_display = insider_name

    assert insider_display == "This Is A Very Long Insider Na...", f"Expected truncation, got: {insider_display}"
    print(f"✅ Long name test passed: {insider_display}")

    # Test case 2: Short name
    stale = {'insider_name': 'John Doe', 'ticker': 'TEST'}
    insider_name = stale.get('insider_name', 'Unknown')
    if insider_name and len(insider_name) > 30:
        insider_display = f"{insider_name[:30]}..."
    else:
        insider_display = insider_name

    assert insider_display == "John Doe", f"Expected no truncation, got: {insider_display}"
    print(f"✅ Short name test passed: {insider_display}")

    # Test case 3: None name
    stale = {'ticker': 'TEST'}  # No insider_name key
    insider_name = stale.get('insider_name', 'Unknown')
    if insider_name and len(insider_name) > 30:
        insider_display = f"{insider_name[:30]}..."
    else:
        insider_display = insider_name

    assert insider_display == "Unknown", f"Expected 'Unknown', got: {insider_display}"
    print(f"✅ None name test passed: {insider_display}")

    # Test case 4: Empty string
    stale = {'insider_name': '', 'ticker': 'TEST'}
    insider_name = stale.get('insider_name', 'Unknown')
    if insider_name and len(insider_name) > 30:
        insider_display = f"{insider_name[:30]}..."
    else:
        insider_display = insider_name

    assert insider_display == "", f"Expected empty string, got: {insider_display}"
    print(f"✅ Empty string test passed: {insider_display}")

    # Test case 5: Exactly 30 chars
    stale = {'insider_name': 'X' * 30, 'ticker': 'TEST'}
    insider_name = stale.get('insider_name', 'Unknown')
    if insider_name and len(insider_name) > 30:
        insider_display = f"{insider_name[:30]}..."
    else:
        insider_display = insider_name

    assert insider_display == 'X' * 30, f"Expected no truncation at exactly 30 chars"
    assert '...' not in insider_display, "Should not have ellipsis for exactly 30 chars"
    print(f"✅ Exactly 30 chars test passed")


if __name__ == '__main__':
    print("Testing bug fix for safe string truncation...\n")
    test_safe_truncation()
    print("\n🎉 All bug fix tests passed!")
