class AIConfig:
    """
    Configuration for AI model parameters.
    Controls context size, generation settings, model path, and prompt templates.
    """
    CTX_SIZE = 2048             # Context window size (max tokens the model can see at once)
    TEMPERATURE = 0.1   # Sampling temperature (higher = more creative/random)
    MAX_TOKENS = 1000   # Max tokens to generate per response
    MODEL_PATH = "models/mistral-7b.gguf"  # Path to the model file

    # Default prompt for invoice extraction
    INVOICE_EXTRACTION_PROMPT = """
        You are an information extraction model. Extract invoice fields from OCR text and return a STRICT JSON object with EXACTLY these keys:

        - "invoice_number" (string)
        - "company_name" (string)
        - "invoice_date" (string, format YYYY-MM-DD)
        - "total_amount" (number, no currency symbols or commas)

        RULES (short and strict):
        1) company_name = the supplier/vendor/emitter of the invoice (the company issuing the invoice), not the client/project/funder/delivery address.
        • Prefer header/logo text; labels "Supplier", "Vendor", "From", "Remit To"; names near tax IDs (GST/HST/VAT) or supplier address.
        • Ignore entities labeled "Bill To", "Ship To", "Client", "Owner", "Project", "Funding Recipient", "Attention".
        • HARD NEGATIVES (never return as company_name): "Toronto Waterfront Revitalization Corporation", "Toronto Waterfront Revitalization", "Waterfront Toronto", "TWRC".

        2) invoice_number: pick the value nearest labels "Invoice", "Invoice No", "Invoice #", "Inv.", "Facture", "No. de facture". Alphanumeric (e.g., INV-2025-1234) is allowed.

        3) invoice_date: prefer labels "Invoice Date", "Date of Issue", "Date", "Date de facture". Normalize to YYYY-MM-DD from formats like DD Mon YYYY, MM/DD/YYYY, DD/MM/YYYY, or YYYY-MM-DD. If multiple candidates conflict, choose the one closest to the invoice date label.

        4) total_amount: prefer "Total", "Amount Due", "Balance Due" / "Total", "Montant dû", "Solde dû". Remove currency symbols and thousand separators; parse parentheses as negative; output a JSON number. Ignore "Subtotal", "Tax", "Paid to date".

        OUTPUT:
        • Return ONLY the JSON object with exactly the four keys. No explanations, no code fences, no trailing text.

        Example output format:
        {{
        "invoice_number": "INV-2025-1234",
        "company_name": "ACME Corporation",
        "invoice_date": "2025-11-13",
        "total_amount": 1234.56
        }}

        Invoice OCR text (header + footer slice):
        {header_text}

        ...
        {footer_text}

        Return ONLY the JSON object.
        """

class SharePointConfig:
    """
    Configuration for SharePoint integration.
    """
    SP_SITE_NAME = "DataScience"                     # SharePoint site name
    SP_LIST_NAME = "invoiceverificationtestlist"     # List to interact with
    TENANT_NAME = "142gc.sharepoint.com"            # Tenant / domain

class OCRConfig:
    # DPI settings for PDF rendering
    DEFAULT_DPI = 300
    DPI_OPTIONS = [150, 300, 600]  # Fast, Normal, High Quality
    
    # EasyOCR settings
    DEFAULT_LANGUAGE = "en"  # EasyOCR uses 'en' not 'eng'
    USE_GPU = False  # Set to True if you have CUDA-capable GPU
    OCR_VERBOSE = False  # Set to True for debug output
    
    # Image preprocessing
    PREPROCESS_CONTRAST = 2.0  # Contrast enhancement factor
    PREPROCESS_SHARPEN = True  # Apply sharpening filter

    # maximum pages that will be OCR'd per invoice
    MAX_OCR_PAGES = 1

class GCDocsConfig:
    """
    Configuration for GCDocs integration.
    """
    INVOICES_FOLDER_NODE = 32495273  # Node ID of the invoices folder in GCDocs