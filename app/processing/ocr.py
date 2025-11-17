from paddleocr import PaddleOCR
from PIL import Image
import fitz
import os
import json

from config import OCRConfig

# Global PaddleOCR instance for lazy loading
_ocr_engine = None

def get_ocr_reader():
    """Lazy initialization of PaddleOCR - EXACT config from your working script"""
    global _ocr_engine
    if _ocr_engine is None:
        print("🔧 Initializing PaddleOCR (first time only, downloads models if needed)...")
        _ocr_engine = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False
        )
        print("✅ PaddleOCR initialized")
    return _ocr_engine

def perform_ocr(pdf_path: str, preprocess: bool = True, max_pages: int = None, native_threshold: int = 25) -> dict:
    """
    Perform OCR on a PDF only if the native text is insufficient.
    Returns a dictionary with OCR results in structured format.
    
    OPTIMIZATIONS:
    - Removed pdfplumber (redundant with PyMuPDF)
    - Lower DPI for faster OCR (200 instead of 300)
    - Only check first page for native text decision
    - Reuse temp directory instead of creating/deleting
    """
    if max_pages is None:
        max_pages = OCRConfig.MAX_OCR_PAGES

    print(f"\n📄 Starting OCR on: {pdf_path}")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    # --- Single method: PyMuPDF native text extraction ---
    doc = fitz.open(pdf_path)
    total_pages = doc.page_count
    pages_to_process = min(total_pages, max_pages)
    print(f"✅ Opened PDF with {total_pages} pages")
    
    if total_pages > max_pages:
        print(f"⚠️ Limiting OCR to first {max_pages} pages (skipping {total_pages - max_pages} pages)")

    # OPTIMIZATION: Only check first page for native text (much faster decision)
    first_page_text = doc[0].get_text("text").strip()
    print(f"📊 First page native text length: {len(first_page_text)} chars")

    # Smart decision: If first page has reasonable native text, extract all pages natively
    # BUT then verify the full extraction isn't too sparse
    if len(first_page_text) > native_threshold:
        print(f"✅ First page check passed, extracting all pages natively...")
        
        # Extract all page texts
        pages_data = []
        native_text = ""
        for i in range(pages_to_process):
            page_text = doc[i].get_text("text")
            native_text += page_text
            pages_data.append({"page_num": i+1, "text": page_text})
        
        # SMART FALLBACK: Check if total extraction is actually useful
        total_chars = len(native_text.strip())
        print(f"📊 Total native text extracted: {total_chars} chars")
        
        if total_chars < 200:
            print(f"⚠️ Native extraction too sparse ({total_chars} chars < 200), falling back to OCR...")
            # Don't close doc yet - we need it for OCR
            # Clear the native data and fall through to OCR
        else:
            print(f"✅ Native extraction successful with {total_chars} chars")
            doc.close()
            return {
                "method": "pymupdf",
                "full_text": native_text,
                "pages": pages_data,
                "total_pages": pages_to_process
            }
    else:
        print(f"⚠️ First page has insufficient text ({len(first_page_text)} chars)")

    # --- OCR fallback with PaddleOCR ---
    print(f"🔄 Starting PaddleOCR processing...")
    ocr = get_ocr_reader()
    
    ocr_results = {
        "method": "paddleocr",
        "pages": [],
        "total_pages": pages_to_process,
        "full_text": ""
    }
    
    all_text_parts = []
    temp_dir = "temp_ocr_images"
    os.makedirs(temp_dir, exist_ok=True)

    for page_num in range(pages_to_process):
        print(f"    📄 Processing page {page_num + 1}/{pages_to_process}...")
        page = doc[page_num]
        
        # OPTIMIZATION: Lower DPI (200 instead of 300) = 2.25x faster with minimal accuracy loss
        pix = page.get_pixmap(dpi=200)
        img_path = os.path.join(temp_dir, f"page_{page_num}.png")
        pix.save(img_path)
        
        try:
            # Run PaddleOCR prediction
            result = ocr.predict(input=img_path)
            
            page_data = {
                "page_num": page_num + 1,
                "blocks": [],
                "text": ""
            }
            
            page_text_lines = []
            
            # Process each result object
            for res in result:
                try:
                    json_data = res.json
                    
                    if isinstance(json_data, dict) and 'res' in json_data:
                        ocr_data = json_data['res']
                        
                        # Extract rec_texts, dt_polys, and rec_scores
                        rec_texts = ocr_data.get('rec_texts', [])
                        dt_polys = ocr_data.get('dt_polys', [])
                        rec_scores = ocr_data.get('rec_scores', [])
                        
                        print(f"    ✅ Found {len(rec_texts)} text items")
                        
                        # Combine texts with their metadata
                        for i, text_content in enumerate(rec_texts):
                            if text_content:
                                block = {
                                    "text": text_content,
                                    "bbox": dt_polys[i] if i < len(dt_polys) else [],
                                    "confidence": float(rec_scores[i]) if i < len(rec_scores) else 0.0
                                }
                                page_data["blocks"].append(block)
                                page_text_lines.append(text_content)
                    else:
                        print(f"    ⚠️ 'res' key not found in json data")
                        
                except Exception as e:
                    print(f"    ❌ Error accessing OCR data: {e}")
            
            # Join all text for this page
            page_text = "\n".join(page_text_lines)
            page_data["text"] = page_text
            
            print(f"    ✓ Page {page_num + 1}: Extracted {len(page_text)} chars, {len(page_data['blocks'])} blocks")
            
            ocr_results["pages"].append(page_data)
            all_text_parts.append(f"--- PAGE {page_num + 1} ---\n{page_text}")
            
        except Exception as e:
            print(f"    ❌ Error processing page {page_num + 1}: {e}")
        finally:
            # Clean up temporary image immediately after processing
            if os.path.exists(img_path):
                os.remove(img_path)

    doc.close()
    
    # Clean up temp directory (optional - leaving it doesn't hurt)
    try:
        os.rmdir(temp_dir)
    except:
        pass
    
    # Combine all text
    ocr_results["full_text"] = "\n\n".join(all_text_parts)
    
    if total_pages > max_pages:
        ocr_results["full_text"] += f"\n\n--- NOTE: {total_pages - max_pages} additional pages not processed ---"
    
    print(f"✅ OCR complete. Pages processed: {pages_to_process}/{total_pages}")
    print(f"📊 Total extracted text length: {len(ocr_results['full_text'])} chars")
    
    return ocr_results

def get_native_pdf_text(pdf_path: str) -> str:
    """Extract native text from PDF using PyMuPDF"""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text("text")
    doc.close()
    return text