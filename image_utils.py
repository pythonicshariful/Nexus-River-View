import os
from PIL import Image
from werkzeug.utils import secure_filename
from datetime import datetime

def save_as_webp(file, upload_folder):
    """
    Takes a Werkzeug FileStorage object, converts it to WebP, 
    saves it to the upload_folder, and returns the new filename.
    """
    if not file:
        return None
        
    original_filename = secure_filename(file.filename)
    if not original_filename:
        return None
        
    # Generate a unique base name to avoid collisions
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base_name = os.path.splitext(original_filename)[0]
    new_filename = f"{base_name}_{timestamp}.webp"
    file_path = os.path.join(upload_folder, new_filename)
    
    try:
        # Open image using Pillow
        img = Image.open(file)
        
        # Convert to RGB if necessary (e.g. for RGBA/PNG)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        # Save as WebP
        img.save(file_path, "WEBP", quality=80)
        return new_filename
    except Exception as e:
        print(f"Error converting image to WebP: {e}")
        # Fallback: Save original if conversion fails (optional, but requested all to be webp)
        return None

def convert_existing_to_webp(file_path):
    """
    Converts an existing file on disk to WebP and removes the original.
    Returns the new filename or None on failure.
    """
    if not os.path.exists(file_path):
        return None
        
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.webp':
        return os.path.basename(file_path)
        
    if ext not in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
        return None
        
    try:
        img = Image.open(file_path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        new_path = os.path.splitext(file_path)[0] + ".webp"
        img.save(new_path, "WEBP", quality=80)
        
        # Remove original
        os.remove(file_path)
        return os.path.basename(new_path)
    except Exception as e:
        print(f"Error converting existing image {file_path}: {e}")
        return None
