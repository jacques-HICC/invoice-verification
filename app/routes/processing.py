from flask import Blueprint, request, Response, current_app, session, jsonify
import os
import tempfile
import time

processing_bp = Blueprint('processing', __name__)

from app.processing.ocr import perform_ocr, wait_for_background_ocr
from config import OCRConfig

@processing_bp.route('/process_with_ai', methods=['POST'])
def process_with_ai():
    # Check authentication FIRST
    if not session.get('gcdocs_authenticated'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    sp_tracker_global = current_app.config.get('SHAREPOINT_TRACKER')
    gcdocs_global = current_app.config.get('GCDOCS')
    
    # Check if services are available
    if not sp_tracker_global or not gcdocs_global:
        return jsonify({'error': 'Services not configured'}), 500
    
    data = request.json
    count = data.get('count', 10)
    model_filename = data.get('model', 'mistral-7b.gguf')
    
    def generate():
        try:
            # Initialize LLM
            yield "data: 🤖 Loading AI model...\n\n"
            from app.processing.extraction import LLMExtractor
            from app.processing.file_converter import FileConverter
            extractor = LLMExtractor(model_filename)
            yield f"data: ✓ Model loaded: {model_filename}\n\n"
            
            # Get unprocessed invoices
            yield "data: 📋 Fetching unprocessed invoices from SharePoint...\n\n"
            all_items = sp_tracker_global.get_all_items()
            unprocessed = [item for item in all_items if not item.get('AI_Processed', False)][:count]
            
            if not unprocessed:
                yield "data: ⚠️ No unprocessed invoices found\n\n"
                yield "data: [DONE]\n\n"
                return
            
            yield f"data: ✓ Found {len(unprocessed)} unprocessed invoices\n\n"
            
            # Process each invoice
            for i, invoice in enumerate(unprocessed, 1):
                invoice_start_time = time.time()
                
                node_id = invoice.get('NodeID')
                filename = invoice.get('Filename', f'Invoice_{node_id}')
                
                yield f"data: \n[{i}/{len(unprocessed)}] {filename}\n\n"
                
                pdf_to_cleanup = None
                
                try:
                    # Download from GCDocs
                    download_start = time.time()
                    yield f"data:     📥 Downloading from GCDocs (Node: {node_id})\n\n"
                    
                    temp_dir = os.path.join(os.getcwd(), "temp")
                    os.makedirs(temp_dir, exist_ok=True)

                    file_ext = os.path.splitext(filename)[1].lower()
                    download_path = os.path.join(temp_dir, f"invoice_{node_id}{file_ext}")
                    
                    gcdocs_global.download_file(node_id=node_id, save_path=download_path)
                    download_time = time.time() - download_start
                    yield f"data:     ✓ File downloaded ({download_time:.1f}s)\n\n"
                    
                    # Convert to PDF if needed
                    if FileConverter.needs_conversion(download_path):
                        yield f"data:     🔄 Converting {file_ext} to PDF...\n\n"
                        convert_start = time.time()
                        pdf_path = FileConverter.convert_to_pdf(download_path)
                        convert_time = time.time() - convert_start
                        yield f"data:     ✓ Converted to PDF ({convert_time:.1f}s)\n\n"
                        
                        os.remove(download_path)
                        pdf_to_cleanup = pdf_path
                    else:
                        pdf_path = download_path
                        pdf_to_cleanup = download_path
                    
                    # ================================================================
                    # OPTIMIZED OCR: Page 1 immediately, rest in background
                    # ================================================================
                    yield f"data:     👀 Reading page 1 (rest processing in background)...\n\n"
                    ocr_start = time.time()
                    
                    # This returns IMMEDIATELY with page 1 data
                    ocr_result = perform_ocr(pdf_path, max_pages=OCRConfig.MAX_OCR_PAGES)
                    
                    ocr_time = time.time() - ocr_start
                    text_length = len(ocr_result.get('full_text', ''))
                    ocr_method = ocr_result.get('method', 'unknown')
                    total_pages = ocr_result.get('total_pages', 1)
                    
                    yield f"data:     ✓ Page 1 ready ({ocr_time:.1f}s, {text_length} chars)\n\n"
                    
                    if total_pages > 1:
                        yield f"data:     🔄 Pages 2-{total_pages} processing in background...\n\n"
                    
                    # ================================================================
                    # LLM EXTRACTION: Starts immediately with page 1 data
                    # ================================================================
                    extraction_start = time.time()
                    yield f"data:     🤖 AI analyzing invoice (using page 1)...\n\n"
                    
                    extracted = extractor.extract_invoice_data(ocr_result)
                    
                    extraction_time = time.time() - extraction_start
                    yield f"data:     ✓ AI extraction complete ({extraction_time:.1f}s)\n\n"
                    
                    # ================================================================
                    # WAIT FOR BACKGROUND OCR (for complete SharePoint storage)
                    # ================================================================
                    if not ocr_result.get('background_complete', False):
                        yield f"data:     ⏳ Finalizing background OCR...\n\n"
                        wait_start = time.time()
                        
                        ocr_result = wait_for_background_ocr(ocr_result, timeout=30.0)
                        
                        wait_time = time.time() - wait_start
                        
                        if ocr_result.get('background_complete'):
                            final_text_length = len(ocr_result.get('full_text', ''))
                            yield f"data:     ✓ All {total_pages} pages complete ({wait_time:.1f}s, {final_text_length} total chars)\n\n"
                        else:
                            yield f"data:     ⚠️ Background OCR timeout (proceeding with page 1 data)\n\n"
                    
                    total_time = time.time() - invoice_start_time
                    
                    # ================================================================
                    # UPDATE SHAREPOINT with complete results
                    # ================================================================
                    yield f"data:     💾 Updating SharePoint...\n\n"
                    sp_tracker_global.create_or_update_item(
                        node_id=int(node_id),
                        filename=filename,
                        gcdocs_url=f"https://gcdocs.gc.ca/infc/llisapi.dll/app/nodes/{node_id}",
                        metadata={
                            'ai_invoice_number': extracted.get('invoice_number', ''),
                            'ai_company_name': extracted.get('company_name', ''),
                            'ai_invoice_date': extracted.get('invoice_date', ''),
                            'ai_total_amount': extracted.get('total_amount', 0),
                            'ai_confidence': extracted.get('confidence', 0),
                            'ai_processed': True,
                            'ocr_method': extracted.get('ocr_method', 'unknown'),
                            'llm_used': extracted.get('model_used', model_filename),
                            'time_taken': total_time,
                            'pages_processed': ocr_result.get('total_pages', 1),
                            'ocr_chars': len(ocr_result.get('full_text', ''))
                        }
                    )

                    # Cleanup
                    if pdf_to_cleanup and os.path.exists(pdf_to_cleanup):
                        os.remove(pdf_to_cleanup)
                    
                    yield f"data:     ✅ Complete in {total_time:.1f}s (OCR: {ocr_time:.1f}s, AI: {extraction_time:.1f}s)\n\n"

                except Exception as e:
                    import traceback
                    
                    # Cleanup on error
                    if pdf_to_cleanup and os.path.exists(pdf_to_cleanup):
                        try:
                            os.remove(pdf_to_cleanup)
                        except:
                            pass
                    
                    total_time = time.time() - invoice_start_time
                    yield f"data:     ❌ Error after {total_time:.1f}s: {str(e)}\n\n"
                    yield f"data:     {traceback.format_exc()}\n\n"
                    continue
            
            yield "data: \n🎉 All invoices processed!\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            import traceback
            yield f"data: ❌ Fatal error: {str(e)}\n\n"
            yield f"data: {traceback.format_exc()}\n\n"
            yield "data: [DONE]\n\n"
    
    return Response(generate(), mimetype='text/event-stream')