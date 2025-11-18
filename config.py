class AIConfig:
    """
    Configuration for AI model parameters.
    Controls context size, generation settings, model path, and prompt templates.
    """
    # 2048 is standard, but if you have RAM, 4096 is safer for dense invoices.
    # 2048 is fine for the slice approach (1200+800 chars is ~500 tokens).
    CTX_SIZE = 2048             
    
    # Lower temperature makes the model more deterministic and stricter with JSON
    TEMPERATURE = 0.0   
    
    MAX_TOKENS = 500   # Reduced: We only need a small JSON object, not a novel.
    MODEL_PATH = "models/mistral-7b.gguf"

    # Improved Prompt Strategy: "Instruction-Input-Response" pattern
    INVOICE_EXTRACTION_PROMPT = """### SYSTEM INSTRUCTIONS
You are a specialized data extraction AI. Your task is to read the provided invoice text segments and extract structured data into a valid JSON object.

### TARGET SCHEMA
Return a JSON object with EXACTLY these four keys:
1. "invoice_number": (string) The unique invoice identifier (e.g., "INV-001").
2. "company_name": (string) The name of the VENDOR/SUPPLIER (the entity getting paid).
3. "invoice_date": (string) The date of issue in format YYYY-MM-DD.
4. "total_amount": (float) The final numeric amount due.

### CRITICAL EXTRACTION RULES
- COMPANY NAME:
  - You must extract the VENDOR name, usually found at the top left or in a logo.
  - IGNORE the "Bill To" or "Client" name.
  - NEGATIVE CONSTRAINT: The company is NOT "Toronto Waterfront Revitalization Corporation", "Waterfront Toronto", "TWRC", or "Waterfront". These are the clients. Look for the OTHER company name.

- TOTAL AMOUNT:
  - Look for "Current Invoice", "Total", "Balance Due", "Total Payable".
  - Do not use "Subtotal" or "Tax" amounts.
  - Format as a number (e.g., 1250.50), not a string. Remove '$' and commas.

- DATE:
  - Prefer the "Invoice Date". Do not use "Due Date" unless Invoice Date is missing.
  - Convert to YYYY-MM-DD (e.g., "Oct 10, 2023" -> "2023-10-10").

### INPUT TEXT (OCR FRAGMENTS)
The following text contains the Header (top of page) and Footer (bottom of page) of the document.

--- BEGIN HEADER ---
{header_slice}
--- END HEADER ---

... [middle content skipped] ...

--- BEGIN FOOTER ---
{footer_slice}
--- END FOOTER ---

### OUTPUT
Return ONLY the raw JSON object. Do not output markdown blocks (```json).

JSON:
"""

class SharePointConfig:
    """
    Configuration for SharePoint integration.
    """
    SP_SITE_NAME = "DataScience"                     # SharePoint site name
    SP_LIST_NAME = "invoiceverificationtestlist"     # List to interact with
    TENANT_NAME = "142gc.sharepoint.com"            # Tenant / domain

class OCRConfig:
    # Maximum pages that will be OCR'd per invoice
    MAX_OCR_PAGES = 1

class GCDocsConfig:
    """
    Configuration for GCDocs integration.
    """
    INVOICES_FOLDER_NODE = 32495273  # Node ID of the invoices folder in GCDocs