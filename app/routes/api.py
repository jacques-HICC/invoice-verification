from flask import Blueprint, jsonify, request, send_file, current_app, Response
import os
import json
from pathlib import Path
from datetime import datetime
from app.utils.pdf_utils import pdf_to_images

api_bp = Blueprint('api', __name__, url_prefix='/api')
validation_bp = Blueprint('validation', __name__)

# ============================================================================
# Processing State Manager
# ============================================================================

class ProcessingStateManager:
    """Manages persistent state for AI processing across page refreshes"""
    
    def __init__(self, state_file=None):
        # 1. Set a safer default path if none provided
        if state_file is None:
            # Use 'temp' folder in current working directory
            state_file = os.path.join(os.getcwd(), 'temp', 'invoice_ai_processing_state.json')
            
        self.state_file = state_file
        
        # 2. Ensure the DIRECTORY exists
        self._ensure_directory_exists()
        
        # 3. Load state (or default if file doesn't exist yet)
        self.state = self._load_state()
    
    def _ensure_directory_exists(self):
        """Create the directory for the state file if it doesn't exist"""
        try:
            directory = os.path.dirname(self.state_file)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
        except Exception as e:
            print(f"Error creating directory for state file: {e}")

    def _load_state(self):
        """Load state from disk"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading state: {e}")
        
        # Return default state if file not found or error
        return {
            'is_processing': False,
            'current_count': 0,
            'total_count': 0,
            'model': None,
            'console_logs': [],
            'started_at': None
        }
    
    def _save_state(self):
        """Save state to disk"""
        try:
            # Ensure directory exists before saving (in case it was deleted)
            self._ensure_directory_exists()
            
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"Error saving state: {e}")

    
    def start_processing(self, total_count, model):
        """Mark processing as started"""
        self.state['is_processing'] = True
        self.state['current_count'] = 0
        self.state['total_count'] = total_count
        self.state['model'] = model
        self.state['console_logs'] = []
        self.state['started_at'] = datetime.now().isoformat()
        self._save_state()
    
    def stop_processing(self):
        """Mark processing as stopped"""
        self.state['is_processing'] = False
        self._save_state()
    
    def update_progress(self, current_count):
        """Update processing progress"""
        self.state['current_count'] = current_count
        self._save_state()
    
    def add_log(self, message):
        """Add a console log message"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        self.state['console_logs'].append(log_entry)
        
        # Keep only last 1000 lines to prevent memory issues
        if len(self.state['console_logs']) > 1000:
            self.state['console_logs'] = self.state['console_logs'][-1000:]
        
        self._save_state()
    
    def get_state(self):
        """Get current state"""
        # Reload from disk to get latest state
        self.state = self._load_state()
        return self.state.copy()
    
    def clear_logs(self):
        """Clear console logs"""
        self.state['console_logs'] = []
        self._save_state()
    
    def reset(self):
        """Reset all state"""
        self.state = {
            'is_processing': False,
            'current_count': 0,
            'total_count': 0,
            'model': None,
            'console_logs': [],
            'started_at': None
        }
        self._save_state()


# Global instance
processing_state = ProcessingStateManager()


# ============================================================================
# Processing State API Routes
# ============================================================================

@api_bp.route('/processing_state', methods=['GET'])
def get_processing_state():
    """Get current processing state for UI restoration"""
    return jsonify(processing_state.get_state())


@api_bp.route('/cancel_processing', methods=['POST'])
def cancel_processing():
    """Cancel ongoing processing"""
    processing_state.stop_processing()
    processing_state.add_log("🛑 Processing cancelled by user")
    return jsonify({'status': 'cancelled'})


# ============================================================================
# Model Management
# ============================================================================

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


# ============================================================================
# PDF & Invoice Display Routes
# ============================================================================

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
        
        # 3) Convert only first page of PDF to image
        image_paths = pdf_to_images(pdf_path, output_folder=temp_dir, max_pages=1)
        if not image_paths:
            return jsonify({'error': 'Failed to render PDF as image'}), 500
        
        # 4) Only serve the first page (page 0)
        if page != 0:
            return jsonify({'error': 'Only first page is available'}), 400
        
        # 5) Serve the first page
        return send_file(image_paths[0], mimetype='image/jpeg')
        
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


# ============================================================================
# Validation Routes
# ============================================================================

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
            
            # Preserve OCR and LLM tracking fields
            "ocr_method": existing.get("OCR_Method", ""),
            "llm_used": existing.get("LLM_Used", ""),
            "time_taken": existing.get("Time_Taken", ""),
            
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