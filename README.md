# CopyClip

**CopyClip** is a Python script that scans a directory, reads the content of files, and copies their contents to the clipboard. It supports advanced features like ignoring files via `.copyclipignore` and filtering files by extension.

## Features
- **Supports .copyclipignore**: Easily exclude files or directories from processing.
- **File extension filtering**: Process only files with specific extensions.
- **Multiprocessing**: Speeds up processing by using multiple CPU cores.
- **Progress bars**: Displays real-time progress for scanning and reading files.

## Installation

### Prerequisites
- **Python 3.6 or higher**
- `pip` (comes with Python)

### Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/sssamuelll/copyclip.git
   cd copyclip
   ```
2. **Install dependencies and the script:**
   ```bash
   pip install .
   ```
3. **Verify the installation:**
   ```bash
   copyclip --help
   ```

## Usage

Run the script from any directory to process files:

```bash
copyclip /path/to/folder --extension .jsx
```

### Options

- `folder`: The directory to scan for files. Defaults to the current directory.
- `--extension`: Filter files by extension (e.g., .jsx, .py). Optional.

### Example

```bash
copyclip ~/projects --extension .py
```

This command copies the contents of all .py files in ~/projects to the clipboard.

## Uninstallation
If you want to remove CopyClip, run:

```bash
pip uninstall copyclip
```

## Advanced Configuration

### `.copyclipignore`

Create a `.copyclipignore` file in the directory you want to scan to exclude specific files or directories. The format follows the same rules as .gitignore

Example `.copyclipignore`:

```bash
# Ignore all `.log` files
*.log

# Ignore the `temp` folder
temp/
```

### Manual PATH Addition (Optional)

If you prefer not to use `pip install`, you can add the script manually to your `PATH`:

1. Make the script executable:
   ```bash
   chmod +x copyclip
   ```
2. Add the script's directory to your `PATH`:
   ```bash
   export PATH=$PATH:/path/to/copyclip
   ```
3. Verify the command:
   ```bash
   copyclip --help
   ```

## Troubleshooting
If you encounter issues:
1. Ensure Python 3.6+ is installed:
   ```bash
   python3 --version
   ```
2. Verify `pip` is working:
   ```bash
   pip --version
   ```
3. Reinstall dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

