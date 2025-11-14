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

## Configuration (`config.py`)

The `config.py` file allows you to modify key variables for AI extraction, SharePoint, OCR, and GCDocs.  

**Examples:**

    # AI model parameters
    AIConfig.CTX_SIZE        # Context window size => lower CTX_SIZE optimizes for lower end CPUs and low RAM
    AIConfig.TEMPERATURE     # Sampling temperature
    AIConfig.MAX_TOKENS      # Max tokens to generate per LLM response
    AIConfig.MODEL_PATH      # Path to model file
    AIConfig.INVOICE_EXTRACTION_PROMPT  # Default invoice extraction prompt

    # SharePoint integration
    SharePointConfig.SP_SITE_NAME
    SharePointConfig.SP_LIST_NAME
    SharePointConfig.TENANT_NAME

    # OCR settings
    OCRConfig.DEFAULT_DPI
    OCRConfig.DPI_OPTIONS
    OCRConfig.DEFAULT_LANGUAGE

    # GCDocs
    GCDocsConfig.INVOICES_FOLDER_NODE

---

## Running the application

1. **Create and activate a virtual environment**:

    python -m venv venv
    venv\Scripts\activate

2. **Install required Python packages**:

    pip install -r requirements.txt

3. **Start the application**:

    python app.py

Enter your credentials when prompted (for both GCDocs and SharePoint).

---

## How It Works

### Workflow

1. **Startup**: App connects to GCDocs and SharePoint.  
2. **Process Invoices**: Downloads unprocessed PDFs from GCDocs.  
3. **AI Extraction**: Extracts invoice data, updates SharePoint `AI_*` fields.  
4. **Human Validation**: User reviews/corrects, updates SharePoint `Human_*` fields.  
5. **Export**: Generate CSV from SharePoint data.  

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
      |
      v
[ CSV Export ]
```
