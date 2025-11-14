# processing/extraction.py
from llama_cpp import Llama
import json
from pathlib import Path
import os
from json_repair import repair_json

from config import AIConfig

class LLMExtractor:
    def __init__(self, model_filename: str = None):
        # Use config values
        n_ctx = AIConfig.CTX_SIZE
        model_filename = model_filename or AIConfig.MODEL_PATH

        # Absolute path to app/models
        app_root = Path(__file__).resolve().parent.parent
        models_dir = app_root / 'models'
        model_path = models_dir / model_filename

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at: {model_path}")

        self.n_ctx = n_ctx
        self.model_name = model_filename

        print(f"Loading model from: {model_path}")
        self.llm = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=4,
            n_gpu_layers=0,
            verbose=False
        )
        self.model_name = model_filename
    
    def extract_invoice_data(self, ocr_text: str) -> dict:
        """Extract structured data from invoice OCR text"""

        header_slice = ocr_text[:1200]
        footer_slice = ocr_text[-800:]

        prompt = AIConfig.INVOICE_EXTRACTION_PROMPT.format(
            header_text=header_slice,
            footer_text=footer_slice
        )
                    
        response = self.llm(
            prompt,
            max_tokens=AIConfig.MAX_TOKENS,
            temperature=AIConfig.TEMPERATURE,
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

            # Clean numeric fields
            try:
                raw_amount = str(data.get('total_amount', 0))
                clean_amount = raw_amount.replace(",", "")
                data['total_amount'] = float(clean_amount)
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