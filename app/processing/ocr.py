from paddleocr import PaddleOCR
from PIL import Image
import fitz
import os
import json
import pdfplumber

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
    """
    if max_pages is None:
        max_pages = OCRConfig.MAX_OCR_PAGES

    print(f"\n📄 Starting OCR on: {pdf_path}")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    # --- Try pdfplumber first ---
    pdfplumber_text = get_pdfplumber_text(pdf_path)
    if len(pdfplumber_text.strip()) > native_threshold:
        print(f"✅ Using pdfplumber text, skipping OCR ({len(pdfplumber_text.strip())} chars)")
        return {
            "method": "pdfplumber",
            "full_text": pdfplumber_text,
            "pages": [{"page_num": 1, "text": pdfplumber_text}],
            "total_pages": 1
        }

    # --- Fallback to PyMuPDF native text extraction ---
    doc = fitz.open(pdf_path)
    total_pages = doc.page_count
    pages_to_process = min(total_pages, max_pages)
    print(f"✅ Opened PDF with {total_pages} pages")
    if total_pages > max_pages:
        print(f"⚠️ Limiting OCR to first {max_pages} pages (skipping {total_pages - max_pages} pages)")

    native_text = ""
    for i in range(pages_to_process):
        native_text += doc[i].get_text("text")

    native_text_stripped = native_text.strip()
    print(f"📊 Native text (PyMuPDF) length: {len(native_text_stripped)} chars")

    if len(native_text_stripped) > native_threshold:
        print(f"✅ Using PyMuPDF native extraction, skipping OCR")
        doc.close()
        return {
            "method": "pymupdf",
            "full_text": native_text,
            "pages": [{"page_num": i+1, "text": doc[i].get_text("text")} for i in range(pages_to_process)],
            "total_pages": pages_to_process
        }

    # --- OCR fallback with PaddleOCR - MATCHING YOUR WORKING SCRIPT ---
    print(f"⚠️ Native text below threshold ({len(native_text_stripped)} chars), performing OCR...")
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
        
        # Convert page to image
        pix = page.get_pixmap(dpi=300)
        img_path = os.path.join(temp_dir, f"page_{page_num}.png")
        pix.save(img_path)
        
        try:
            # Run PaddleOCR prediction - EXACT method from your working script
            result = ocr.predict(input=img_path)
            
            # Extract structured data from result - MATCHING YOUR SCRIPT
            page_data = {
                "page_num": page_num + 1,
                "blocks": [],
                "text": ""
            }
            
            page_text_lines = []
            
            # Process each result object (matching your working example)
            for res in result:
                print(f"    🔍 Processing result object: {type(res)}")
                
                try:
                    # Access the nested 'res' key which contains the actual OCR data
                    # Structure: res.json['res']['rec_texts']
                    json_data = res.json
                    
                    # The actual data is nested inside another 'res' key
                    if isinstance(json_data, dict) and 'res' in json_data:
                        ocr_data = json_data['res']
                        print(f"    📋 Found nested data with keys: {ocr_data.keys()}")
                        
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
                        print(f"    📋 Available keys: {json_data.keys() if isinstance(json_data, dict) else 'Not a dict'}")
                        
                except Exception as e:
                    print(f"    ❌ Error accessing OCR data: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Join all text for this page
            page_text = "\n".join(page_text_lines)
            page_data["text"] = page_text
            
            print(f"    ✓ Page {page_num + 1}: Extracted {len(page_text)} chars, {len(page_data['blocks'])} blocks")
            
            # Debug: print first few lines
            if page_text_lines:
                print(f"    📝 First 3 lines: {page_text_lines[:3]}")
            
            ocr_results["pages"].append(page_data)
            all_text_parts.append(f"--- PAGE {page_num + 1} ---\n{page_text}")
            
        except Exception as e:
            print(f"    ❌ Error processing page {page_num + 1}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Clean up temporary image
            if os.path.exists(img_path):
                os.remove(img_path)

    doc.close()
    
    # Clean up temp directory
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
    print(f"📝 Preview of extracted text:\n{ocr_results['full_text'][:500]}")
    
    return ocr_results

def get_pdfplumber_text(pdf_path: str) -> str:
    """Extract text using pdfplumber"""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"⚠️ pdfplumber extraction failed: {e}")
    return text.strip()

def get_native_pdf_text(pdf_path: str) -> str:
    """Extract native text from PDF using PyMuPDF"""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text("text")
    doc.close()
    return text