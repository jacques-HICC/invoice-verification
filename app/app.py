from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, Response, stream_with_context
import os
import csv
from datetime import datetime

import fitz  # PyMuPDF
from PIL import Image
#import pytesseract
import io

from services.gcdocs import Session, GCDocs
from services.sharepoint import SharePointTracker
from services.invoice_repo import InvoiceRepository

# Create Flask app first
app = Flask(__name__)

# Now import and register blueprints
from routes.api import api_bp
from routes.api import validation_bp
from routes.processing import processing_bp


app.register_blueprint(validation_bp, url_prefix='/api')
app.register_blueprint(api_bp)
app.register_blueprint(processing_bp)

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Store processed invoice data
processed_invoices = []

# globals for services
session_global = None
gcdocs_global = None
repo_global = None
sp_tracker_global = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_invoice/<int:invoice_id>')
def get_invoice(invoice_id):
    """Get data for a specific invoice by ID"""
    if 0 <= invoice_id < len(processed_invoices):
        return jsonify(processed_invoices[invoice_id])
    else:
        return jsonify({'error': 'Invoice not found'}), 404

@app.route('/get_all_invoices')
def get_all_invoices():
    """Get all processed invoices"""
    return jsonify({
        'invoices': processed_invoices,
        'total': len(processed_invoices)
    })

@app.route('/validate', methods=['POST'])
def validate_invoice():
    """Save validated/corrected invoice data and update GCDocs metadata"""
    data = request.json
    invoice_id = data.get('invoice_id')
    
    if 0 <= invoice_id < len(processed_invoices):
        # Prepare validated data
        validated_data = {
            'vendor_name': data.get('vendor_name'),
            'invoice_number': data.get('invoice_number'),
            'invoice_date': data.get('invoice_date'),
            'total_amount': float(data.get('total_amount', 0))
        }
        
        flagged = data.get('flagged', False)
        notes = data.get('notes', '')
        
        # Update local record
        processed_invoices[invoice_id]['extracted_data'] = validated_data
        processed_invoices[invoice_id]['notes'] = notes
        processed_invoices[invoice_id]['validated'] = True
        processed_invoices[invoice_id]['flagged'] = flagged
        
        # Update GCDocs metadata with human validation
        filename = processed_invoices[invoice_id]['filename']
        repo_global.update_human_metadata(
            filename,
            validated_data,
            flagged,
            notes
        )
        
        return jsonify({'status': 'success'})
    
    return jsonify({'error': 'Invoice not found'}), 404

@app.route('/export')
def export_csv():
    """Export validated invoices to CSV"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f'validated_invoices_{timestamp}.csv'
    csv_path = os.path.join(OUTPUT_FOLDER, csv_filename)
    
    # Write CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'Filename',
            'Vendor Name',
            'Invoice Number',
            'Invoice Date',
            'Total Amount',
            'Validated',
            'Flagged for Review',
            'Notes',
            'AI Confidence'
        ]
        
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for inv in processed_invoices:
            data = inv['extracted_data']
            writer.writerow({
                'Filename': inv['filename'],
                'Vendor Name': data.get('vendor_name', ''),
                'Invoice Number': data.get('invoice_number', ''),
                'Invoice Date': data.get('invoice_date', ''),
                'Total Amount': data.get('total_amount', ''),
                'Validated': 'Yes' if inv['validated'] else 'No',
                'Flagged for Review': 'Yes' if inv.get('flagged', False) else 'No',
                'Notes': inv.get('notes', ''),
                'AI Confidence': inv.get('confidence_scores', {}).get('overall', '')
            })
    
    return send_file(
        csv_path,
        mimetype='text/csv',
        as_attachment=True,
        download_name=csv_filename
    )

@app.route('/uploads/<path:filename>')
def serve_uploaded_file(filename):
    return send_from_directory('uploads', filename)

@app.route('/status')
def get_status():
    """Get processing status from GCDocs"""
    all_invoices = repo_global.get_all_invoices(include_processed=True)
    
    ai_processed = sum(1 for inv in all_invoices if inv['ai_processed'])
    human_validated = sum(1 for inv in all_invoices if inv['human_validated'])
    pending = len(all_invoices) - ai_processed
    
    return jsonify({
        'total': len(all_invoices),
        'ai_processed': ai_processed,
        'human_validated': human_validated,
        'pending': pending
    })

@app.route("/sync_to_sharepoint", methods=["GET"])
def stream_sync():
    def generate():
        global sp_tracker_global
        yield f"data: ✓ Using existing SharePoint connection: {sp_tracker_global.list_name}\n\n"

        for msg in gcdocs_global.sync_gcdocs_nodes_to_sharepoint_minimal(
            sp_tracker=sp_tracker_global,
            folder_id=32495273,
            stream=True
        ):
            yield f"data: {msg}\n\n"

        yield "data: Sync complete.\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

@app.route('/sharepoint_stats')
def sharepoint_stats():
    try:
        global sp_tracker_global
        items = sp_tracker_global.get_all_items()
        total = len(items)
        ai_processed = sum(1 for i in items if i.get("AI_Processed"))
        human_validated = sum(1 for i in items if i.get("Human_Validated"))
        return jsonify({
            "total": total,
            "ai_processed": ai_processed,
            "human_validated": human_validated
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def start_app():
    global session_global, gcdocs_global, repo_global, sp_tracker_global

    print("Starting Invoice AI...")
    print("Connecting to GCDocs...")

    session_global = Session()
    session_global.login()

    gcdocs_global = GCDocs(session_global)

    SP_SITE_NAME = "DataScience"
    SP_LIST_NAME = "invoiceverificationtestlist"
    TENANT_NAME = "142gc.sharepoint.com"

    sp_tracker_global = SharePointTracker(SP_SITE_NAME, SP_LIST_NAME, TENANT_NAME)
    sp_tracker_global.login()
    all_items = sp_tracker_global.get_all_items()
    print(f"Total items in list: {len(all_items)}")

    # Store in Flask app config for access in routes
    app.config['GCDOCS'] = gcdocs_global
    app.config['SHAREPOINT_TRACKER'] = sp_tracker_global
    app.config['INVOICE_REPO'] = repo_global

    print("✓ Connected to GCDocs")
    print("Starting web server...")

    app.run(debug=True, use_reloader=False, port=5000)

if __name__ == "__main__":
    start_app()