from flask import Blueprint, jsonify, request, send_file, current_app
import os
from pathlib import Path
from app.utils.pdf_utils import pdf_to_images

api_bp = Blueprint('api', __name__, url_prefix='/api')
validation_bp = Blueprint('validation', __name__)

@api_bp.route('/models', methods=['GET'])
def get_available_models():
    """Scan models/ directory and return available GGUF models"""
    models_dir = Path(__file__).resolve().parent.parent / 'models'
    
    print(f"Looking for models in: {models_dir}")
    print(f"Does models/ exist? {models_dir.exists()}")
    
    if not models_dir.exists():
        return jsonify([])
    
    models = []
    for file in models_dir.glob('*.gguf'):
        display_name = file.stem.replace('-', ' ').replace('_', ' ').title()
        models.append({
            'filename': file.name,
            'display_name': display_name,
            'path': str(file),
            'size_mb': round(file.stat().st_size / (1024*1024), 2),
            'is_default': file.name == 'mistral-7b.gguf'
        })
    
    models.sort(key=lambda x: x['display_name'])
    
    print(f"Returning {len(models)} models")
    return jsonify(models)

@validation_bp.route('/download_pdf/<node_id>', methods=['GET'])
def download_pdf(node_id):
    """Download PDF from GCDocs and serve it"""
    gcdocs = current_app.config['GCDOCS']
    
    try:
        # Create temp directory
        temp_dir = os.path.join(os.getcwd(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Download PDF
        pdf_path = os.path.join(temp_dir, f"invoice_{node_id}.pdf")
        
        # Only download if not already cached
        if not os.path.exists(pdf_path):
            gcdocs.download_file(node_id=int(node_id), save_path=pdf_path)
            
            if not os.path.exists(pdf_path):
                return jsonify({'error': 'PDF download failed'}), 500
        
        # Serve the PDF with inline display (opens in browser tab)
        return send_file(
            pdf_path, 
            mimetype='application/pdf',
            as_attachment=False,  # Display inline, not download
            download_name=f'invoice_{node_id}.pdf'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@validation_bp.route('/next_invoice', methods=['GET'])
def get_next_invoice():
    """Get next unvalidated invoice that has been AI processed"""
    sp_tracker = current_app.config['SHAREPOINT_TRACKER']
    
    try:
        all_items = sp_tracker.get_all_items()
        
        # Find invoices that are AI processed but not human validated
        unvalidated = [
            item for item in all_items 
            if item.get('AI_Processed', False) and not item.get('Human_Validated', False)
        ]
        
        if not unvalidated:
            return jsonify({'error': 'No invoices to validate'}), 404
        
        # Get the first one
        invoice = unvalidated[0]
        
        return jsonify({
            'id': invoice.get('id'),
            'node_id': invoice.get('NodeID'),
            'filename': invoice.get('Filename', ''),
            'ai_invoice_number': invoice.get('AI_InvoiceNumber', ''),
            'ai_company_name': invoice.get('AI_CompanyName', ''),
            'ai_invoice_date': invoice.get('AI_InvoiceDate', ''),
            'ai_total_amount': invoice.get('AI_TotalAmount', 0),
            'ai_confidence': invoice.get('AI_Confidence', 0),
            'remaining_count': len(unvalidated)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@validation_bp.route('/invoice_image/<node_id>', methods=['GET'])
@validation_bp.route('/invoice_image/<node_id>/<int:page>', methods=['GET'])
def get_invoice_image(node_id, page=0):
    """Download invoice from GCDocs, convert to images, and serve specific page"""
    gcdocs = current_app.config['GCDOCS']
    
    try:
        # 1) Create temp directory
        temp_dir = os.path.join(os.getcwd(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # 2) Download PDF
        pdf_path = os.path.join(temp_dir, f"invoice_{node_id}.pdf")
        
        # Only download if not already cached
        if not os.path.exists(pdf_path):
            gcdocs.download_file(node_id=int(node_id), save_path=pdf_path)
            
            if not os.path.exists(pdf_path):
                return jsonify({'error': 'PDF download failed'}), 500
        
        # 3) Convert PDF to images (this will use cached images if they exist)
        image_paths = pdf_to_images(pdf_path, output_folder=temp_dir)
        if not image_paths:
            return jsonify({'error': 'Failed to render PDF as image'}), 500
        
        # 4) Validate page number
        if page < 0 or page >= len(image_paths):
            return jsonify({'error': f'Invalid page number. Document has {len(image_paths)} pages.'}), 400
        
        # 5) Serve the requested page
        return send_file(image_paths[page], mimetype='image/jpeg')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@validation_bp.route('/invoice_page_count/<node_id>', methods=['GET'])
def get_invoice_page_count(node_id):
    """Get the total number of pages for an invoice"""
    gcdocs = current_app.config['GCDOCS']
    
    try:
        temp_dir = os.path.join(os.getcwd(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Download PDF if not cached
        pdf_path = os.path.join(temp_dir, f"invoice_{node_id}.pdf")
        if not os.path.exists(pdf_path):
            gcdocs.download_file(node_id=int(node_id), save_path=pdf_path)
            
            if not os.path.exists(pdf_path):
                return jsonify({'page_count': 1}), 500
        
        # Get page count from PDF using PyMuPDF
        import fitz
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()
        
        return jsonify({'page_count': page_count})
        
    except Exception as e:
        print(f"Error getting page count: {e}")
        return jsonify({'error': str(e), 'page_count': 1}), 500


@validation_bp.route('/save_validation', methods=['POST'])
def save_validation():
    """Save human validation and mark as complete without overwriting AI fields"""
    sp_tracker = current_app.config['SHAREPOINT_TRACKER']
    
    data = request.json
    node_id = data.get('node_id')
    
    if not node_id:
        return jsonify({'error': 'node_id required'}), 400
    
    try:
        # Get current item to preserve AI fields
        existing = sp_tracker.get_item_by_node_id(int(node_id))
        if not existing:
            return jsonify({'error': 'Invoice not found'}), 404
        
        # Build metadata dict with **existing AI fields plus new human fields**
        metadata = {
            # Preserve AI fields from existing SharePoint item
            "ai_invoice_number": existing.get("AI_InvoiceNumber", ""),
            "ai_company_name": existing.get("AI_CompanyName", ""),
            "ai_invoice_date": existing.get("AI_InvoiceDate", ""),
            "ai_total_amount": existing.get("AI_TotalAmount", 0),
            "ai_confidence": existing.get("AI_Confidence", 0),
            "ai_processed": existing.get("AI_Processed", False),
            
            # Human validation fields from request
            "human_invoice_number": data.get('invoice_number', ''),
            "human_company_name": data.get('company_name', ''),
            "human_invoice_date": data.get('invoice_date', ''),
            "human_total_amount": float(data.get('total_amount', 0)),
            "human_notes": data.get('notes', ''),
            "human_validated": True,
            "human_flagged": data.get('flagged', False)
        }
        
        # Update item
        sp_tracker.create_or_update_item(
            node_id=int(node_id),
            filename=existing.get('Filename', ''),
            gcdocs_url=existing.get('GCDocsURL', ''),
            metadata=metadata
        )
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500