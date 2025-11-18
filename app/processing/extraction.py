from llama_cpp import Llama
import json
from pathlib import Path
from json_repair import repair_json
from dateutil import parser  # <--- 1. ADD THIS IMPORT

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

    def _sanitize_date(self, date_str: str) -> str:
        """Helper to force dates into YYYY-MM-DD format for SharePoint"""
        if not date_str:
            return None
        try:
            # dateutil is smart: handles "Oct 12 2023", "12/10/2023", etc.
            dt = parser.parse(str(date_str))
            return dt.strftime('%Y-%m-%d')
        except Exception:
            print(f"⚠️ Could not parse date: '{date_str}' - returning None")
            return None

    def extract_invoice_data(self, ocr_result) -> dict:
        # ... [Input handling logic remains the same] ...
        
        # Handle different input types
        if isinstance(ocr_result, dict):
            ocr_text = ocr_result.get("full_text", "")
            ocr_method = ocr_result.get("method", "unknown")
        elif isinstance(ocr_result, list):
            ocr_text = ""
            for item in ocr_result:
                if isinstance(item, dict):
                    ocr_text += item.get("text", "") + "\n"
                elif isinstance(item, str):
                    ocr_text += item + "\n"
            ocr_method = "list_format"
        elif isinstance(ocr_result, str):
            ocr_text = ocr_result
            ocr_method = "legacy"
        else:
            return {
                "invoice_number": "", "company_name": "", "invoice_date": None, # Return None for date
                "total_amount": 0.0, "confidence": 0.0, "model_used": self.model_name,
                "ocr_method": "error", "error": f"Unexpected OCR result type"
            }
        
        if not ocr_text or len(ocr_text.strip()) < 10:
            return {
                "invoice_number": "", "company_name": "", "invoice_date": None,
                "total_amount": 0.0, "confidence": 0.0, "model_used": self.model_name,
                "ocr_method": ocr_method if isinstance(ocr_result, dict) else "legacy",
                "error": "No text content in OCR result"
            }

        # Clean up the text
        header_slice = ocr_text[:min(1200, len(ocr_text))]
        footer_slice = ocr_text[-min(800, len(ocr_text)):] if len(ocr_text) > 800 else ocr_text

        # Build prompt
        prompt = AIConfig.INVOICE_EXTRACTION_PROMPT.format(
            header_slice=header_slice,
            footer_slice=footer_slice
        )

        # --- DEBUG: SAVE PROMPT TO FILE ---
        try:
            # Ensure temp dir exists
            debug_path = Path("temp")
            debug_path.mkdir(parents=True, exist_ok=True)
            
            # Write prompt to prompt.txt (overwrites every time)
            with open(debug_path / "prompt.txt", "w", encoding="utf-8") as f:
                f.write(prompt)
            
            print(f"💾 Debug: Prompt saved to {debug_path / 'prompt.txt'}")
        except Exception as e:
            print(f"⚠️ Failed to save debug prompt: {e}")
        # ----------------------------------

        print(f"📤 Sending prompt to LLM ({len(prompt)} chars)")

        print(f"📤 Sending prompt to LLM ({len(prompt)} chars)")

        output_text = ""
        try:
            response = self.llm(
                prompt,
                max_tokens=AIConfig.MAX_TOKENS,
                temperature=AIConfig.TEMPERATURE,
                stop=["INVOICE TEXT:", "Your task:", "\n\n\n"],
                echo=False
            )
            output_text = response['choices'][0]['text'].strip()

        except ValueError as e:
            if "exceed context window" in str(e):
                print("❌ Prompt too large, retrying with simplified prompt...")
                # 2. UPDATE PROMPT TO ASK FOR YYYY-MM-DD
                simple_prompt = f"""Extract invoice data from this text.
                
                DATES MUST BE IN FORMAT: YYYY-MM-DD (e.g. 2023-12-31)

                Text:
                {ocr_text[:2000]}

                Return JSON format:
                {{"invoice_number": "", "company_name": "", "invoice_date": "YYYY-MM-DD", "total_amount": 0.0}}

                JSON:"""
                response = self.llm(
                    simple_prompt,
                    max_tokens=200, temperature=0.1, stop=["\n\n"], echo=False
                )
                output_text = response['choices'][0]['text'].strip()
            else:
                raise

        # Fallback logic
        if not output_text or len(output_text) < 10:
            print("⚠️ LLM output unusable, retrying with simplified prompt...")
            simple_prompt = f"""Extract invoice data from this text.
            
            DATES MUST BE IN FORMAT: YYYY-MM-DD (e.g. 2023-12-31)

            Text:
            {ocr_text[:2000]}

            Return JSON format:
            {{"invoice_number": "", "company_name": "", "invoice_date": "YYYY-MM-DD", "total_amount": 0.0}}

            JSON:"""
            response = self.llm(
                simple_prompt,
                max_tokens=200, temperature=0.1, stop=["\n\n"], echo=False
            )
            output_text = response['choices'][0]['text'].strip()

        try:
            # Clean markdown
            if "```json" in output_text:
                output_text = output_text.split("```json")[1].split("```")[0].strip()
            elif "```" in output_text:
                output_text = output_text.split("```")[1].split("```")[0].strip()
            
            if '{' in output_text and '}' in output_text:
                start_idx = output_text.find('{')
                end_idx = output_text.rfind('}') + 1
                output_text = output_text[start_idx:end_idx]
            
            repaired = repair_json(output_text)
            data = json.loads(repaired)

            # --- 3. SANITIZATION LOGIC START ---
            
            # Clean numeric fields
            try:
                raw_amount = str(data.get('total_amount', 0))
                clean_amount = raw_amount.replace(",", "").replace("$", "").strip()
                data['total_amount'] = float(clean_amount)
            except (ValueError, TypeError):
                data['total_amount'] = 0.0
            
            # Clean Date Field
            raw_date = data.get('invoice_date', '')
            # This forces it to 'YYYY-MM-DD' or None
            data['invoice_date'] = self._sanitize_date(raw_date)
            
            # --- SANITIZATION LOGIC END ---
            
            # Add metadata
            data['confidence'] = 0.85
            data['model_used'] = self.model_name
            data['ocr_method'] = ocr_method
            
            print(f"✅ Successfully extracted: {data}")
            return data
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON Parse Error: {str(e)}")
            return {
                "invoice_number": "", "company_name": "", "invoice_date": None,
                "total_amount": 0.0, "confidence": 0.0, "model_used": self.model_name,
                "ocr_method": ocr_method, "error": f"Failed to parse: {str(e)}"
            }