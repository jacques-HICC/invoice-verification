from paddleocr import PaddleOCR
from PIL import Image
import fitz  # PyMuPDF
import os
import json
import gc
import time

from config import OCRConfig

# Keep this for Windows stability (prevents library conflicts), 
# even if we don't pass arguments to Paddle.
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Global PaddleOCR instance for lazy loading
_ocr_engine = None

def get_ocr_reader():
    """Lazy initialization using YOUR EXACT CONFIGURATION"""
    global _ocr_engine
    if _ocr_engine is None:
        print("🔧 Initializing PaddleOCR (User Config)...")
        # Reverted to your exact working configuration
        _ocr_engine = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False
        )
        print("✅ PaddleOCR initialized")
    return _ocr_engine

def perform_ocr(pdf_path: str, preprocess: bool = True, max_pages: int = None) -> dict:
    """
    Priority: PaddleOCR -> Fallback: PyMuPDF
    Optimized with DPI=200 for speed.
    """
    if max_pages is None:
        max_pages = OCRConfig.MAX_OCR_PAGES

    print(f"\n📄 Starting OCR on: {pdf_path}")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    doc = None 
    
    # Prepare temp directory
    temp_dir = os.path.join(os.getcwd(), "temp")
    os.makedirs(temp_dir, exist_ok=True)

    ocr_results = {
        "method": "paddleocr",
        "pages": [],
        "total_pages": 0,
        "full_text": ""
    }
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        pages_to_process = min(total_pages, max_pages)
        ocr_results["total_pages"] = pages_to_process
        
        all_text_parts = []

        # =========================================================================
        # ATTEMPT 1: PaddleOCR (Primary)
        # =========================================================================
        try:
            print(f"🔄 Starting PaddleOCR processing...")
            ocr = get_ocr_reader()
            
            for page_num in range(pages_to_process):
                loop_start = time.time()
                page = doc[page_num]
                
                pix = page.get_pixmap(dpi=200)
                
                img_path = os.path.join(temp_dir, f"proc_p{page_num}_{int(time.time())}.png")
                pix.save(img_path)
                pix = None 
                
                try:
                    # Your specific prediction method
                    result = ocr.predict(input=img_path)
                    
                    page_data = {
                        "page_num": page_num + 1,
                        "blocks": [],
                        "text": ""
                    }
                    
                    page_text_lines = []
                    
                    # Your specific parsing logic
                    for res in result:
                        try:
                            json_data = res.json
                            if isinstance(json_data, dict) and 'res' in json_data:
                                ocr_data = json_data['res']
                                rec_texts = ocr_data.get('rec_texts', [])
                                dt_polys = ocr_data.get('dt_polys', [])
                                rec_scores = ocr_data.get('rec_scores', [])
                                
                                for i, text_content in enumerate(rec_texts):
                                    if text_content:
                                        block = {
                                            "text": text_content,
                                            "bbox": dt_polys[i] if i < len(dt_polys) else [],
                                            "confidence": float(rec_scores[i]) if i < len(rec_scores) else 0.0
                                        }
                                        page_data["blocks"].append(block)
                                        page_text_lines.append(text_content)
                        except Exception:
                            continue
                    
                    page_text = "\n".join(page_text_lines)
                    page_data["text"] = page_text
                    
                    proc_time = time.time() - loop_start
                    print(f"    ✓ Page {page_num + 1}: {len(page_text)} chars ({proc_time:.2f}s)")
                    
                    ocr_results["pages"].append(page_data)
                    all_text_parts.append(f"--- PAGE {page_num + 1} ---\n{page_text}")
                    
                finally:
                    if os.path.exists(img_path):
                        try: os.remove(img_path)
                        except: pass
            
            full_text = "\n\n".join(all_text_parts)
            if not full_text.strip():
                raise Exception("PaddleOCR produced empty text results")
                
            ocr_results["full_text"] = full_text
            return ocr_results

        # =========================================================================
        # ATTEMPT 2: PyMuPDF Fallback
        # =========================================================================
        except Exception as e:
            print(f"❌ PaddleOCR Failed: {type(e).__name__}: {e}")
            print(f"⚠️ Falling back to PyMuPDF Native Extraction...")
            
            ocr_results = {
                "method": "pymupdf_fallback",
                "pages": [],
                "total_pages": pages_to_process,
                "full_text": ""
            }
            all_text_parts = []
            
            try:
                for i in range(pages_to_process):
                    page_text = doc[i].get_text("text")
                    page_data = {"page_num": i+1, "text": page_text, "blocks": []}
                    ocr_results["pages"].append(page_data)
                    all_text_parts.append(f"--- PAGE {i + 1} ---\n{page_text}")
                
                ocr_results["full_text"] = "\n\n".join(all_text_parts)
                print(f"✅ Fallback successful.")
                return ocr_results
                
            except Exception as fallback_error:
                print(f"❌ Both methods failed: {fallback_error}")
                return {"method": "error", "full_text": "", "pages": [], "error": str(e)}
    
    finally:
        if doc:
            try: doc.close()
            except: pass
        
        try:
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
        except: pass
        
        gc.collect()