# Invoice Verification & Extraction

This project is a Python/Flask application designed to streamline invoice processing by combining OCR with AI-assisted data extraction. It automates the extraction of key invoice fields and tracks validation status while integrating with GCDocs for finding invoices and SharePoint for record management.

## Key Features

- OCR-based invoice reading: Uses PaddleOCR to extract text from the first page of invoices.
- AI-assisted extraction: Sends invoice text to a local LLM to reliably extract structured data
  - Invoice number
  - Vendor/company name
  - Invoice date
  - Total amount
- Human-in-the-loop validation: Users can review AI-extracted data and mark invoices as valid, “not an invoice,” or needing splitting.
- SharePoint integration: Automatically updates a SharePoint list with AI results and validation status.
- Flexible file sourcing: Supports invoices stored in OpenText nodes and can handle multiple formats.
- Local-first processing: Optimized for CPU-only environments to avoid heavy cloud dependency.

# Setup Guide

## Prerequisites

- **Access to example GCDocs folder**:  
  `https://gcdocs.gc.ca/infc/llisapi.dll/app/nodes/32495273`

- **Access to example SharePoint list**:  
  `https://142gc.sharepoint.com/sites/DataScience/Lists/invoiceverificationtestlist/AllItems.aspx?env=WebViewList`

---

## SharePoint List Requirements

The application expects a SharePoint list with the following **columns and data types**:

| Column | Type |
|--------|------|
| Title | Single line of text |
| Filename | Single line of text |
| AI_InvoiceNumber | Single line of text |
| AI_CompanyName | Single line of text |
| AI_TotalAmount | Currency |
| AI_Processed | Yes/No |
| AI_Confidence | Number |
| Human_InvoiceNumber | Single line of text |
| Human_InvoiceDate | Single line of text |
| Human_CompanyName | Single line of text |
| Human_TotalAmount | Currency |
| Human_Validated | Yes/No |
| Human_Notes | Multiple lines of text |
| Human_Flagged | Yes/No |
| AI_InvoiceDate | Single line of text |
| GCDocsURL | Single line of text |
| NodeID | Single line of text |
| OCR_Method | Single line of text |
| LLM_Used | Single line of text |
| Time_Taken | Single line of text |

> Make sure the **data types match** exactly (e.g., Currency fields for totals, Number for confidence) for correct integration.

---

# Configuration (`config.py`) overview
```bash
class AIConfig:
    # Model Configuration
    MODEL_PATH = "mistral-7b.gguf"  # Your model filename
    CTX_SIZE = 8192  # Context window size
    MAX_TOKENS = 200  # Max tokens for extraction response
    TEMPERATURE = 0.1  # Low temperature for deterministic extraction
    
    # Text Slicing Configuration
    MAX_PAGE_CHARS = 8000  # Maximum characters before falling back to header+footer
    HEADER_SIZE = 2000  # Characters to take from start of document
    FOOTER_SIZE = 1000  # Characters to take from end of document
    
    # ==========================================================================
    # FULL PAGE PROMPT (Used when page 1 text < MAX_PAGE_CHARS)
    # ==========================================================================
    INVOICE_EXTRACTION_PROMPT_FULL_PAGE = """### SYSTEM INSTRUCTIONS
You are a specialized data extraction AI. Your task is to read the provided invoice text and extract structured data into a valid JSON object.

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

### INPUT TEXT (FULL PAGE 1)
The following text contains the complete first page of the invoice document.

--- BEGIN INVOICE PAGE 1 ---
{full_text}
--- END INVOICE PAGE 1 ---

### OUTPUT
Return ONLY the raw JSON object. Do not output markdown blocks (```json).

JSON:
"""

    # ==========================================================================
    # HEADER+FOOTER PROMPT (Fallback for abnormally large pages > MAX_PAGE_CHARS)
    # ==========================================================================
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
```
---

## Running the application

1. **Install Python from the Company Portal**

2. **Clone this repository onto your system by navigating to the target directory in cmd and using:**
    DevOps:
    ```bash
    git clone https://INFC-Hub@dev.azure.com/INFC-Hub/Data%20Science/_git/invoice-verification
    ```
    GitHub:
    ```bash
    git clone https://github.com/jacques-HICC/invoice-verification.git
    ```

3. **Double click on SETUP.bat for first time setup**

4. **Double click on START_APP.bat to launch the application**

    You will be prompted to authenticate into Azure (browser-based auth) and GCDocs (credentials-based auth).

---

## How It Works

### Workflow

1. **Startup**: App connects to GCDocs and SharePoint.  
2. **Scan for new invoices**: Finds and adds invoices from the target GCDocs folder to the SharePoint list.  
3. **Process with AI**: Extracts invoice data which updates SharePoint `AI_*` fields.  
4. **Invoice Preview / Human Validation**: User reviews/corrects which updates SharePoint `Human_*` fields.

### Notes

- All AI extraction and human validation data is automatically pushed to the SharePoint list.  
- Config variables in `config.py` let you tweak AI prompt, parameters, file paths, OCR settings, and SharePoint integration.  
- SharePoint list **must exist with the expected columns and types** for the application to work correctly.  

---

## Diagram

```
[ GCDocs PDFs ] 
      |
      v
[ AI Extraction (LLM) ]
      |
      v
[ SharePoint AI_* fields ]
      |
      v
[ Human Validation UI ]
      |
      v
[ SharePoint Human_* fields ]
```
