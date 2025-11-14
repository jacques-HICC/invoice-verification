# Invoice Verification Setup Guide

## Prerequisites

- **Download Mistral7b** and place it in the `models` folder:  
  `https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf`

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

> Make sure the **data types match** exactly (e.g., Currency fields for totals, Number for confidence) for correct integration.

---

# Configuration (`config.py`) overview

# AI model parameters
class AIConfig:
    """
    Configuration for AI model parameters.
    Controls context size, generation settings, model path, and prompt templates.
    """
    CTX_SIZE = 2048             # Context window size (max tokens the model can see at once)
    TEMPERATURE = 0.1           # Sampling temperature (higher = more creative/random)
    MAX_TOKENS = 1000           # Max tokens to generate per response
    MODEL_PATH = "models/mistral-7b.gguf"  # Path to the model file

    # Default prompt for invoice extraction
    INVOICE_EXTRACTION_PROMPT = """
        You are an information extraction model. Extract invoice fields from OCR text and return a STRICT JSON object with EXACTLY these keys:

        - "invoice_number" (string)
        - "company_name" (string)
        - "invoice_date" (string, format YYYY-MM-DD)
        - "total_amount" (number, no currency symbols or commas)

        [Prompt continues...]
    """
```bash
# SharePoint integration
class SharePointConfig:
    SP_SITE_NAME = "DataScience"                     # SharePoint site name
    SP_LIST_NAME = "invoiceverificationtestlist"     # List to interact with
    TENANT_NAME = "142gc.sharepoint.com"            # Tenant / domain

# OCR settings
class OCRConfig:
    # DPI settings for PDF rendering
    DEFAULT_DPI = 300
    DPI_OPTIONS = [150, 300, 600]  # Fast, Normal, High Quality

    # EasyOCR settings
    DEFAULT_LANGUAGE = "en"      # EasyOCR uses 'en' not 'eng'
    USE_GPU = False              # Set to True if you have CUDA-capable GPU
    OCR_VERBOSE = False          # Set to True for debug output

    # Image preprocessing
    PREPROCESS_CONTRAST = 2.0   # Contrast enhancement factor
    PREPROCESS_SHARPEN = True   # Apply sharpening filter

    # Maximum pages that will be OCR'd per invoice
    MAX_OCR_PAGES = 5

# GCDocs integration
class GCDocsConfig:
    INVOICES_FOLDER_NODE = 32495273  # Node ID of the invoices folder in GCDocs

```
---

## Running the application

1. **Create and activate a virtual environment**:

    ```bash
    python -m venv venv
    venv\Scripts\activate
    ```

2. **Install required Python packages**:

    ```bash
    pip install -r requirements.txt
    ```

3. **Start the application**:

    ```bash
    python app.py
    ```

    Enter your credentials when prompted (for both GCDocs and SharePoint) and wait for the app to launch.

---

## How It Works

### Workflow

1. **Startup**: App connects to GCDocs and SharePoint.  
2. **Process Invoices**: Downloads unprocessed PDFs from GCDocs.  
3. **AI Extraction**: Extracts invoice data, updates SharePoint `AI_*` fields.  
4. **Human Validation**: User reviews/corrects, updates SharePoint `Human_*` fields.

### Notes

- All AI extraction and human validation data is automatically pushed to the SharePoint list.  
- Config variables in `config.py` let you tweak AI parameters, file paths, OCR settings, and SharePoint integration.  
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
