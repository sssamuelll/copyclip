import platform
import subprocess
import shutil
import os
try:
    import pyperclip  # type: ignore
except Exception:
    pyperclip = None

# Brief: ClipboardManager
class ClipboardManager:
    """Cross-platform clipboard management with robust fallback support"""
    def __init__(self):
        self.system = platform.system()
        self.backends = self._get_backends()
        self.fallback_path = "copyclip_fallback.txt"

    def _get_backends(self):
        """
        Get clipboard backends in priority order for current OS with availability checks
        Args:
            TODO: describe arguments
        """
        if self.system == 'Darwin':  # macOS
            return [
                self._pyperclip_backend,
                self._pbcopy_backend
            ]
        elif self.system == 'Linux':
            # Detect desktop environment
            session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
            wayland_display = os.environ.get('WAYLAND_DISPLAY')
            is_wayland = 'wayland' in session_type or wayland_display
            
            # Prioritize Wayland backends if detected
            if is_wayland:
                return [
                    self._wayland_backend,
                    self._xclip_backend,
                    self._xsel_backend,
                    self._pyperclip_backend
                ]
            else:  # X11
                return [
                    self._xclip_backend,
                    self._xsel_backend,
                    self._pyperclip_backend
                ]
        elif self.system == 'Windows':
            return [
                self._pyperclip_backend,
                self._win32_backend
            ]
        else:
            return [self._pyperclip_backend]

    def copy(self, text):
        """
        Copy text to clipboard using available backends
        Args:
            TODO: describe arguments
        """
        if not text:
            print("[WARN] No content to copy")
            return False

        backend_names = []
        for backend in self.backends:
            try:
                backend_name = backend.__name__
                backend_names.append(backend_name)
                if backend(text):
                    return True
            except Exception as e:
                print(f"[DEBUG] Clipboard backend {backend_name} failed: {e}")

        # All backends failed
        print("[ERROR] All clipboard backends failed. Trying fallback...")
        return self._file_fallback(text)

    def _pyperclip_backend(self, text):
        """
        Use pyperclip as primary backend
        Args:
            TODO: describe arguments
        """
        try:
            if pyperclip is None:
                return False
            pyperclip.copy(text)
            return True
        except Exception as e:
            print(f"[WARN] Pyperclip failed: {e}")
            return False

    def _pbcopy_backend(self, text):
        """
        macOS native clipboard
        Args:
            TODO: describe arguments
        """
        if not shutil.which('pbcopy'):
            return False
        try:
            subprocess.run('pbcopy', input=text.encode('utf-8'), check=True)
            return True
        except Exception as e:
            print(f"[WARN] pbcopy failed: {e}")
            return False

    def _xclip_backend(self, text):
        """
        XClip for Linux X11 systems
        Args:
            TODO: describe arguments
        """
        if not shutil.which('xclip'):
            return False
        try:
            subprocess.run(['xclip', '-selection', 'clipboard'],
                          input=text.encode('utf-8'), check=True)
            return True
        except Exception as e:
            print(f"[WARN] xclip failed: {e}")
            return False

    def _xsel_backend(self, text):
        """
        XSel for Linux X11 systems
        Args:
            TODO: describe arguments
        """
        if not shutil.which('xsel'):
            return False
        try:
            subprocess.run(['xsel', '--clipboard'],
                          input=text.encode('utf-8'), check=True)
            return True
        except Exception as e:
            print(f"[WARN] xsel failed: {e}")
            return False

    def _wayland_backend(self, text):
        """
        wl-clipboard for Wayland systems
        Args:
            TODO: describe arguments
        """
        if not shutil.which('wl-copy'):
            return False
        try:
            subprocess.run(['wl-copy'], input=text.encode('utf-8'), check=True)
            return True
        except Exception as e:
            print(f"[WARN] wl-copy failed: {e}")
            return False

    def _win32_backend(self, text):
        """
        Windows native clipboard
        Args:
            TODO: describe arguments
        """
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text)
            win32clipboard.CloseClipboard()
            return True
        except ImportError:
            print("[INFO] win32clipboard module not installed")
        except Exception as e:
            print(f"[WARN] win32clipboard failed: {e}")
        return False

    def _file_fallback(self, text):
        """
        Fallback to file-based clipboard
        Args:
            TODO: describe arguments
        """
        try:
            with open(self.fallback_path, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"[WARN] Clipboard not available. Content saved to {self.fallback_path}")
            print("       You can install clipboard tools with:")
            print(self.get_install_instructions())
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save fallback file: {e}")
            return False

    def get_install_instructions(self):
        """
        Get clipboard tool installation instructions for current platform
        Args:
            TODO: describe arguments
        """
        if self.system == 'Linux':
            return ("  sudo apt install xclip   # for X11 systems\n"
                    "  sudo apt install wl-clipboard   # for Wayland systems")
        elif self.system == 'Darwin':
            return "  pbcopy is built-in on macOS"
        elif self.system == 'Windows':
            return ("  pip install pywin32   # for native clipboard support")
        return "  Consult your OS documentation for clipboard tools"