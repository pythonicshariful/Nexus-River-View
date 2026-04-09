import PyInstaller.__main__
import os
import shutil
import certifi

# Clean up previous build
if os.path.exists('dist'):
    shutil.rmtree('dist')
if os.path.exists('build'):
    shutil.rmtree('build')

import sys
import tkinter

# Detect TCL/TK paths
tcl_lib = os.path.join(sys.base_prefix, 'tcl', 'tcl8.6')
tk_lib = os.path.join(sys.base_prefix, 'tcl', 'tk8.6')

if not os.path.exists(tcl_lib):
    # Fallback/Search
    tcl_dir = os.path.join(sys.base_prefix, 'tcl')
    if os.path.exists(tcl_dir):
        for d in os.listdir(tcl_dir):
            if d.startswith('tcl'): tcl_lib = os.path.join(tcl_dir, d)
            if d.startswith('tk'): tk_lib = os.path.join(tcl_dir, d)

print(f"Detected TCL: {tcl_lib}")
print(f"Detected TK: {tk_lib}")

# Define PyInstaller arguments
cert_path =  os.path.join(os.path.dirname(certifi.__file__), 'cacert.pem')

args = [
    'run_gui.py',
    '--name=NexusRiverView',
    '--onefile',
    '--noconsole',
    '--add-data=templates;templates',
    '--add-data=static;static',
    '--add-data=admin_config.json;.',
    '--add-data=.env;.',
    '--add-data=credentials.json;.',
    '--add-data=nexus-river-view-600x866.ico;.', 
    f'--add-data={cert_path};certifi',
    # Add TCL/TK libraries explicitly
    f'--add-data={tcl_lib};tcl',
    f'--add-data={tk_lib};tk',
    # Hidden imports
    '--hidden-import=engineio.async_drivers.threading',
    '--hidden-import=certifi', 
    '--hidden-import=pandas',
    '--hidden-import=openpyxl',
    '--hidden-import=openpyxl.cell._writer',
    '--hidden-import=webview',
    '--hidden-import=tkinter',
    '--hidden-import=_tkinter',
    '--hidden-import=tkinter.filedialog',
    '--icon=nexus-river-view-600x866.ico',
    '--clean',
]

# Set environment variables for the build process to help Tkinter find its libs
os.environ['TCL_LIBRARY'] = tcl_lib
os.environ['TK_LIBRARY'] = tk_lib

print("Building EXE with arguments:", args)
PyInstaller.__main__.run(args)

# Post-build: Copy nexus.db to dist folder if it exists in root
db_path = 'nexus.db'
if os.path.exists(db_path):
    shutil.copy2(db_path, os.path.join('dist', 'nexus.db'))
    print(f"Copied {db_path} to dist/ for immediate use.")

print("Build complete. detailed logs in build/ and output in dist/")
