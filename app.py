from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, Response, stream_with_context, redirect, url_for, flash, session
import os
import csv
from datetime import datetime

import fitz  # PyMuPDF
from PIL import Image
import io

from app.services.gcdocs import Session as GCDocsSession, GCDocs
from app.services.sharepoint import SharePointTracker
from app.services.invoice_repo import InvoiceRepository

# Create Flask app first
app = Flask(
    __name__,
    template_folder='app/templates',
    static_folder='app/static'
)
app.secret_key = 'very-secret-key-dont-tell-anyone'

# Now import and register blueprints
from app.routes.api import api_bp
from app.routes.api import validation_bp
from app.routes.processing import processing_bp

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
    print(f"Session contents: {session}")
    print(f"Is authenticated: {'gcdocs_authenticated' in session}")
    
    # Check if user is logged in AND if GCDOCS is actually configured
    if 'gcdocs_authenticated' not in session or not app.config.get('GCDOCS'):
        print("Redirecting to login...")
        session.clear()  # Clear stale session
        return redirect(url_for('login'))
    
    print("Rendering index.html")
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            global gcdocs_global, session_global
            
            # Create session and login
            session_global = GCDocsSession()
            session_global.login(username, password)
            
            # Create GCDocs instance
            gcdocs_global = GCDocs(session_global)
            
            # Store in app.config so routes can access it
            app.config['GCDOCS'] = gcdocs_global
            
            # Mark as authenticated
            session['gcdocs_authenticated'] = True
            flash('Successfully logged in to GCDocs!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Login failed: {str(e)}', 'error')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('gcdocs_authenticated', None)
    global gcdocs_global, session_global
    gcdocs_global = None
    session_global = None
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

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
        # Check if user is logged in
        if 'gcdocs_authenticated' not in session:
            yield "data: ❌ Error: Please login to GCDocs first\n\n"
            yield "data: [DONE]\n\n"
            return
        
        # Get services from app.config
        gcdocs = app.config.get('GCDOCS')
        sp_tracker = app.config.get('SHAREPOINT_TRACKER')
        
        if not gcdocs:
            yield "data: ❌ Error: GCDocs not connected. Please login.\n\n"
            yield "data: [DONE]\n\n"
            return
            
        if not sp_tracker:
            yield "data: ❌ Error: SharePoint not connected\n\n"
            yield "data: [DONE]\n\n"
            return
        
        yield f"data: ✓ Using existing SharePoint connection: {sp_tracker.list_name}\n\n"

        for msg in gcdocs.sync_gcdocs_nodes_to_sharepoint_minimal(
            sp_tracker=sp_tracker,
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
        sp_tracker = app.config.get('SHAREPOINT_TRACKER')
        if not sp_tracker:
            return jsonify({"error": "SharePoint not connected"}), 500
            
        items = sp_tracker.get_all_items()
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
    global sp_tracker_global

    print("Starting Invoice AI...")
    
    # Setup SharePoint (browser auth - happens once at startup)
    SP_SITE_NAME = "DataScience"
    SP_LIST_NAME = "invoiceverificationtestlist"
    TENANT_NAME = "142gc.sharepoint.com"

    print("Connecting to SharePoint...")
    sp_tracker_global = SharePointTracker(SP_SITE_NAME, SP_LIST_NAME, TENANT_NAME)
    sp_tracker_global.login()  # This does browser auth
    all_items = sp_tracker_global.get_all_items()
    print(f"✓ Connected to SharePoint - Total items in list: {len(all_items)}")
    
    # Store in app.config so routes can access it
    app.config['SHAREPOINT_TRACKER'] = sp_tracker_global
    
    print("Starting web server...")
    print("📱 Navigate to http://localhost:5000 to login to GCDocs")
    
    app.run(debug=True, use_reloader=False, port=5000)

if __name__ == "__main__":
    start_app()