# processing/extraction.py
from llama_cpp import Llama
import json
from pathlib import Path
import os
from json_repair import repair_json

class LLMExtractor:
    def __init__(self, model_filename: str):
        # Absolute path to app/models
        app_root = Path(__file__).resolve().parent.parent  # from processing/ up to app/
        models_dir = app_root / 'models'
        model_path = models_dir / model_filename

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at: {model_path}")

        print(f"Loading model from: {model_path}")
        self.llm = Llama(
            model_path=str(model_path),
            n_ctx=8192,
            n_threads=4,
            n_gpu_layers=0,
            verbose=False
        )
        self.model_name = model_filename
    
    def extract_invoice_data(self, ocr_text: str) -> dict:
        """Extract structured data from invoice OCR text"""

        prompt = f"""
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
        {ocr_text[:1200]}

        ...
        {ocr_text[-800:]}

        Return ONLY the JSON object.
        """
                    
        response = self.llm(
            prompt,
            max_tokens=512,
            temperature=0.1,
            stop=["###", "\n\n\n"],
            echo=False
        )
        
        # In extract_invoice_data method:
        output_text = response['choices'][0]['text'].strip()
        print(f"🔍 RAW LLM OUTPUT: {output_text}")

        try:
            # Remove markdown fences if present
            if "```json" in output_text:
                output_text = output_text.split("```json")[1].split("```")[0].strip()
            elif "```" in output_text:
                output_text = output_text.split("```")[1].split("```")[0].strip()
            
            # Repair common JSON issues (missing commas, brackets, quotes, etc.)
            repaired = repair_json(output_text)
            print(f"🔍 REPAIRED JSON: {repaired}")
            
            data = json.loads(repaired)
            
            # Ensure total_amount is a float
            try:
                data['total_amount'] = float(data.get('total_amount', 0))
            except (ValueError, TypeError):
                data['total_amount'] = 0.0
            
            data['confidence'] = 0.85
            data['model_used'] = self.model_name
            
            return data
            
        except json.JSONDecodeError as e:
            return {
                "invoice_number": "",
                "company_name": "",
                "invoice_date": "",
                "total_amount": 0.0,  # Changed to 0.0 for consistency
                "confidence": 0.0,
                "model_used": self.model_name,
                "error": f"Failed to parse: {str(e)}"
            }