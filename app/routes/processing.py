from flask import Blueprint, request, Response, current_app
import os
import tempfile
import time

processing_bp = Blueprint('processing', __name__)

@processing_bp.route('/process_with_ai', methods=['POST'])
def process_with_ai():
    sp_tracker_global = current_app.config['SHAREPOINT_TRACKER']
    gcdocs_global = current_app.config['GCDOCS']
    
    data = request.json
    count = data.get('count', 10)
    model_filename = data.get('model', 'mistral-7b.gguf')
    
    def generate():
        try:
            # Initialize LLM
            yield "data: 🤖 Loading AI model...\n\n"
            from processing.extraction import LLMExtractor
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
                
                try:
                    # Download from GCDocs
                    download_start = time.time()
                    yield f"data:     📥 Downloading from GCDocs (Node: {node_id})...\n\n"
                    
                    # Make sure temp folder exists
                    temp_dir = os.path.join(os.getcwd(), "temp")
                    os.makedirs(temp_dir, exist_ok=True)

                    pdf_path = os.path.join(temp_dir, f"invoice_{node_id}.pdf")
                    
                    # Download using API-safe method
                    gcdocs_global.download_file(node_id=node_id, save_path=pdf_path)
                    download_time = time.time() - download_start
                    yield f"data:     ✓ PDF downloaded ({download_time:.1f}s)\n\n"
                    print(f"📥 Invoice saved to: {pdf_path}")
                    
                    # OCR
                    ocr_start = time.time()
                    yield f"data:     👁️ Performing OCR...\n\n"
                    from processing.ocr import perform_ocr
                    ocr_text = perform_ocr(pdf_path)
                    ocr_time = time.time() - ocr_start
                    yield f"data:     ✓ OCR complete ({ocr_time:.1f}s, {len(ocr_text)} chars)\n\n"
                    print(f"📝 Text passed to LLM ({len(ocr_text)} chars):\n{ocr_text[:500]}")

                    # Extract with LLM
                    extraction_start = time.time()
                    yield f"data:     🤖 Extracting data with AI...\n\n"
                    extracted = extractor.extract_invoice_data(ocr_text)
                    extraction_time = time.time() - extraction_start
                    yield f"data:     ✓ AI extraction complete ({extraction_time:.1f}s)\n\n"
                    print(f"🔍 DEBUG: Extracted data: {extracted}")

                    # Update SharePoint
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
                            'ai_processed': True
                        }
                    )

                    # delete the local file
                    os.remove(pdf_path)
                    
                    total_time = time.time() - invoice_start_time
                    yield f"data:     ✅ Complete in {total_time:.1f}s (Confidence: {extracted.get('confidence', 0) * 100:.0f}%)\n\n"

                except Exception as e:
                    import traceback
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