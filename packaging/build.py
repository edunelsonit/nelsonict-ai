"""Build a platform-local frozen desktop folder; installers wrap this output."""
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
os.chdir(root)
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name','nelsonict-ai',
         '--paths',str(root),'--add-data',f'app/static{os.pathsep}app/static','--add-data',f'LICENSE{os.pathsep}.',
         '--collect-submodules','app','--collect-all','llama_cpp','--collect-all','pypdfium2',
         '--collect-all','docx','--collect-all','openpyxl','--collect-all','uvicorn',
         '--hidden-import','PIL._tkinter_finder','--hidden-import','tkinter']
# Console mode keeps subprocess shutdown signals and diagnostic output available.
command+=['packaging/desktop_entry.py']
subprocess.run(command,check=True)
