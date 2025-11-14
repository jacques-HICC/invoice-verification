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

def perform_ocr(pdf_path: str, preprocess: bool = True) -> str:
    print(f"\n📄 Starting OCR on: {pdf_path}")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
        print(f"✅ Opened PDF with {doc.page_count} pages")

        # Native text extraction first
        native_text = ""
        for i, page in enumerate(doc):
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
        for page_num, page in enumerate(doc):
            print(f"🖼️ Rendering page {page_num + 1} to image...")
            pix = page.get_pixmap(dpi=300)
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))

            # Save debug image
            #debug_img_path = f"debug_page_{page_num+1}.png"
            #image.save(debug_img_path)
            #print(f"  → Saved debug image: {debug_img_path}")

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
        print(f"✅ OCR complete. Total pages processed: {len(all_text)}")
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