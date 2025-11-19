# app/processing/ocr.py
from paddleocr import PaddleOCR
from PIL import Image
import fitz  # PyMuPDF
import os
import json
import gc
import time
import threading
from typing import Dict, List

from config import OCRConfig

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

_ocr_engine = None

def get_ocr_reader():
    """Lazy initialization using YOUR EXACT CONFIGURATION"""
    global _ocr_engine
    if _ocr_engine is None:
        print("🔧 Initializing PaddleOCR (User Config)...")
        _ocr_engine = PaddleOCR(
            lang="en",
            ocr_version="PP-OCRv4",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False
        )
        print("✅ PaddleOCR initialized")
    return _ocr_engine


def _process_single_page(ocr, page, page_num: int, temp_dir: str) -> Dict:
    """Process a single page and return structured data"""
    loop_start = time.time()
    
    pix = page.get_pixmap(dpi=200)
    img_path = os.path.join(temp_dir, f"proc_p{page_num}_{int(time.time() * 1000)}.png")
    pix.save(img_path)
    pix = None
    
    try:
        result = ocr.predict(input=img_path)
        
        page_data = {
            "page_num": page_num + 1,
            "blocks": [],
            "text": ""
        }
        
        page_text_lines = []
        
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
        
        return page_data
        
    finally:
        if os.path.exists(img_path):
            try: 
                os.remove(img_path)
            except: 
                pass


def _background_ocr_worker(doc, ocr, start_page: int, end_page: int, 
                          temp_dir: str, results_container: Dict):
    """Background worker that processes pages 2-N"""
    try:
        print(f"🔄 Background OCR worker starting (pages {start_page+1}-{end_page})...")
        
        for page_num in range(start_page, end_page):
            page = doc[page_num]
            page_data = _process_single_page(ocr, page, page_num, temp_dir)
            
            # Thread-safe append to results
            results_container["pages"].append(page_data)
            results_container["full_text"] += f"\n\n--- PAGE {page_num + 1} ---\n{page_data['text']}"
        
        results_container["background_complete"] = True
        print(f"✅ Background OCR complete ({end_page - start_page} pages)")
        
    except Exception as e:
        print(f"❌ Background OCR error: {e}")
        results_container["background_error"] = str(e)


def perform_ocr(pdf_path: str, preprocess: bool = True, max_pages: int = None) -> dict:
    """
    OPTIMIZED: Process page 1 immediately, background-process rest
    
    Returns immediately with page 1 data, spawns background thread for pages 2-N
    """
    if max_pages is None:
        max_pages = OCRConfig.MAX_OCR_PAGES

    print(f"\n📄 Starting OPTIMIZED OCR on: {pdf_path}")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    doc = None 
    temp_dir = os.path.join(os.getcwd(), "temp")
    os.makedirs(temp_dir, exist_ok=True)

    ocr_results = {
        "method": "paddleocr_optimized",
        "pages": [],
        "total_pages": 0,
        "full_text": "",
        "background_complete": False,
        "background_error": None
    }
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        pages_to_process = min(total_pages, max_pages)
        ocr_results["total_pages"] = pages_to_process
        
        # ========================================================================
        # STEP 1: FAST PATH - Process Page 1 IMMEDIATELY
        # ========================================================================
        try:
            print(f"⚡ FAST PATH: Processing page 1 for immediate LLM submission...")
            ocr = get_ocr_reader()
            
            page_1_data = _process_single_page(ocr, doc[0], 0, temp_dir)
            
            ocr_results["pages"].append(page_1_data)
            ocr_results["full_text"] = f"--- PAGE 1 ---\n{page_1_data['text']}"
            
            print(f"✅ Page 1 ready for LLM ({len(page_1_data['text'])} chars)")
            
            # ====================================================================
            # STEP 2: BACKGROUND PATH - Spawn thread for pages 2-N
            # ====================================================================
            if pages_to_process > 1:
                print(f"🔄 Spawning background thread for pages 2-{pages_to_process}...")
                
                # Create background thread
                bg_thread = threading.Thread(
                    target=_background_ocr_worker,
                    args=(doc, ocr, 1, pages_to_process, temp_dir, ocr_results),
                    daemon=True  # Allow main thread to exit even if background not done
                )
                bg_thread.start()
                
                print(f"⚡ Returning page 1 immediately while background processes rest...")
            else:
                ocr_results["background_complete"] = True
                print(f"ℹ️ No background processing needed")
            
            return ocr_results

        # ====================================================================
        # FALLBACK: PyMuPDF if PaddleOCR fails
        # ====================================================================
        except Exception as e:
            print(f"❌ PaddleOCR Failed: {type(e).__name__}: {e}")
            print(f"⚠️ Falling back to PyMuPDF Native Extraction...")
            
            ocr_results = {
                "method": "pymupdf_fallback",
                "pages": [],
                "total_pages": pages_to_process,
                "full_text": "",
                "background_complete": True  # Fallback is synchronous
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
                return {
                    "method": "error", 
                    "full_text": "", 
                    "pages": [], 
                    "error": str(e),
                    "background_complete": True
                }
    
    finally:
        # NOTE: We do NOT close the doc here anymore since background thread needs it
        # The background thread will handle cleanup when done
        # gc.collect() will run periodically anyway
        pass


def wait_for_background_ocr(ocr_results: Dict, timeout: float = 60.0) -> Dict:
    """
    Optional: Call this if you need to wait for background processing to complete
    (e.g., before saving final results to SharePoint)
    
    Returns the updated ocr_results dict
    """
    start_time = time.time()
    
    while not ocr_results.get("background_complete", False):
        if time.time() - start_time > timeout:
            print(f"⚠️ Background OCR timeout after {timeout}s")
            break
        time.sleep(0.1)
    
    if ocr_results.get("background_error"):
        print(f"⚠️ Background OCR had errors: {ocr_results['background_error']}")
    
    return ocr_results