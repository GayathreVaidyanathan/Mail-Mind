"""
cleanup_labels.py

Removes all Gmail labels created by the pipeline.
Also removes pipeline-applied labels from all emails.

Usage:
  python cleanup_labels.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gmail_client import authenticate
from googleapiclient.errors import HttpError

# All labels the pipeline may have created
PIPELINE_LABELS = [
    # Topic labels
    "PhD Stuff", "Internships", "Coding", "Finance", "College",
    # Auto labels
    "Auto/Spam", "Auto/Promotional",
    # Platform labels from PLATFORM_MAP
    "Swiggy", "Zomato", "Blinkit", "Dunzo", "Zepto",
    "Reddit", "LinkedIn", "Twitter", "Instagram", "YouTube",
    "Substack", "Medium", "GitHub", "GitLab", "StackOverflow",
    "LeetCode", "HackerRank", "Kaggle", "NPTEL", "Coursera",
    "Udemy", "Infosys Springboard", "interACT", "Google One",
    "Google", "Amazon", "Flipkart", "Myntra", "Meesho", "AJIO",
    "Nykaa", "Paytm", "PhonePe", "Razorpay", "HDFC Bank",
    "ICICI Bank", "SBI", "Axis Bank", "Kotak Bank", "PayU", "UPI",
    "MakeMyTrip", "IRCTC", "Ola", "Uber", "Rapido", "A1 Travels",
    "RedBus", "AbhiBus", "Naukri", "Internshala", "Unstop",
    "Wellfound", "Dare2Compete", "Crowdfunding",
    # Other labels that may have been created
    "mark_as_important", "Notifications", "Personal",
    "Promotional", "Policy", "Research",
]


def cleanup(service):
    print("\n🔍 Fetching all Gmail labels...")
    result = service.users().labels().list(userId="me").execute()
    all_labels = result.get("labels", [])

    # Find which pipeline labels actually exist
    to_delete = []
    for label in all_labels:
        name = label["name"]
        label_id = label["id"]
        # Match exact name or nested (e.g. Auto/Promotional)
        if any(name.lower() == pl.lower() for pl in PIPELINE_LABELS):
            to_delete.append((name, label_id))

    if not to_delete:
        print("  ✓ No pipeline labels found. Inbox is already clean!")
        return

    print(f"\n  Found {len(to_delete)} pipeline label(s) to remove:")
    for name, _ in to_delete:
        print(f"    - {name}")

    confirm = input("\n  Proceed? This will remove labels from all emails too. (y/n): ")
    if confirm.lower() != "y":
        print("  Cancelled.")
        return

    print("\n🧹 Removing labels...")
    for name, label_id in to_delete:
        try:
            # First remove label from all emails that have it
            msgs = service.users().messages().list(
                userId="me", labelIds=[label_id], maxResults=500
            ).execute().get("messages", [])

            if msgs:
                print(f"  Removing '{name}' from {len(msgs)} email(s)...")
                for msg in msgs:
                    service.users().messages().modify(
                        userId="me", id=msg["id"],
                        body={"removeLabelIds": [label_id]},
                    ).execute()

            # Then delete the label itself
            service.users().labels().delete(
                userId="me", id=label_id
            ).execute()
            print(f"  ✓ Deleted label: {name}")

        except HttpError as e:
            print(f"  ✗ Could not delete '{name}': {e}")

    print("\n✅ Cleanup complete!")


def main():
    print("═" * 50)
    print("  Gmail Pipeline Label Cleanup")
    print("═" * 50)
    service = authenticate()
    cleanup(service)


if __name__ == "__main__":
    main()