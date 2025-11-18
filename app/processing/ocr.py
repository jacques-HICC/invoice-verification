from paddleocr import PaddleOCR
from PIL import Image
import fitz  # PyMuPDF
import os
import json
import gc
import time

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

def perform_ocr(pdf_path: str, preprocess: bool = True, max_pages: int = None) -> dict:
    """
    Priority: PaddleOCR -> Fallback: PyMuPDF
    """
    if max_pages is None:
        max_pages = OCRConfig.MAX_OCR_PAGES

    print(f"\n📄 Starting OCR on: {pdf_path}")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    doc = None # Initialize as None for safety
    
    # Prepare temp directory for images
    temp_dir = os.path.join(os.getcwd(), "temp")
    os.makedirs(temp_dir, exist_ok=True)

    # Initialize result container
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
            print(f"🔄 Starting PaddleOCR processing (Priority Method)...")
            ocr = get_ocr_reader()
            
            for page_num in range(pages_to_process):
                print(f"    📄 Processing page {page_num + 1}/{pages_to_process}...")
                page = doc[page_num]
                
                # Render page to image
                pix = page.get_pixmap(dpi=300)
                
                # Unique filename to avoid conflicts
                img_path = os.path.join(temp_dir, f"proc_p{page_num}_{int(time.time())}.png")
                pix.save(img_path)
                pix = None # Free memory
                
                try:
                    # --- YOUR SPECIFIC PARSING LOGIC START ---
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
                                
                        except Exception as inner_e:
                            print(f"    ⚠️ Warning parsing specific block: {inner_e}")
                    
                    # Join all text for this page
                    page_text = "\n".join(page_text_lines)
                    page_data["text"] = page_text
                    # --- YOUR SPECIFIC PARSING LOGIC END ---
                    
                    print(f"    ✓ Page {page_num + 1}: Extracted {len(page_text)} chars")
                    
                    ocr_results["pages"].append(page_data)
                    all_text_parts.append(f"--- PAGE {page_num + 1} ---\n{page_text}")
                    
                finally:
                    # Clean up temporary image immediately
                    if os.path.exists(img_path):
                        try:
                            os.remove(img_path)
                        except: pass
            
            # Check if we actually got text
            full_text = "\n\n".join(all_text_parts)
            if not full_text.strip():
                raise Exception("PaddleOCR produced empty text results")
                
            ocr_results["full_text"] = full_text
            print(f"✅ PaddleOCR complete. Total chars: {len(full_text)}")
            
            # CRITICAL FIX: Do NOT close doc here. 
            # Let the outer finally block handle it.
            return ocr_results

        # =========================================================================
        # ATTEMPT 2: PyMuPDF Fallback
        # =========================================================================
        except Exception as e:
            print(f"❌ PaddleOCR Failed: {e}")
            print(f"⚠️ Falling back to PyMuPDF Native Extraction...")
            
            # Reset results for fallback
            ocr_results = {
                "method": "pymupdf_fallback",
                "pages": [],
                "total_pages": pages_to_process,
                "full_text": ""
            }
            all_text_parts = []
            
            try:
                # We can reuse the open 'doc' object because we didn't close it!
                for i in range(pages_to_process):
                    page_text = doc[i].get_text("text")
                    
                    page_data = {
                        "page_num": i+1, 
                        "text": page_text,
                        "blocks": [] # Native text doesn't usually give blocks in same format
                    }
                    
                    ocr_results["pages"].append(page_data)
                    all_text_parts.append(f"--- PAGE {i + 1} ---\n{page_text}")
                
                ocr_results["full_text"] = "\n\n".join(all_text_parts)
                print(f"✅ Fallback successful. Extracted {len(ocr_results['full_text'])} chars.")
                
                return ocr_results
                
            except Exception as fallback_error:
                print(f"❌ Critical Error: Both PaddleOCR and Fallback failed: {fallback_error}")
                return {
                    "method": "error",
                    "full_text": "",
                    "pages": [],
                    "error": str(e)
                }
    
    # =========================================================================
    # FINALLY: Cleanup
    # =========================================================================
    finally:
        # This block handles closing for BOTH Success and Failure paths
        if doc:
            try:
                # Safe close check
                doc.close()
            except:
                pass
        
        # Cleanup temp dir
        try:
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
        except:
            pass
        
        gc.collect()