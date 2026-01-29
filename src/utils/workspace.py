"""Workspace management utilities for CTF Agent"""
import os
import shutil
from datetime import datetime
from typing import List


def _archive_files_before_cleanup(workspace_dir: str, filenames: List[str]) -> None:
    """
    Copy files slated for emptying into timestamped archives under ./ctf-logs.
    Creates one directory per file stem (e.g., flags_logs) to keep history.
    """
    if not filenames:
        return

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    log_root = "./ctf-logs"
    os.makedirs(log_root, exist_ok=True)

    for filename in filenames:
        source_path = os.path.join(workspace_dir, filename)
        if not os.path.exists(source_path):
            continue

        stem, ext = os.path.splitext(os.path.basename(filename))
        archive_dir = os.path.join(log_root, f"{stem}_logs")
        os.makedirs(archive_dir, exist_ok=True)

        archive_name = f"{stem}-{timestamp}{ext}"
        archive_path = os.path.join(archive_dir, archive_name)

        try:
            shutil.copy2(source_path, archive_path)
            print(f"🗂️  Archived {filename} to {os.path.relpath(archive_path)}")
        except Exception as e:
            print(f"⚠️  Could not archive {filename}: {e}")

def cleanup_workspace(
    workspace_dir: str,
    approved_files: List[str],
    files_to_empty: List[str],
    auto_confirm: bool = False
) -> bool:
    """
    Clean up workspace from previous sessions.

    Args:
        workspace_dir: Path to workspace directory
        approved_files: List of files/patterns to keep (e.g., "*.ovpn", "connect-htb.sh")
        files_to_empty: List of files to empty (not delete)
        auto_confirm: Skip user confirmation and proceed with cleanup (for automated runs)

    Returns:
        True if cleanup was performed or approved, False if user cancelled
    """
    # Check if workspace exists
    if not os.path.exists(workspace_dir):
        return True  # Nothing to clean, continue

    workspace_items = os.listdir(workspace_dir)

    # Filter items to delete (everything not in approved list and not in FILES_TO_EMPTY)
    items_to_delete = []
    for item in workspace_items:
        item_path = os.path.join(workspace_dir, item)

        # Skip files that should be emptied instead of deleted
        if item in files_to_empty:
            continue

        # Check if item matches any approved pattern
        is_approved = False
        for pattern in approved_files:
            if pattern.startswith("*"):
                # Wildcard pattern (e.g., *.ovpn)
                if item.endswith(pattern[1:]):
                    is_approved = True
                    break
            else:
                # Exact match
                if item == pattern:
                    is_approved = True
                    break

        if not is_approved:
            items_to_delete.append(item_path)

    # Check which files to empty exist and have content
    files_to_empty_list = []
    for filename in files_to_empty:
        file_path = os.path.join(workspace_dir, filename)
        if os.path.exists(file_path):
            # Check if file has content
            if os.path.getsize(file_path) > 0:
                files_to_empty_list.append(filename)

    # Ask user if they want to clean
    if items_to_delete or files_to_empty_list:
        print(f"\n🧹 Workspace cleanup:")

        if items_to_delete:
            print(f"\n🗑️  Will DELETE {len(items_to_delete)} item(s):")
            for item in items_to_delete[:5]:  # Show first 5
                print(f"   - {os.path.basename(item)}")
            if len(items_to_delete) > 5:
                print(f"   ... and {len(items_to_delete) - 5} more")

        if files_to_empty_list:
            print(f"\n📝 Will EMPTY (keep file, clear contents):")
            for filename in files_to_empty_list:
                print(f"   - {filename}")

        if auto_confirm:
            wipe_choice = "y"
        else:
            wipe_choice = input("\n🧹 Proceed with cleanup? (y/n) [y]: ").strip().lower()

        if wipe_choice == "" or wipe_choice == "y":
            _archive_files_before_cleanup(workspace_dir, files_to_empty_list)

            # Delete unapproved items
            for item_path in items_to_delete:
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        print(f"🗑️  Deleted directory: {os.path.basename(item_path)}")
                    else:
                        os.remove(item_path)
                        print(f"🗑️  Deleted file: {os.path.basename(item_path)}")
                except Exception as e:
                    print(f"⚠️  Could not delete {os.path.basename(item_path)}: {e}")

            # Empty files that have content
            for filename in files_to_empty_list:
                file_path = os.path.join(workspace_dir, filename)
                try:
                    open(file_path, 'w').close()
                    print(f"📝 Emptied: {filename}")
                except Exception as e:
                    print(f"⚠️  Could not empty {filename}: {e}")
            return True
        else:
            print("\n🛑 Cleanup cancelled. Exiting...")
            return False

    # Nothing to clean, continue
    return True
