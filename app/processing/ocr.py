import easyocr
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance, ImageFilter
import fitz
import io
import os
import numpy as np

from config import OCRConfig

# Global reader instance for lazy loading
_reader = None

def get_ocr_reader():
    """Lazy initialization of EasyOCR reader"""
    global _reader
    if _reader is None:
        print("🔧 Initializing EasyOCR (first time only, downloads models if needed)...")
        _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        print("✅ EasyOCR initialized")
    return _reader

def perform_ocr(pdf_path: str, preprocess: bool = True, max_pages: int = None) -> str:
    """
    Perform OCR on a PDF file.
    
    Args:
        pdf_path: Path to PDF file
        preprocess: Whether to apply image preprocessing
        max_pages: Maximum number of pages to OCR (defaults to OCRConfig.MAX_OCR_PAGES)
    
    Returns:
        Extracted text from the PDF
    """
    if max_pages is None:
        max_pages = OCRConfig.MAX_OCR_PAGES
    
    print(f"\n📄 Starting OCR on: {pdf_path}")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        pages_to_process = min(total_pages, max_pages)
        
        print(f"✅ Opened PDF with {total_pages} pages")
        if total_pages > max_pages:
            print(f"⚠️ Limiting OCR to first {max_pages} pages (skipping {total_pages - max_pages} pages)")

        # Native text extraction first (only check the pages we'll process)
        native_text = ""
        for i in range(pages_to_process):
            page = doc[i]
            text = page.get_text("text")
            native_text += text
            print(f"  → Page {i+1}: native text length = {len(text)}")

        if len(native_text.strip()) > 100:
            print("✅ Using native extraction (enough text found)")
            doc.close()
            return native_text
        
        print("⚠️ Native extraction insufficient, switching to OCR...")
        
        # Get EasyOCR reader
        reader = get_ocr_reader()
        
        all_text = []
        for page_num in range(pages_to_process):
            page = doc[page_num]
            print(f"🖼️ Rendering page {page_num + 1}/{pages_to_process} to image...")
            pix = page.get_pixmap(dpi=300)
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))

            if preprocess:
                image = preprocess_image(
                    image, 
                    contrast=OCRConfig.PREPROCESS_CONTRAST, 
                    sharpen=OCRConfig.PREPROCESS_SHARPEN
                )

            # EasyOCR returns list of (bbox, text, confidence)
            image_np = np.array(image)
            results = reader.readtext(image_np)
            
            # Combine all detected text
            text = "\n".join([result[1] for result in results])

            print(f"  → OCR text length: {len(text)}")
            if len(text.strip()) == 0:
                print("    ⚠️ OCR returned no text on this page!")

            all_text.append(f"--- PAGE {page_num + 1} ---\n{text}")

        doc.close()
        
        if total_pages > max_pages:
            all_text.append(f"\n--- NOTE: {total_pages - max_pages} additional pages not processed ---")
        
        print(f"✅ OCR complete. Pages processed: {pages_to_process}/{total_pages}")
        return "\n\n".join(all_text)

    except Exception as e:
        raise Exception(f"OCR failed for {pdf_path}: {str(e)}")

def preprocess_image(image: Image.Image, contrast: float = 2.0, sharpen: bool = True) -> Image.Image:
    image = image.convert("L")
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(contrast)
    if sharpen:
        image = image.filter(ImageFilter.SHARPEN)
    return image