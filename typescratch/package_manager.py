"""TypeScratch Package Manager - install libraries from GitHub.

Usage:
    typescratch install <github-user/repo>
    typescratch install <github-user/repo>@<tag>
    typescratch uninstall <package-name>
    typescratch list

Packages are cloned into ./typescratch_packages/<repo-name>/
and can be fused with: fuse "typescratch_packages/<repo-name>/main.tysh"
"""

import os
import sys
import shutil
import subprocess
from typing import Optional


PACKAGES_DIR = "typescratch_packages"


def install(repo: str) -> int:
    """Install a package from GitHub.

    repo can be:
      user/repo
      user/repo@tag
      https://github.com/user/repo
    """
    # Parse the repo spec
    tag = None
    if "@" in repo:
        repo, tag = repo.rsplit("@", 1)

    # Clean up URL form
    if repo.startswith("https://github.com/"):
        repo = repo[len("https://github.com/"):]

    # Build the clone URL
    clone_url = f"https://github.com/{repo}.git"

    # Extract repo name
    repo_name = repo.split("/")[-1] if "/" in repo else repo

    # Create packages dir
    if not os.path.exists(PACKAGES_DIR):
        os.makedirs(PACKAGES_DIR)

    dest = os.path.join(PACKAGES_DIR, repo_name)

    # If already exists, remove it
    if os.path.exists(dest):
        print(f"Package {repo_name} already installed, updating...")
        shutil.rmtree(dest)

    # Clone
    print(f"Installing {repo_name} from {clone_url}...")
    cmd = ["git", "clone", "--depth", "1"]
    if tag:
        cmd.extend(["--branch", tag])
    cmd.extend([clone_url, dest])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"Error: git clone failed: {result.stderr}", file=sys.stderr)
            return 1
    except FileNotFoundError:
        print("Error: git is not installed. Install git first.", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("Error: git clone timed out.", file=sys.stderr)
        return 1

    # Remove .git directory to save space
    git_dir = os.path.join(dest, ".git")
    if os.path.exists(git_dir):
        shutil.rmtree(git_dir)

    print(f"Installed {repo_name} to {dest}/")

    # Check for a main.tysh file
    main_file = os.path.join(dest, "main.tysh")
    if os.path.isfile(main_file):
        print(f"\nTo use this package, add this to your .tysh file:")
        print(f'  fuse "{PACKAGES_DIR}/{repo_name}/main.tysh"')
    else:
        # List .tysh files
        tysh_files = [f for f in os.listdir(dest) if f.endswith(".tysh")]
        if tysh_files:
            print(f"\nAvailable .tysh files:")
            for f in tysh_files:
                print(f'  fuse "{PACKAGES_DIR}/{repo_name}/{f}"')
        else:
            print(f"\nNo .tysh files found in package.")

    return 0


def uninstall(name: str) -> int:
    """Remove an installed package."""
    dest = os.path.join(PACKAGES_DIR, name)
    if not os.path.exists(dest):
        print(f"Package {name} is not installed.", file=sys.stderr)
        return 1
    shutil.rmtree(dest)
    print(f"Uninstalled {name}")
    return 0


def list_packages() -> int:
    """List installed packages."""
    if not os.path.exists(PACKAGES_DIR):
        print("No packages installed.")
        return 0
    packages = [d for d in os.listdir(PACKAGES_DIR)
                if os.path.isdir(os.path.join(PACKAGES_DIR, d))]
    if not packages:
        print("No packages installed.")
        return 0
    print(f"Installed packages ({len(packages)}):")
    for p in sorted(packages):
        dest = os.path.join(PACKAGES_DIR, p)
        tysh_files = [f for f in os.listdir(dest) if f.endswith(".tysh")]
        print(f"  {p} ({len(tysh_files)} .tysh files)")
    return 0
