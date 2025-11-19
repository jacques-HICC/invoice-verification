import fitz  # PyMuPDF
from PIL import Image
import os

def pdf_to_images(pdf_path, output_folder='temp', max_pages=None):
    """
    Convert PDF to images using PyMuPDF (no Poppler required)
    Returns list of image paths
    
    Args:
        pdf_path: Path to the PDF file
        output_folder: Folder to save images
        max_pages: Maximum number of pages to convert (None = all pages)
    """
    os.makedirs(output_folder, exist_ok=True)
    image_paths = []
    doc = fitz.open(pdf_path)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]

    # Determine how many pages to process
    num_pages = len(doc) if max_pages is None else min(max_pages, len(doc))

    for i in range(num_pages):
        page = doc[i]
        pix = page.get_pixmap(dpi=150)  # Adjust DPI as needed
        img_path = os.path.join(output_folder, f"{base_name}_page_{i+1}.jpg")
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.save(img_path, "JPEG", quality=85)
        image_paths.append(img_path)

    doc.close()
    return image_paths