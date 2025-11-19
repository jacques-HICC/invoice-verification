from llama_cpp import Llama
import json
import re
from pathlib import Path
from json_repair import repair_json
from dateutil import parser

from config import AIConfig

class LLMExtractor:
    def __init__(self, model_filename: str = None):
        # Use config values
        n_ctx = AIConfig.CTX_SIZE
        model_filename = model_filename or AIConfig.MODEL_PATH

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
            n_batch=1024,  # Fast prompt processing
            n_threads=4,
            n_gpu_layers=0,
            verbose=False
        )

    def _sanitize_date(self, date_str: str) -> str:
        if not date_str:
            return None
        try:
            dt = parser.parse(str(date_str))
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return None

    def _clean_ocr_text(self, text: str) -> str:
        """Compress whitespace to save tokens"""
        if not text: return ""
        # Replace 3+ newlines with 2
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove multiple spaces
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    def extract_invoice_data(self, ocr_result) -> dict:
        # --- 1. INPUT HANDLING ---
        if isinstance(ocr_result, dict):
            ocr_text = ocr_result.get("full_text", "")
            ocr_method = ocr_result.get("method", "unknown")
        elif isinstance(ocr_result, list):
            ocr_text = "\n".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in ocr_result])
            ocr_method = "list_format"
        else:
            ocr_text = str(ocr_result)
            ocr_method = "legacy"
        
        # Quick exit for empty text
        if not ocr_text or len(ocr_text.strip()) < 10:
            return self._return_empty_error(ocr_method, "No text content in OCR result")

        # Clean the text
        ocr_text = self._clean_ocr_text(ocr_text)
        total_len = len(ocr_text)

        print(f"📊 Using full page text: {total_len} chars")
        
        # Check if text exceeds maximum page size
        if total_len > AIConfig.MAX_PAGE_CHARS:
            print(f"⚠️ Text exceeds {AIConfig.MAX_PAGE_CHARS} chars, using smart slicing fallback")
            # Fallback to header+footer if page is abnormally large
            header_slice = ocr_text[:AIConfig.HEADER_SIZE]
            footer_slice = ocr_text[-AIConfig.FOOTER_SIZE:]
            
            prompt = AIConfig.INVOICE_EXTRACTION_PROMPT.format(
                header_slice=header_slice,
                footer_slice=footer_slice
            )
        else:
            # Use FULL page text directly from config
            prompt = AIConfig.INVOICE_EXTRACTION_PROMPT_FULL_PAGE.format(full_text=ocr_text)

        # Debug save
        try:
            debug_path = Path("temp")
            debug_path.mkdir(parents=True, exist_ok=True)
            with open(debug_path / "prompt.txt", "w", encoding="utf-8") as f:
                f.write(prompt)
        except: 
            pass

        print(f"📤 Sending prompt to LLM ({len(prompt)} chars)")

        try:
            response = self.llm(
                prompt,
                max_tokens=AIConfig.MAX_TOKENS,
                temperature=AIConfig.TEMPERATURE,
                stop=["\n\n\n", "```", "}"],  # Stop at JSON closing brace
                echo=False
            )
            output_text = response['choices'][0]['text'].strip()
            
            # If we stopped at '}', add it back for valid JSON
            if not output_text.endswith("}"):
                output_text += "}"

            return self._parse_output(output_text, ocr_method)

        except Exception as e:
            print(f"❌ AI Error: {e}")
            return self._return_empty_error(ocr_method, str(e))

    def _parse_output(self, output_text, ocr_method):
        """Separated parsing logic for cleanliness"""
        try:
            # Remove markdown fences
            clean_text = output_text.replace("```json", "").replace("```", "").strip()
            
            # Repair JSON
            repaired = repair_json(clean_text)
            data = json.loads(repaired)

            # Sanitize Amount
            try:
                raw_amount = str(data.get('total_amount', 0))
                clean_amount = re.sub(r'[^\d.-]', '', raw_amount)
                data['total_amount'] = float(clean_amount)
            except:
                data['total_amount'] = 0.0
            
            # Sanitize Date
            data['invoice_date'] = self._sanitize_date(data.get('invoice_date', ''))
            
            # Metadata
            data['confidence'] = 0.85
            data['model_used'] = self.model_name
            data['ocr_method'] = ocr_method
            
            print(f"✅ Extracted: {data['company_name']} | ${data['total_amount']}")
            return data
            
        except Exception as e:
            print(f"❌ Parse Error: {e}")
            return self._return_empty_error(ocr_method, f"Parse failed: {e}")

    def _return_empty_error(self, method, error_msg):
        return {
            "invoice_number": "", 
            "company_name": "", 
            "invoice_date": None,
            "total_amount": 0.0, 
            "confidence": 0.0, 
            "model_used": self.model_name,
            "ocr_method": method, 
            "error": error_msg
        }