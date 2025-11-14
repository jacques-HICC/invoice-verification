# Invoice Verification Setup Guide

## Prerequisites

Download Mistral7b and place it in the "models" folder: https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf

Access to example GCDocs folder: https://gcdocs.gc.ca/infc/llisapi.dll/app/nodes/32495273

Access to example SharePoint list: https://142gc.sharepoint.com/sites/DataScience/Lists/invoiceverificationtestlist/AllItems.aspx?env=WebViewList

## Running the application

Create and activate a virtual environment:
```bash
python -m venv venv
venv\Scripts\activate
```

Install required Python packages into the virtual environment:

```bash
pip install -r requirements.txt
```

```bash
python app.py
```

Enter your credentials (same for GCDocs and SharePoint).

## How It Works

### Workflow:

1. **Startup**: App connects to both GCDocs and SharePoint
2. **Process Invoices**: Downloads unprocessed PDFs from GCDocs
3. **AI Extraction**: Extracts invoice data, updates SharePoint `AI_*` fields
4. **Human Validation**: User reviews/corrects, updates SharePoint `Human_*` fields
5. **Export**: Generate CSV from SharePoint data

AI Extraction data and Human Validation data is automatically pushed to the SharePoint list to allow evaluating and further training the AI model.