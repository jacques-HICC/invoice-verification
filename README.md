# Invoice Verification Setup Guide

## Prerequisites

Install required Python packages:

```bash
pip install -r requirements.txt
```

Download Mistral7b and place it in the "models" folder: https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf

Access to example GCDocs folder: https://gcdocs.gc.ca/infc/llisapi.dll/app/nodes/32495273

Access to example SharePoint list: https://142gc.sharepoint.com/sites/DataScience/Lists/invoiceverificationtestlist/AllItems.aspx?env=WebViewList

## Running the application

```bash
python app/app.py
```

Enter your credentials (same for GCDocs and SharePoint).

## How It Works

### Workflow:

1. **Startup**: App connects to both GCDocs and SharePoint
2. **Process Invoices**: Downloads unprocessed PDFs from GCDocs
3. **AI Extraction**: Extracts invoice data, updates SharePoint `AI_*` fields
4. **Human Validation**: User reviews/corrects, updates SharePoint `Human_*` fields
5. **Export**: Generate CSV from SharePoint data

### Benefits:

✅ **Concurrent Users**: Multiple people can validate simultaneously
✅ **Real-time Tracking**: SharePoint shows live status
✅ **No Training Needed**: Client already knows SharePoint
✅ **Audit Trail**: SharePoint tracks all changes
✅ **Filtering/Views**: Use SharePoint views to filter by status
✅ **Mobile Access**: Works on tablets/phones via SharePoint app